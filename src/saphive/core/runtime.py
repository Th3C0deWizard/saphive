"""Core runtime facade for SAPHive."""

import json
import logging
from contextlib import nullcontext
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime
from logging import Logger
from pathlib import Path
from uuid import uuid4

from saphive.core.config import SapCleanupMode, SapConnectionMode, SAPHiveConfig
from saphive.core.context import SapContext, build_sap_context
from saphive.core.errors import (
    ComRuntimeError,
    ExcelInfrastructureError,
    FatalAutomationError,
    SAPHiveError,
    SapInfrastructureError,
    ScriptExecutionError,
    ScriptValidationError,
)
from saphive.core.results import ExecutionStatus, ScriptExecutionResult
from saphive.sap.interfaces import SapConnection, SapConnectionResolver
from saphive.sap.resolver import DefaultSapConnectionResolver, normalize_auth_path
from saphive.sap.windows import sap_com_initialized
from saphive.scripts.discovery import discover_scripts
from saphive.scripts.loader import LoadedScript, load_script_from_path, load_script_from_registry
from saphive.scripts.registry import ScriptRegistry


@dataclass(frozen=True, slots=True)
class SapRuntime:
    """Core runtime facade for validating and running SAPHive scripts."""

    config: SAPHiveConfig = field(default_factory=SAPHiveConfig)
    config_path: Path | None = None
    auth_file: Path | None = None
    sap_mode: SapConnectionMode | None = None
    sap_connection: str | None = None
    sap_cleanup: SapCleanupMode | None = None
    sap_cleanup_force: bool = False
    workdir: Path | None = None
    logger: Logger | None = None
    sap: SapConnection | None = None
    connection_resolver: SapConnectionResolver = field(default_factory=DefaultSapConnectionResolver)

    def discover_scripts(self) -> "ScriptRegistry":
        """Discover configured SAPHive scripts."""
        return discover_scripts(self.config.paths.scripts)

    def validate_script(
        self,
        script: str | Path,
        *,
        inputs: dict[str, object] | None = None,
        run_id: str | None = None,
    ) -> ScriptExecutionResult:
        """Load a SAPHive script and run its validate(ctx) function only."""
        return self._execute_script(script, inputs=inputs, run_id=run_id, run_script=False)

    def run_script(
        self,
        script: str | Path,
        *,
        inputs: dict[str, object] | None = None,
        run_id: str | None = None,
    ) -> ScriptExecutionResult:
        """Load a SAPHive script, validate it, and run its run(ctx) function."""
        return self._execute_script(script, inputs=inputs, run_id=run_id, run_script=True)

    def _execute_script(
        self,
        script: str | Path,
        *,
        inputs: dict[str, object] | None,
        run_id: str | None,
        run_script: bool,
    ) -> ScriptExecutionResult:
        resolved_run_id = uuid4().hex if run_id is None else run_id
        started_at = datetime.now(UTC)
        logger, logs_path = _build_run_logger(
            run_id=resolved_run_id,
            script=str(script),
            started_at=started_at,
            config=self.config,
            logger=self.logger,
        )
        logger.info("SAPHive run started", extra={"script": str(script), "run_id": resolved_run_id})

        try:
            loaded_script = self._load_script(script)
        except SAPHiveError as exc:
            _log_failure(logger, "SAPHive script load failed", run_id=resolved_run_id, error=exc)
            return _failed_result(
                script_name=str(script),
                run_id=resolved_run_id,
                started_at=started_at,
                error=exc,
                logs_path=logs_path,
            )

        validation_context = build_sap_context(
            script=loaded_script.metadata,
            config=self.config,
            inputs=inputs,
            run_id=resolved_run_id,
            workdir=self.workdir,
            logger=logger,
        )

        validation_result = _validate_loaded_script(
            loaded_script,
            validation_context,
            started_at,
            logs_path,
            logger,
        )
        if validation_result is not None:
            logger.info(
                "SAPHive validation finished",
                extra={"status": validation_result.status.value, "run_id": resolved_run_id},
            )
            return validation_result

        if not run_script:
            result = _success_result(validation_context, started_at, logs_path)
            logger.info("SAPHive validation succeeded", extra={"run_id": resolved_run_id})
            return result

        should_prepare_sap = self.sap is not None or _should_resolve_sap(self)
        sap_scope = sap_com_initialized() if should_prepare_sap else nullcontext()
        try:
            with sap_scope as base_com_runtime:
                context_com_runtime = base_com_runtime
                if should_prepare_sap:
                    try:
                        sap_connection = self.sap or self.connection_resolver.resolve_connection(
                            config=self.config,
                            mode=self.sap_mode,
                            connection_name=self.sap_connection,
                            auth_file=normalize_auth_path(self.auth_file),
                            config_path=normalize_auth_path(self.config_path),
                            script_path=str(loaded_script.source_path),
                        )
                    except SAPHiveError as exc:
                        _log_failure(
                            logger,
                            "SAPHive SAP connection resolution failed",
                            run_id=validation_context.run_id,
                            error=exc,
                            outputs=validation_context.outputs,
                        )
                        return _failed_result(
                            script_name=validation_context.script.name,
                            run_id=validation_context.run_id,
                            started_at=started_at,
                            error=exc,
                            outputs=validation_context.outputs,
                            logs_path=logs_path,
                        )
                else:
                    sap_connection = None

                if sap_connection is not None:
                    logger.info(
                        "SAPHive SAP connection resolved",
                        extra={
                            "run_id": resolved_run_id,
                            "sap_connection": sap_connection.connection_name,
                        },
                    )

                context = build_sap_context(
                    script=loaded_script.metadata,
                    config=self.config,
                    inputs=inputs,
                    run_id=resolved_run_id,
                    workdir=self.workdir,
                    logger=logger,
                    sap=sap_connection,
                    com=context_com_runtime,
                )
                context.outputs.update(validation_context.outputs)

                execution_result = _run_loaded_script(
                    loaded_script,
                    context,
                    started_at,
                    logs_path,
                    logger,
                )
                result = execution_result or _success_result(context, started_at, logs_path)
                cleanup_error = _cleanup_loaded_script(loaded_script, context, logger)
                sap_cleanup_error = _cleanup_sap_connection(
                    sap_connection,
                    cleanup_mode=self.sap_cleanup or self.config.sap.cleanup,
                    force=self.sap_cleanup_force or self.config.sap.cleanup_force,
                    logger=logger,
                    run_id=context.run_id,
                    outputs=context.outputs,
                )
                result = replace(result, outputs=dict(context.outputs))
                cleanup_failure = cleanup_error or sap_cleanup_error
                if cleanup_failure is not None and result.status is ExecutionStatus.SUCCESS:
                    result = _failed_result(
                        script_name=context.script.name,
                        run_id=context.run_id,
                        started_at=started_at,
                        error=cleanup_failure,
                        outputs=context.outputs,
                        logs_path=logs_path,
                    )
                logger.info(
                    "SAPHive run finished",
                    extra={"status": result.status.value, "run_id": resolved_run_id},
                )
                return result
        except SAPHiveError as exc:
            _log_failure(
                logger,
                "SAPHive SAP COM initialization failed",
                run_id=validation_context.run_id,
                error=exc,
                outputs=validation_context.outputs,
            )
            return _failed_result(
                script_name=validation_context.script.name,
                run_id=validation_context.run_id,
                started_at=started_at,
                error=exc,
                outputs=validation_context.outputs,
                logs_path=logs_path,
            )

    def _load_script(self, script: str | Path) -> "LoadedScript":
        if isinstance(script, Path):
            return load_script_from_path(script)

        script_path = Path(script)
        if _looks_like_path(script) or script_path.exists():
            return load_script_from_path(script_path)

        return load_script_from_registry(self.discover_scripts(), script)


