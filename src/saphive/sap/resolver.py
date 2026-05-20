"""SAP connection resolution for SAPHive runtime runs."""

from dataclasses import dataclass, field
from pathlib import Path

from saphive.core.config import SapConnectionMode, SapConnectionProfile, SAPHiveConfig
from saphive.core.errors import ConfigurationError, SapConnectionError
from saphive.sap.auth import find_auth_file, load_auth_config, resolve_credentials
from saphive.sap.interfaces import SapConnection
from saphive.sap.windows import WindowsSapGuiClient


@dataclass(frozen=True, slots=True)
class DefaultSapConnectionResolver:
    """Default resolver using the Windows SAP GUI Scripting boundary."""

    client: WindowsSapGuiClient = field(default_factory=WindowsSapGuiClient)

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
        """Resolve a SAP connection using auto, attach, or open mode."""
        resolved_mode = config.sap.mode if mode is None else mode
        resolved_name, profile = _resolve_profile(config, connection_name)

        if resolved_mode is SapConnectionMode.ATTACH:
            return self.client.attach_connection(resolved_name, profile)

        if resolved_mode is SapConnectionMode.OPEN:
            return self._open_connection(
                resolved_name,
                profile,
                auth_file,
                config_path,
                script_path,
            )

        try:
            return self.client.attach_connection(resolved_name, profile)
        except SapConnectionError as exc:
            if not _should_auto_open_after_attach_failure(exc):
                raise

            return self._open_connection(
                resolved_name,
                profile,
                auth_file,
                config_path,
                script_path,
            )

    def _open_connection(
        self,
        connection_name: str,
        profile: SapConnectionProfile,
        auth_file: str | None,
        config_path: str | None,
        script_path: str | None,
    ) -> SapConnection:
        auth_path = find_auth_file(
            explicit_path=auth_file,
            config_path=config_path,
            script_path=script_path,
        )
        if auth_path is None:
            raise SapConnectionError(
                "SAP auth file is required to open a new connection.",
                details={"connection": connection_name},
            )

        auth_config = load_auth_config(auth_path)
        credentials = resolve_credentials(connection_name=connection_name, auth_config=auth_config)
        return self.client.open_connection(connection_name, profile, credentials)


def _resolve_profile(
    config: SAPHiveConfig,
    connection_name: str | None,
) -> tuple[str, SapConnectionProfile]:
    resolved_name = connection_name or config.sap.connection
    if resolved_name is None:
        raise ConfigurationError("SAP connection profile was not configured.")

    profile = config.sap.connections.get(resolved_name)
    if profile is None:
        raise ConfigurationError(
            "SAP connection profile was not found.",
            details={"connection": resolved_name},
        )

    return resolved_name, profile


def _should_auto_open_after_attach_failure(error: SapConnectionError) -> bool:
    return error.message in {
        "SAPHive could not access SAP GUI Scripting engine.",
        "No active SAP GUI connections were found.",
        "Requested SAP GUI connection was not found.",
    }


def normalize_auth_path(auth_file: str | Path | None) -> str | None:
    """Normalize auth file paths for resolver protocol compatibility."""
    return None if auth_file is None else str(auth_file)
