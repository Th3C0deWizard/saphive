"""Domain errors raised by SAPHive Core."""

from collections.abc import Mapping


class SAPHiveError(Exception):
    """Base class for all SAPHive domain errors."""

    def __init__(self, message: str, *, details: Mapping[str, object] | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.details = dict(details or {})


class ConfigurationError(SAPHiveError):
    """Raised when SAPHive configuration is missing or invalid."""


class ScriptDiscoveryError(SAPHiveError):
    """Raised when SAPHive cannot discover automation scripts."""


class ScriptLoadError(SAPHiveError):
    """Raised when SAPHive cannot load an automation script."""


class ScriptContractError(SAPHiveError):
    """Raised when an automation script does not match the SAPHive contract."""


class ScriptValidationError(SAPHiveError):
    """Raised when automation script input validation fails."""


class SapConnectionError(SAPHiveError):
    """Raised when SAPHive cannot connect to SAP GUI."""


class SapSessionError(SAPHiveError):
    """Raised when SAPHive cannot access or manage a SAP GUI session."""


class SapGuiError(SAPHiveError):
    """Raised when SAP GUI Scripting reports an operation failure."""


class ScriptExecutionError(SAPHiveError):
    """Raised when an automation script fails during execution."""