def _looks_like_path(script: str) -> bool:
    return script.endswith(".py") or "/" in script or "\\" in script


def _should_resolve_sap(runtime: SapRuntime) -> bool:
    return (
        runtime.sap_mode is not None
        or runtime.sap_connection is not None
        or runtime.config.sap.connection is not None
    )


def _validate_loaded_script(
    loaded_script: LoadedScript,
    context: SapContext,
    started_at: datetime,
    logs_path: Path | None,
    logger: Logger,
) -> ScriptExecutionResult | None:
    try:
        loaded_script.validate(context)
    except ScriptValidationError as exc:
        _log_failure(
            logger,
            "SAPHive validation failed",
            run_id=context.run_id,
            error=exc,
            outputs=context.outputs,
        )
        return _validation_failed_result(context, started_at, exc, logs_path)
    except SAPHiveError as exc:
        _log_failure(
            logger,
            "SAPHive validation failed",
            run_id=context.run_id,
            error=exc,
            outputs=context.outputs,
        )
        return _failed_result(
            script_name=context.script.name,
            run_id=context.run_id,
            started_at=started_at,
            error=exc,
            outputs=context.outputs,
            logs_path=logs_path,
        )
    except Exception as exc:
        _log_failure(
            logger,
            "SAPHive validation crashed",
            run_id=context.run_id,
            error=exc,
            outputs=context.outputs,
        )
        return _failed_result(
            script_name=context.script.name,
            run_id=context.run_id,
            started_at=started_at,
            error=ScriptValidationError(str(exc)),
            outputs=context.outputs,
            logs_path=logs_path,
        )

    return None


