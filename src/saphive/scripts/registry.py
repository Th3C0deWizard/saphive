"""Registry for discovered SAPHive bots."""

from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

from saphive.bot import Bot
from saphive.core.errors import ScriptDiscoveryError


class ScriptSourceKind(StrEnum):
    """Supported source shapes for discovered SAPHive bots."""

    FILE = "file"
    PACKAGE = "package"


@dataclass(frozen=True, slots=True)
class ScriptRegistryEntry:
    """A discovered SAPHive bot entry."""

    bot: Bot
    source_path: Path
    module_path: Path
    source_kind: ScriptSourceKind

    @property
    def name(self) -> str:
        """Return the bot name used as the registry key."""
        return self.bot.name


class ScriptRegistry:
    """Registry of discovered SAPHive bots keyed by bot name."""

    def __init__(self, entries: list[ScriptRegistryEntry] | None = None) -> None:
        self._entries: dict[str, ScriptRegistryEntry] = {}
        for entry in entries or []:
            self.add(entry)

    def __contains__(self, bot_name: str) -> bool:
        return bot_name in self._entries

    def __len__(self) -> int:
        return len(self._entries)

    def add(self, entry: ScriptRegistryEntry) -> None:
        """Add a discovered bot entry, rejecting duplicate names."""
        existing = self._entries.get(entry.name)
        if existing is not None:
            raise ScriptDiscoveryError(
                "Duplicate SAPHive bot name discovered.",
                details={
                    "bot_name": entry.name,
                    "first_path": str(existing.source_path),
                    "duplicate_path": str(entry.source_path),
                },
            )
        self._entries[entry.name] = entry

    def get(self, bot_name: str) -> ScriptRegistryEntry:
        """Return a registry entry by bot name."""
        try:
            return self._entries[bot_name]
        except KeyError as exc:
            raise ScriptDiscoveryError(
                "SAPHive bot was not found in the registry.",
                details={"bot_name": bot_name},
            ) from exc

    def names(self) -> tuple[str, ...]:
        """Return discovered bot names sorted alphabetically."""
        return tuple(sorted(self._entries))

    def entries(self) -> tuple[ScriptRegistryEntry, ...]:
        """Return discovered registry entries sorted by bot name."""
        return tuple(self._entries[name] for name in self.names())

    def bots(self) -> tuple[Bot, ...]:
        """Return discovered bots sorted by bot name."""
        return tuple(entry.bot for entry in self.entries())
