from pathlib import Path

import pytest

from saphive import ScriptDiscoveryError
from saphive.scripts import ScriptRegistry, ScriptSourceKind, discover_scripts


def test_discover_scripts_returns_empty_registry_for_empty_directory(tmp_path: Path) -> None:
    registry = discover_scripts([tmp_path])

    assert isinstance(registry, ScriptRegistry)
    assert len(registry) == 0
    assert registry.names() == ()
    assert registry.metadata() == ()


def test_discover_scripts_finds_single_file_scripts(tmp_path: Path) -> None:
    script_path = tmp_path / "create_notifications.py"
    _write_valid_script(script_path, "create_notifications")

    registry = discover_scripts([tmp_path])
    entry = registry.get("create_notifications")

    assert registry.names() == ("create_notifications",)
    assert entry.metadata.name == "create_notifications"
    assert entry.metadata.description == "Create notifications."
    assert entry.metadata.path == script_path.resolve()
    assert entry.metadata.version == "0.1.0"
    assert entry.metadata.author == "Maintenance Team"
    assert entry.metadata.tags == ("maintenance", "notifications")
    assert entry.source_path == script_path.resolve()
    assert entry.module_path == script_path.resolve()
    assert entry.source_kind is ScriptSourceKind.FILE


def test_discover_scripts_finds_package_scripts(tmp_path: Path) -> None:
    package_path = tmp_path / "download_report"
    package_path.mkdir()
    init_path = package_path / "__init__.py"
    _write_valid_script(init_path, "download_report", description="Download a SAP report.")

    registry = discover_scripts([tmp_path])
    entry = registry.get("download_report")

    assert entry.metadata.path == package_path.resolve()
    assert entry.source_path == package_path.resolve()
    assert entry.module_path == init_path.resolve()
    assert entry.source_kind is ScriptSourceKind.PACKAGE


def test_discover_scripts_sorts_names(tmp_path: Path) -> None:
    _write_valid_script(tmp_path / "z_script.py", "z_script")
    _write_valid_script(tmp_path / "a_script.py", "a_script")

    registry = discover_scripts([tmp_path])

    assert registry.names() == ("a_script", "z_script")


def test_registry_get_raises_for_missing_script(tmp_path: Path) -> None:
    registry = discover_scripts([tmp_path])

    with pytest.raises(ScriptDiscoveryError, match="not found") as exc_info:
        registry.get("missing_script")

    assert exc_info.value.details == {"script_name": "missing_script"}


def test_discover_scripts_detects_duplicate_names(tmp_path: Path) -> None:
    _write_valid_script(tmp_path / "first.py", "duplicate_script")
    _write_valid_script(tmp_path / "second.py", "duplicate_script")

    with pytest.raises(ScriptDiscoveryError, match="Duplicate") as exc_info:
        discover_scripts([tmp_path])

    assert exc_info.value.details["script_name"] == "duplicate_script"


def test_discover_scripts_raises_for_missing_directory(tmp_path: Path) -> None:
    missing_dir = tmp_path / "missing"

    with pytest.raises(ScriptDiscoveryError, match="does not exist") as exc_info:
        discover_scripts([missing_dir])

    assert exc_info.value.details == {"path": str(missing_dir)}


def test_discover_scripts_raises_for_file_configured_as_directory(tmp_path: Path) -> None:
    file_path = tmp_path / "not_a_directory.py"
    file_path.write_text("", encoding="utf-8")

    with pytest.raises(ScriptDiscoveryError, match="not a directory") as exc_info:
        discover_scripts([file_path])

    assert exc_info.value.details == {"path": str(file_path)}


def test_discover_scripts_raises_for_invalid_script(tmp_path: Path) -> None:
    script_path = tmp_path / "invalid_script.py"
    script_path.write_text(
        """
SCRIPT_NAME = "invalid_script"

def validate(ctx):
    pass

def run(ctx):
    pass
""".strip(),
        encoding="utf-8",
    )

    with pytest.raises(ScriptDiscoveryError, match="Invalid") as exc_info:
        discover_scripts([tmp_path])

    assert exc_info.value.details["path"] == str(script_path)


def test_discover_scripts_raises_for_invalid_python_syntax(tmp_path: Path) -> None:
    script_path = tmp_path / "broken_script.py"
    script_path.write_text("def run(:\n", encoding="utf-8")

    with pytest.raises(ScriptDiscoveryError, match="invalid Python syntax") as exc_info:
        discover_scripts([tmp_path])

    assert exc_info.value.details["path"] == str(script_path)


def test_discover_scripts_does_not_import_or_execute_script_code(tmp_path: Path) -> None:
    script_path = tmp_path / "safe_discovery.py"
    script_path.write_text(
        """
SCRIPT_NAME = "safe_discovery"
DESCRIPTION = "Discovery should not execute top-level code."

raise RuntimeError("This would fail if discovery imported the script")

def validate(ctx):
    raise AssertionError("validate should not run during discovery")

def run(ctx):
    raise AssertionError("run should not run during discovery")
""".strip(),
        encoding="utf-8",
    )

    registry = discover_scripts([tmp_path])

    assert registry.names() == ("safe_discovery",)


def test_discover_scripts_ignores_non_script_files(tmp_path: Path) -> None:
    (tmp_path / "README.md").write_text("not a script", encoding="utf-8")
    (tmp_path / "__init__.py").write_text("", encoding="utf-8")

    registry = discover_scripts([tmp_path])

    assert registry.names() == ()


def _write_valid_script(
    path: Path,
    script_name: str,
    *,
    description: str = "Create notifications.",
) -> None:
    path.write_text(
        f'''
SCRIPT_NAME = "{script_name}"
DESCRIPTION = "{description}"
VERSION = "0.1.0"
AUTHOR = "Maintenance Team"
TAGS = ("maintenance", "notifications")

def validate(ctx):
    pass

def run(ctx):
    pass
'''.strip(),
        encoding="utf-8",
    )
