"""Dry-run example for running a bot in its own SAP GUI session."""

from pydantic import BaseModel

from saphive import SapContext, bot


class CreateSessionsInput(BaseModel):
    transaction: str = "IW32"


class CreateSessionsOutput(BaseModel):
    transaction: str


@bot(
    name="create_sessions",
    description="Example that shows how to create a dedicated SAP GUI session",
    input_model=CreateSessionsInput,
    output_model=CreateSessionsOutput,
    version="0.2.0",
    author="SAPHive Examples",
)
def run(ctx: SapContext, data: CreateSessionsInput) -> CreateSessionsOutput:
    session = ctx.sap.create_session()
    session.start_transaction(data.transaction)
    return CreateSessionsOutput(transaction=data.transaction)
