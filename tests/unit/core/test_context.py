from pathlib import Path

from saphive import SapContext, ScriptMetadata


def test_sap_context_stores_runtime_script_data() -> None:
    metadata = ScriptMetadata(
        name="create_notifications",
        description="Create SAP maintenance notifications.",
    )
    context = SapContext(
        script=metadata,
        run_id="run-001",
        workdir=Path(),
        inputs={"input_file": "notifications.xlsx"},
        config={"log_level": "INFO"},
    )

    assert context.script == metadata
    assert context.run_id == "run-001"
    assert context.inputs == {"input_file": "notifications.xlsx"}
    assert context.config == {"log_level": "INFO"}
    assert context.outputs == {}


def test_sap_context_can_store_outputs() -> None:
    context = SapContext(
        script=ScriptMetadata(name="download_report", description="Download a SAP report."),
        run_id="run-002",
        workdir=Path(),
    )

    context.set_output("rows_downloaded", 25)

    assert context.outputs == {"rows_downloaded": 25}
