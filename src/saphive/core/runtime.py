"""Core runtime facade for SAPHive."""

from dataclasses import dataclass, field
from datetime import UTC, datetime
from logging import Logger
from pathlib import Path
from uuid import uuid4

from saphive.core.config import SAPHiveConfig
from saphive.core.context import SapContext, build_sap_context
from saphive.core.errors import SAPHiveError, ScriptExecutionError, ScriptValidationError
from saphive.core.results import ExecutionStatus, ScriptExecutionResult
from saphive.sap.interfaces import SapClient
from saphive.scripts.discovery import discover_scripts
from saphive.scripts.loader import LoadedScript, load_script_from_path, load_script_from_registry
from saphive.scripts.registry import ScriptRegistry


@dataclass(frozen=True, slots=True)
class SapRuntime:
    """Core runtime facade for validating and running SAPHive scripts."""

    config: SAPHiveConfig = field(default_factory=SAPHiveConfig)
    workdir: Path | None = None
    logger: Logger | None = None
    sap: SapClient | None = None

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

        try:
            loaded_script = self._load_script(script)
        except SAPHiveError as exc:
            return _failed_result(
                script_name=str(script),
                run_id=resolved_run_id,
                started_at=started_at,
                error=exc,
            )

        context = build_sap_context(
            script=loaded_script.metadata,
            config=self.config,
            inputs=inputs,
            run_id=resolved_run_id,
            workdir=self.workdir,
            logger=self.logger,
            sap=self.sap,
        )

        validation_result = _validate_loaded_script(loaded_script, context, started_at)
        if validation_result is not None:
            return validation_result

        if not run_script:
            return _success_result(context, started_at)

        execution_result = _run_loaded_script(loaded_script, context, started_at)
        return execution_result or _success_result(context, started_at)

    def _load_script(self, script: str | Path) -> "LoadedScript":
        if isinstance(script, Path):
            return load_script_from_path(script)

        script_path = Path(script)
        if _looks_like_path(script) or script_path.exists():
            return load_script_from_path(script_path)

        return load_script_from_registry(self.discover_scripts(), script)


def _looks_like_path(script: str) -> bool:
    return script.endswith(".py") or "/" in script or "\\" in script


def _validate_loaded_script(
    loaded_script: LoadedScript,
    context: SapContext,
    started_at: datetime,
) -> ScriptExecutionResult | None:
    try:
        loaded_script.validate(context)
    except ScriptValidationError as exc:
        return _validation_failed_result(context, started_at, exc)
    except SAPHiveError as exc:
        return _failed_result(
            script_name=context.script.name,
            run_id=context.run_id,
            started_at=started_at,
            error=exc,
            outputs=context.outputs,
        )
    except Exception as exc:
        return _failed_result(
            script_name=context.script.name,
            run_id=context.run_id,
            started_at=started_at,
            error=ScriptValidationError(str(exc)),
            outputs=context.outputs,
        )

    return None


def _run_loaded_script(
    loaded_script: LoadedScript,
    context: SapContext,
    started_at: datetime,
) -> ScriptExecutionResult | None:
    try:
        loaded_script.run(context)
    except ScriptExecutionError as exc:
        return _failed_result(
            script_name=context.script.name,
            run_id=context.run_id,
            started_at=started_at,
            error=exc,
            outputs=context.outputs,
        )
    except SAPHiveError as exc:
        return _failed_result(
            script_name=context.script.name,
            run_id=context.run_id,
            started_at=started_at,
            error=exc,
            outputs=context.outputs,
        )
    except Exception as exc:
        return _failed_result(
            script_name=context.script.name,
            run_id=context.run_id,
            started_at=started_at,
            error=ScriptExecutionError(str(exc)),
            outputs=context.outputs,
        )

    return None


def _success_result(context: SapContext, started_at: datetime) -> ScriptExecutionResult:
    return ScriptExecutionResult(
        script_name=context.script.name,
        run_id=context.run_id,
        status=ExecutionStatus.SUCCESS,
        started_at=started_at,
        finished_at=datetime.now(UTC),
        outputs=dict(context.outputs),
    )


def _validation_failed_result(
    context: SapContext,
    started_at: datetime,
    error: ScriptValidationError,
) -> ScriptExecutionResult:
    return ScriptExecutionResult(
        script_name=context.script.name,
        run_id=context.run_id,
        status=ExecutionStatus.VALIDATION_FAILED,
        started_at=started_at,
        finished_at=datetime.now(UTC),
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
) -> ScriptExecutionResult:
    return ScriptExecutionResult(
        script_name=script_name,
        run_id=run_id,
        status=ExecutionStatus.FAILED,
        started_at=started_at,
        finished_at=datetime.now(UTC),
        outputs=dict(outputs or {}),
        error=error.message,
    )
