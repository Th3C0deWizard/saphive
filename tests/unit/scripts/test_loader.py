from pathlib import Path

import pytest

from saphive import BotContractError, ScriptLoadError
from saphive.scripts import (
    LoadedBot,
    ScriptSourceKind,
    discover_scripts,
    load_bot_from_entry,
    load_bot_from_path,
    load_bot_from_registry,
)


def test_load_bot_from_file_path_returns_loaded_bot(tmp_path: Path) -> None:
    bot_path = tmp_path / "create_notifications.py"
    _write_valid_bot(bot_path, "create_notifications")

    loaded_bot = load_bot_from_path(bot_path)

    assert isinstance(loaded_bot, LoadedBot)
    assert loaded_bot.bot.name == "create_notifications"
    assert loaded_bot.source_path == bot_path.resolve()
    assert loaded_bot.module_path == bot_path.resolve()
    assert loaded_bot.source_kind is ScriptSourceKind.FILE


def test_load_bot_from_package_path_returns_loaded_bot(tmp_path: Path) -> None:
    package_path = tmp_path / "download_report"
    package_path.mkdir()
    init_path = package_path / "__init__.py"
    _write_valid_bot(init_path, "download_report")

    loaded_bot = load_bot_from_path(package_path)

    assert loaded_bot.bot.name == "download_report"
    assert loaded_bot.source_path == package_path.resolve()
    assert loaded_bot.module_path == init_path.resolve()
    assert loaded_bot.source_kind is ScriptSourceKind.PACKAGE


def test_load_bot_from_package_supports_relative_imports(tmp_path: Path) -> None:
    package_path = tmp_path / "package_bot"
    package_path.mkdir()
    (package_path / "helpers.py").write_text(
        'DESCRIPTION_SUFFIX = "with helper"\n',
        encoding="utf-8",
    )
    (package_path / "__init__.py").write_text(
        """
from pydantic import BaseModel
from saphive import bot
from .helpers import DESCRIPTION_SUFFIX

class Input(BaseModel):
    value: str = "ok"

class Output(BaseModel):
    result: str

@bot(
    name="package_bot",
    description=f"Package bot {DESCRIPTION_SUFFIX}.",
    input_model=Input,
    output_model=Output,
)
def run(ctx, data):
    return Output(result=data.value)
""".strip(),
        encoding="utf-8",
    )

    loaded_bot = load_bot_from_path(package_path)

    assert loaded_bot.bot.description == "Package bot with helper."


def test_load_bot_from_entry_returns_loaded_bot(tmp_path: Path) -> None:
    bot_path = tmp_path / "update_orders.py"
    _write_valid_bot(bot_path, "update_orders")
    registry = discover_scripts([tmp_path])

    loaded_bot = load_bot_from_entry(registry.get("update_orders"))

    assert loaded_bot.bot.name == "update_orders"


def test_load_bot_from_registry_loads_by_bot_name(tmp_path: Path) -> None:
    bot_path = tmp_path / "load_operations.py"
    _write_valid_bot(bot_path, "load_operations")
    registry = discover_scripts([tmp_path])

    loaded_bot = load_bot_from_registry(registry, "load_operations")

    assert loaded_bot.bot.name == "load_operations"


def test_load_bot_from_path_raises_for_missing_path(tmp_path: Path) -> None:
    missing_path = tmp_path / "missing.py"

    with pytest.raises(ScriptLoadError, match="does not exist") as exc_info:
        load_bot_from_path(missing_path)

    assert exc_info.value.details == {"path": str(missing_path)}


def test_load_bot_from_path_raises_for_non_python_file(tmp_path: Path) -> None:
    bot_path = tmp_path / "README.md"
    bot_path.write_text("not a bot", encoding="utf-8")

    with pytest.raises(ScriptLoadError, match="Python file"):
        load_bot_from_path(bot_path)


def test_load_bot_from_path_raises_for_package_without_init(tmp_path: Path) -> None:
    package_path = tmp_path / "missing_init"
    package_path.mkdir()

    with pytest.raises(ScriptLoadError, match="__init__"):
        load_bot_from_path(package_path)


def test_load_bot_from_path_raises_for_import_failure(tmp_path: Path) -> None:
    bot_path = tmp_path / "broken_import.py"
    bot_path.write_text('raise RuntimeError("boom")', encoding="utf-8")

    with pytest.raises(ScriptLoadError, match="failed while being imported") as exc_info:
        load_bot_from_path(bot_path)

    assert exc_info.value.details["path"] == str(bot_path.resolve())
    assert exc_info.value.details["error"] == "boom"


def test_load_bot_from_path_validates_contract_after_import(tmp_path: Path) -> None:
    bot_path = tmp_path / "invalid_contract.py"
    bot_path.write_text(
        """
from pydantic import BaseModel
from saphive import Bot

class Input(BaseModel):
    value: str

class Output(BaseModel):
    result: str

def run(ctx):
    return Output(result="invalid")

BOT = Bot(name="invalid", description="Invalid.", input_model=Input, output_model=Output, run=run)
""".strip(),
        encoding="utf-8",
    )

    with pytest.raises(BotContractError, match="exactly 2"):
        load_bot_from_path(bot_path)


def _write_valid_bot(path: Path, bot_name: str) -> None:
    path.write_text(
        f'''
from pydantic import BaseModel
from saphive import bot

class Input(BaseModel):
    value: str = "ok"

class Output(BaseModel):
    result: str

@bot(name="{bot_name}", description="A valid SAPHive bot.", input_model=Input, output_model=Output)
def run(ctx, data):
    return Output(result=data.value)
'''.strip(),
        encoding="utf-8",
    )
