"""Runtime context passed to SAPHive automation scripts."""

from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path

from saphive.core.metadata import ScriptMetadata


@dataclass(slots=True)
class SapContext:
    """Initial SAPHive runtime context shared with automation scripts."""

    script: ScriptMetadata
    run_id: str
    workdir: Path
    inputs: dict[str, object] = field(default_factory=dict)
    config: Mapping[str, object] = field(default_factory=dict)
    outputs: dict[str, object] = field(default_factory=dict)

    def set_output(self, key: str, value: object) -> None:
        """Store a named output produced by a runtime-executed script."""
        self.outputs[key] = value
