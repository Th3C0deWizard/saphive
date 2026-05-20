"""Execution result types for SAPHive Core."""

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from pathlib import Path


class ExecutionStatus(StrEnum):
    """Possible outcomes for a SAPHive runtime execution."""

    SUCCESS = "success"
    VALIDATION_FAILED = "validation_failed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass(frozen=True, slots=True)
class ScriptExecutionResult:
    """Structured result returned by SAPHive Core after an execution attempt."""

    script_name: str
    run_id: str
    status: ExecutionStatus
    started_at: datetime
    finished_at: datetime | None = None
    logs_path: Path | None = None
    outputs: dict[str, object] = field(default_factory=dict)
    error: str | None = None

    @property
    def duration_seconds(self) -> float | None:
        """Return the execution duration when the result has a finish time."""
        if self.finished_at is None:
            return None

        return (self.finished_at - self.started_at).total_seconds()
