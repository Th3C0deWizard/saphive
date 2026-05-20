import pytest
from tests.support.sap import InMemorySapClient, InMemorySapSession

from saphive import SapGuiPlaceholder, SapSessionError
from saphive.sap import SapClient, SapSession


def test_sap_placeholder_fails_without_configured_client() -> None:
    placeholder = SapGuiPlaceholder()

    with pytest.raises(SapSessionError, match="not been configured"):
        placeholder.connect()


def test_in_memory_sap_client_matches_protocols() -> None:
    client = InMemorySapClient()

    assert isinstance(client, SapClient)
    assert isinstance(client.connect(), SapSession)


def test_in_memory_sap_session_records_operations() -> None:
    session = InMemorySapSession(status_text="Saved")

    session.start_transaction("IW21")
    session.set_text("wnd[0]/usr/ctxtQMART", "M1")
    session.press("wnd[0]/tbar[0]/btn[11]")

    assert session.get_text("wnd[0]/usr/ctxtQMART") == "M1"
    assert session.status_bar_text() == "Saved"
    assert session.operations == [
        ("start_transaction", "IW21"),
        ("set_text", "wnd[0]/usr/ctxtQMART"),
        ("press", "wnd[0]/tbar[0]/btn[11]"),
        ("get_text", "wnd[0]/usr/ctxtQMART"),
        ("status_bar_text", "wnd[0]/sbar"),
    ]
