"""Script loading for SAPHive automation scripts."""

import hashlib
import importlib.util
import sys
from dataclasses import dataclass
from pathlib import Path
from types import ModuleType

from saphive.core import ScriptContractError, ScriptLoadError, ScriptMetadata
from saphive.scripts.contract import ScriptContract, ScriptFunction, validate_script_contract
from saphive.scripts.registry import ScriptRegistry, ScriptRegistryEntry, ScriptSourceKind


@dataclass(frozen=True, slots=True)
class LoadedScript:
    """A loaded and contract-validated SAPHive automation script."""

    module: ModuleType
    contract: ScriptContract
    source_path: Path
    module_path: Path
    source_kind: ScriptSourceKind

    @property
    def metadata(self) -> ScriptMetadata:
        """Return loaded script metadata."""
        return self.contract.metadata

    @property
    def validate(self) -> ScriptFunction:
        """Return loaded script validation function."""
        return self.contract.validate

    @property
    def run(self) -> ScriptFunction:
        """Return loaded script run function."""
        return self.contract.run

    @property
    def cleanup(self) -> ScriptFunction | None:
        """Return loaded script cleanup function when present."""
        return self.contract.cleanup


def load_script_from_registry(registry: ScriptRegistry, script_name: str) -> LoadedScript:
    """Load a SAPHive script by name from an existing script registry."""
    return load_script_from_entry(registry.get(script_name))


def load_script_from_entry(entry: ScriptRegistryEntry) -> LoadedScript:
    """Load a SAPHive script from a registry entry."""
    module = _import_script_module(
        source_path=entry.source_path,
        module_path=entry.module_path,
        source_kind=entry.source_kind,
    )
    contract = validate_script_contract(module, path=entry.source_path)
    return LoadedScript(
        module=module,
        contract=contract,
        source_path=entry.source_path,
        module_path=entry.module_path,
        source_kind=entry.source_kind,
    )


def load_script_from_path(path: str | Path) -> LoadedScript:
    """Load a SAPHive script from an explicit file path or package directory."""
    source_path = Path(path)
    source_kind, module_path = _resolve_script_source(source_path)
    module = _import_script_module(
        source_path=source_path,
        module_path=module_path,
        source_kind=source_kind,
    )
    contract = validate_script_contract(module, path=source_path)
    return LoadedScript(
        module=module,
        contract=contract,
        source_path=source_path.resolve(),
        module_path=module_path.resolve(),
        source_kind=source_kind,
    )


def _resolve_script_source(source_path: Path) -> tuple[ScriptSourceKind, Path]:
    if not source_path.exists():
        raise ScriptLoadError(
            "SAPHive script path does not exist.",
            details={"path": str(source_path)},
        )

    if source_path.is_file():
        if source_path.suffix != ".py":
            raise ScriptLoadError(
                "SAPHive script file must be a Python file.",
                details={"path": str(source_path)},
            )

        return ScriptSourceKind.FILE, source_path

    if source_path.is_dir():
        module_path = source_path / "__init__.py"
        if not module_path.is_file():
            raise ScriptLoadError(
                "SAPHive script package directory must contain __init__.py.",
                details={"path": str(source_path)},
            )

        return ScriptSourceKind.PACKAGE, module_path

    raise ScriptLoadError(
        "SAPHive script path is not a file or package directory.",
        details={"path": str(source_path)},
    )


def _import_script_module(
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
            "SAPHive could not create an import specification for the script.",
            details={"path": str(resolved_source_path)},
        )

    module = importlib.util.module_from_spec(spec)
    sys.modules.pop(module_name, None)
    sys.modules[module_name] = module

    try:
        spec.loader.exec_module(module)
    except ScriptContractError:
        sys.modules.pop(module_name, None)
        raise
    except Exception as exc:
        sys.modules.pop(module_name, None)
        raise ScriptLoadError(
            "SAPHive script failed while being imported.",
            details={"path": str(resolved_source_path), "error": str(exc)},
        ) from exc

    return module


def _module_name_for_path(path: Path) -> str:
    path_digest = hashlib.sha256(str(path).encode("utf-8")).hexdigest()[:16]
    safe_name = path.stem.replace("-", "_")
    return f"_saphive_script_{safe_name}_{path_digest}"
