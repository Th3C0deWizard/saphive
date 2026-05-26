"""Windows SAP GUI Scripting boundary for SAPHive."""

import subprocess
import sys
import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager, suppress
from dataclasses import dataclass, field
from importlib import import_module
from pathlib import Path
from typing import Any, TypeVar

from saphive.core.com import ComRuntime
from saphive.core.errors import SapConnectionError, SapGuiError, SapSessionError
from saphive.sap.auth import SapCredentials

SapGuiObjectFactory = Callable[[str], Any]
Sleep = Callable[[float], None]
T = TypeVar("T")

SAP_GUI_START_TIMEOUT_SECONDS = 10.0
SAP_GUI_POLL_SECONDS = 0.5
SAP_SESSION_CREATE_TIMEOUT_SECONDS = 10.0
SAP_LOGON_EXECUTABLE_CANDIDATES = (
    Path("C:/Program Files/SAP/FrontEnd/SAPgui/saplogon.exe"),
    Path("C:/Program Files (x86)/SAP/FrontEnd/SAPgui/saplogon.exe"),
)


@contextmanager
def sap_com_initialized() -> Iterator[ComRuntime]:
    """Keep COM initialized on the current thread for SAP GUI automation."""
    if sys.platform != "win32":
        yield ComRuntime(enabled=False)
        return

    try:
        pythoncom = import_module("pythoncom")
    except ImportError as exc:
        raise SapConnectionError(
            "SAP GUI Scripting requires pywin32 on Windows.",
            details={"missing_dependency": "pywin32"},
        ) from exc

    try:
        pythoncom.CoInitialize()
    except Exception as exc:
        raise SapConnectionError(
            "SAPHive could not initialize Windows COM for SAP GUI Scripting.",
            details={"error": str(exc)},
        ) from exc

    try:
        yield ComRuntime(enabled=True)
    finally:
        with suppress(Exception):
            pythoncom.CoUninitialize()


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

        return WindowsSapConnection(
            connection_name=connection_name,
            connection=connection,
            client=self,
            profile=profile,
            opened_by_saphive=False,
        )

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
            session = _wait_for_connection_child(connection, 0)
            _login(session, profile, credentials)
            _wait_for_session_ready(session)
        except Exception as exc:
            raise SapConnectionError(
                "SAPHive could not open SAP GUI connection.",
                details={"connection": connection_name, "error": str(exc)},
            ) from exc

        return WindowsSapConnection(
            connection_name=connection_name,
            connection=connection,
            client=self,
            profile=profile,
            opened_by_saphive=True,
            initial_session=session,
        )

    def _application(self, *, start_sap_logon: bool) -> Any:
        dispatch = self.dispatch_factory or _load_dispatch_factory(
            start_sap_logon=start_sap_logon,
        )
        try:
            sap_gui = dispatch("SAPGUI")
            return _resolve_sap_application(sap_gui)
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
    client: WindowsSapGuiClient | None = field(default=None, repr=False, compare=False)
    profile: Any = field(default=None, repr=False, compare=False)
    opened_by_saphive: bool = False
    initial_session: Any | None = field(default=None, repr=False, compare=False)
    created_sessions: list["WindowsSapSession"] = field(default_factory=list, repr=False)

    def list_sessions(self) -> tuple["WindowsSapSession", ...]:
        try:
            return self.with_connection(
                lambda connection: tuple(
                    self._wrap_session(connection.Children(index), index)
                    for index in range(int(connection.Children.Count))
                )
            )
        except Exception as exc:
            raise SapSessionError(
                "SAPHive could not list SAP GUI sessions.",
                details={"connection": self.connection_name, "error": str(exc)},
            ) from exc

    def attach_session(self, index: int = 0) -> "WindowsSapSession":
        try:
            return self.with_connection(
                lambda connection: self._wrap_session(connection.Children(index), index)
            )
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
            return self.with_connection(self._create_session)
        except Exception as exc:
            raise SapSessionError(
                "SAPHive could not create SAP GUI session.",
                details={"connection": self.connection_name, "error": str(exc)},
            ) from exc

    def with_connection(self, callback: Callable[[Any], T]) -> T:
        return callback(self.connection)

    def _create_session(self, connection: Any) -> "WindowsSapSession":
        before_sessions = _wait_for_connection_sessions(connection)
        if not before_sessions:
            raise SapSessionError(
                "SAP GUI connection does not have a source session to create from.",
                details={"connection": self.connection_name},
            )

        before_sessions[0].CreateSession()
        session_index, raw_session = _wait_for_created_session(
            connection,
            before_sessions,
            connection_name=self.connection_name,
        )
        session = self._wrap_session(raw_session, session_index)
        self.created_sessions.append(session)
        return session

    def close_created_sessions(self) -> None:
        for session in tuple(reversed(self.created_sessions)):
            session.close()

        self.created_sessions.clear()

    def close_connection(self, *, force: bool = False) -> None:
        if not self.opened_by_saphive and not force:
            return

        self.with_connection(_close_connection)

    def close_application(self) -> None:
        if self.client is None:
            return

        client = self.client
        _close_application(client._application(start_sap_logon=False))

    def _wrap_session(self, session: Any, session_index: int) -> "WindowsSapSession":
        return WindowsSapSession(
            session=session,
            connection_owner=self,
            session_index=session_index,
            session_identity=_session_identity(session),
        )

    def _forget_created_session(self, session: "WindowsSapSession") -> None:
        with suppress(ValueError):
            self.created_sessions.remove(session)


