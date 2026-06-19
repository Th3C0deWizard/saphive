"""Bot loading and discovery package for SAPHive."""

from saphive.scripts.discovery import discover_scripts
from saphive.scripts.loader import (
    LoadedBot,
    load_bot_from_entry,
    load_bot_from_path,
    load_bot_from_registry,
)
from saphive.scripts.registry import ScriptRegistry, ScriptRegistryEntry, ScriptSourceKind

__all__ = [
    "LoadedBot",
    "ScriptRegistry",
    "ScriptRegistryEntry",
    "ScriptSourceKind",
    "discover_scripts",
    "load_bot_from_entry",
    "load_bot_from_path",
    "load_bot_from_registry",
]
