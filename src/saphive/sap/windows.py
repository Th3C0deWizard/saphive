"""Windows SAP GUI Scripting boundary for SAPHive."""

import subprocess
import sys
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from importlib import import_module
from pathlib import Path
from typing import Any

from saphive.core.errors import SapConnectionError, SapGuiError, SapSessionError
from saphive.sap.auth import SapCredentials

SapGuiObjectFactory = Callable[[str], Any]
Sleep = Callable[[float], None]

SAP_GUI_START_TIMEOUT_SECONDS = 10.0
SAP_GUI_POLL_SECONDS = 0.5
SAP_LOGON_EXECUTABLE_CANDIDATES = (
    Path("C:/Program Files/SAP/FrontEnd/SAPgui/saplogon.exe"),
    Path("C:/Program Files (x86)/SAP/FrontEnd/SAPgui/saplogon.exe"),
)


@dataclass(frozen=True, slots=True)
class WindowsSapGuiClient:
    """Windows-only SAP GUI Scripting client boundary."""

    connection_name: str | None = None
    session_index: int = 0
    dispatch_factory: SapGuiObjectFactory | None = field(default=None, repr=False, compare=False)

    def attach_connection(
        self,
        connection_name: str,
        profile: Any,
    ) -> "WindowsSapConnection":
        """Attach to an existing SAP GUI connection matching a profile."""
        application = self._application(start_sap_logon=False)
        try:
            connection = _select_connection(application, profile)
        except SapConnectionError:
            raise
        except Exception as exc:
            raise SapConnectionError(
                "SAPHive could not connect to SAP GUI Scripting.",
                details={"connection": connection_name, "error": str(exc)},
            ) from exc

        return WindowsSapConnection(connection_name=connection_name, connection=connection)

    def open_connection(
        self,
        connection_name: str,
        profile: Any,
        credentials: SapCredentials,
    ) -> "WindowsSapConnection":
        """Open a new SAP Logon connection and authenticate with username/password."""
        application = self._application(start_sap_logon=True)
        try:
            connection = application.OpenConnection(profile.sap_logon_name, True)
            session = connection.Children(0)
            _login(session, profile, credentials)
        except Exception as exc:
            raise SapConnectionError(
                "SAPHive could not open SAP GUI connection.",
                details={"connection": connection_name, "error": str(exc)},
            ) from exc

        return WindowsSapConnection(connection_name=connection_name, connection=connection)

    def _application(self, *, start_sap_logon: bool) -> Any:
        dispatch = self.dispatch_factory or _load_dispatch_factory(
            start_sap_logon=start_sap_logon,
        )
        try:
            sap_gui = dispatch("SAPGUI")
            return getattr(sap_gui, "GetScriptingEngine", sap_gui)
        except SapConnectionError:
            raise
        except Exception as exc:
            raise SapConnectionError(
                "SAPHive could not access SAP GUI Scripting engine.",
                details={"error": str(exc)},
            ) from exc


@dataclass(frozen=True, slots=True)
class WindowsSapConnection:
    """Connection-scoped wrapper around a COM SAP GUI connection object."""

    connection_name: str
    connection: Any = field(repr=False)

    def list_sessions(self) -> tuple["WindowsSapSession", ...]:
        try:
            session_count = int(self.connection.Children.Count)
            return tuple(
                WindowsSapSession(session=self.connection.Children(index))
                for index in range(session_count)
            )
        except Exception as exc:
            raise SapSessionError(
                "SAPHive could not list SAP GUI sessions.",
                details={"connection": self.connection_name, "error": str(exc)},
            ) from exc

    def attach_session(self, index: int = 0) -> "WindowsSapSession":
        try:
            return WindowsSapSession(session=self.connection.Children(index))
        except Exception as exc:
            raise SapSessionError(
                "SAPHive could not attach to SAP GUI session.",
                details={
                    "connection": self.connection_name,
                    "session_index": index,
                    "error": str(exc),
                },
            ) from exc

    def create_session(self) -> "WindowsSapSession":
        try:
            before_count = int(self.connection.Children.Count)
            self.connection.Children(0).CreateSession()
            after_count = int(self.connection.Children.Count)
            session_index = (
                after_count - 1 if after_count > before_count else max(0, after_count - 1)
            )
            return self.attach_session(session_index)
        except Exception as exc:
            raise SapSessionError(
                "SAPHive could not create SAP GUI session.",
                details={"connection": self.connection_name, "error": str(exc)},
            ) from exc

    def active_session(self) -> "WindowsSapSession":
        return self.attach_session(0)