class WindowsSapSession:
    """Thin wrapper around a COM SAP GUI Scripting session object."""

    __slots__ = ("_closed", "_session", "connection_owner", "session_identity", "session_index")

    def __init__(
        self,
        session: Any,
        *,
        connection_owner: WindowsSapConnection | None = None,
        session_index: int | None = None,
        session_identity: str | None = None,
    ) -> None:
        self._closed = False
        self._session = session
        self.connection_owner = connection_owner
        self.session_index = session_index
        self.session_identity = session_identity

    @property
    def session(self) -> Any:
        return self._session

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

    def is_usable(self) -> bool:
        try:
            self.session.findById("wnd[0]")
            return True
        except Exception:
            return False

    def close(self) -> None:
        if self._closed:
            return

        try:
            _close_session(self.session)
        except Exception as exc:
            raise SapSessionError(
                "SAPHive could not close SAP GUI session.",
                details={"error": str(exc)},
            ) from exc
        self._closed = True
        if self.connection_owner is not None:
            self.connection_owner._forget_created_session(self)


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


def _resolve_sap_application(sap_gui: Any) -> Any:
    scripting_engine = getattr(sap_gui, "GetScriptingEngine", None)
    if scripting_engine is None:
        return sap_gui

    if _looks_like_sap_application(scripting_engine):
        return scripting_engine

    if callable(scripting_engine):
        return scripting_engine()

    return scripting_engine


def _looks_like_sap_application(value: Any) -> bool:
    return _has_com_member(value, "Children") or _has_com_member(value, "OpenConnection")


def _has_com_member(value: Any, member: str) -> bool:
    try:
        getattr(value, member)
        return True
    except Exception:
        return False


def _wait_for_connection_child(
    connection: Any,
    index: int,
    *,
    sleep: Sleep | None = None,
) -> Any:
    sleep_func = time.sleep if sleep is None else sleep
    attempts = max(1, int(SAP_GUI_START_TIMEOUT_SECONDS / SAP_GUI_POLL_SECONDS))
    last_error: Exception | None = None
    for attempt in range(attempts):
        try:
            return connection.Children(index)
        except Exception as exc:
            if not _is_session_index_not_found_error(exc):
                raise

            last_error = exc
            if attempt < attempts - 1:
                sleep_func(SAP_GUI_POLL_SECONDS)

    if last_error is not None:
        raise last_error

    raise SapSessionError(
        "SAP GUI connection did not expose the requested session.",
        details={"session_index": index},
    )


def _wait_for_session_ready(
    session: Any,
    *,
    sleep: Sleep | None = None,
) -> Any:
    sleep_func = time.sleep if sleep is None else sleep
    attempts = max(1, int(SAP_GUI_START_TIMEOUT_SECONDS / SAP_GUI_POLL_SECONDS))
    last_error: Exception | None = None
    for attempt in range(attempts):
        try:
            session.findById("wnd[0]")
            return session
        except Exception as exc:
            if not _is_retryable_sap_gui_startup_error(exc):
                raise

            last_error = exc
            if attempt < attempts - 1:
                sleep_func(SAP_GUI_POLL_SECONDS)

    if last_error is not None:
        raise last_error

    raise SapSessionError("SAP GUI session did not become ready.")


def _select_connection(application: Any, profile: Any) -> Any:
    matching_connections: list[Any] = []
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
            matching_connections.append(connection)

    if len(matching_connections) == 1:
        return matching_connections[0]

    if len(matching_connections) > 1:
        raise SapConnectionError(
            "Requested SAP GUI connection matched multiple open connections.",
            details={
                "sap_logon_name": profile.sap_logon_name,
                "client": profile.client,
                "matching_connection_count": len(matching_connections),
            },
        )

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


def _connection_sessions(connection: Any) -> tuple[Any, ...]:
    session_count = int(connection.Children.Count)
    return tuple(connection.Children(index) for index in range(session_count))


