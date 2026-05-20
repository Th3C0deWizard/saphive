"""SAP authentication file loading and credential resolution."""

import getpass
import os
import tomllib
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from saphive.core.config import default_cli_config_dir
from saphive.core.errors import ConfigurationError, SapConnectionError

DEFAULT_AUTH_FILENAME = ".saphive.auth.toml"


class SapAuthProfile(BaseModel):
    """SAP username/password auth profile without storing raw passwords."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    username: str
    password_env: str | None = None
    password_prompt: bool = False

    @model_validator(mode="after")
    def require_password_source(self) -> "SapAuthProfile":
        """Require exactly one supported password source."""
        if self.password_env is None and not self.password_prompt:
            raise ValueError("SAP auth profile requires password_env or password_prompt.")

        if self.password_env is not None and self.password_prompt:
            raise ValueError("SAP auth profile cannot use both password_env and password_prompt.")

        return self


class SapAuthConfig(BaseModel):
    """Root SAP auth file model."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    connections: dict[str, SapAuthProfile] = Field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class SapCredentials:
    """Resolved SAP credentials used only when opening a connection."""

    username: str
    password: str


PasswordPrompt = Callable[[str], str]


def find_auth_file(
    *,
    explicit_path: str | Path | None = None,
    config_path: str | Path | None = None,
    script_path: str | Path | None = None,
    config_dir: str | Path | None = None,
) -> Path | None:
    """Find a SAPHive auth file using the documented lookup order."""
    if explicit_path is not None:
        path = Path(explicit_path)
        return path if path.is_file() else None

    if config_path is not None:
        candidate = Path(config_path).parent / DEFAULT_AUTH_FILENAME
        if candidate.is_file():
            return candidate

    if script_path is not None:
        script_dir = _script_directory(Path(script_path))
        candidate = script_dir / DEFAULT_AUTH_FILENAME
        if candidate.is_file():
            return candidate

    cli_config_dir = default_cli_config_dir() if config_dir is None else Path(config_dir)
    candidate = cli_config_dir / DEFAULT_AUTH_FILENAME
    if candidate.is_file():
        return candidate

    return None


def load_auth_config(auth_path: str | Path) -> SapAuthConfig:
    """Load a SAPHive auth TOML file."""
    path = Path(auth_path)
    if not path.exists():
        raise ConfigurationError(
            "SAPHive auth file does not exist.",
            details={"path": str(path)},
        )

    if not path.is_file():
        raise ConfigurationError(
            "SAPHive auth path is not a file.",
            details={"path": str(path)},
        )

    try:
        with path.open("rb") as auth_file:
            raw_config = tomllib.load(auth_file)
    except tomllib.TOMLDecodeError as exc:
        raise ConfigurationError(
            "SAPHive auth file is not valid TOML.",
            details={"path": str(path), "error": str(exc)},
        ) from exc

    try:
        return SapAuthConfig.model_validate(raw_config)
    except ValidationError as exc:
        raise ConfigurationError(
            "SAPHive auth file validation failed.",
            details={"path": str(path), "errors": exc.errors()},
        ) from exc


def resolve_credentials(
    *,
    connection_name: str,
    auth_config: SapAuthConfig,
    environ: Mapping[str, str] | None = None,
    password_prompt: PasswordPrompt | None = None,
) -> SapCredentials:
    """Resolve credentials for an SAP connection profile."""
    profile = auth_config.connections.get(connection_name)
    if profile is None:
        raise SapConnectionError(
            "SAP auth profile was not found for the selected connection.",
            details={"connection": connection_name},
        )

    password = _resolve_password(
        profile,
        environ=os.environ if environ is None else environ,
        password_prompt=password_prompt or getpass.getpass,
    )
    return SapCredentials(username=profile.username, password=password)


def _resolve_password(
    profile: SapAuthProfile,
    *,
    environ: Mapping[str, str],
    password_prompt: PasswordPrompt,
) -> str:
    if profile.password_env is not None:
        password = environ.get(profile.password_env)
        if password is None or password == "":
            raise SapConnectionError(
                "SAP password environment variable is not set.",
                details={"password_env": profile.password_env},
            )

        return password

    return password_prompt(f"SAP password for {profile.username}: ")


def _script_directory(script_path: Path) -> Path:
    return script_path if script_path.is_dir() else script_path.parent