def _run_loaded_script(
    loaded_script: LoadedScript,
    context: SapContext,
    started_at: datetime,
    logs_path: Path | None,
    logger: Logger,
) -> ScriptExecutionResult | None:
    try:
        loaded_script.run(context)
    except ScriptExecutionError as exc:
        _log_failure(
            logger,
            "SAPHive script execution failed",
            run_id=context.run_id,
            error=exc,
            outputs=context.outputs,
        )
        return _failed_result(
            script_name=context.script.name,
            run_id=context.run_id,
            started_at=started_at,
            error=exc,
            outputs=context.outputs,
            logs_path=logs_path,
        )
    except FatalAutomationError as exc:
        _log_failure(
            logger,
            "SAPHive script execution stopped by fatal automation error",
            run_id=context.run_id,
            error=exc,
            outputs=context.outputs,
        )
        return _failed_result(
            script_name=context.script.name,
            run_id=context.run_id,
            started_at=started_at,
            error=exc,
            outputs=context.outputs,
            logs_path=logs_path,
        )
    except SAPHiveError as exc:
        _log_failure(
            logger,
            "SAPHive script execution failed",
            run_id=context.run_id,
            error=exc,
            outputs=context.outputs,
        )
        return _failed_result(
            script_name=context.script.name,
            run_id=context.run_id,
            started_at=started_at,
            error=exc,
            outputs=context.outputs,
            logs_path=logs_path,
        )
    except Exception as exc:
        error = _classify_unhandled_execution_error(exc)
        _log_failure(
            logger,
            "SAPHive script execution crashed",
            run_id=context.run_id,
            error=error,
            outputs=context.outputs,
        )
        return _failed_result(
            script_name=context.script.name,
            run_id=context.run_id,
            started_at=started_at,
            error=error,
            outputs=context.outputs,
            logs_path=logs_path,
        )

    return None


def _cleanup_loaded_script(
    loaded_script: LoadedScript,
    context: SapContext,
    logger: Logger,
) -> SAPHiveError | None:
    if loaded_script.cleanup is None:
        return None

    try:
        loaded_script.cleanup(context)
    except SAPHiveError as exc:
        _log_failure(
            logger,
            "SAPHive script cleanup failed",
            run_id=context.run_id,
            error=exc,
            outputs=context.outputs,
        )
        return exc
    except Exception as exc:
        error = ScriptExecutionError(f"SAPHive script cleanup failed: {exc}")
        _log_failure(
            logger,
            "SAPHive script cleanup crashed",
            run_id=context.run_id,
            error=exc,
            outputs=context.outputs,
        )
        return error

    logger.info("SAPHive script cleanup succeeded", extra={"run_id": context.run_id})
    return None


