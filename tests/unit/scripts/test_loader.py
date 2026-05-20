from pathlib import Path

import pytest

from saphive import ScriptContractError, ScriptLoadError
from saphive.scripts import (
    LoadedScript,
    ScriptSourceKind,
    discover_scripts,
    load_script_from_entry,
    load_script_from_path,
    load_script_from_registry,
)


def test_load_script_from_file_path_returns_loaded_script(tmp_path: Path) -> None:
    script_path = tmp_path / "create_notifications.py"
    _write_valid_script(script_path, "create_notifications")

    loaded_script = load_script_from_path(script_path)

    assert isinstance(loaded_script, LoadedScript)
    assert loaded_script.metadata.name == "create_notifications"
    assert loaded_script.source_path == script_path.resolve()
    assert loaded_script.module_path == script_path.resolve()
    assert loaded_script.source_kind is ScriptSourceKind.FILE
    assert loaded_script.validate.__name__ == "validate"
    assert loaded_script.run.__name__ == "run"


def test_load_script_from_package_path_returns_loaded_script(tmp_path: Path) -> None:
    package_path = tmp_path / "download_report"
    package_path.mkdir()
    init_path = package_path / "__init__.py"
    _write_valid_script(init_path, "download_report")

    loaded_script = load_script_from_path(package_path)

    assert loaded_script.metadata.name == "download_report"
    assert loaded_script.source_path == package_path.resolve()
    assert loaded_script.module_path == init_path.resolve()
    assert loaded_script.source_kind is ScriptSourceKind.PACKAGE


def test_load_script_from_package_supports_relative_imports(tmp_path: Path) -> None:
    package_path = tmp_path / "package_script"
    package_path.mkdir()
    (package_path / "helpers.py").write_text(
        'DESCRIPTION_SUFFIX = "with helper"\n',
        encoding="utf-8",
    )
    (package_path / "__init__.py").write_text(
        """
from .helpers import DESCRIPTION_SUFFIX

SCRIPT_NAME = "package_script"
DESCRIPTION = f"Package script {DESCRIPTION_SUFFIX}."

def validate(ctx):
    pass

def run(ctx):
    pass
""".strip(),
        encoding="utf-8",
    )

    loaded_script = load_script_from_path(package_path)

    assert loaded_script.metadata.description == "Package script with helper."


def test_load_script_from_entry_returns_loaded_script(tmp_path: Path) -> None:
    script_path = tmp_path / "update_orders.py"
    _write_valid_script(script_path, "update_orders")
    registry = discover_scripts([tmp_path])

    loaded_script = load_script_from_entry(registry.get("update_orders"))

    assert loaded_script.metadata.name == "update_orders"


def test_load_script_from_registry_loads_by_script_name(tmp_path: Path) -> None:
    script_path = tmp_path / "load_operations.py"
    _write_valid_script(script_path, "load_operations")
    registry = discover_scripts([tmp_path])

    loaded_script = load_script_from_registry(registry, "load_operations")

    assert loaded_script.metadata.name == "load_operations"


def test_load_script_from_path_raises_for_missing_path(tmp_path: Path) -> None:
    missing_path = tmp_path / "missing.py"

    with pytest.raises(ScriptLoadError, match="does not exist") as exc_info:
        load_script_from_path(missing_path)

    assert exc_info.value.details == {"path": str(missing_path)}


def test_load_script_from_path_raises_for_non_python_file(tmp_path: Path) -> None:
    script_path = tmp_path / "README.md"
    script_path.write_text("not a script", encoding="utf-8")

    with pytest.raises(ScriptLoadError, match="Python file"):
        load_script_from_path(script_path)


def test_load_script_from_path_raises_for_package_without_init(tmp_path: Path) -> None:
    package_path = tmp_path / "missing_init"
    package_path.mkdir()

    with pytest.raises(ScriptLoadError, match="__init__"):
        load_script_from_path(package_path)


def test_load_script_from_path_raises_for_import_failure(tmp_path: Path) -> None:
    script_path = tmp_path / "broken_import.py"
    script_path.write_text(
        """
SCRIPT_NAME = "broken_import"
DESCRIPTION = "Fails during import."

raise RuntimeError("boom")

def validate(ctx):
    pass

def run(ctx):
    pass
""".strip(),
        encoding="utf-8",
    )

    with pytest.raises(ScriptLoadError, match="failed while being imported") as exc_info:
        load_script_from_path(script_path)

    assert exc_info.value.details["path"] == str(script_path.resolve())
    assert exc_info.value.details["error"] == "boom"


def test_load_script_from_path_validates_contract_after_import(tmp_path: Path) -> None:
    script_path = tmp_path / "invalid_contract.py"
    script_path.write_text(
        """
SCRIPT_NAME = "invalid_contract"
DESCRIPTION = "Invalid contract."

def validate(ctx, extra):
    pass

def run(ctx):
    pass
""".strip(),
        encoding="utf-8",
    )

    with pytest.raises(ScriptContractError, match="exactly one ctx"):
        load_script_from_path(script_path)


def test_load_script_from_path_executes_loaded_functions_when_called(tmp_path: Path) -> None:
    script_path = tmp_path / "callable_script.py"
    _write_valid_script(script_path, "callable_script")
    loaded_script = load_script_from_path(script_path)

    assert loaded_script.module.CALLS == []
    loaded_script.validate(None)  # type: ignore[arg-type]
    loaded_script.run(None)  # type: ignore[arg-type]

    assert loaded_script.module.CALLS == ["validate", "run"]


def _write_valid_script(path: Path, script_name: str) -> None:
    path.write_text(
        f'''
SCRIPT_NAME = "{script_name}"
DESCRIPTION = "A valid SAPHive script."
CALLS = []

def validate(ctx):
    CALLS.append("validate")

def run(ctx):
    CALLS.append("run")
'''.strip(),
        encoding="utf-8",
    )
