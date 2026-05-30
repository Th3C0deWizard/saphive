"""Core runtime facade for SAPHive."""

import json
import logging
import time
from collections.abc import Callable
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
    ScriptContractError,
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


DEFAULT_SAP_RECONNECT_DELAY_SECONDS = 5.0
DEFAULT_SAP_RECONNECT_BACKOFF_MULTIPLIER = 1.0


@dataclass(frozen=True, slots=True)
class SapReconnectPolicy:
    """Bot-defined SAP reconnect retry behavior."""

    retries: int = 0
    delay_seconds: float = DEFAULT_SAP_RECONNECT_DELAY_SECONDS
    backoff_multiplier: float = DEFAULT_SAP_RECONNECT_BACKOFF_MULTIPLIER
    max_delay_seconds: float | None = None

    @property
    def enabled(self) -> bool:
        return self.retries > 0


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

        try:
            sap_reconnect_policy = _sap_reconnect_policy(loaded_script)
        except ScriptContractError as exc:
            _log_failure(logger, "SAPHive script contract failed", run_id=resolved_run_id, error=exc)
            return _failed_result(
                script_name=loaded_script.metadata.name,
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
                if should_prepare_sap and sap_reconnect_policy.enabled:
                    logger.info(
                        "SAPHive SAP reconnect retry policy enabled",
                        extra={
                            "run_id": resolved_run_id,
                            "sap_reconnect_retries": sap_reconnect_policy.retries,
                            "sap_reconnect_delay_seconds": sap_reconnect_policy.delay_seconds,
                            "sap_reconnect_backoff_multiplier": (
                                sap_reconnect_policy.backoff_multiplier
                            ),
                            "sap_reconnect_max_delay_seconds": (
                                sap_reconnect_policy.max_delay_seconds
                            ),
                        },
                    )

                max_attempts = sap_reconnect_policy.retries + 1
                for attempt in range(1, max_attempts + 1):
                    sap_connection = None
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
                            if _should_retry_sap_run(
                                exc,
                                sap_reconnect_policy,
                                attempt=attempt,
                                should_prepare_sap=should_prepare_sap,
                            ):
                                _wait_before_sap_retry(
                                    logger,
                                    policy=sap_reconnect_policy,
                                    run_id=resolved_run_id,
                                    attempt=attempt,
                                    error=exc,
                                    outputs=validation_context.outputs,
                                )
                                continue

                            return _failed_result(
                                script_name=validation_context.script.name,
                                run_id=validation_context.run_id,
                                started_at=started_at,
                                error=exc,
                                outputs=validation_context.outputs,
                                logs_path=logs_path,
                            )

                    if sap_connection is not None:
                        logger.info(
                            "SAPHive SAP connection resolved",
                            extra={
                                "run_id": resolved_run_id,
                                "sap_connection": sap_connection.connection_name,
                                "sap_reconnect_attempt": attempt,
                                "sap_reconnect_max_attempts": max_attempts,
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

                    execution_result, execution_error = _run_loaded_script(
                        loaded_script,
                        context,
                        started_at,
                        logs_path,
                        logger,
                    )
                    result = execution_result or _success_result(context, started_at, logs_path)
                    if _should_retry_sap_run(
                        execution_error,
                        sap_reconnect_policy,
                        attempt=attempt,
                        should_prepare_sap=should_prepare_sap,
                    ):
                        _cleanup_loaded_script(loaded_script, context, logger)
                        _cleanup_sap_before_reconnect_retry(
                            sap_connection,
                            mode=self.sap_mode or self.config.sap.mode,
                            logger=logger,
                            run_id=context.run_id,
                            outputs=context.outputs,
                        )
                        _wait_before_sap_retry(
                            logger,
                            policy=sap_reconnect_policy,
                            run_id=resolved_run_id,
                            attempt=attempt,
                            error=execution_error,
                            outputs=context.outputs,
                        )
                        continue

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


def _sap_reconnect_policy(loaded_script: LoadedScript) -> SapReconnectPolicy:
    module = loaded_script.module
    if not hasattr(module, "SAP_RECONNECT_RETRIES"):
        return SapReconnectPolicy()

    return SapReconnectPolicy(
        retries=_int_script_constant(
            module,
            "SAP_RECONNECT_RETRIES",
            min_value=0,
        ),
        delay_seconds=_float_script_constant(
            module,
            "SAP_RECONNECT_DELAY_SECONDS",
            default=DEFAULT_SAP_RECONNECT_DELAY_SECONDS,
            min_value=0,
        ),
        backoff_multiplier=_float_script_constant(
            module,
            "SAP_RECONNECT_BACKOFF_MULTIPLIER",
            default=DEFAULT_SAP_RECONNECT_BACKOFF_MULTIPLIER,
            min_value=1,
        ),
        max_delay_seconds=_optional_float_script_constant(
            module,
            "SAP_RECONNECT_MAX_DELAY_SECONDS",
            min_value=0,
        ),
    )


def _int_script_constant(module: object, name: str, *, min_value: int) -> int:
    value = getattr(module, name)
    if isinstance(value, bool) or not isinstance(value, int):
        raise ScriptContractError(
            f"Optional SAPHive script attribute {name} must be an integer.",
            details={"attribute": name, "value": value},
        )
    if value < min_value:
        raise ScriptContractError(
            f"Optional SAPHive script attribute {name} must be >= {min_value}.",
            details={"attribute": name, "value": value},
        )
    return value


def _float_script_constant(
    module: object,
    name: str,
    *,
    default: float,
    min_value: float,
) -> float:
    if not hasattr(module, name):
        return default

    value = getattr(module, name)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ScriptContractError(
            f"Optional SAPHive script attribute {name} must be a number.",
            details={"attribute": name, "value": value},
        )

    normalized = float(value)
    if normalized < min_value:
        raise ScriptContractError(
            f"Optional SAPHive script attribute {name} must be >= {min_value}.",
            details={"attribute": name, "value": value},
        )
    return normalized


def _optional_float_script_constant(
    module: object,
    name: str,
    *,
    min_value: float,
) -> float | None:
    if not hasattr(module, name):
        return None

    return _float_script_constant(module, name, default=0, min_value=min_value)


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
) -> tuple[ScriptExecutionResult | None, SAPHiveError | None]:
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
        result = _failed_result(
            script_name=context.script.name,
            run_id=context.run_id,
            started_at=started_at,
            error=exc,
            outputs=context.outputs,
            logs_path=logs_path,
        )
        return result, exc
    except FatalAutomationError as exc:
        _log_failure(
            logger,
            "SAPHive script execution stopped by fatal automation error",
            run_id=context.run_id,
            error=exc,
            outputs=context.outputs,
        )
        result = _failed_result(
            script_name=context.script.name,
            run_id=context.run_id,
            started_at=started_at,
            error=exc,
            outputs=context.outputs,
            logs_path=logs_path,
        )
        return result, exc
    except SAPHiveError as exc:
        _log_failure(
            logger,
            "SAPHive script execution failed",
            run_id=context.run_id,
            error=exc,
            outputs=context.outputs,
        )
        result = _failed_result(
            script_name=context.script.name,
            run_id=context.run_id,
            started_at=started_at,
            error=exc,
            outputs=context.outputs,
            logs_path=logs_path,
        )
        return result, exc
    except Exception as exc:
        error = _classify_unhandled_execution_error(exc)
        _log_failure(
            logger,
            "SAPHive script execution crashed",
            run_id=context.run_id,
            error=error,
            outputs=context.outputs,
        )
        result = _failed_result(
            script_name=context.script.name,
            run_id=context.run_id,
            started_at=started_at,
            error=error,
            outputs=context.outputs,
            logs_path=logs_path,
        )
        return result, error

    return None, None


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


def _cleanup_sap_before_reconnect_retry(
    sap_connection: SapConnection | None,
    *,
    mode: SapConnectionMode,
    logger: Logger,
    run_id: str,
    outputs: dict[str, object],
) -> None:
    if sap_connection is None:
        return

    logger.info(
        "SAPHive cleaning SAP state before reconnect retry",
        extra={"run_id": run_id, "sap_mode": mode.value},
    )
    _try_retry_cleanup_step(
        logger,
        run_id=run_id,
        outputs=outputs,
        step="close_created_sessions",
        callback=sap_connection.close_created_sessions,
    )
    if mode is SapConnectionMode.ATTACH:
        return

    _try_retry_cleanup_step(
        logger,
        run_id=run_id,
        outputs=outputs,
        step="close_connection",
        callback=lambda: sap_connection.close_connection(force=True),
    )


def _try_retry_cleanup_step(
    logger: Logger,
    *,
    run_id: str,
    outputs: dict[str, object],
    step: str,
    callback: Callable[[], None],
) -> None:
    try:
        callback()
    except Exception as exc:
        logger.warning(
            "SAPHive SAP reconnect cleanup step failed",
            extra={
                "run_id": run_id,
                "cleanup_step": step,
                "error_type": type(exc).__name__,
                "error": str(exc),
                "outputs": dict(outputs),
            },
        )


def _should_retry_sap_run(
    error: SAPHiveError | None,
    policy: SapReconnectPolicy,
    *,
    attempt: int,
    should_prepare_sap: bool,
) -> bool:
    return (
        error is not None
        and should_prepare_sap
        and policy.enabled
        and attempt <= policy.retries
        and _is_sap_connection_lost_error(error)
    )


def _wait_before_sap_retry(
    logger: Logger,
    *,
    policy: SapReconnectPolicy,
    run_id: str,
    attempt: int,
    error: BaseException | None,
    outputs: dict[str, object],
) -> None:
    delay_seconds = _sap_retry_delay_seconds(policy, attempt)
    logger.warning(
        "SAPHive retrying script after SAP connection loss",
        extra={
            "run_id": run_id,
            "sap_reconnect_attempt": attempt,
            "sap_reconnect_next_attempt": attempt + 1,
            "sap_reconnect_max_attempts": policy.retries + 1,
            "sap_reconnect_delay_seconds": delay_seconds,
            "error_type": None if error is None else type(error).__name__,
            "error": None if error is None else str(error),
            "outputs": dict(outputs),
        },
    )
    if delay_seconds > 0:
        time.sleep(delay_seconds)


def _sap_retry_delay_seconds(policy: SapReconnectPolicy, attempt: int) -> float:
    delay_seconds = policy.delay_seconds * (policy.backoff_multiplier ** (attempt - 1))
    if policy.max_delay_seconds is not None:
        delay_seconds = min(delay_seconds, policy.max_delay_seconds)
    return delay_seconds


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
    raw_message = str(error)
    message = _exception_search_text(error)
    normalized = message.lower()
    return (
        (isinstance(error, AttributeError) and raw_message.startswith("<unknown>."))
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


def _is_sap_connection_lost_error(error: BaseException) -> bool:
    message = _exception_search_text(error)
    normalized = message.lower()
    return (
        "rpc_e_disconnected" in normalized
        or "object invoked has disconnected" in normalized
        or "object is not connected to server" in normalized
        or "objeto invocado se desconect" in normalized
        or "objeto no está conectado al servidor" in normalized
        or "objeto no esta conectado al servidor" in normalized
        or "remote procedure call failed" in normalized
        or "rpc server is unavailable" in normalized
        or "no active sap gui connections were found" in normalized
        or "requested sap gui connection was not found" in normalized
        or "destinatario" in normalized
        or "conexiones no son válidas" in normalized
        or "conexiones no son validas" in normalized
        or ("server" in normalized and "not available" in normalized)
        or "-2147417848" in message
        or "-2147418094" in message
        or "-2147023174" in message
        or "-2147220995" in message
    )


def _exception_search_text(error: BaseException) -> str:
    parts: list[str] = []
    seen: set[int] = set()
    current: BaseException | None = error
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        parts.extend(
            (
                type(current).__module__,
                type(current).__qualname__,
                str(current),
                repr(getattr(current, "args", ())),
                repr(getattr(current, "details", {})),
            )
        )
        current = current.__cause__ or current.__context__

    return " ".join(parts)


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
