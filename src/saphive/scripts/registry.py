"""Registry for discovered SAPHive automation scripts."""

from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

from saphive.core import ScriptDiscoveryError, ScriptMetadata


class ScriptSourceKind(StrEnum):
    """Supported source shapes for discovered SAPHive scripts."""

    FILE = "file"
    PACKAGE = "package"


@dataclass(frozen=True, slots=True)
class ScriptRegistryEntry:
    """A discovered SAPHive script entry."""

    metadata: ScriptMetadata
    source_path: Path
    module_path: Path
    source_kind: ScriptSourceKind

    @property
    def name(self) -> str:
        """Return the script name used as the registry key."""
        return self.metadata.name


class ScriptRegistry:
    """Registry of discovered SAPHive automation scripts keyed by script name."""

    def __init__(self, entries: list[ScriptRegistryEntry] | None = None) -> None:
        self._entries: dict[str, ScriptRegistryEntry] = {}
        for entry in entries or []:
            self.add(entry)

    def __contains__(self, script_name: str) -> bool:
        return script_name in self._entries

    def __len__(self) -> int:
        return len(self._entries)

    def add(self, entry: ScriptRegistryEntry) -> None:
        """Add a discovered script entry, rejecting duplicate names."""
        existing = self._entries.get(entry.name)
        if existing is not None:
            raise ScriptDiscoveryError(
                "Duplicate SAPHive script name discovered.",
                details={
                    "script_name": entry.name,
                    "first_path": str(existing.source_path),
                    "duplicate_path": str(entry.source_path),
                },
            )

        self._entries[entry.name] = entry

    def get(self, script_name: str) -> ScriptRegistryEntry:
        """Return a registry entry by script name."""
        try:
            return self._entries[script_name]
        except KeyError as exc:
            raise ScriptDiscoveryError(
                "SAPHive script was not found in the registry.",
                details={"script_name": script_name},
            ) from exc

    def names(self) -> tuple[str, ...]:
        """Return discovered script names sorted alphabetically."""
        return tuple(sorted(self._entries))

    def entries(self) -> tuple[ScriptRegistryEntry, ...]:
        """Return discovered registry entries sorted by script name."""
        return tuple(self._entries[name] for name in self.names())

    def metadata(self) -> tuple[ScriptMetadata, ...]:
        """Return discovered script metadata sorted by script name."""
        return tuple(entry.metadata for entry in self.entries())
