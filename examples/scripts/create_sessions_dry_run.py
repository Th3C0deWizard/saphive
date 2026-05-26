"""Dry-run example for running a bot in its own SAP GUI session."""

from saphive import SapContext

SCRIPT_NAME = "create_sessions"
DESCRIPTION = "Example that shows how to create a dedicated SAP GUI session"
VERSION = "0.1.0"
AUTHOR = "SAPHive Examples"

def validate(ctx: SapContext) -> None:
    pass

def run(ctx: SapContext) -> None:
    session = ctx.sap.create_session()
    session.start_transaction("IW32")
