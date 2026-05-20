from pathlib import Path

from tests.support.sap import InMemorySapClient, InMemorySapSession

from saphive import ExecutionStatus, PathsConfig, SAPHiveConfig, SapRuntime


def test_runtime_validate_script_runs_validate_only(tmp_path: Path) -> None:
    script_path = tmp_path / "validate_only.py"
    _write_script(
        script_path,
        "validate_only",
        validate_body='ctx.set_output("validated", True)',
        run_body='ctx.set_output("ran", True)',
    )

    result = SapRuntime().validate_script(script_path, run_id="run-validate")

    assert result.status is ExecutionStatus.SUCCESS
    assert result.script_name == "validate_only"
    assert result.run_id == "run-validate"
    assert result.outputs == {"validated": True}
    assert result.error is None
    assert result.duration_seconds is not None


def test_runtime_run_script_runs_validate_and_run(tmp_path: Path) -> None:
    script_path = tmp_path / "run_script.py"
    _write_script(
        script_path,
        "run_script",
        validate_body='ctx.set_output("validated", True)',
        run_body='ctx.set_output("ran", True)',
    )

    result = SapRuntime().run_script(script_path, run_id="run-full")

    assert result.status is ExecutionStatus.SUCCESS
    assert result.outputs == {"validated": True, "ran": True}


def test_runtime_loads_named_script_from_configured_paths(tmp_path: Path) -> None:
    script_path = tmp_path / "named_script.py"
    _write_script(
        script_path,
        "named_script",
        validate_body='ctx.set_output("validated", ctx.inputs["value"])',
        run_body='ctx.set_output("ran", True)',
    )
    runtime = SapRuntime(config=SAPHiveConfig(paths=PathsConfig(scripts=(tmp_path,))))

    result = runtime.run_script("named_script", inputs={"value": 42})

    assert result.status is ExecutionStatus.SUCCESS
    assert result.script_name == "named_script"
    assert result.outputs == {"validated": 42, "ran": True}


def test_runtime_returns_validation_failed_result(tmp_path: Path) -> None:
    script_path = tmp_path / "invalid_input.py"
    _write_script(
        script_path,
        "invalid_input",
        validate_body=(
            'ctx.set_output("checked", True)\n'
            '    raise ScriptValidationError("Input file is missing")'
        ),
        run_body='ctx.set_output("ran", True)',
        imports="from saphive import ScriptValidationError",
    )

    result = SapRuntime().run_script(script_path)

    assert result.status is ExecutionStatus.VALIDATION_FAILED
    assert result.outputs == {"checked": True}
    assert result.error == "Input file is missing"


def test_runtime_returns_failed_result_for_execution_error(tmp_path: Path) -> None:
    script_path = tmp_path / "execution_error.py"
    _write_script(
        script_path,
        "execution_error",
        validate_body='ctx.set_output("validated", True)',
        run_body=(
            'ctx.set_output("started", True)\n'
            '    raise ScriptExecutionError("SAP transaction failed")'
        ),
        imports="from saphive import ScriptExecutionError",
    )

    result = SapRuntime().run_script(script_path)

    assert result.status is ExecutionStatus.FAILED
    assert result.outputs == {"validated": True, "started": True}
    assert result.error == "SAP transaction failed"


def test_runtime_returns_failed_result_for_unexpected_execution_error(tmp_path: Path) -> None:
    script_path = tmp_path / "unexpected_error.py"
    _write_script(
        script_path,
        "unexpected_error",
        validate_body='ctx.set_output("validated", True)',
        run_body='raise RuntimeError("boom")',
    )

    result = SapRuntime().run_script(script_path)

    assert result.status is ExecutionStatus.FAILED
    assert result.outputs == {"validated": True}
    assert result.error == "boom"


def test_runtime_returns_failed_result_for_load_error(tmp_path: Path) -> None:
    missing_path = tmp_path / "missing.py"

    result = SapRuntime().run_script(missing_path, run_id="run-load-failure")

    assert result.status is ExecutionStatus.FAILED
    assert result.script_name == str(missing_path)
    assert result.run_id == "run-load-failure"
    assert result.error == "SAPHive script path does not exist."


def test_runtime_context_uses_injected_sap_client(tmp_path: Path) -> None:
    script_path = tmp_path / "sap_script.py"
    _write_script(
        script_path,
        "sap_script",
        validate_body='ctx.set_output("validated", True)',
        run_body=(
            'session = ctx.sap.connect()\n'
            '    session.start_transaction("IW21")\n'
            '    ctx.set_output("status", session.status_bar_text())'
        ),
    )
    sap_session = InMemorySapSession(status_text="Notification created")
    runtime = SapRuntime(sap=InMemorySapClient(session=sap_session))

    result = runtime.run_script(script_path)

    assert result.status is ExecutionStatus.SUCCESS
    assert result.outputs == {"validated": True, "status": "Notification created"}
    assert sap_session.operations == [
        ("start_transaction", "IW21"),
        ("status_bar_text", "wnd[0]/sbar"),
    ]


def _write_script(
    path: Path,
    script_name: str,
    *,
    validate_body: str,
    run_body: str,
    imports: str = "",
) -> None:
    path.write_text(
        f'''
{imports}

SCRIPT_NAME = "{script_name}"
DESCRIPTION = "Runtime test script."

def validate(ctx):
    {validate_body}

def run(ctx):
    {run_body}
'''.strip(),
        encoding="utf-8",
    )
