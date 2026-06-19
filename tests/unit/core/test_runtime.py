from collections.abc import Callable
from pathlib import Path

from pydantic import BaseModel
from tests.support.sap import (
    InMemorySapConnection,
    InMemorySapConnectionResolver,
    InMemorySapSession,
)

from saphive import (
    Bot,
    ExecutionStatus,
    PathsConfig,
    SapCleanupMode,
    SapConfig,
    SapConnectionMode,
    SapConnectionProfile,
    SapContext,
    SAPHiveConfig,
    SapRuntime,
    ScriptExecutionError,
    ScriptValidationError,
)


class Input(BaseModel):
    value: str = "ok"


class Output(BaseModel):
    result: str


def test_runtime_validate_bot_runs_input_and_bot_validation_only() -> None:
    def validate(ctx: SapContext) -> None:
        ctx.set_output("validated", ctx.inputs["value"])

    instance = _bot(validate=validate)

    result = SapRuntime().validate_bot(instance, inputs={"value": "4000001"}, run_id="run-validate")

    assert result.status is ExecutionStatus.SUCCESS
    assert result.script_name == "test_bot"
    assert result.run_id == "run-validate"
    assert result.outputs == {"validated": "4000001"}


def test_runtime_run_bot_runs_programmatic_bot() -> None:
    result = SapRuntime().run_bot(_bot(), inputs={"value": "done"}, run_id="run-full")

    assert result.status is ExecutionStatus.SUCCESS
    assert result.outputs == {"result": "done"}


def test_runtime_run_bot_loads_file_bot(tmp_path: Path) -> None:
    script_path = tmp_path / "file_bot.py"
    _write_bot(script_path, "file_bot", run_body='return Output(result=data.value + "!")')

    result = SapRuntime().run_bot(script_path, inputs={"value": "hello"})

    assert result.status is ExecutionStatus.SUCCESS
    assert result.script_name == "file_bot"
    assert result.outputs == {"result": "hello!"}


def test_runtime_loads_named_bot_from_configured_paths(tmp_path: Path) -> None:
    _write_bot(tmp_path / "named_bot.py", "named_bot")
    runtime = SapRuntime(config=SAPHiveConfig(paths=PathsConfig(scripts=(tmp_path,))))

    result = runtime.run_bot("named_bot", inputs={"value": "loaded"})

    assert result.status is ExecutionStatus.SUCCESS
    assert result.outputs == {"result": "loaded"}


def test_runtime_returns_validation_failed_result_for_invalid_input() -> None:
    result = SapRuntime().run_bot(_bot(), inputs={"value": 1})

    assert result.status is ExecutionStatus.VALIDATION_FAILED
    assert result.error == "SAPHive bot input validation failed."


def test_runtime_returns_validation_failed_result_from_bot_validate() -> None:
    def validate(ctx: SapContext) -> None:
        raise ScriptValidationError("Input file is missing")

    result = SapRuntime().run_bot(_bot(validate=validate))

    assert result.status is ExecutionStatus.VALIDATION_FAILED
    assert result.error == "Input file is missing"


def test_runtime_returns_failed_result_for_execution_error() -> None:
    def run(ctx: SapContext, data: Input) -> Output:
        raise ScriptExecutionError("SAP transaction failed")

    result = SapRuntime().run_bot(_bot(run=run))

    assert result.status is ExecutionStatus.FAILED
    assert result.error == "SAP transaction failed"


def test_runtime_context_uses_injected_sap_client() -> None:
    def run(ctx: SapContext, data: Input) -> Output:
        session = ctx.sap.create_session()
        session.start_transaction("IW21")
        return Output(result=session.status_bar_text())

    sap_session = InMemorySapSession(status_text="Notification created")
    sap_connection = InMemorySapConnection(session=sap_session)
    runtime = SapRuntime(sap=sap_connection)

    result = runtime.run_bot(_bot(run=run))

    assert result.status is ExecutionStatus.SUCCESS
    assert result.outputs == {"result": "Notification created"}
    assert sap_connection.closed_created_sessions[0].operations == [
        ("start_transaction", "IW21"),
        ("status_bar_text", "wnd[0]/sbar"),
    ]


def test_runtime_does_not_resolve_sap_when_validation_fails() -> None:
    def validate(ctx: SapContext) -> None:
        raise ScriptValidationError("bad input")

    resolver = InMemorySapConnectionResolver()
    runtime = SapRuntime(config=_sap_config(), connection_resolver=resolver)

    result = runtime.run_bot(_bot(validate=validate))

    assert result.status is ExecutionStatus.VALIDATION_FAILED
    assert resolver.resolved_modes == []


def test_runtime_resolves_sap_after_validation_for_run() -> None:
    def run(ctx: SapContext, data: Input) -> Output:
        ctx.set_output("connection", ctx.sap.connection_name)
        session = ctx.sap.create_session()
        session.start_transaction("IW21")
        return Output(result="ran")

    resolver = InMemorySapConnectionResolver()
    runtime = SapRuntime(config=_sap_config(), connection_resolver=resolver)

    result = runtime.run_bot(_bot(run=run))

    assert result.status is ExecutionStatus.SUCCESS
    assert result.outputs == {"connection": "prd", "result": "ran"}
    assert resolver.resolved_modes == [SapConnectionMode.AUTO]
    assert resolver.connection.closed_created_sessions[0].operations == [
        ("start_transaction", "IW21")
    ]
    assert resolver.connection.cleanup_operations == ["close_created_sessions"]


def test_runtime_honors_sap_cleanup_none() -> None:
    def run(ctx: SapContext, data: Input) -> Output:
        ctx.sap.create_session()
        return Output(result="ran")

    sap_connection = InMemorySapConnection()
    runtime = SapRuntime(sap=sap_connection, sap_cleanup=SapCleanupMode.NONE)

    result = runtime.run_bot(_bot(run=run))

    assert result.status is ExecutionStatus.SUCCESS
    assert sap_connection.cleanup_operations == []


def _bot(
    *,
    run: Callable[[SapContext, Input], Output] | None = None,
    validate: Callable[[SapContext], None] | None = None,
) -> Bot:
    return Bot(
        name="test_bot",
        description="Runtime test bot.",
        input_model=Input,
        output_model=Output,
        run=run or _run,
        validate=validate,
    )


def _run(ctx: SapContext, data: Input) -> Output:
    return Output(result=data.value)


def _sap_config() -> SAPHiveConfig:
    return SAPHiveConfig(
        sap=SapConfig(
            mode=SapConnectionMode.AUTO,
            connection="prd",
            connections={
                "prd": SapConnectionProfile(
                    sap_logon_name="PRD",
                    client="100",
                    language="EN",
                )
            },
        )
    )


def _write_bot(
    path: Path,
    bot_name: str,
    *,
    run_body: str = "return Output(result=data.value)",
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
    description="Runtime test bot.",
    input_model=Input,
    output_model=Output,
    version="0.1.0",
)
def run(ctx, data):
    {run_body}
'''.strip(),
        encoding="utf-8",
    )
