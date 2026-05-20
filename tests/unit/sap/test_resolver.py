from pathlib import Path
from typing import Any, cast

import pytest
from tests.support.sap import InMemorySapConnection

from saphive import (
    SapConfig,
    SapConnectionError,
    SapConnectionMode,
    SapConnectionProfile,
    SAPHiveConfig,
)
from saphive.sap.auth import SapCredentials
from saphive.sap.resolver import DefaultSapConnectionResolver


def test_resolver_attach_mode_attaches_existing_connection() -> None:
    client = FakeSapGuiClient(attach_connection=InMemorySapConnection(connection_name="prd"))
    resolver = DefaultSapConnectionResolver(client=cast(Any, client))

    connection = resolver.resolve_connection(
        config=_config(),
        mode=SapConnectionMode.ATTACH,
    )

    assert connection.connection_name == "prd"
    assert client.actions == ["attach:prd"]


def test_resolver_open_mode_uses_auth_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    auth_file = _write_auth_file(tmp_path)
    monkeypatch.setenv("SAP_PASSWORD", "secret")
    client = FakeSapGuiClient(open_connection=InMemorySapConnection(connection_name="prd"))
    resolver = DefaultSapConnectionResolver(client=cast(Any, client))

    connection = resolver.resolve_connection(
        config=_config(),
        mode=SapConnectionMode.OPEN,
        auth_file=str(auth_file),
    )

    assert connection.connection_name == "prd"
    assert client.actions == ["open:prd:SAP_USER"]


def test_resolver_open_mode_uses_script_directory_auth(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    script_dir = tmp_path / "scripts"
    script_dir.mkdir()
    _write_auth_file(script_dir)
    monkeypatch.setenv("SAP_PASSWORD", "secret")
    client = FakeSapGuiClient(open_connection=InMemorySapConnection(connection_name="prd"))
    resolver = DefaultSapConnectionResolver(client=cast(Any, client))

    connection = resolver.resolve_connection(
        config=_config(),
        mode=SapConnectionMode.OPEN,
        script_path=str(script_dir / "job.py"),
    )

    assert connection.connection_name == "prd"
    assert client.actions == ["open:prd:SAP_USER"]


def test_resolver_auto_mode_attaches_first() -> None:
    client = FakeSapGuiClient(attach_connection=InMemorySapConnection(connection_name="prd"))
    resolver = DefaultSapConnectionResolver(client=cast(Any, client))

    connection = resolver.resolve_connection(config=_config(), mode=SapConnectionMode.AUTO)

    assert connection.connection_name == "prd"
    assert client.actions == ["attach:prd"]


def test_resolver_auto_mode_opens_when_attach_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    auth_file = _write_auth_file(tmp_path)
    monkeypatch.setenv("SAP_PASSWORD", "secret")
    client = FakeSapGuiClient(open_connection=InMemorySapConnection(connection_name="prd"))
    resolver = DefaultSapConnectionResolver(client=cast(Any, client))

    connection = resolver.resolve_connection(
        config=_config(),
        mode=SapConnectionMode.AUTO,
        auth_file=str(auth_file),
    )

    assert connection.connection_name == "prd"
    assert client.actions == ["attach:prd", "open:prd:SAP_USER"]


def test_resolver_auto_mode_opens_when_sap_gui_is_inaccessible(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    auth_file = _write_auth_file(tmp_path)
    monkeypatch.setenv("SAP_PASSWORD", "secret")
    client = FakeSapGuiClient(
        attach_error=SapConnectionError("SAPHive could not access SAP GUI Scripting engine."),
        open_connection=InMemorySapConnection(connection_name="prd"),
    )
    resolver = DefaultSapConnectionResolver(client=cast(Any, client))

    connection = resolver.resolve_connection(
        config=_config(),
        mode=SapConnectionMode.AUTO,
        auth_file=str(auth_file),
    )

    assert connection.connection_name == "prd"
    assert client.actions == ["attach:prd", "open:prd:SAP_USER"]


def test_resolver_open_mode_requires_auth_file() -> None:
    client = FakeSapGuiClient(open_connection=InMemorySapConnection(connection_name="prd"))
    resolver = DefaultSapConnectionResolver(client=cast(Any, client))

    with pytest.raises(SapConnectionError, match="auth file"):
        resolver.resolve_connection(config=_config(), mode=SapConnectionMode.OPEN)


class FakeSapGuiClient:
    def __init__(
        self,
        *,
        attach_connection: InMemorySapConnection | None = None,
        open_connection: InMemorySapConnection | None = None,
        attach_error: SapConnectionError | None = None,
    ) -> None:
        self._attach_connection = attach_connection
        self._open_connection = open_connection
        self._attach_error = attach_error
        self.actions: list[str] = []

    def attach_connection(
        self,
        connection_name: str,
        profile: SapConnectionProfile,
    ) -> InMemorySapConnection:
        self.actions.append(f"attach:{connection_name}")
        if self._attach_error is not None:
            raise self._attach_error

        if self._attach_connection is None:
            raise SapConnectionError("Requested SAP GUI connection was not found.")

        return self._attach_connection

    def open_connection(
        self,
        connection_name: str,
        profile: SapConnectionProfile,
        credentials: SapCredentials,
    ) -> InMemorySapConnection:
        self.actions.append(f"open:{connection_name}:{credentials.username}")
        if self._open_connection is None:
            raise SapConnectionError("Could not open SAP connection.")

        return self._open_connection


def _config() -> SAPHiveConfig:
    return SAPHiveConfig(
        sap=SapConfig(
            mode=SapConnectionMode.AUTO,
            connection="prd",
            connections={"prd": SapConnectionProfile(sap_logon_name="PRD", client="100")},
        )
    )


def _write_auth_file(tmp_path: Path) -> Path:
    auth_file = tmp_path / ".saphive.auth.toml"
    auth_file.write_text(
        """
[connections.prd]
username = "SAP_USER"
password_env = "SAP_PASSWORD"
""".strip(),
        encoding="utf-8",
    )
    return auth_file
