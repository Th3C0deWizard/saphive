"""SAP GUI abstraction package for SAPHive."""

from saphive.sap.auth import SapAuthConfig, SapAuthProfile, SapCredentials
from saphive.sap.interfaces import (
    SapConnection,
    SapConnectionResolver,
    SapGuiPlaceholder,
    SapSession,
)
from saphive.sap.resolver import DefaultSapConnectionResolver
from saphive.sap.windows import WindowsSapConnection, WindowsSapGuiClient, WindowsSapSession

__all__ = [
    "DefaultSapConnectionResolver",
    "SapAuthConfig",
    "SapAuthProfile",
    "SapConnection",
    "SapConnectionResolver",
    "SapCredentials",
    "SapGuiPlaceholder",
    "SapSession",
    "WindowsSapConnection",
    "WindowsSapGuiClient",
    "WindowsSapSession",
]
