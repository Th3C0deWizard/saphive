"""SAP GUI abstraction interfaces used by SAPHive Core and scripts."""

from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from saphive.core.errors import SapSessionError


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


@runtime_checkable
class SapClient(Protocol):
    """Client capable of creating or returning a SAP GUI session."""

    def connect(self) -> SapSession:
        """Connect to SAP GUI and return a session abstraction."""


@dataclass(frozen=True, slots=True)
class SapGuiPlaceholder:
    """Placeholder SAP client used before a real SAP GUI client is configured."""

    def connect(self) -> SapSession:
        """Fail clearly until a SAP GUI client is supplied."""
        raise SapSessionError("SAP GUI session handling has not been configured yet.")
