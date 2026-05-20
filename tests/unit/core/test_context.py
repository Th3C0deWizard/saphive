from logging import getLogger
from pathlib import Path

import pytest
from tests.support.sap import InMemorySapClient

from saphive import (
    RuntimePaths,
    SapGuiPlaceholder,
    SAPHiveConfig,
    SapSessionError,
    ScriptMetadata,
    build_sap_context,
)


def test_sap_context_stores_runtime_script_data() -> None:
    metadata = ScriptMetadata(
        name="create_notifications",
        description="Create SAP maintenance notifications.",
    )
    config = SAPHiveConfig()
    context = build_sap_context(
        script=metadata,
        run_id="run-001",
        workdir=Path(),
        inputs={"input_file": "notifications.xlsx"},
        config=config,
    )

    assert context.script == metadata
    assert context.run_id == "run-001"
    assert context.inputs == {"input_file": "notifications.xlsx"}
    assert context.config == config
    assert context.outputs == {}


def test_sap_context_can_store_outputs() -> None:
    context = build_sap_context(
        script=ScriptMetadata(name="download_report", description="Download a SAP report."),
        run_id="run-002",
        workdir=Path(),
    )

    context.set_output("rows_downloaded", 25)

    assert context.outputs == {"rows_downloaded": 25}


def test_build_sap_context_attaches_runtime_paths(tmp_path: Path) -> None:
    config = SAPHiveConfig()
    context = build_sap_context(
        script=ScriptMetadata(name="load_operations", description="Load operations."),
        config=config,
        run_id="run-003",
        workdir=tmp_path,
    )

    assert isinstance(context.paths, RuntimePaths)
    assert context.workdir == tmp_path
    assert context.paths.workdir == tmp_path
    assert context.paths.logs_dir == config.logging.directory
    assert context.paths.run_dir == tmp_path / ".saphive" / "runs" / "run-003"


def test_build_sap_context_attaches_logger() -> None:
    logger = getLogger("tests.saphive.context")

    context = build_sap_context(
        script=ScriptMetadata(name="update_orders", description="Update SAP orders."),
        run_id="run-004",
        logger=logger,
    )

    assert context.logger is logger


def test_build_sap_context_creates_default_logger_name() -> None:
    context = build_sap_context(
        script=ScriptMetadata(name="download_report", description="Download report."),
        run_id="run-005",
    )

    assert context.logger.name == "saphive.download_report.run-005"


def test_build_sap_context_copies_inputs() -> None:
    inputs: dict[str, object] = {"order": "4000001"}
    context = build_sap_context(
        script=ScriptMetadata(name="update_orders", description="Update SAP orders."),
        inputs=inputs,
    )

    inputs["order"] = "changed"

    assert context.inputs == {"order": "4000001"}


def test_build_sap_context_attaches_sap_placeholder() -> None:
    context = build_sap_context(
        script=ScriptMetadata(name="create_notifications", description="Create notifications."),
    )

    assert isinstance(context.sap, SapGuiPlaceholder)
    with pytest.raises(SapSessionError, match="not been configured"):
        context.sap.connect()


def test_build_sap_context_accepts_sap_test_double() -> None:
    sap = InMemorySapClient()
    context = build_sap_context(
        script=ScriptMetadata(name="create_notifications", description="Create notifications."),
        sap=sap,
    )

    assert context.sap is sap
