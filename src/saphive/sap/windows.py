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
            connection = _wait_for_selected_connection(
                application,
                profile,
                require_session=True,
            )
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
    managed_sessions: list["WindowsSapSession"] = field(default_factory=list, repr=False)

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
            return self.with_connection(self._create_session_without_retry)
        except Exception as exc:
            raise SapSessionError(
                "SAPHive could not create SAP GUI session.",
                details={"connection": self.connection_name, "error": str(exc)},
            ) from exc

    def active_session(self) -> "WindowsSapSession":
        return self.attach_session(0)

    def with_connection(self, callback: Callable[[Any], T]) -> T:
        try:
            return callback(self.connection)
        except Exception as exc:
            if _is_com_not_initialized_error(exc):
                return self._retry_callback_with_initialized_com(callback)

            if _is_stale_com_proxy_error(exc):
                return self._refresh_and_retry_callback(callback)

            raise

    def _create_session_without_retry(self, connection: Any) -> "WindowsSapSession":
        before_count = _connection_session_count(connection)
        if before_count == 0 and self._can_refresh_connection():
            try:
                self._refresh_connection()
            except SapConnectionError:
                if self.initial_session is not None:
                    return self._wrap_session(self.initial_session, 0)
                raise

            connection = self.connection
            before_count = _connection_session_count(connection)

        if before_count == 0 and self.initial_session is not None:
            return self._wrap_session(self.initial_session, 0)

        _wait_for_connection_child(connection, 0).CreateSession()
        after_count = int(connection.Children.Count)
        session_index = after_count - 1 if after_count > before_count else max(0, after_count - 1)
        session = self._wrap_session(connection.Children(session_index), session_index)
        self.created_sessions.append(session)
        return session

    def recover_context_after_external_com(self) -> None:
        """Refresh connection and session COM proxies after another COM owner ran."""
        if self._can_refresh_connection():
            try:
                self._refresh_connection()
            except SapConnectionError:
                if self._has_usable_managed_session():
                    return
                raise

        for session in tuple(self.managed_sessions):
            try:
                session.refresh_from_connection()
            except Exception:
                if session.is_usable():
                    continue
                raise

    def safe_execute(self, callback: Callable[[], T]) -> T:
        try:
            return callback()
        except Exception as exc:
            if not _is_com_not_initialized_error(exc):
                raise

            with sap_com_initialized():
                return callback()

    def close_created_sessions(self) -> None:
        for session in reversed(self.created_sessions):
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
        self.safe_execute(
            lambda: _close_application(client._application(start_sap_logon=False))
        )

    def _retry_callback_with_initialized_com(self, callback: Callable[[Any], T]) -> T:
        with sap_com_initialized():
            try:
                return callback(self.connection)
            except Exception as exc:
                if _is_stale_com_proxy_error(exc):
                    self._refresh_connection()
                    return callback(self.connection)

                raise

    def _refresh_and_retry_callback(self, callback: Callable[[Any], T]) -> T:
        if not self._can_refresh_connection():
            raise SapConnectionError(
                "SAPHive could not refresh a stale SAP GUI connection.",
                details={"connection": self.connection_name},
            )

        with sap_com_initialized():
            self._refresh_connection()
            return callback(self.connection)

    def _can_refresh_connection(self) -> bool:
        return self.client is not None and self.profile is not None

    def _has_usable_managed_session(self) -> bool:
        return any(session.is_usable() for session in self.managed_sessions)

    def _refresh_connection(self) -> None:
        if self.client is None or self.profile is None:
            return

        application = self.client._application(start_sap_logon=False)
        connection = _select_connection(application, self.profile)
        object.__setattr__(self, "connection", connection)

    def _wrap_session(self, session: Any, session_index: int) -> "WindowsSapSession":
        wrapped = WindowsSapSession(
            session=session,
            connection_owner=self,
            session_index=session_index,
        )
        self.managed_sessions.append(wrapped)
        return wrapped


