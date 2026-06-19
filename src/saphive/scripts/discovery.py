"""Import-based discovery for SAPHive bots."""

from collections.abc import Iterable
from pathlib import Path

from saphive.core.errors import BotContractError, ScriptDiscoveryError, ScriptLoadError
from saphive.scripts.loader import LoadedBot, load_bot_from_path
from saphive.scripts.registry import ScriptRegistry, ScriptRegistryEntry


def discover_scripts(script_dirs: Iterable[str | Path]) -> ScriptRegistry:
    """Discover SAPHive bots from configured directories."""
    registry = ScriptRegistry()
    for script_dir in script_dirs:
        for entry in _discover_directory(Path(script_dir)):
            registry.add(entry)
    return registry


def _discover_directory(script_dir: Path) -> tuple[ScriptRegistryEntry, ...]:
    if not script_dir.exists():
        raise ScriptDiscoveryError(
            "Configured SAPHive bot directory does not exist.",
            details={"path": str(script_dir)},
        )
    if not script_dir.is_dir():
        raise ScriptDiscoveryError(
            "Configured SAPHive bot path is not a directory.",
            details={"path": str(script_dir)},
        )

    entries: list[ScriptRegistryEntry] = []
    for child in sorted(script_dir.iterdir(), key=lambda path: path.name):
        if not (_is_single_file_bot(child) or _is_package_bot(child)):
            continue
        loaded = _try_load_discovered_bot(child)
        if loaded is None:
            continue
        if loaded.source_path is None or loaded.module_path is None or loaded.source_kind is None:
            continue
        entries.append(
            ScriptRegistryEntry(
                bot=loaded.bot,
                source_path=loaded.source_path,
                module_path=loaded.module_path,
                source_kind=loaded.source_kind,
            )
        )

    return tuple(entries)


def _try_load_discovered_bot(path: Path) -> LoadedBot | None:
    try:
        return load_bot_from_path(path)
    except BotContractError:
        return None
    except ScriptLoadError as exc:
        raise ScriptDiscoveryError(
            "SAPHive could not load discovered bot candidate.",
            details={"path": str(path), "error": exc.message, "load_details": exc.details},
        ) from exc


def _is_single_file_bot(path: Path) -> bool:
    return path.is_file() and path.suffix == ".py" and path.name != "__init__.py"


def _is_package_bot(path: Path) -> bool:
    return path.is_dir() and (path / "__init__.py").is_file()
