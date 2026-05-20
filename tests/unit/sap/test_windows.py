import sys
from typing import Any

import pytest

from saphive import SapConnectionError, SapGuiError
from saphive.sap import WindowsSapGuiClient, WindowsSapSession


def test_windows_client_does_not_require_pywin32_until_connect() -> None:
    client = WindowsSapGuiClient(connection_name="PRD")

    assert client.connection_name == "PRD"


def test_windows_client_guards_non_windows_platform(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "platform", "linux")

    with pytest.raises(SapConnectionError, match="requires Windows"):
        WindowsSapGuiClient().connect()


def test_windows_client_wraps_dispatch_failures() -> None:
    def failing_dispatch(name: str) -> object:
        raise RuntimeError(f"{name} unavailable")

    with pytest.raises(SapConnectionError, match="could not connect") as exc_info:
        WindowsSapGuiClient(dispatch_factory=failing_dispatch).connect()

    assert exc_info.value.details["error"] == "SAPGUI unavailable"


def test_windows_client_selects_connection_and_session() -> None:
    session = FakeComSession()
    connection = FakeConnection(description="PRD", sessions=[session])
    application = FakeApplication(connections=[connection])

    def dispatch(name: str) -> FakeSapGui:
        assert name == "SAPGUI"
        return FakeSapGui(application=application)

    wrapped_session = WindowsSapGuiClient(
        connection_name="PRD",
        dispatch_factory=dispatch,
    ).connect()

    assert isinstance(wrapped_session, WindowsSapSession)
    wrapped_session.start_transaction("IW21")
    wrapped_session.set_text("wnd[0]/usr/ctxtQMART", "M1")
    wrapped_session.press("wnd[0]/tbar[0]/btn[11]")

    assert wrapped_session.get_text("wnd[0]/usr/ctxtQMART") == "M1"
    assert session.started_transactions == ["IW21"]
    assert session.elements["wnd[0]/tbar[0]/btn[11]"].pressed is True


def test_windows_client_raises_when_connection_name_is_missing() -> None:
    application = FakeApplication(connections=[FakeConnection(description="QAS", sessions=[])])

    def dispatch(name: str) -> FakeSapGui:
        return FakeSapGui(application=application)

    with pytest.raises(SapConnectionError, match="not found") as exc_info:
        WindowsSapGuiClient(connection_name="PRD", dispatch_factory=dispatch).connect()

    assert exc_info.value.details == {"connection_name": "PRD"}


def test_windows_session_wraps_gui_operation_failures() -> None:
    session = WindowsSapSession(session=FailingComSession())

    with pytest.raises(SapGuiError, match="set SAP GUI") as exc_info:
        session.set_text("missing", "value")

    assert exc_info.value.details["element_id"] == "missing"


class FakeSapGui:
    def __init__(self, application: "FakeApplication") -> None:
        self.GetScriptingEngine = application


class FakeApplication:
    def __init__(self, connections: list["FakeConnection"]) -> None:
        self.Children = FakeChildren(connections)


class FakeConnection:
    def __init__(self, description: str, sessions: list["FakeComSession"]) -> None:
        self.Description = description
        self.Children = FakeChildren(sessions)


class FakeChildren:
    def __init__(self, values: list[Any]) -> None:
        self._values = values
        self.Count = len(values)

    def __call__(self, index: int) -> Any:
        return self._values[index]


class FakeComSession:
    def __init__(self) -> None:
        self.elements: dict[str, FakeElement] = {}
        self.started_transactions: list[str] = []
        self.__dict__["StartTransaction"] = self._start_transaction
        self.__dict__["findById"] = self._find_by_id

    def _start_transaction(self, transaction_code: str) -> None:
        self.started_transactions.append(transaction_code)

    def _find_by_id(self, element_id: str) -> "FakeElement":
        element = self.elements.get(element_id)
        if element is None:
            element = FakeElement()
            self.elements[element_id] = element

        return element


class FailingComSession:
    def __init__(self) -> None:
        self.__dict__["findById"] = self._find_by_id

    def _find_by_id(self, element_id: str) -> object:
        raise RuntimeError(f"missing {element_id}")


class FakeElement:
    def __init__(self) -> None:
        self.Text = ""
        self.pressed = False

    def press(self) -> None:
        self.pressed = True
