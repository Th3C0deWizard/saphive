import re
from collections.abc import Callable
from pathlib import Path
from types import SimpleNamespace
from typing import Any, TypeVar

import pytest
from tests.support.sap import (
    InMemorySapConnection,
    InMemorySapConnectionResolver,
    InMemorySapSession,
)

from saphive import (
    ExecutionStatus,
    LoggingConfig,
    PathsConfig,
    SapCleanupMode,
    SapConfig,
    SapConnectionMode,
    SapConnectionProfile,
    SAPHiveConfig,
    SapRuntime,
)

T = TypeVar("T")


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
            'session = ctx.sap.create_session()\n'
            '    session.start_transaction("IW21")\n'
            '    ctx.set_output("status", session.status_bar_text())'
        ),
    )
    sap_session = InMemorySapSession(status_text="Notification created")
    sap_connection = InMemorySapConnection(session=sap_session)
    runtime = SapRuntime(sap=sap_connection)

    result = runtime.run_script(script_path)

    assert result.status is ExecutionStatus.SUCCESS
    assert result.outputs == {"validated": True, "status": "Notification created"}
    assert sap_connection.closed_created_sessions[0].operations == [
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
    assert resolver.connection.closed_created_sessions[0].operations == [
        ("start_transaction", "IW21")
    ]
    assert resolver.connection.cleanup_operations == ["close_created_sessions"]


def test_runtime_runs_script_cleanup_after_success(tmp_path: Path) -> None:
    script_path = tmp_path / "cleanup_success.py"
    _write_script(
        script_path,
        "cleanup_success",
        validate_body='ctx.set_output("validated", True)',
        run_body='ctx.set_output("ran", True)',
        cleanup_body='ctx.set_output("cleaned", True)',
    )

    result = SapRuntime().run_script(script_path)

    assert result.status is ExecutionStatus.SUCCESS
    assert result.outputs == {"validated": True, "ran": True, "cleaned": True}


def test_runtime_runs_script_cleanup_after_failure(tmp_path: Path) -> None:
    script_path = tmp_path / "cleanup_after_failure.py"
    _write_script(
        script_path,
        "cleanup_after_failure",
        validate_body='ctx.set_output("validated", True)',
        run_body='raise RuntimeError("boom")',
        cleanup_body='ctx.set_output("cleaned", True)',
    )

    result = SapRuntime().run_script(script_path)

    assert result.status is ExecutionStatus.FAILED
    assert result.error == "boom"
    assert result.outputs == {"validated": True, "cleaned": True}


def test_runtime_fails_when_cleanup_fails_after_success(tmp_path: Path) -> None:
    script_path = tmp_path / "cleanup_failure.py"
    _write_script(
        script_path,
        "cleanup_failure",
        validate_body='ctx.set_output("validated", True)',
        run_body='ctx.set_output("ran", True)',
        cleanup_body='raise RuntimeError("cleanup boom")',
    )

    result = SapRuntime().run_script(script_path)

    assert result.status is ExecutionStatus.FAILED
    assert result.error == "SAPHive script cleanup failed: cleanup boom"
    assert result.outputs == {"validated": True, "ran": True}


def test_runtime_connection_cleanup_respects_force_flag(tmp_path: Path) -> None:
    script_path = tmp_path / "connection_cleanup.py"
    _write_script(
        script_path,
        "connection_cleanup",
        validate_body='ctx.set_output("validated", True)',
        run_body='ctx.sap.create_session()',
    )
    connection = InMemorySapConnection(opened_by_saphive=False)
    runtime = SapRuntime(
        config=_sap_config(),
        sap_cleanup=SapCleanupMode.CONNECTION,
        sap=connection,
    )

    result = runtime.run_script(script_path)

    assert result.status is ExecutionStatus.SUCCESS
    assert connection.cleanup_operations == []

    forced_runtime = SapRuntime(
        config=_sap_config(),
        sap_cleanup=SapCleanupMode.CONNECTION,
        sap_cleanup_force=True,
        sap=connection,
    )
    forced_result = forced_runtime.run_script(script_path)

    assert forced_result.status is ExecutionStatus.SUCCESS
    assert connection.cleanup_operations == ["close_connection"]


def test_runtime_keeps_com_initialized_while_sap_script_runs(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    script_path = tmp_path / "com_guarded_sap.py"
    _write_script(
        script_path,
        "com_guarded_sap",
        validate_body='ctx.set_output("validated", True)',
        run_body=(
            'ctx.set_output("events_before_sap", tuple(ctx.sap.events))\n'
            '    ctx.sap.create_session()\n'
            '    ctx.set_output("events_after_sap", tuple(ctx.sap.events))'
        ),
    )
    events: list[str] = []

    def fake_import_module(name: str) -> object:
        assert name == "pythoncom"
        return SimpleNamespace(
            CoInitialize=lambda: events.append("init"),
            CoUninitialize=lambda: events.append("uninit"),
        )

    monkeypatch.setattr("saphive.sap.windows.sys.platform", "win32")
    monkeypatch.setattr("saphive.sap.windows.import_module", fake_import_module)
    runtime = SapRuntime(
        config=_sap_config(),
        connection_resolver=EventRecordingSapResolver(events),
    )

    result = runtime.run_script(script_path)

    assert result.status is ExecutionStatus.SUCCESS
    assert result.outputs["events_before_sap"] == ("init", "resolve")
    assert result.outputs["events_after_sap"] == ("init", "resolve", "sap")
    assert events == ["init", "resolve", "sap", "close_created_sessions", "uninit"]


def test_runtime_includes_log_path_in_result(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
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
    assert result.logs_path is not None
    assert result.logs_path.parent == logs_dir
    assert re.fullmatch(r"\d{8}T\d{6}_\d{6}Z_run-logs\.log", result.logs_path.name)
    assert result.logs_path.is_file()
    assert f"SAPHive log file: {result.logs_path}" in capsys.readouterr().out


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
    assert "error_type=saphive.core.errors.ScriptExecutionError" in log_text
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


def test_runtime_text_log_includes_extra_context(tmp_path: Path) -> None:
    script_path = tmp_path / "context_log.py"
    logs_dir = tmp_path / "logs"
    _write_script(
        script_path,
        "context_log",
        validate_body='ctx.set_output("validated", True)',
        run_body='ctx.logger.info("row event", extra={"item_id": "123", "row_index": 4})',
    )
    runtime = SapRuntime(config=SAPHiveConfig(logging=LoggingConfig(directory=logs_dir)))

    result = runtime.run_script(script_path, run_id="run-context-log")

    assert result.status is ExecutionStatus.SUCCESS
    assert result.logs_path is not None
    log_text = result.logs_path.read_text(encoding="utf-8")
    assert "row event" in log_text
    assert "item_id=123" in log_text
    assert "row_index=4" in log_text


def test_runtime_jsonl_log_includes_extra_context(tmp_path: Path) -> None:
    script_path = tmp_path / "json_log.py"
    logs_dir = tmp_path / "logs"
    _write_script(
        script_path,
        "json_log",
        validate_body='ctx.set_output("validated", True)',
        run_body='ctx.logger.info("row event", extra={"item_id": "123", "row_index": 4})',
    )
    runtime = SapRuntime(
        config=SAPHiveConfig(
            logging=LoggingConfig(directory=logs_dir, jsonl_enabled=True)
        )
    )

    result = runtime.run_script(script_path, run_id="run-json-log")

    assert result.status is ExecutionStatus.SUCCESS
    assert result.logs_path is not None
    log_text = result.logs_path.read_text(encoding="utf-8")
    assert '"message": "row event"' in log_text
    assert '"item_id": "123"' in log_text
    assert '"row_index": 4' in log_text


def test_runtime_fatal_error_runs_cleanup_and_sap_cleanup(tmp_path: Path) -> None:
    script_path = tmp_path / "fatal_error.py"
    _write_script(
        script_path,
        "fatal_error",
        validate_body='ctx.set_output("validated", True)',
        run_body=(
            'ctx.sap.create_session()\n'
            '    raise SapInfrastructureError("SAP session is corrupted")'
        ),
        cleanup_body='ctx.set_output("cleaned", True)',
        imports="from saphive import SapInfrastructureError",
    )
    sap_connection = InMemorySapConnection()
    runtime = SapRuntime(sap=sap_connection)

    result = runtime.run_script(script_path)

    assert result.status is ExecutionStatus.FAILED
    assert result.error == "SAP session is corrupted"
    assert result.outputs == {"validated": True, "cleaned": True}
    assert sap_connection.cleanup_operations == ["close_created_sessions"]


def test_runtime_context_exposes_com_guard(tmp_path: Path) -> None:
    script_path = tmp_path / "com_guard.py"
    _write_script(
        script_path,
        "com_guard",
        validate_body='ctx.set_output("validated", True)',
        run_body='ctx.set_output("guarded", ctx.com.run_with_com_guard(lambda: "ok"))',
    )

    result = SapRuntime().run_script(script_path)

    assert result.status is ExecutionStatus.SUCCESS
    assert result.outputs == {"validated": True, "guarded": "ok"}


def _write_script(
    path: Path,
    script_name: str,
    *,
    validate_body: str,
    run_body: str,
    cleanup_body: str | None = None,
    imports: str = "",
) -> None:
    cleanup_source = "" if cleanup_body is None else f"\ndef cleanup(ctx):\n    {cleanup_body}\n"
    path.write_text(
        f'''
{imports}

SCRIPT_NAME = "{script_name}"
DESCRIPTION = "Runtime test script."

def validate(ctx):
    {validate_body}

def run(ctx):
    {run_body}
{cleanup_source}
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


class EventRecordingSapResolver:
    def __init__(self, events: list[str]) -> None:
        self.events = events

    def resolve_connection(
        self,
        *,
        config: SAPHiveConfig,
        mode: SapConnectionMode | None = None,
        connection_name: str | None = None,
        auth_file: str | None = None,
        config_path: str | None = None,
        script_path: str | None = None,
    ) -> "EventRecordingSapConnection":
        self.events.append("resolve")
        return EventRecordingSapConnection(self.events)


class EventRecordingSapConnection:
    def __init__(self, events: list[str]) -> None:
        self.events = events
        self.session = InMemorySapSession()

    @property
    def connection_name(self) -> str:
        return "prd"

    def list_sessions(self) -> tuple[InMemorySapSession, ...]:
        self.events.append("sap")
        return (self.session,)

    def attach_session(self, index: int = 0) -> InMemorySapSession:
        self.events.append("sap")
        return self.session

    def create_session(self) -> InMemorySapSession:
        self.events.append("sap")
        return self.session

    def with_connection(self, callback: Callable[[Any], T]) -> T:
        return callback(self)

    def close_created_sessions(self) -> None:
        self.events.append("close_created_sessions")

    def close_connection(self, *, force: bool = False) -> None:
        self.events.append("close_connection")

    def close_application(self) -> None:
        self.events.append("close_application")
