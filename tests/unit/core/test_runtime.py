from pathlib import Path

from tests.support.sap import (
    InMemorySapConnection,
    InMemorySapConnectionResolver,
    InMemorySapSession,
)

from saphive import (
    ExecutionStatus,
    LoggingConfig,
    PathsConfig,
    SapConfig,
    SapConnectionMode,
    SapConnectionProfile,
    SAPHiveConfig,
    SapRuntime,
)


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
            'session = ctx.sap.active_session()\n'
            '    session.start_transaction("IW21")\n'
            '    ctx.set_output("status", session.status_bar_text())'
        ),
    )
    sap_session = InMemorySapSession(status_text="Notification created")
    runtime = SapRuntime(sap=InMemorySapConnection(session=sap_session))

    result = runtime.run_script(script_path)

    assert result.status is ExecutionStatus.SUCCESS
    assert result.outputs == {"validated": True, "status": "Notification created"}
    assert sap_session.operations == [
        ("start_transaction", "IW21"),
        ("status_bar_text", "wnd[0]/sbar"),
    ]


def test_runtime_does_not_resolve_sap_when_validation_fails(tmp_path: Path) -> None:
    script_path = tmp_path / "validation_blocks_sap.py"
    _write_script(
        script_path,
        "validation_blocks_sap",
        validate_body='raise ScriptValidationError("bad input")',
        run_body='ctx.set_output("ran", True)',
        imports="from saphive import ScriptValidationError",
    )
    resolver = InMemorySapConnectionResolver()
    runtime = SapRuntime(config=_sap_config(), connection_resolver=resolver)

    result = runtime.run_script(script_path)

    assert result.status is ExecutionStatus.VALIDATION_FAILED
    assert resolver.resolved_modes == []


def test_runtime_resolves_sap_after_validation_for_run(tmp_path: Path) -> None:
    script_path = tmp_path / "connection_scoped_sap.py"
    _write_script(
        script_path,
        "connection_scoped_sap",
        validate_body='ctx.set_output("validated", True)',
        run_body=(
            'ctx.set_output("connection", ctx.sap.connection_name)\n'
            '    session = ctx.sap.create_session()\n'
            '    session.start_transaction("IW21")'
        ),
    )
    resolver = InMemorySapConnectionResolver()
    runtime = SapRuntime(config=_sap_config(), connection_resolver=resolver)

    result = runtime.run_script(script_path)

    assert result.status is ExecutionStatus.SUCCESS
    assert result.outputs == {"validated": True, "connection": "prd"}
    assert resolver.resolved_modes == [SapConnectionMode.AUTO]
    assert resolver.connection.created_sessions[0].operations == [("start_transaction", "IW21")]


def test_runtime_includes_log_path_in_result(tmp_path: Path) -> None:
    script_path = tmp_path / "logged_script.py"
    logs_dir = tmp_path / "logs"
    _write_script(
        script_path,
        "logged_script",
        validate_body='ctx.set_output("validated", True)',
        run_body='ctx.set_output("ran", True)',
    )
    runtime = SapRuntime(config=SAPHiveConfig(logging=LoggingConfig(directory=logs_dir)))

    result = runtime.run_script(script_path, run_id="run-logs")

    assert result.status is ExecutionStatus.SUCCESS
    assert result.logs_path == logs_dir / "run-logs.log"
    assert result.logs_path.is_file()


def test_runtime_debug_log_includes_failure_details_and_traceback(tmp_path: Path) -> None:
    script_path = tmp_path / "debug_failure.py"
    logs_dir = tmp_path / "logs"
    _write_script(
        script_path,
        "debug_failure",
        validate_body='ctx.set_output("validated", True)',
        run_body='raise RuntimeError("boom")',
    )
    runtime = SapRuntime(
        config=SAPHiveConfig(logging=LoggingConfig(level="DEBUG", directory=logs_dir))
    )

    result = runtime.run_script(script_path, run_id="run-debug-failure")

    assert result.status is ExecutionStatus.FAILED
    assert result.logs_path is not None
    log_text = result.logs_path.read_text(encoding="utf-8")
    assert "SAPHive script execution crashed debug details" in log_text
    assert "error_type=builtins.RuntimeError" in log_text
    assert "outputs={'validated': True}" in log_text
    assert "Traceback (most recent call last)" in log_text
    assert 'raise RuntimeError("boom")' in log_text


def test_runtime_info_log_omits_failure_traceback(tmp_path: Path) -> None:
    script_path = tmp_path / "info_failure.py"
    logs_dir = tmp_path / "logs"
    _write_script(
        script_path,
        "info_failure",
        validate_body='ctx.set_output("validated", True)',
        run_body='raise RuntimeError("boom")',
    )
    runtime = SapRuntime(config=SAPHiveConfig(logging=LoggingConfig(directory=logs_dir)))

    result = runtime.run_script(script_path, run_id="run-info-failure")

    assert result.status is ExecutionStatus.FAILED
    assert result.logs_path is not None
    log_text = result.logs_path.read_text(encoding="utf-8")
    assert "SAPHive script execution crashed: boom" in log_text
    assert "Traceback (most recent call last)" not in log_text


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


def _sap_config() -> SAPHiveConfig:
    return SAPHiveConfig(
        sap=SapConfig(
            mode=SapConnectionMode.AUTO,
            connection="prd",
            connections={"prd": SapConnectionProfile(sap_logon_name="PRD", client="100")},
        )
    )