def _cleanup_sap_connection(
    sap_connection: SapConnection | None,
    *,
    cleanup_mode: SapCleanupMode,
    force: bool,
    logger: Logger,
    run_id: str,
    outputs: dict[str, object],
) -> SAPHiveError | None:
    if sap_connection is None or cleanup_mode is SapCleanupMode.NONE:
        return None

    try:
        if cleanup_mode is SapCleanupMode.CREATED_SESSIONS:
            sap_connection.close_created_sessions()
        elif cleanup_mode is SapCleanupMode.CONNECTION:
            sap_connection.close_connection(force=force)
        elif cleanup_mode is SapCleanupMode.APPLICATION:
            sap_connection.close_application()
    except SAPHiveError as exc:
        _log_failure(
            logger,
            "SAPHive SAP cleanup failed",
            run_id=run_id,
            error=exc,
            outputs=outputs,
        )
        return exc
    except Exception as exc:
        error = ScriptExecutionError(f"SAPHive SAP cleanup failed: {exc}")
        _log_failure(
            logger,
            "SAPHive SAP cleanup crashed",
            run_id=run_id,
            error=exc,
            outputs=outputs,
        )
        return error

    logger.info(
        "SAPHive SAP cleanup succeeded",
        extra={"run_id": run_id, "sap_cleanup": cleanup_mode.value},
    )
    return None


def _success_result(
    context: SapContext,
    started_at: datetime,
    logs_path: Path | None,
) -> ScriptExecutionResult:
    return ScriptExecutionResult(
        script_name=context.script.name,
        run_id=context.run_id,
        status=ExecutionStatus.SUCCESS,
        started_at=started_at,
        finished_at=datetime.now(UTC),
        logs_path=logs_path,
        outputs=dict(context.outputs),
    )


def _validation_failed_result(
    context: SapContext,
    started_at: datetime,
    error: ScriptValidationError,
    logs_path: Path | None,
) -> ScriptExecutionResult:
    return ScriptExecutionResult(
        script_name=context.script.name,
        run_id=context.run_id,
        status=ExecutionStatus.VALIDATION_FAILED,
        started_at=started_at,
        finished_at=datetime.now(UTC),
        logs_path=logs_path,
        outputs=dict(context.outputs),
        error=error.message,
    )


def _failed_result(
    *,
    script_name: str,
    run_id: str,
    started_at: datetime,
    error: SAPHiveError,
    outputs: dict[str, object] | None = None,
    logs_path: Path | None = None,
) -> ScriptExecutionResult:
    return ScriptExecutionResult(
        script_name=script_name,
        run_id=run_id,
        status=ExecutionStatus.FAILED,
        started_at=started_at,
        finished_at=datetime.now(UTC),
        logs_path=logs_path,
        outputs=dict(outputs or {}),
        error=error.message,
    )


def _classify_unhandled_execution_error(error: Exception) -> SAPHiveError:
    message = str(error)
    if _looks_like_com_lifecycle_error(error):
        return ComRuntimeError(
            "SAPHive detected an invalid Windows COM lifecycle while running the script.",
            details={"error": message, "error_type": type(error).__name__},
        )

    if _looks_like_sap_infrastructure_error(error):
        return SapInfrastructureError(
            "SAPHive detected an unusable SAP GUI scripting session while running the script.",
            details={"error": message, "error_type": type(error).__name__},
        )

    if _looks_like_excel_infrastructure_error(error):
        return ExcelInfrastructureError(
            "SAPHive detected an Excel automation failure while running the script.",
            details={"error": message, "error_type": type(error).__name__},
        )

    return ScriptExecutionError(message)


def _looks_like_com_lifecycle_error(error: Exception) -> bool:
    message = str(error).lower()
    return (
        "coinitialize" in message
        or "couninitialize" in message
        or "coinitialize has not been called" in message
        or "no se ha llamado a coinitialize" in message
        or "-2147221008" in message
    )


def _looks_like_sap_infrastructure_error(error: Exception) -> bool:
    message = str(error)
    normalized = message.lower()
    return (
        (isinstance(error, AttributeError) and message.startswith("<unknown>."))
        or "rpc_e_disconnected" in normalized
        or "object invoked has disconnected" in normalized
        or "object is not connected to server" in normalized
        or "objeto invocado se desconect" in normalized
        or "objeto no está conectado al servidor" in normalized
        or "objeto no esta conectado al servidor" in normalized
        or ("saplogon" in normalized and "enumerator of the collection" in normalized)
        or ("sap gui" in normalized and "session" in normalized and "invalid" in normalized)
        or "-2147417848" in message
        or "-2147023174" in message
        or "-2147220995" in message
    )


