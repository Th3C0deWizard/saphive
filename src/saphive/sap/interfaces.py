"""SAP GUI abstraction interfaces used by SAPHive Core and scripts."""

from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Protocol, TypeVar, runtime_checkable

from saphive.core.errors import SapConnectionError, SapSessionError

if TYPE_CHECKING:
    from saphive.core.config import SapConnectionMode, SAPHiveConfig

T = TypeVar("T")


@runtime_checkable
class SapSession(Protocol):
    """Minimal SAP session operations exposed to SAPHive scripts."""

    def start_transaction(self, transaction_code: str) -> None:
        """Start a SAP transaction."""

    def set_text(self, element_id: str, value: str) -> None:
        """Set text on a SAP GUI element."""

    def press(self, element_id: str) -> None:
        """Press a SAP GUI button or command element."""

    def get_text(self, element_id: str) -> str:
        """Read text from a SAP GUI element."""

    def status_bar_text(self) -> str:
        """Read the SAP GUI status bar text."""

    def close(self) -> None:
        """Close this SAP GUI session."""


@runtime_checkable
class SapConnection(Protocol):
    """Connection-scoped SAP APIs exposed to SAPHive scripts."""

    @property
    def connection_name(self) -> str:
        """Return the selected SAP connection name."""

    def list_sessions(self) -> tuple[SapSession, ...]:
        """List sessions available inside the selected SAP connection."""

    def attach_session(self, index: int = 0) -> SapSession:
        """Attach to an existing session inside the selected SAP connection."""

    def create_session(self) -> SapSession:
        """Create a new session inside the selected SAP connection."""

    def with_connection(self, callback: Callable[[Any], T]) -> T:
        """Run a callback with the raw connection object."""

    def close_created_sessions(self) -> None:
        """Close SAP sessions created through this connection wrapper."""

    def close_connection(self, *, force: bool = False) -> None:
        """Close the selected SAP connection when permitted by runtime policy."""

    def close_application(self) -> None:
        """Close the SAP GUI application."""


@runtime_checkable
class SapConnectionResolver(Protocol):
    """Resolver that selects or opens the SAP connection for a script run."""

    def resolve_connection(
        self,
        *,
        config: "SAPHiveConfig",
        mode: "SapConnectionMode | None" = None,
        connection_name: str | None = None,
        auth_file: str | None = None,
        config_path: str | None = None,
        script_path: str | None = None,
    ) -> SapConnection:
        """Resolve the connection-scoped SAP object exposed as ctx.sap."""


@dataclass(frozen=True, slots=True)
class SapGuiPlaceholder:
    """Placeholder SAP connection used before a real SAP GUI connection is configured."""

    @property
    def connection_name(self) -> str:
        """Return a placeholder connection name."""
        return "unconfigured"

    def list_sessions(self) -> tuple[SapSession, ...]:
        """Fail clearly until a SAP GUI connection is supplied."""
        raise SapConnectionError("SAP GUI connection has not been configured yet.")

    def attach_session(self, index: int = 0) -> SapSession:
        """Fail clearly until a SAP GUI connection is supplied."""
        raise SapSessionError(
            "SAP GUI session handling has not been configured yet.",
            details={"session_index": index},
        )

    def create_session(self) -> SapSession:
        """Fail clearly until a SAP GUI connection is supplied."""
        raise SapSessionError("SAP GUI session handling has not been configured yet.")

    def with_connection(self, callback: Callable[[Any], T]) -> T:
        """Fail clearly until a SAP GUI connection is supplied."""
        raise SapConnectionError("SAP GUI connection has not been configured yet.")

    def close_created_sessions(self) -> None:
        """Fail clearly until a SAP GUI connection is supplied."""
        raise SapConnectionError("SAP GUI connection has not been configured yet.")

    def close_connection(self, *, force: bool = False) -> None:
        """Fail clearly until a SAP GUI connection is supplied."""
        raise SapConnectionError("SAP GUI connection has not been configured yet.")

    def close_application(self) -> None:
        """Fail clearly until a SAP GUI connection is supplied."""
        raise SapConnectionError("SAP GUI connection has not been configured yet.")
