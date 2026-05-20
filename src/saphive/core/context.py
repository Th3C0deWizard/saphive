"""Runtime context passed to SAPHive automation scripts."""

from dataclasses import dataclass, field
from logging import Logger, getLogger
from pathlib import Path
from uuid import uuid4

from saphive.core.config import SAPHiveConfig
from saphive.core.metadata import ScriptMetadata
from saphive.sap.interfaces import SapConnection, SapGuiPlaceholder


@dataclass(frozen=True, slots=True)
class RuntimePaths:
    """Filesystem paths attached to a SAPHive runtime context."""

    workdir: Path
    logs_dir: Path
    run_dir: Path


@dataclass(slots=True)
class SapContext:
    """Initial SAPHive runtime context shared with automation scripts."""

    script: ScriptMetadata
    run_id: str
    workdir: Path
    paths: RuntimePaths
    config: SAPHiveConfig
    logger: Logger
    sap: SapConnection
    inputs: dict[str, object] = field(default_factory=dict)
    outputs: dict[str, object] = field(default_factory=dict)

    def set_output(self, key: str, value: object) -> None:
        """Store a named output produced by a runtime-executed script."""
        self.outputs[key] = value


def build_sap_context(
    *,
    script: ScriptMetadata,
    config: SAPHiveConfig | None = None,
    inputs: dict[str, object] | None = None,
    run_id: str | None = None,
    workdir: str | Path | None = None,
    logger: Logger | None = None,
    sap: SapConnection | None = None,
) -> SapContext:
    """Build a consistent runtime context for validation or execution paths."""
    resolved_config = SAPHiveConfig() if config is None else config
    resolved_run_id = uuid4().hex if run_id is None else run_id
    resolved_workdir = Path.cwd() if workdir is None else Path(workdir)
    runtime_paths = RuntimePaths(
        workdir=resolved_workdir,
        logs_dir=resolved_config.logging.directory,
        run_dir=resolved_workdir / ".saphive" / "runs" / resolved_run_id,
    )
    resolved_logger = logger or getLogger(f"saphive.{script.name}.{resolved_run_id}")

    return SapContext(
        script=script,
        run_id=resolved_run_id,
        workdir=resolved_workdir,
        paths=runtime_paths,
        config=resolved_config,
        logger=resolved_logger,
        sap=sap or SapGuiPlaceholder(),
        inputs=dict(inputs or {}),
    )