@dataclass(frozen=True, slots=True)
class WindowsSapSession:
    """Thin wrapper around a COM SAP GUI Scripting session object."""

    session: Any = field(repr=False)

    def start_transaction(self, transaction_code: str) -> None:
        try:
            self.session.StartTransaction(transaction_code)
        except Exception as exc:
            raise SapGuiError(
                "SAPHive could not start SAP transaction.",
                details={"transaction_code": transaction_code, "error": str(exc)},
            ) from exc

    def set_text(self, element_id: str, value: str) -> None:
        try:
            self.session.findById(element_id).Text = value
        except Exception as exc:
            raise SapGuiError(
                "SAPHive could not set SAP GUI element text.",
                details={"element_id": element_id, "error": str(exc)},
            ) from exc

    def press(self, element_id: str) -> None:
        try:
            self.session.findById(element_id).press()
        except Exception as exc:
            raise SapGuiError(
                "SAPHive could not press SAP GUI element.",
                details={"element_id": element_id, "error": str(exc)},
            ) from exc

    def get_text(self, element_id: str) -> str:
        try:
            value = self.session.findById(element_id).Text
        except Exception as exc:
            raise SapGuiError(
                "SAPHive could not read SAP GUI element text.",
                details={"element_id": element_id, "error": str(exc)},
            ) from exc

        return str(value)

    def status_bar_text(self) -> str:
        return self.get_text("wnd[0]/sbar")


def _load_dispatch_factory(
    *,
    start_sap_logon: bool = False,
    sap_logon_paths: tuple[Path, ...] = SAP_LOGON_EXECUTABLE_CANDIDATES,
    sleep: Sleep = time.sleep,
) -> SapGuiObjectFactory:
    if sys.platform != "win32":
        raise SapConnectionError(
            "SAP GUI Scripting requires Windows with SAP GUI installed.",
            details={"platform": sys.platform},
        )

    try:
        win32com_client = import_module("win32com.client")
    except ImportError as exc:
        raise SapConnectionError(
            "SAP GUI Scripting requires pywin32 on Windows.",
            details={"missing_dependency": "pywin32"},
        ) from exc

    def get_sap_gui_object(prog_id: str) -> Any:
        errors: dict[str, str] = {}
        try:
            return win32com_client.GetObject(prog_id)
        except Exception as get_object_error:
            errors["get_object_error"] = str(get_object_error)

        if start_sap_logon:
            start_path, start_error = _start_sap_logon(sap_logon_paths)
            if start_path is None:
                errors["sap_logon_start_error"] = start_error or "saplogon.exe was not found."
            else:
                errors["sap_logon_started"] = str(start_path)
                retry_error = _retry_get_sap_gui_object(
                    win32com_client,
                    prog_id,
                    sleep=sleep,
                )
                if not isinstance(retry_error, Exception):
                    return retry_error

                errors["get_object_after_start_error"] = str(retry_error)

        try:
            return win32com_client.Dispatch("Sapgui.ScriptingCtrl.1")
        except Exception as dispatch_error:
            errors["dispatch_error"] = str(dispatch_error)
            raise SapConnectionError(
                "SAPHive could not access SAP GUI Scripting engine.",
                details=errors,
            ) from dispatch_error

    return get_sap_gui_object


def _start_sap_logon(sap_logon_paths: tuple[Path, ...]) -> tuple[Path | None, str | None]:
    for path in sap_logon_paths:
        if not path.is_file():
            continue

        try:
            subprocess.Popen(
                [str(path)],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        except Exception as exc:
            return None, str(exc)

        return path, None

    return None, "saplogon.exe was not found in common SAP GUI install paths."


def _retry_get_sap_gui_object(
    win32com_client: Any,
    prog_id: str,
    *,
    sleep: Sleep,
) -> Any | Exception:
    attempts = max(1, int(SAP_GUI_START_TIMEOUT_SECONDS / SAP_GUI_POLL_SECONDS))
    last_error: Exception | None = None
    for _ in range(attempts):
        sleep(SAP_GUI_POLL_SECONDS)
        try:
            return win32com_client.GetObject(prog_id)
        except Exception as exc:
            last_error = exc

    return last_error or SapConnectionError("SAP GUI Scripting engine did not become available.")


def _select_connection(application: Any, profile: Any) -> Any:
    try:
        connection_count = int(application.Children.Count)
    except Exception as exc:
        raise SapConnectionError(
            "SAPHive could not inspect SAP GUI connections.",
            details={"error": str(exc)},
        ) from exc

    if connection_count == 0:
        raise SapConnectionError("No active SAP GUI connections were found.")

    for index in range(connection_count):
        connection = application.Children(index)
        if _connection_matches(connection, profile):
            return connection

    raise SapConnectionError(
        "Requested SAP GUI connection was not found.",
        details={"sap_logon_name": profile.sap_logon_name, "client": profile.client},
    )


def _connection_matches(connection: Any, profile: Any) -> bool:
    candidates = (
        getattr(connection, "Description", None),
        getattr(connection, "Name", None),
        getattr(connection, "SystemName", None),
    )
    if profile.sap_logon_name not in candidates:
        return False

    if profile.client is None:
        return True

    return bool(str(getattr(connection, "Client", profile.client)) == profile.client)


def _login(session: Any, profile: Any, credentials: SapCredentials) -> None:
    if profile.client is not None:
        session.findById("wnd[0]/usr/txtRSYST-MANDT").Text = profile.client

    session.findById("wnd[0]/usr/txtRSYST-BNAME").Text = credentials.username
    session.findById("wnd[0]/usr/pwdRSYST-BCODE").Text = credentials.password
    session.findById("wnd[0]/usr/txtRSYST-LANGU").Text = profile.language
    session.findById("wnd[0]/tbar[0]/btn[0]").press()
