"""Bot loading for SAPHive."""

import hashlib
import importlib.util
import sys
from dataclasses import dataclass
from pathlib import Path
from types import ModuleType

from saphive.bot import Bot, bot_from_module
from saphive.core.errors import BotContractError, ScriptLoadError
from saphive.scripts.registry import ScriptRegistry, ScriptRegistryEntry, ScriptSourceKind


@dataclass(frozen=True, slots=True)
class LoadedBot:
    """A loaded and contract-validated SAPHive bot module."""

    module: ModuleType | None
    bot: Bot
    source_path: Path | None = None
    module_path: Path | None = None
    source_kind: ScriptSourceKind | None = None


def load_bot_from_registry(registry: ScriptRegistry, bot_name: str) -> LoadedBot:
    """Load a SAPHive bot by name from an existing registry."""
    return load_bot_from_entry(registry.get(bot_name))


def load_bot_from_entry(entry: ScriptRegistryEntry) -> LoadedBot:
    """Load a SAPHive bot from a registry entry."""
    module = _import_bot_module(
        source_path=entry.source_path,
        module_path=entry.module_path,
        source_kind=entry.source_kind,
    )
    bot = bot_from_module(module)
    return LoadedBot(
        module=module,
        bot=bot,
        source_path=entry.source_path,
        module_path=entry.module_path,
        source_kind=entry.source_kind,
    )


def load_bot_from_path(path: str | Path) -> LoadedBot:
    """Load a SAPHive bot from an explicit file path or package directory."""
    source_path = Path(path)
    source_kind, module_path = _resolve_bot_source(source_path)
    module = _import_bot_module(
        source_path=source_path,
        module_path=module_path,
        source_kind=source_kind,
    )
    bot = bot_from_module(module)
    return LoadedBot(
        module=module,
        bot=bot,
        source_path=source_path.resolve(),
        module_path=module_path.resolve(),
        source_kind=source_kind,
    )


def _resolve_bot_source(source_path: Path) -> tuple[ScriptSourceKind, Path]:
    if not source_path.exists():
        raise ScriptLoadError(
            "SAPHive bot path does not exist.",
            details={"path": str(source_path)},
        )

    if source_path.is_file():
        if source_path.suffix != ".py":
            raise ScriptLoadError(
                "SAPHive bot file must be a Python file.",
                details={"path": str(source_path)},
            )
        return ScriptSourceKind.FILE, source_path

    if source_path.is_dir():
        module_path = source_path / "__init__.py"
        if not module_path.is_file():
            raise ScriptLoadError(
                "SAPHive bot package directory must contain __init__.py.",
                details={"path": str(source_path)},
            )
        return ScriptSourceKind.PACKAGE, module_path

    raise ScriptLoadError(
        "SAPHive bot path is not a file or package directory.",
        details={"path": str(source_path)},
    )


def _import_bot_module(
    *,
    source_path: Path,
    module_path: Path,
    source_kind: ScriptSourceKind,
) -> ModuleType:
    resolved_source_path = source_path.resolve()
    resolved_module_path = module_path.resolve()
    module_name = _module_name_for_path(resolved_source_path)
    submodule_locations = (
        [str(resolved_source_path)] if source_kind is ScriptSourceKind.PACKAGE else None
    )
    spec = importlib.util.spec_from_file_location(
        module_name,
        resolved_module_path,
        submodule_search_locations=submodule_locations,
    )
    if spec is None or spec.loader is None:
        raise ScriptLoadError(
            "SAPHive could not create an import specification for the bot.",
            details={"path": str(resolved_source_path)},
        )

    module = importlib.util.module_from_spec(spec)
    sys.modules.pop(module_name, None)
    sys.modules[module_name] = module
    try:
        spec.loader.exec_module(module)
    except BotContractError:
        sys.modules.pop(module_name, None)
        raise
    except Exception as exc:
        sys.modules.pop(module_name, None)
        raise ScriptLoadError(
            "SAPHive bot failed while being imported.",
            details={"path": str(resolved_source_path), "error": str(exc)},
        ) from exc

    return module


def _module_name_for_path(path: Path) -> str:
    path_digest = hashlib.sha256(str(path).encode("utf-8")).hexdigest()[:16]
    safe_name = path.stem.replace("-", "_")
    return f"_saphive_bot_{safe_name}_{path_digest}"
