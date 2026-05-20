"""Dry-run example for creating SAP maintenance notifications."""

from saphive import SapContext

SCRIPT_NAME = "create_sessions"
DESCRIPTION = "Example that shows ho to create new sessions"
VERSION = "0.1.0"
AUTHOR = "SAPHive Examples"

def validate(ctx: SapContext) -> None:
    pass

def run(ctx: SapContext) -> None:
    session = ctx.sap.create_session()
    session.start_transaction("IW32")
    session.session.StartTransaction("IW38")
