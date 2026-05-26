"""In-memory SAP GUI test doubles for SAPHive unit tests."""

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, TypeVar

from saphive.core.config import SapConnectionMode, SAPHiveConfig
from saphive.core.errors import SapConnectionError
from saphive.sap.interfaces import SapConnection, SapSession

T = TypeVar("T")


@dataclass(slots=True)
class InMemorySapSession:
    """Simple in-memory SAP session test double."""

    values: dict[str, str] = field(default_factory=dict)
    operations: list[tuple[str, str]] = field(default_factory=list)
    status_text: str = ""

    def start_transaction(self, transaction_code: str) -> None:
        self.operations.append(("start_transaction", transaction_code))

    def set_text(self, element_id: str, value: str) -> None:
        self.values[element_id] = value
        self.operations.append(("set_text", element_id))

    def press(self, element_id: str) -> None:
        self.operations.append(("press", element_id))

    def get_text(self, element_id: str) -> str:
        self.operations.append(("get_text", element_id))
        return self.values.get(element_id, "")

    def status_bar_text(self) -> str:
        self.operations.append(("status_bar_text", "wnd[0]/sbar"))
        return self.status_text

    def close(self) -> None:
        self.operations.append(("close", ""))


@dataclass(slots=True)
class InMemorySapConnection:
    """Connection-scoped SAP test double."""

    connection_name: str = "test"
    session: InMemorySapSession = field(default_factory=InMemorySapSession)
    created_sessions: list[InMemorySapSession] = field(default_factory=list)
    closed_created_sessions: list[InMemorySapSession] = field(default_factory=list)
    cleanup_operations: list[str] = field(default_factory=list)
    opened_by_saphive: bool = True

    def list_sessions(self) -> tuple[SapSession, ...]:
        return (self.session, *self.created_sessions)

    def attach_session(self, index: int = 0) -> SapSession:
        return self.list_sessions()[index]

    def create_session(self) -> SapSession:
        session = InMemorySapSession(status_text=self.session.status_text)
        self.created_sessions.append(session)
        return session

    def with_connection(self, callback: Callable[[Any], T]) -> T:
        return callback(self)

    def close_created_sessions(self) -> None:
        self.cleanup_operations.append("close_created_sessions")
        self.closed_created_sessions.extend(self.created_sessions)
        self.created_sessions.clear()

    def close_connection(self, *, force: bool = False) -> None:
        if self.opened_by_saphive or force:
            self.cleanup_operations.append("close_connection")

    def close_application(self) -> None:
        self.cleanup_operations.append("close_application")

@dataclass(slots=True)
class InMemorySapConnectionResolver:
    """Configurable SAP connection resolver test double."""

    connection: InMemorySapConnection = field(default_factory=InMemorySapConnection)
    attach_available: bool = True
    resolved_modes: list[SapConnectionMode] = field(default_factory=list)

    def resolve_connection(
        self,
        *,
        config: SAPHiveConfig,
        mode: SapConnectionMode | None = None,
        connection_name: str | None = None,
        auth_file: str | None = None,
        config_path: str | None = None,
        script_path: str | None = None,
    ) -> SapConnection:
        resolved_mode = config.sap.mode if mode is None else mode
        self.resolved_modes.append(resolved_mode)
        self.connection.connection_name = connection_name or config.sap.connection or "test"
        if resolved_mode is SapConnectionMode.ATTACH and not self.attach_available:
            raise SapConnectionError("Requested SAP GUI connection was not found.")

        return self.connection