def _wait_for_connection_sessions(
    connection: Any,
    *,
    sleep: Sleep | None = None,
) -> tuple[Any, ...]:
    sleep_func = time.sleep if sleep is None else sleep
    attempts = max(1, int(SAP_GUI_START_TIMEOUT_SECONDS / SAP_GUI_POLL_SECONDS))
    last_error: Exception | None = None
    for attempt in range(attempts):
        try:
            return _connection_sessions(connection)
        except Exception as exc:
            if not _is_session_index_not_found_error(exc):
                raise

            last_error = exc
            if attempt < attempts - 1:
                sleep_func(SAP_GUI_POLL_SECONDS)

    if last_error is not None:
        raise last_error

    raise SapSessionError("SAP GUI connection did not expose its sessions.")


def _wait_for_created_session(
    connection: Any,
    before_sessions: tuple[Any, ...],
    *,
    connection_name: str,
    sleep: Sleep | None = None,
) -> tuple[int, Any]:
    sleep_func = time.sleep if sleep is None else sleep
    attempts = max(1, int(SAP_SESSION_CREATE_TIMEOUT_SECONDS / SAP_GUI_POLL_SECONDS))
    last_error: Exception | None = None
    for attempt in range(attempts):
        try:
            candidate = _find_created_session(before_sessions, _connection_sessions(connection))
            if candidate is not None:
                return candidate
        except Exception as exc:
            last_error = exc

        if attempt < attempts - 1:
            sleep_func(SAP_GUI_POLL_SECONDS)

    details: dict[str, object] = {
        "connection": connection_name,
        "before_count": len(before_sessions),
    }
    if last_error is not None:
        details["error"] = str(last_error)
    raise SapSessionError(
        "SAP GUI did not expose exactly one newly created session.",
        details=details,
    )


def _find_created_session(
    before_sessions: tuple[Any, ...],
    after_sessions: tuple[Any, ...],
) -> tuple[int, Any] | None:
    if len(after_sessions) <= len(before_sessions):
        return None

    before_identities = set()
    for session in before_sessions:
        identity = _session_identity(session)
        if identity is not None:
            before_identities.add(identity)
    if before_identities:
        candidates = [
            (index, session)
            for index, session in enumerate(after_sessions)
            if _session_identity(session) not in before_identities
        ]
        if len(candidates) == 1:
            return candidates[0]
        if len(candidates) > 1:
            raise SapSessionError(
                "SAP GUI exposed multiple newly created sessions.",
                details={"new_session_count": len(candidates)},
            )
        return None

    if len(after_sessions) == len(before_sessions) + 1:
        session_index = len(after_sessions) - 1
        return session_index, after_sessions[session_index]

    raise SapSessionError(
        "SAP GUI exposed multiple newly created sessions.",
        details={"new_session_count": len(after_sessions) - len(before_sessions)},
    )


def _session_identity(session: Any) -> str | None:
    try:
        identity = session.Id
    except Exception:
        return None

    if identity is None:
        return None

    return str(identity)


def _is_stale_com_proxy_error(error: Exception) -> bool:
    message = str(error)
    normalized_message = message.lower()
    return (
        (isinstance(error, AttributeError) and message.startswith("<unknown>."))
        or "RPC_E_DISCONNECTED" in message
        or "object invoked has disconnected" in normalized_message
        or "object is not connected to server" in normalized_message
        or "objeto invocado se desconect" in normalized_message
        or "objeto no está conectado al servidor" in normalized_message
        or "objeto no esta conectado al servidor" in normalized_message
        or "destinatario" in normalized_message
        or "conexiones no son válidas" in normalized_message
        or "conexiones no son validas" in normalized_message
        or ("server" in normalized_message and "not available" in normalized_message)
        or "-2147417848" in message
        or "-2147418094" in message
        or "-2147023174" in message
        or "-2147220995" in message
    )


def _is_session_index_not_found_error(error: Exception) -> bool:
    message = str(error).lower()
    return (
        "specified index" in message
        or "enumerator of the collection cannot find" in message
        or "614, 'sapfewse'" in message
    )


def _is_retryable_sap_gui_startup_error(error: Exception) -> bool:
    return _is_stale_com_proxy_error(error) or _is_session_index_not_found_error(error)


def _close_session(session: Any) -> None:
    try:
        session.findById("wnd[0]").Close()
    except Exception:
        session.CloseSession()


def _close_connection(connection: Any) -> None:
    try:
        connection.CloseConnection()
    except Exception:
        session_count = int(connection.Children.Count)
        for index in reversed(range(session_count)):
            _close_session(connection.Children(index))


def _close_application(application: Any) -> None:
    application.Quit()


def _login(session: Any, profile: Any, credentials: SapCredentials) -> None:
    if profile.client is not None:
        session.findById("wnd[0]/usr/txtRSYST-MANDT").Text = profile.client

    session.findById("wnd[0]/usr/txtRSYST-BNAME").Text = credentials.username
    session.findById("wnd[0]/usr/pwdRSYST-BCODE").Text = credentials.password
    session.findById("wnd[0]/usr/txtRSYST-LANGU").Text = profile.language
    session.findById("wnd[0]/tbar[0]/btn[0]").press()
