"""Configuration models and loading helpers for SAPHive Core."""

import tomllib
from enum import StrEnum
from pathlib import Path
from typing import Any

from platformdirs import user_config_path
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from saphive.core.errors import ConfigurationError

DEFAULT_CONFIG_FILENAMES = ("saphive.toml",)
DEFAULT_APP_NAME = "saphive"
LOG_LEVELS = frozenset({"CRITICAL", "ERROR", "WARNING", "INFO", "DEBUG"})
SAP_LANGUAGE_CODE_LENGTH = 2


class SapConnectionMode(StrEnum):
    """SAP connection resolution modes for a script run."""

    AUTO = "auto"
    ATTACH = "attach"
    OPEN = "open"


class SapCleanupMode(StrEnum):
    """SAP cleanup policy applied after a script run."""

    NONE = "none"
    CREATED_SESSIONS = "created-sessions"
    CONNECTION = "connection"
    APPLICATION = "application"


class PathsConfig(BaseModel):
    """Filesystem paths used by the SAPHive runtime."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    scripts: tuple[Path, ...] = Field(default_factory=tuple)


class RuntimeConfig(BaseModel):
    """General runtime configuration."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    default_timeout_seconds: int = Field(default=300, gt=0)


class LoggingConfig(BaseModel):
    """Logging configuration for SAPHive runs."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    level: str = "INFO"
    directory: Path = Path("logs")
    jsonl_enabled: bool = False

    @field_validator("level")
    @classmethod
    def validate_level(cls, level: str) -> str:
        """Normalize and validate configured log levels."""
        normalized = level.upper()
        if normalized not in LOG_LEVELS:
            allowed = ", ".join(sorted(LOG_LEVELS))
            raise ValueError(f"Invalid log level '{level}'. Expected one of: {allowed}.")

        return normalized


class SapConnectionProfile(BaseModel):
    """Non-secret SAP connection profile."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    sap_logon_name: str
    client: str | None = None
    language: str = "EN"

    @field_validator("language")
    @classmethod
    def normalize_language(cls, language: str) -> str:
        """Normalize SAP language codes to uppercase."""
        return _normalize_sap_language(language)


class SapConfig(BaseModel):
    """SAP GUI connection preferences without storing secrets."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    mode: SapConnectionMode = SapConnectionMode.AUTO
    connection: str | None = None
    cleanup: SapCleanupMode = SapCleanupMode.CREATED_SESSIONS
    cleanup_force: bool = False
    connections: dict[str, SapConnectionProfile] = Field(default_factory=dict)


def _normalize_sap_language(language: str) -> str:
    normalized = language.upper()
    if len(normalized) != SAP_LANGUAGE_CODE_LENGTH:
        raise ValueError("SAP language must be a two-letter code.")

    return normalized


class SAPHiveConfig(BaseModel):
    """Root configuration model used by SAPHive Core and frontends."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    paths: PathsConfig = Field(default_factory=PathsConfig)
    runtime: RuntimeConfig = Field(default_factory=RuntimeConfig)
    logging: LoggingConfig = Field(default_factory=LoggingConfig)
    sap: SapConfig = Field(default_factory=SapConfig)


def load_config(config_path: str | Path) -> SAPHiveConfig:
    """Load and validate SAPHive configuration from an explicit TOML file path."""
    path = Path(config_path)
    if not path.exists():
        raise ConfigurationError(
            "SAPHive configuration file does not exist.",
            details={"path": str(path)},
        )

    if not path.is_file():
        raise ConfigurationError(
            "SAPHive configuration path is not a file.",
            details={"path": str(path)},
        )

    try:
        with path.open("rb") as config_file:
            raw_config = tomllib.load(config_file)
    except tomllib.TOMLDecodeError as exc:
        raise ConfigurationError(
            "SAPHive configuration file is not valid TOML.",
            details={"path": str(path), "error": str(exc)},
        ) from exc

    return _build_config(raw_config, base_dir=path.parent)


def find_default_config(start: str | Path | None = None) -> Path | None:
    """Find the nearest default SAPHive configuration file from a starting directory."""
    current = Path.cwd() if start is None else Path(start)
    if current.is_file():
        current = current.parent

    for directory in (current, *current.parents):
        for filename in DEFAULT_CONFIG_FILENAMES:
            candidate = directory / filename
            if candidate.is_file():
                return candidate

    return None


def default_cli_config_dir() -> Path:
    """Return the OS-specific user config directory for SAPHive CLI files."""
    return user_config_path(DEFAULT_APP_NAME, appauthor=False)


def find_cli_config(
    *,
    script_path: str | Path | None = None,
    config_dir: str | Path | None = None,
) -> Path | None:
    """Find CLI config using script-local, OS config directory, then code defaults."""
    if script_path is not None:
        script_dir = _script_directory(Path(script_path))
        candidate = script_dir / DEFAULT_CONFIG_FILENAMES[0]
        if candidate.is_file():
            return candidate

    cli_config_dir = default_cli_config_dir() if config_dir is None else Path(config_dir)
    candidate = cli_config_dir / DEFAULT_CONFIG_FILENAMES[0]
    if candidate.is_file():
        return candidate

    return None


def load_default_config(start: str | Path | None = None) -> SAPHiveConfig:
    """Load the nearest default SAPHive configuration file."""
    config_path = find_default_config(start)
    if config_path is None:
        raise ConfigurationError(
            "No default SAPHive configuration file was found.",
            details={"filenames": DEFAULT_CONFIG_FILENAMES},
        )

    return load_config(config_path)


def _build_config(raw_config: dict[str, Any], *, base_dir: Path) -> SAPHiveConfig:
    try:
        config = SAPHiveConfig.model_validate(raw_config)
    except ValidationError as exc:
        raise ConfigurationError(
            "SAPHive configuration validation failed.",
            details={"errors": exc.errors()},
        ) from exc

    return _normalize_paths(config, base_dir=base_dir)


def _normalize_paths(config: SAPHiveConfig, *, base_dir: Path) -> SAPHiveConfig:
    scripts = tuple(_resolve_path(script_path, base_dir) for script_path in config.paths.scripts)
    log_directory = _resolve_path(config.logging.directory, base_dir)

    return config.model_copy(
        update={
            "paths": config.paths.model_copy(update={"scripts": scripts}),
            "logging": config.logging.model_copy(update={"directory": log_directory}),
        }
    )


def _resolve_path(path: Path, base_dir: Path) -> Path:
    if path.is_absolute():
        return path.resolve()

    return (base_dir / path).resolve()


def _script_directory(script_path: Path) -> Path:
    return script_path if script_path.is_dir() else script_path.parent
