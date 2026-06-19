from pathlib import Path

import pytest

from saphive import ScriptDiscoveryError
from saphive.scripts import ScriptRegistry, ScriptSourceKind, discover_scripts


def test_discover_scripts_returns_empty_registry_for_empty_directory(tmp_path: Path) -> None:
    registry = discover_scripts([tmp_path])

    assert isinstance(registry, ScriptRegistry)
    assert len(registry) == 0
    assert registry.names() == ()
    assert registry.bots() == ()


def test_discover_scripts_finds_single_file_bots(tmp_path: Path) -> None:
    bot_path = tmp_path / "create_notifications.py"
    _write_valid_bot(bot_path, "create_notifications")

    registry = discover_scripts([tmp_path])
    entry = registry.get("create_notifications")

    assert registry.names() == ("create_notifications",)
    assert entry.bot.name == "create_notifications"
    assert entry.bot.description == "Create notifications."
    assert entry.bot.version == "0.1.0"
    assert entry.bot.author == "Maintenance Team"
    assert entry.bot.tags == ("maintenance", "notifications")
    assert entry.source_path == bot_path.resolve()
    assert entry.module_path == bot_path.resolve()
    assert entry.source_kind is ScriptSourceKind.FILE


def test_discover_scripts_finds_package_bots(tmp_path: Path) -> None:
    package_path = tmp_path / "download_report"
    package_path.mkdir()
    init_path = package_path / "__init__.py"
    _write_valid_bot(init_path, "download_report", description="Download a SAP report.")

    registry = discover_scripts([tmp_path])
    entry = registry.get("download_report")

    assert entry.source_path == package_path.resolve()
    assert entry.module_path == init_path.resolve()
    assert entry.source_kind is ScriptSourceKind.PACKAGE


def test_discover_scripts_sorts_names(tmp_path: Path) -> None:
    _write_valid_bot(tmp_path / "z_bot.py", "z_bot")
    _write_valid_bot(tmp_path / "a_bot.py", "a_bot")

    registry = discover_scripts([tmp_path])

    assert registry.names() == ("a_bot", "z_bot")


def test_registry_get_raises_for_missing_bot(tmp_path: Path) -> None:
    registry = discover_scripts([tmp_path])

    with pytest.raises(ScriptDiscoveryError, match="not found") as exc_info:
        registry.get("missing_bot")

    assert exc_info.value.details == {"bot_name": "missing_bot"}


def test_discover_scripts_detects_duplicate_names(tmp_path: Path) -> None:
    _write_valid_bot(tmp_path / "first.py", "duplicate_bot")
    _write_valid_bot(tmp_path / "second.py", "duplicate_bot")

    with pytest.raises(ScriptDiscoveryError, match="Duplicate") as exc_info:
        discover_scripts([tmp_path])

    assert exc_info.value.details["bot_name"] == "duplicate_bot"


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


def test_discover_scripts_ignores_python_files_without_bot(tmp_path: Path) -> None:
    (tmp_path / "helpers.py").write_text("VALUE = 1", encoding="utf-8")

    registry = discover_scripts([tmp_path])

    assert registry.names() == ()


def test_discover_scripts_raises_for_import_failure(tmp_path: Path) -> None:
    script_path = tmp_path / "broken_bot.py"
    script_path.write_text('raise RuntimeError("boom")', encoding="utf-8")

    with pytest.raises(ScriptDiscoveryError, match="could not load") as exc_info:
        discover_scripts([tmp_path])

    assert exc_info.value.details["path"] == str(script_path)


def _write_valid_bot(
    path: Path,
    bot_name: str,
    *,
    description: str = "Create notifications.",
) -> None:
    path.write_text(
        f'''
from pydantic import BaseModel
from saphive import bot

class Input(BaseModel):
    value: str = "ok"

class Output(BaseModel):
    result: str

@bot(
    name="{bot_name}",
    description="{description}",
    input_model=Input,
    output_model=Output,
    version="0.1.0",
    author="Maintenance Team",
    tags=("maintenance", "notifications"),
)
def run(ctx, data):
    return Output(result=data.value)
'''.strip(),
        encoding="utf-8",
    )
