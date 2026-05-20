"""Windows SAP GUI Scripting boundary for SAPHive."""

import sys
from collections.abc import Callable
from dataclasses import dataclass, field
from importlib import import_module
from typing import Any, cast

from saphive.core.errors import SapConnectionError, SapGuiError

DispatchFactory = Callable[[str], Any]


@dataclass(frozen=True, slots=True)
class WindowsSapGuiClient:
    """Windows-only SAP GUI Scripting client boundary."""

    connection_name: str | None = None
    session_index: int = 0
    dispatch_factory: DispatchFactory | None = field(default=None, repr=False, compare=False)

    def connect(self) -> "WindowsSapSession":
        """Connect to SAP GUI Scripting and return a wrapped session."""
        dispatch = self.dispatch_factory or _load_dispatch_factory()
        try:
            sap_gui = dispatch("SAPGUI")
            application = sap_gui.GetScriptingEngine
            connection = _select_connection(application, self.connection_name)
            session = connection.Children(self.session_index)
        except SapConnectionError:
            raise
        except Exception as exc:
            raise SapConnectionError(
                "SAPHive could not connect to SAP GUI Scripting.",
                details={"connection_name": self.connection_name, "error": str(exc)},
            ) from exc

        return WindowsSapSession(session=session)


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


def _load_dispatch_factory() -> DispatchFactory:
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

    return cast(DispatchFactory, win32com_client.Dispatch)


def _select_connection(application: Any, connection_name: str | None) -> Any:
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
        if connection_name is None or _connection_matches(connection, connection_name):
            return connection

    raise SapConnectionError(
        "Requested SAP GUI connection was not found.",
        details={"connection_name": connection_name},
    )


def _connection_matches(connection: Any, connection_name: str) -> bool:
    candidates = (
        getattr(connection, "Description", None),
        getattr(connection, "Name", None),
        getattr(connection, "SystemName", None),
    )
    return connection_name in candidates
