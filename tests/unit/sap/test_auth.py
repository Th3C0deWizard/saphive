from pathlib import Path

import pytest

from saphive import ConfigurationError, SapConnectionError
from saphive.sap.auth import (
    find_auth_file,
    load_auth_config,
    resolve_credentials,
)


def test_find_auth_file_prefers_explicit_path(tmp_path: Path) -> None:
    config_dir = tmp_path / "config"
    explicit_dir = tmp_path / "explicit"
    config_dir.mkdir()
    explicit_dir.mkdir()
    config_auth = config_dir / ".saphive.auth.toml"
    explicit_auth = explicit_dir / "auth.toml"
    config_auth.write_text("", encoding="utf-8")
    explicit_auth.write_text("", encoding="utf-8")

    assert (
        find_auth_file(explicit_path=explicit_auth, config_path=config_dir / "saphive.toml")
        == explicit_auth
    )


def test_find_auth_file_uses_config_directory(tmp_path: Path) -> None:
    auth_path = tmp_path / ".saphive.auth.toml"
    auth_path.write_text("", encoding="utf-8")

    assert find_auth_file(config_path=tmp_path / "saphive.toml") == auth_path


def test_find_auth_file_uses_script_directory_after_config_directory(tmp_path: Path) -> None:
    script_dir = tmp_path / "scripts"
    config_dir = tmp_path / "config"
    script_dir.mkdir()
    config_dir.mkdir()
    script_auth = script_dir / ".saphive.auth.toml"
    config_auth = config_dir / ".saphive.auth.toml"
    script_auth.write_text("", encoding="utf-8")
    config_auth.write_text("", encoding="utf-8")

    assert (
        find_auth_file(
            config_path=config_dir / "saphive.toml",
            script_path=script_dir / "job.py",
        )
        == config_auth
    )


def test_find_auth_file_uses_script_directory(tmp_path: Path) -> None:
    script_dir = tmp_path / "scripts"
    cli_config_dir = tmp_path / "cli-config"
    script_dir.mkdir()
    cli_config_dir.mkdir()
    script_auth = script_dir / ".saphive.auth.toml"
    cli_auth = cli_config_dir / ".saphive.auth.toml"
    script_auth.write_text("", encoding="utf-8")
    cli_auth.write_text("", encoding="utf-8")

    assert (
        find_auth_file(script_path=script_dir / "job.py", config_dir=cli_config_dir) == script_auth
    )


def test_find_auth_file_uses_os_config_directory(tmp_path: Path) -> None:
    cli_config_dir = tmp_path / "cli-config"
    cli_config_dir.mkdir()
    auth_path = cli_config_dir / ".saphive.auth.toml"
    auth_path.write_text("", encoding="utf-8")

    assert find_auth_file(config_dir=cli_config_dir) == auth_path


def test_load_auth_config_and_resolve_env_password(tmp_path: Path) -> None:
    auth_path = tmp_path / ".saphive.auth.toml"
    auth_path.write_text(
        """
[connections.prd]
username = "SAP_USER"
password_env = "SAP_PASSWORD"
""".strip(),
        encoding="utf-8",
    )

    auth_config = load_auth_config(auth_path)
    credentials = resolve_credentials(
        connection_name="prd",
        auth_config=auth_config,
        environ={"SAP_PASSWORD": "secret"},
    )

    assert credentials.username == "SAP_USER"
    assert credentials.password == "secret"


def test_resolve_credentials_supports_prompt(tmp_path: Path) -> None:
    auth_path = tmp_path / ".saphive.auth.toml"
    auth_path.write_text(
        """
[connections.prd]
username = "SAP_USER"
password_prompt = true
""".strip(),
        encoding="utf-8",
    )

    auth_config = load_auth_config(auth_path)
    credentials = resolve_credentials(
        connection_name="prd",
        auth_config=auth_config,
        password_prompt=lambda prompt: f"{prompt}secret",
    )

    assert credentials.password == "SAP password for SAP_USER: secret"


def test_resolve_credentials_raises_for_missing_env_value(tmp_path: Path) -> None:
    auth_path = tmp_path / ".saphive.auth.toml"
    auth_path.write_text(
        """
[connections.prd]
username = "SAP_USER"
password_env = "SAP_PASSWORD"
""".strip(),
        encoding="utf-8",
    )

    with pytest.raises(SapConnectionError, match="environment variable"):
        resolve_credentials(
            connection_name="prd",
            auth_config=load_auth_config(auth_path),
            environ={},
        )


def test_load_auth_config_rejects_raw_unknown_password_field(tmp_path: Path) -> None:
    auth_path = tmp_path / ".saphive.auth.toml"
    auth_path.write_text(
        """
[connections.prd]
username = "SAP_USER"
password = "secret"
""".strip(),
        encoding="utf-8",
    )

    with pytest.raises(ConfigurationError, match="validation failed"):
        load_auth_config(auth_path)