class WindowsSapSession:
    """Thin wrapper around a COM SAP GUI Scripting session object."""

    __slots__ = ("_session", "connection_owner", "session_index")

    def __init__(
        self,
        session: Any,
        *,
        connection_owner: WindowsSapConnection | None = None,
        session_index: int | None = None,
    ) -> None:
        self._session = session
        self.connection_owner = connection_owner
        self.session_index = session_index

    @property
    def session(self) -> Any:
        if self._session_is_usable(self._session):
            return self._session

        return self._refresh_session()

    def start_transaction(self, transaction_code: str) -> None:
        try:
            self._with_com_retry(lambda: self.session.StartTransaction(transaction_code))
        except Exception as exc:
            raise SapGuiError(
                "SAPHive could not start SAP transaction.",
                details={"transaction_code": transaction_code, "error": str(exc)},
            ) from exc

    def set_text(self, element_id: str, value: str) -> None:
        try:
            self._with_com_retry(lambda: setattr(self.session.findById(element_id), "Text", value))
        except Exception as exc:
            raise SapGuiError(
                "SAPHive could not set SAP GUI element text.",
                details={"element_id": element_id, "error": str(exc)},
            ) from exc

    def press(self, element_id: str) -> None:
        try:
            self._with_com_retry(lambda: self.session.findById(element_id).press())
        except Exception as exc:
            raise SapGuiError(
                "SAPHive could not press SAP GUI element.",
                details={"element_id": element_id, "error": str(exc)},
            ) from exc

    def get_text(self, element_id: str) -> str:
        try:
            value = self._with_com_retry(lambda: self.session.findById(element_id).Text)
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
            return self._session_is_usable(self._session)
        except Exception:
            return False

    def close(self) -> None:
        try:
            self._with_com_retry(lambda: _close_session(self.session))
        except Exception as exc:
            raise SapSessionError(
                "SAPHive could not close SAP GUI session.",
                details={"error": str(exc)},
            ) from exc

    def _with_com_retry(self, action: Callable[[], T]) -> T:
        try:
            return action()
        except Exception as exc:
            if _is_stale_com_proxy_error(exc):
                self._refresh_session()
                return action()

            if not _is_com_not_initialized_error(exc):
                raise

            with sap_com_initialized():
                return action()

    def _session_is_usable(self, session: Any) -> bool:
        try:
            _ = session.findById
            return True
        except Exception as exc:
            if _is_stale_com_proxy_error(exc):
                return False

            raise

    def _refresh_session(self) -> Any:
        if self.connection_owner is None or self.session_index is None:
            raise SapSessionError("SAPHive could not refresh a stale SAP GUI session.")

        return self.refresh_from_connection()

    def refresh_from_connection(self) -> Any:
        if self.connection_owner is None or self.session_index is None:
            raise SapSessionError("SAPHive could not refresh a stale SAP GUI session.")

        session = self.connection_owner.with_connection(
            lambda connection: connection.Children(self.session_index)
        )
        self._session = session
        return session


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


def _wait_for_selected_connection(
    application: Any,
    profile: Any,
    *,
    require_session: bool = False,
    sleep: Sleep | None = None,
) -> Any:
    sleep_func = time.sleep if sleep is None else sleep
    attempts = max(1, int(SAP_GUI_START_TIMEOUT_SECONDS / SAP_GUI_POLL_SECONDS))
    last_error: Exception | None = None
    for attempt in range(attempts):
        try:
            connection = _select_connection(application, profile)
            if not require_session or _connection_session_count(connection) > 0:
                return connection
        except Exception as exc:
            last_error = exc

        if attempt < attempts - 1:
            sleep_func(SAP_GUI_POLL_SECONDS)

    if last_error is not None:
        raise last_error

    raise SapConnectionError(
        "SAP GUI connection was found but did not expose any sessions.",
        details={"sap_logon_name": profile.sap_logon_name, "client": profile.client},
    )


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

    for connection in matching_connections:
        if _connection_session_count(connection) > 0:
            return connection

    if matching_connections:
        return matching_connections[0]

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


def _connection_session_count(connection: Any) -> int:
    try:
        return int(connection.Children.Count)
    except Exception:
        return 0


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
        or "-2147417848" in message
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


def _is_com_not_initialized_error(error: Exception) -> bool:
    message = str(error).lower()
    return (
        ("coinitialize" in message
        and (
            "has not been called" in message
            or "no se ha llamado" in message
        ))
        or "-2147221008" in message
    )


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
