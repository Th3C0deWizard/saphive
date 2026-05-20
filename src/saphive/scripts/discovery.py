"""Static discovery for SAPHive automation scripts."""

import ast
from collections.abc import Iterable
from pathlib import Path

from saphive.core import ScriptContractError, ScriptDiscoveryError, ScriptMetadata
from saphive.scripts.contract import REQUIRED_FUNCTION_ATTRIBUTES, REQUIRED_METADATA_ATTRIBUTES
from saphive.scripts.registry import ScriptRegistry, ScriptRegistryEntry, ScriptSourceKind

OPTIONAL_STRING_ATTRIBUTES = ("VERSION", "AUTHOR")


def discover_scripts(script_dirs: Iterable[str | Path]) -> ScriptRegistry:
    """Discover SAPHive scripts from configured directories without importing them."""
    registry = ScriptRegistry()
    for script_dir in script_dirs:
        for entry in _discover_directory(Path(script_dir)):
            registry.add(entry)

    return registry


def _discover_directory(script_dir: Path) -> tuple[ScriptRegistryEntry, ...]:
    if not script_dir.exists():
        raise ScriptDiscoveryError(
            "Configured SAPHive script directory does not exist.",
            details={"path": str(script_dir)},
        )

    if not script_dir.is_dir():
        raise ScriptDiscoveryError(
            "Configured SAPHive script path is not a directory.",
            details={"path": str(script_dir)},
        )

    entries: list[ScriptRegistryEntry] = []
    for child in sorted(script_dir.iterdir(), key=lambda path: path.name):
        if _is_single_file_script(child):
            entries.append(_build_entry(child, child, ScriptSourceKind.FILE))
        elif _is_package_script(child):
            entries.append(_build_entry(child, child / "__init__.py", ScriptSourceKind.PACKAGE))

    return tuple(entries)


def _is_single_file_script(path: Path) -> bool:
    return path.is_file() and path.suffix == ".py" and path.name != "__init__.py"


def _is_package_script(path: Path) -> bool:
    return path.is_dir() and (path / "__init__.py").is_file()


def _build_entry(
    source_path: Path,
    module_path: Path,
    source_kind: ScriptSourceKind,
) -> ScriptRegistryEntry:
    metadata = _extract_static_metadata(module_path, source_path=source_path)
    return ScriptRegistryEntry(
        metadata=metadata,
        source_path=source_path.resolve(),
        module_path=module_path.resolve(),
        source_kind=source_kind,
    )


def _extract_static_metadata(module_path: Path, *, source_path: Path) -> ScriptMetadata:
    module = _parse_module(module_path)
    assignments = _collect_literal_assignments(module)
    function_names = {
        node.name
        for node in module.body
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef)
    }

    try:
        script_name = _required_string(assignments, REQUIRED_METADATA_ATTRIBUTES[0], module_path)
        description = _required_string(assignments, REQUIRED_METADATA_ATTRIBUTES[1], module_path)
        _validate_required_functions(function_names, module_path)
        version = _optional_string(assignments, "VERSION", module_path)
        author = _optional_string(assignments, "AUTHOR", module_path)
        tags = _optional_tags(assignments, module_path)
    except ScriptContractError as exc:
        raise ScriptDiscoveryError(
            "Invalid SAPHive script discovered.",
            details={
                "path": str(source_path),
                "error": exc.message,
                "contract_details": exc.details,
            },
        ) from exc

    return ScriptMetadata(
        name=script_name,
        description=description,
        path=source_path.resolve(),
        version=version,
        author=author,
        tags=tags,
    )


def _parse_module(module_path: Path) -> ast.Module:
    try:
        source = module_path.read_text(encoding="utf-8")
        return ast.parse(source, filename=str(module_path))
    except OSError as exc:
        raise ScriptDiscoveryError(
            "SAPHive could not read script file during discovery.",
            details={"path": str(module_path), "error": str(exc)},
        ) from exc
    except SyntaxError as exc:
        raise ScriptDiscoveryError(
            "SAPHive script has invalid Python syntax.",
            details={"path": str(module_path), "error": str(exc)},
        ) from exc


def _collect_literal_assignments(module: ast.Module) -> dict[str, object]:
    assignments: dict[str, object] = {}
    for node in module.body:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    assignments[target.id] = _literal_value(node.value)
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            assignments[node.target.id] = _literal_value(node.value)

    return assignments


def _literal_value(node: ast.expr | None) -> object:
    if node is None:
        return None

    try:
        return ast.literal_eval(node)
    except (ValueError, TypeError):
        return None


def _required_string(assignments: dict[str, object], name: str, module_path: Path) -> str:
    value = assignments.get(name)
    if not isinstance(value, str) or value.strip() == "":
        raise ScriptContractError(
            f"SAPHive script requires a non-empty string {name} attribute.",
            details={"path": str(module_path), "attribute": name},
        )

    return value


def _optional_string(assignments: dict[str, object], name: str, module_path: Path) -> str | None:
    value = assignments.get(name)
    if value is None:
        return None

    if not isinstance(value, str) or value.strip() == "":
        raise ScriptContractError(
            f"Optional SAPHive script attribute {name} must be a non-empty string.",
            details={"path": str(module_path), "attribute": name},
        )

    return value


def _optional_tags(assignments: dict[str, object], module_path: Path) -> tuple[str, ...]:
    value = assignments.get("TAGS")
    if value is None:
        return ()

    if not isinstance(value, (list, tuple)):
        raise ScriptContractError(
            "Optional SAPHive script attribute TAGS must be a sequence of strings.",
            details={"path": str(module_path), "attribute": "TAGS"},
        )

    tags = tuple(value)
    if not all(isinstance(tag, str) and tag.strip() != "" for tag in tags):
        raise ScriptContractError(
            "Optional SAPHive script attribute TAGS must contain only non-empty strings.",
            details={"path": str(module_path), "attribute": "TAGS"},
        )

    return tags


def _validate_required_functions(function_names: set[str], module_path: Path) -> None:
    for function_name in REQUIRED_FUNCTION_ATTRIBUTES:
        if function_name not in function_names:
            raise ScriptContractError(
                f"SAPHive script requires a {function_name}(ctx) function.",
                details={"path": str(module_path), "function": function_name},
            )
