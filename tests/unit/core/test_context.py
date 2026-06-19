from logging import getLogger
from pathlib import Path

import pytest
from pydantic import BaseModel
from tests.support.sap import InMemorySapConnection

from saphive import (
    Bot,
    RuntimePaths,
    SapContext,
    SapGuiPlaceholder,
    SAPHiveConfig,
    SapSessionError,
    build_sap_context,
)


class Input(BaseModel):
    order: str = "4000001"


class Output(BaseModel):
    ok: bool = True


def run(ctx: SapContext, data: Input) -> Output:
    return Output(ok=True)


def test_sap_context_stores_runtime_bot_data() -> None:
    instance = _bot()
    config = SAPHiveConfig()
    context = build_sap_context(
        bot=instance,
        run_id="run-001",
        workdir=Path(),
        inputs={"input_file": "notifications.xlsx"},
        config=config,
    )

    assert context.bot == instance
    assert context.run_id == "run-001"
    assert context.inputs == {"input_file": "notifications.xlsx"}
    assert context.config == config
    assert context.outputs == {}


def test_sap_context_can_store_outputs() -> None:
    context = build_sap_context(bot=_bot(), run_id="run-002", workdir=Path())

    context.set_output("rows_downloaded", 25)

    assert context.outputs == {"rows_downloaded": 25}


def test_build_sap_context_attaches_runtime_paths(tmp_path: Path) -> None:
    config = SAPHiveConfig()
    context = build_sap_context(bot=_bot(), config=config, run_id="run-003", workdir=tmp_path)

    assert isinstance(context.paths, RuntimePaths)
    assert context.workdir == tmp_path
    assert context.paths.workdir == tmp_path
    assert context.paths.logs_dir == config.logging.directory
    assert context.paths.run_dir == tmp_path / ".saphive" / "runs" / "run-003"


def test_build_sap_context_attaches_logger() -> None:
    logger = getLogger("tests.saphive.context")

    context = build_sap_context(bot=_bot(name="update_orders"), run_id="run-004", logger=logger)

    assert context.logger is logger


def test_build_sap_context_creates_default_logger_name() -> None:
    context = build_sap_context(bot=_bot(name="download_report"), run_id="run-005")

    assert context.logger.name == "saphive.download_report.run-005"


def test_build_sap_context_copies_inputs() -> None:
    inputs: dict[str, object] = {"order": "4000001"}
    context = build_sap_context(bot=_bot(name="update_orders"), inputs=inputs)

    inputs["order"] = "changed"

    assert context.inputs == {"order": "4000001"}


def test_build_sap_context_attaches_sap_placeholder() -> None:
    context = build_sap_context(bot=_bot(name="create_notifications"))

    assert isinstance(context.sap, SapGuiPlaceholder)
    with pytest.raises(SapSessionError, match="not been configured"):
        context.sap.create_session()


def test_build_sap_context_accepts_sap_test_double() -> None:
    sap = InMemorySapConnection()
    context = build_sap_context(bot=_bot(name="create_notifications"), sap=sap)

    assert context.sap is sap


def _bot(name: str = "create_notifications") -> Bot:
    return Bot(
        name=name,
        description="Create notifications.",
        input_model=Input,
        output_model=Output,
        run=run,
    )
