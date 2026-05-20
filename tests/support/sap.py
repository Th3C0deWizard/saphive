"""In-memory SAP GUI test doubles for SAPHive unit tests."""

from dataclasses import dataclass, field

from saphive.sap.interfaces import SapSession


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


@dataclass(frozen=True, slots=True)
class InMemorySapClient:
    """SAP client test double returning a preconfigured in-memory session."""

    session: InMemorySapSession = field(default_factory=InMemorySapSession)

    def connect(self) -> SapSession:
        return self.session
