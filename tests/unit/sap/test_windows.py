import sys
from collections.abc import Callable
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from saphive import SapConnectionError, SapConnectionProfile, SapGuiError
from saphive.sap import WindowsSapGuiClient, WindowsSapSession
from saphive.sap.windows import _load_dispatch_factory


def test_windows_client_does_not_require_pywin32_until_connect() -> None:
    client = WindowsSapGuiClient(connection_name="PRD")

    assert client.connection_name == "PRD"


def test_windows_client_guards_non_windows_platform(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "platform", "linux")

    with pytest.raises(SapConnectionError, match="requires Windows"):
        WindowsSapGuiClient().attach_connection("PRD", SapConnectionProfile(sap_logon_name="PRD"))


def test_windows_client_wraps_dispatch_failures() -> None:
    def failing_dispatch(name: str) -> object:
        raise RuntimeError(f"{name} unavailable")

    with pytest.raises(SapConnectionError, match="could not access") as exc_info:
        WindowsSapGuiClient(dispatch_factory=failing_dispatch).attach_connection(
            "PRD",
            SapConnectionProfile(sap_logon_name="PRD"),
        )

    assert exc_info.value.details["error"] == "SAPGUI unavailable"


def test_windows_dispatch_factory_uses_sapgui_running_object(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[str] = []

    def get_object(name: str) -> object:
        calls.append(name)
        return object()

    def fake_import_module(name: str) -> object:
        assert name == "win32com.client"
        return SimpleNamespace(GetObject=get_object)

    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setattr("saphive.sap.windows.import_module", fake_import_module)

    factory = _load_dispatch_factory()

    assert factory("SAPGUI") is not None
    assert calls == ["SAPGUI"]


def test_windows_dispatch_factory_falls_back_to_scripting_control(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[str] = []
    scripting_control = object()

    def get_object(name: str) -> object:
        calls.append(f"get:{name}")
        raise RuntimeError("SAPGUI running object unavailable")

    def dispatch(name: str) -> object:
        calls.append(f"dispatch:{name}")
        return scripting_control

    def fake_import_module(name: str) -> object:
        assert name == "win32com.client"
        return SimpleNamespace(GetObject=get_object, Dispatch=dispatch)

    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setattr("saphive.sap.windows.import_module", fake_import_module)

    factory = _load_dispatch_factory()

    assert factory("SAPGUI") is scripting_control
    assert calls == ["get:SAPGUI", "dispatch:Sapgui.ScriptingCtrl.1"]


def test_windows_dispatch_factory_starts_sap_logon_before_retry(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[str] = []
    sap_gui = object()
    sap_logon_path = tmp_path / "saplogon.exe"
    sap_logon_path.write_text("", encoding="utf-8")

    def get_object(name: str) -> object:
        calls.append(f"get:{name}")
        if calls.count(f"get:{name}") == 1:
            raise RuntimeError("SAPGUI running object unavailable")

        return sap_gui

    def dispatch(name: str) -> object:
        calls.append(f"dispatch:{name}")
        raise RuntimeError("scripting control unavailable")

    def fake_import_module(name: str) -> object:
        assert name == "win32com.client"
        return SimpleNamespace(GetObject=get_object, Dispatch=dispatch)

    popen_calls: list[list[str]] = []

    def fake_popen(args: list[str], **kwargs: object) -> object:
        popen_calls.append(args)
        return object()

    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setattr("saphive.sap.windows.import_module", fake_import_module)
    monkeypatch.setattr("saphive.sap.windows.subprocess.Popen", fake_popen)

    factory = _load_dispatch_factory(
        start_sap_logon=True,
        sap_logon_paths=(sap_logon_path,),
        sleep=lambda _: None,
    )

    assert factory("SAPGUI") is sap_gui
    assert popen_calls == [[str(sap_logon_path)]]
    assert calls == ["get:SAPGUI", "get:SAPGUI"]


def test_windows_client_selects_connection_and_session() -> None:
    session = FakeComSession()
    com_connection = FakeConnection(description="PRD", sessions=[session])
    application = FakeApplication(connections=[com_connection])

    def dispatch(name: str) -> FakeSapGui:
        assert name == "SAPGUI"
        return FakeSapGui(application=application)

    sap_connection = WindowsSapGuiClient(dispatch_factory=dispatch).attach_connection(
        "prd",
        SapConnectionProfile(sap_logon_name="PRD"),
    )
    wrapped_session = sap_connection.attach_session()

    assert isinstance(wrapped_session, WindowsSapSession)
    wrapped_session.start_transaction("IW21")
    wrapped_session.set_text("wnd[0]/usr/ctxtQMART", "M1")
    wrapped_session.press("wnd[0]/tbar[0]/btn[11]")

    assert wrapped_session.get_text("wnd[0]/usr/ctxtQMART") == "M1"
    assert session.started_transactions == ["IW21"]
    assert session.elements["wnd[0]/tbar[0]/btn[11]"].pressed is True


def test_windows_client_accepts_callable_scripting_engine() -> None:
    session = FakeComSession()
    com_connection = FakeConnection(description="PRD", sessions=[session])
    application = FakeApplication(connections=[com_connection])

    def dispatch(name: str) -> FakeSapGuiWithCallableEngine:
        assert name == "SAPGUI"
        return FakeSapGuiWithCallableEngine(application=application)

    sap_connection = WindowsSapGuiClient(dispatch_factory=dispatch).attach_connection(
        "prd",
        SapConnectionProfile(sap_logon_name="PRD"),
    )

    assert sap_connection.with_connection(lambda connection: connection.Description) == "PRD"


def test_windows_client_does_not_call_application_like_scripting_engine() -> None:
    session = FakeComSession()
    com_connection = FakeConnection(description="PRD", sessions=[session])
    application = FakeCallableApplication(connections=[com_connection])

    def dispatch(name: str) -> FakeSapGui:
        assert name == "SAPGUI"
        return FakeSapGui(application=application)

    sap_connection = WindowsSapGuiClient(dispatch_factory=dispatch).attach_connection(
        "prd",
        SapConnectionProfile(sap_logon_name="PRD"),
    )

    assert sap_connection.with_connection(lambda connection: connection.Description) == "PRD"
    assert application.called is False


def test_windows_connection_normal_operation_does_not_initialize_com(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = FakeComSession()
    com_connection = FakeConnection(description="PRD", sessions=[session])
    application = FakeApplication(connections=[com_connection])

    def dispatch(name: str) -> FakeSapGui:
        assert name == "SAPGUI"
        return FakeSapGui(application=application)

    def fail_import_module(name: str) -> object:
        raise AssertionError(f"unexpected import: {name}")

    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setattr("saphive.sap.windows.import_module", fail_import_module)
    sap_connection = WindowsSapGuiClient(dispatch_factory=dispatch).attach_connection(
        "prd",
        SapConnectionProfile(sap_logon_name="PRD"),
    )

    assert sap_connection.with_connection(lambda connection: connection.Description) == "PRD"
    assert isinstance(sap_connection.create_session(), WindowsSapSession)


def test_windows_connection_waits_for_initial_session_before_create(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = FakeComSession()
    com_connection = FakeConnection(description="PRD", sessions=[session])
    com_connection.Children = DelayedChildren([session], failures=1)
    application = FakeApplication(connections=[com_connection])

    def dispatch(name: str) -> FakeSapGui:
        assert name == "SAPGUI"
        return FakeSapGui(application=application)

    sleep_calls: list[float] = []

    monkeypatch.setattr("saphive.sap.windows.time.sleep", sleep_calls.append)
    sap_connection = WindowsSapGuiClient(dispatch_factory=dispatch).attach_connection(
        "prd",
        SapConnectionProfile(sap_logon_name="PRD"),
    )

    assert isinstance(sap_connection.create_session(), WindowsSapSession)
    assert session.created_sessions == 1
    assert sleep_calls == [0.5]


def test_windows_connection_does_not_track_session_when_create_does_not_increase_count() -> None:
    session = FakeComSession()
    com_connection = FakeConnection(description="PRD", sessions=[session])
    application = FakeApplication(connections=[com_connection])

    def dispatch(name: str) -> FakeSapGui:
        assert name == "SAPGUI"
        return FakeSapGui(application=application)

    sap_connection = WindowsSapGuiClient(dispatch_factory=dispatch).attach_connection(
        "prd",
        SapConnectionProfile(sap_logon_name="PRD"),
    )

    wrapped_session = sap_connection.create_session()
    sap_connection.close_created_sessions()

    assert wrapped_session.session is session
    assert session.created_sessions == 1
    assert session.closed_sessions == 0


def test_windows_connection_closes_only_session_created_by_create_session() -> None:
    com_connection = FakeConnection(description="PRD", sessions=[])
    initial_session = GrowingComSession(com_connection.Children)
    com_connection.Children._values.append(initial_session)
    com_connection.Children.Count = 1
    application = FakeApplication(connections=[com_connection])

    def dispatch(name: str) -> FakeSapGui:
        assert name == "SAPGUI"
        return FakeSapGui(application=application)

    sap_connection = WindowsSapGuiClient(dispatch_factory=dispatch).attach_connection(
        "prd",
        SapConnectionProfile(sap_logon_name="PRD"),
    )

    created_session = sap_connection.create_session().session
    sap_connection.close_created_sessions()

    assert initial_session.created_sessions == 1
    assert initial_session.closed_sessions == 0
    assert created_session.closed_sessions == 1


def test_windows_connection_refreshes_connection_without_sessions_before_create() -> None:
    stale_connection = FakeConnection(description="PRD", sessions=[])
    fresh_session = FakeComSession()
    fresh_connection = FakeConnection(description="PRD", sessions=[fresh_session])
    applications = [
        FakeApplication(connections=[stale_connection]),
        FakeApplication(connections=[fresh_connection]),
    ]

    def dispatch(name: str) -> FakeSapGui:
        assert name == "SAPGUI"
        return FakeSapGui(application=applications.pop(0))

    sap_connection = WindowsSapGuiClient(dispatch_factory=dispatch).attach_connection(
        "prd",
        SapConnectionProfile(sap_logon_name="PRD"),
    )

    wrapped_session = sap_connection.create_session()

    assert isinstance(wrapped_session, WindowsSapSession)
    assert fresh_session.created_sessions == 1
    assert applications == []


def test_windows_opened_connection_uses_initial_session_when_connection_disappears() -> None:
    initial_session = FakeComSession()
    opened_connection = FakeConnection(description="PRD", sessions=[initial_session])
    applications = [
        FakeOpenApplication(connections=[opened_connection], opened_connection=opened_connection),
        FakeApplication(connections=[]),
    ]

    def dispatch(name: str) -> FakeApplication:
        assert name == "SAPGUI"
        return applications.pop(0)

    sap_connection = WindowsSapGuiClient(dispatch_factory=dispatch).open_connection(
        "prd",
        SapConnectionProfile(sap_logon_name="PRD", client="300", language="ES"),
        SimpleNamespace(username="INV10018", password="secret"),
    )
    opened_connection.Children = FakeChildren([])

    wrapped_session = sap_connection.create_session()

    assert wrapped_session.session is initial_session
    assert applications == []


def test_windows_recovery_keeps_usable_session_when_connection_disappears() -> None:
    initial_session = FakeComSession()
    opened_connection = FakeConnection(description="PRD", sessions=[initial_session])
    applications = [
        FakeOpenApplication(connections=[opened_connection], opened_connection=opened_connection),
        FakeApplication(connections=[]),
        FakeApplication(connections=[]),
    ]

    def dispatch(name: str) -> FakeApplication:
        assert name == "SAPGUI"
        return applications.pop(0)

    sap_connection = WindowsSapGuiClient(dispatch_factory=dispatch).open_connection(
        "prd",
        SapConnectionProfile(sap_logon_name="PRD", client="300", language="ES"),
        SimpleNamespace(username="INV10018", password="secret"),
    )
    opened_connection.Children = FakeChildren([])
    wrapped_session = sap_connection.create_session()

    sap_connection.recover_context_after_external_com()

    assert wrapped_session.session is initial_session
    assert applications == []


def test_windows_connection_lazily_initializes_com_after_uninitialize(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    events: list[str] = []
    initialized = False
    session = FakeComSession()
    com_connection = CoInitializeRequiredConnection(
        description="PRD",
        sessions=[session],
        initialized=lambda: initialized,
    )
    application = FakeApplication(connections=[com_connection])

    def dispatch(name: str) -> FakeSapGui:
        assert name == "SAPGUI"
        return FakeSapGui(application=application)

    def co_initialize() -> None:
        nonlocal initialized
        initialized = True
        events.append("init")

    def co_uninitialize() -> None:
        nonlocal initialized
        initialized = False
        events.append("uninit")

    def fake_import_module(name: str) -> object:
        assert name == "pythoncom"
        return SimpleNamespace(CoInitialize=co_initialize, CoUninitialize=co_uninitialize)

    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setattr("saphive.sap.windows.import_module", fake_import_module)
    sap_connection = WindowsSapGuiClient(dispatch_factory=dispatch).attach_connection(
        "prd",
        SapConnectionProfile(sap_logon_name="PRD"),
    )

    assert isinstance(sap_connection.create_session(), WindowsSapSession)
    assert session.created_sessions == 1
    assert events == ["init", "uninit"]


def test_windows_connection_refreshes_stale_com_proxy_before_creating_session() -> None:
    stale_connection = StaleConnection(description="PRD")
    fresh_session = FakeComSession()
    fresh_connection = FakeConnection(description="PRD", sessions=[fresh_session])
    applications = [
        FakeApplication(connections=[stale_connection]),
        FakeApplication(connections=[fresh_connection]),
    ]

    def dispatch(name: str) -> FakeSapGui:
        assert name == "SAPGUI"
        return FakeSapGui(application=applications.pop(0))

    sap_connection = WindowsSapGuiClient(dispatch_factory=dispatch).attach_connection(
        "prd",
        SapConnectionProfile(sap_logon_name="PRD"),
    )

    wrapped_session = sap_connection.create_session()

    assert isinstance(wrapped_session, WindowsSapSession)
    assert fresh_session.created_sessions == 1
    assert applications == []


def test_windows_connection_refreshes_disconnected_com_proxy_before_creating_session() -> None:
    disconnected_connection = DisconnectedConnection(description="PRD")
    fresh_session = FakeComSession()
    fresh_connection = FakeConnection(description="PRD", sessions=[fresh_session])
    applications = [
        FakeApplication(connections=[disconnected_connection]),
        FakeApplication(connections=[fresh_connection]),
    ]

    def dispatch(name: str) -> FakeSapGui:
        assert name == "SAPGUI"
        return FakeSapGui(application=applications.pop(0))

    sap_connection = WindowsSapGuiClient(dispatch_factory=dispatch).attach_connection(
        "prd",
        SapConnectionProfile(sap_logon_name="PRD"),
    )

    wrapped_session = sap_connection.create_session()

    assert isinstance(wrapped_session, WindowsSapSession)
    assert fresh_session.created_sessions == 1
    assert applications == []


def test_windows_session_refreshes_stale_raw_session_proxy() -> None:
    stale_session = StaleSession()
    fresh_session = FakeComSession()
    com_connection = FakeConnection(description="PRD", sessions=[stale_session])
    application = FakeApplication(connections=[com_connection])

    def dispatch(name: str) -> FakeSapGui:
        assert name == "SAPGUI"
        return FakeSapGui(application=application)

    sap_connection = WindowsSapGuiClient(dispatch_factory=dispatch).attach_connection(
        "prd",
        SapConnectionProfile(sap_logon_name="PRD"),
    )
    wrapped_session = sap_connection.attach_session()
    com_connection.Children._values[0] = fresh_session

    wrapped_session.start_transaction("IW21")

    assert fresh_session.started_transactions == ["IW21"]


def test_windows_session_refreshes_unavailable_raw_session_proxy() -> None:
    unavailable_session = UnavailableSession()
    fresh_session = FakeComSession()
    com_connection = FakeConnection(description="PRD", sessions=[unavailable_session])
    application = FakeApplication(connections=[com_connection])

    def dispatch(name: str) -> FakeSapGui:
        assert name == "SAPGUI"
        return FakeSapGui(application=application)

    sap_connection = WindowsSapGuiClient(dispatch_factory=dispatch).attach_connection(
        "prd",
        SapConnectionProfile(sap_logon_name="PRD"),
    )
    wrapped_session = sap_connection.attach_session()
    com_connection.Children._values[0] = fresh_session

    wrapped_session.start_transaction("IW41")

    assert fresh_session.started_transactions == ["IW41"]


def test_windows_connection_recovers_sessions_after_external_com() -> None:
    original_session = FakeComSession()
    fresh_session = FakeComSession()
    com_connection = FakeConnection(description="PRD", sessions=[original_session])
    application = FakeApplication(connections=[com_connection])

    def dispatch(name: str) -> FakeSapGui:
        assert name == "SAPGUI"
        return FakeSapGui(application=application)

    sap_connection = WindowsSapGuiClient(dispatch_factory=dispatch).attach_connection(
        "prd",
        SapConnectionProfile(sap_logon_name="PRD"),
    )
    wrapped_session = sap_connection.attach_session()
    com_connection.Children._values[0] = fresh_session

    sap_connection.recover_context_after_external_com()
    wrapped_session.start_transaction("IW21")

    assert original_session.started_transactions == []
    assert fresh_session.started_transactions == ["IW21"]


def test_windows_client_raises_when_connection_name_is_missing() -> None:
    application = FakeApplication(connections=[FakeConnection(description="QAS", sessions=[])])

    def dispatch(name: str) -> FakeSapGui:
        return FakeSapGui(application=application)

    with pytest.raises(SapConnectionError, match="not found") as exc_info:
        WindowsSapGuiClient(dispatch_factory=dispatch).attach_connection(
            "prd",
            SapConnectionProfile(sap_logon_name="PRD"),
        )

    assert exc_info.value.details == {"sap_logon_name": "PRD", "client": None}


def test_windows_session_wraps_gui_operation_failures() -> None:
    session = WindowsSapSession(session=FailingComSession())

    with pytest.raises(SapGuiError, match="set SAP GUI") as exc_info:
        session.set_text("missing", "value")

    assert exc_info.value.details["element_id"] == "missing"


class FakeSapGui:
    def __init__(self, application: "FakeApplication") -> None:
        self.GetScriptingEngine = application


class FakeSapGuiWithCallableEngine:
    def __init__(self, application: "FakeApplication") -> None:
        self.GetScriptingEngine = lambda: application


class FakeApplication:
    def __init__(self, connections: list[Any]) -> None:
        self.Children = FakeChildren(connections)


class FakeCallableApplication(FakeApplication):
    def __init__(self, connections: list[Any]) -> None:
        super().__init__(connections)
        self.called = False

    def __call__(self) -> object:
        self.called = True
        raise RuntimeError("application object must not be called")


class FakeOpenApplication(FakeApplication):
    def __init__(self, connections: list[Any], opened_connection: "FakeConnection") -> None:
        super().__init__(connections)
        self.opened_connection = opened_connection
        self.OpenConnection = self._open_connection

    def _open_connection(self, name: str, sync: bool) -> "FakeConnection":
        assert name == "PRD"
        assert sync is True
        return self.opened_connection


class FakeConnection:
    def __init__(self, description: str, sessions: list["FakeComSession"]) -> None:
        self.Description = description
        self.Children = FakeChildren(sessions)


class StaleConnection:
    def __init__(self, description: str) -> None:
        self.Description = description

    def __getattr__(self, name: str) -> object:
        if name == "Children":
            raise AttributeError("<unknown>.Children")

        raise AttributeError(name)


class DisconnectedConnection:
    def __init__(self, description: str) -> None:
        self.Description = description

    def __getattr__(self, name: str) -> object:
        if name == "Children":
            raise RuntimeError("(-2147220995, 'El objeto no está conectado al servidor')")

        raise AttributeError(name)


class StaleSession:
    def __getattr__(self, name: str) -> object:
        if name in {"findById", "StartTransaction", "CloseSession"}:
            raise AttributeError(f"<unknown>.{name}")

        raise AttributeError(name)


class UnavailableSession:
    def __init__(self) -> None:
        self.__dict__["findById"] = self._find_by_id

    def _find_by_id(self, element_id: str) -> object:
        raise RuntimeError(
            "(-2147418094, 'El destinatario (servidor [no una aplicación de servidor]) "
            "no está disponible ni presente; las conexiones no son válidas. "
            "La llamada no se ejecutó.', None, None)"
        )


class CoInitializeRequiredConnection:
    def __init__(
        self,
        description: str,
        sessions: list["FakeComSession"],
        initialized: Callable[[], bool],
    ) -> None:
        self.Description = description
        self._children = FakeChildren(sessions)
        self._initialized = initialized

    def __getattr__(self, name: str) -> object:
        if name != "Children":
            raise AttributeError(name)

        if not self._initialized():
            raise RuntimeError("No se ha llamado a CoInitialize.")

        return self._children


class FakeChildren:
    def __init__(self, values: list[Any]) -> None:
        self._values = values
        self.Count = len(values)

    def __call__(self, index: int) -> Any:
        return self._values[index]


class DelayedChildren(FakeChildren):
    def __init__(self, values: list[Any], failures: int) -> None:
        super().__init__(values)
        self.failures = failures

    def __call__(self, index: int) -> Any:
        if self.failures > 0:
            self.failures -= 1
            raise RuntimeError(
                "(614, 'sapfewse', 'The enumerator of the collection cannot find "
                "an element with the specified index.')"
            )
        return super().__call__(index)


class FakeComSession:
    def __init__(self) -> None:
        self.elements: dict[str, FakeElement] = {}
        self.started_transactions: list[str] = []
        self.created_sessions = 0
        self.closed_sessions = 0
        self.__dict__["StartTransaction"] = self._start_transaction
        self.__dict__["findById"] = self._find_by_id
        self.__dict__["CreateSession"] = self._create_session
        self.__dict__["CloseSession"] = self._close_session

    def _start_transaction(self, transaction_code: str) -> None:
        self.started_transactions.append(transaction_code)

    def _create_session(self) -> None:
        self.created_sessions += 1

    def _close_session(self) -> None:
        self.closed_sessions += 1

    def _find_by_id(self, element_id: str) -> "FakeElement":
        element = self.elements.get(element_id)
        if element is None:
            element = FakeElement()
            self.elements[element_id] = element

        return element


class GrowingComSession(FakeComSession):
    def __init__(self, children: FakeChildren) -> None:
        super().__init__()
        self.children = children

    def _create_session(self) -> None:
        super()._create_session()
        self.children._values.append(FakeComSession())
        self.children.Count = len(self.children._values)


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
