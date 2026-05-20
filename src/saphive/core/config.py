"""Configuration models and loading helpers for SAPHive Core."""

import tomllib
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from saphive.core.errors import ConfigurationError

DEFAULT_CONFIG_FILENAMES = ("saphive.toml",)
LOG_LEVELS = frozenset({"CRITICAL", "ERROR", "WARNING", "INFO", "DEBUG"})
SAP_LANGUAGE_CODE_LENGTH = 2


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


class SapConfig(BaseModel):
    """SAP GUI connection preferences without storing secrets."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    connection_name: str | None = None
    client: str | None = None
    language: str = "EN"

    @field_validator("language")
    @classmethod
    def normalize_language(cls, language: str) -> str:
        """Normalize SAP language codes to uppercase."""
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