def _looks_like_excel_infrastructure_error(error: Exception) -> bool:
    module_name = type(error).__module__.lower()
    message = str(error).lower()
    return (
        module_name.startswith("pymacros")
        or "workbook" in message
        or "powerquery" in message
        or "power query" in message
        or "excel" in message
    )


def _log_failure(
    logger: Logger,
    message: str,
    *,
    run_id: str,
    error: BaseException,
    outputs: dict[str, object] | None = None,
) -> None:
    logger.error(
        "%s: %s",
        message,
        error,
        extra={"run_id": run_id, "error_type": type(error).__name__},
    )
    if not logger.isEnabledFor(logging.DEBUG):
        return

    details = getattr(error, "details", None)
    debug_lines = [
        f"{message} debug details",
        f"run_id={run_id}",
        f"error_type={type(error).__module__}.{type(error).__qualname__}",
        f"error_message={error}",
        f"error_details={details!r}",
        f"outputs={dict(outputs or {})!r}",
    ]
    logger.debug(
        "\n".join(debug_lines),
        exc_info=True,
        extra={"run_id": run_id, "error_type": type(error).__name__},
    )


def _build_run_logger(
    *,
    run_id: str,
    script: str,
    started_at: datetime,
    config: SAPHiveConfig,
    logger: Logger | None,
) -> tuple[Logger, Path | None]:
    if logger is not None:
        return logger, None

    logs_dir = config.logging.directory
    logs_dir.mkdir(parents=True, exist_ok=True)
    logs_path = logs_dir / f"{_log_filename_timestamp(started_at)}_{run_id}.log"
    run_logger = logging.getLogger(f"saphive.run.{run_id}")
    run_logger.setLevel(config.logging.level)
    run_logger.propagate = False
    run_logger.handlers.clear()

    handler = logging.FileHandler(logs_path, encoding="utf-8")
    if config.logging.jsonl_enabled:
        handler.setFormatter(JsonLinesFormatter())
    else:
        handler.setFormatter(ContextFormatter("%(asctime)s %(levelname)s %(name)s %(message)s"))
    run_logger.addHandler(handler)
    print(f"SAPHive log file: {logs_path}", flush=True)
    run_logger.info("Logger initialized", extra={"script": script, "run_id": run_id})
    return run_logger, logs_path


def _log_filename_timestamp(value: datetime) -> str:
    return value.astimezone(UTC).strftime("%Y%m%dT%H%M%S_%fZ")


class ContextFormatter(logging.Formatter):
    """Text formatter that appends structured logging fields."""

    def format(self, record: logging.LogRecord) -> str:
        message = super().format(record)
        context = _record_context(record)
        if not context:
            return message

        rendered_context = " ".join(
            f"{key}={_format_log_value(value)}" for key, value in sorted(context.items())
        )
        return f"{message} {rendered_context}"


class JsonLinesFormatter(logging.Formatter):
    """JSON Lines formatter for structured run logs."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, object] = {
            "timestamp": self.formatTime(record),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        payload.update(_record_context(record))
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)

        return json.dumps(payload, ensure_ascii=False, default=str)


_BASE_LOG_RECORD_KEYS = frozenset(
    logging.LogRecord(
        name="",
        level=0,
        pathname="",
        lineno=0,
        msg="",
        args=(),
        exc_info=None,
    ).__dict__
) | {"message", "asctime"}


def _record_context(record: logging.LogRecord) -> dict[str, object]:
    return {
        key: value
        for key, value in record.__dict__.items()
        if key not in _BASE_LOG_RECORD_KEYS and not key.startswith("_")
    }


def _format_log_value(value: object) -> str:
    if value is None:
        return "null"
    if isinstance(value, str):
        return json.dumps(value, ensure_ascii=False) if " " in value else value
    return str(value)
