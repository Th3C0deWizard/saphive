"""Metadata types for SAPHive automation scripts."""

from dataclasses import dataclass, field
from pathlib import Path


@dataclass(frozen=True, slots=True)
class ScriptMetadata:
    """Descriptive metadata extracted from a SAPHive script."""

    name: str
    description: str
    path: Path | None = None
    version: str | None = None
    author: str | None = None
    tags: tuple[str, ...] = field(default_factory=tuple)
