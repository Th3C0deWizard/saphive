from pathlib import Path

import pytest

from saphive import (
    ConfigurationError,
    LoggingConfig,
    SapConfig,
    SAPHiveConfig,
    find_default_config,
    load_config,
    load_default_config,
)

DEFAULT_TIMEOUT_SECONDS = 300
CUSTOM_TIMEOUT_SECONDS = 120


def test_config_defaults_are_safe_for_wsl_unit_tests() -> None:
    config = SAPHiveConfig()

    assert config.paths.scripts == ()
    assert config.runtime.default_timeout_seconds == DEFAULT_TIMEOUT_SECONDS
    assert config.logging.level == "INFO"
    assert config.logging.directory == Path("logs")
    assert config.sap.connection_name is None
    assert config.sap.client is None
    assert config.sap.language == "EN"


def test_logging_config_normalizes_level() -> None:
    config = LoggingConfig(level="debug")

    assert config.level == "DEBUG"


def test_sap_config_normalizes_language() -> None:
    config = SapConfig(language="es")

    assert config.language == "ES"


def test_load_config_from_explicit_toml_file(tmp_path: Path) -> None:
    config_path = tmp_path / "saphive.toml"
    config_path.write_text(
        """
[paths]
scripts = ["automations", "department_scripts"]

[runtime]
default_timeout_seconds = 120

[logging]
level = "debug"
directory = "runtime_logs"
jsonl_enabled = true

[sap]
connection_name = "PRD"
client = "100"
language = "en"
""".strip(),
        encoding="utf-8",
    )

    config = load_config(config_path)

    assert config.paths.scripts == (
        (tmp_path / "automations").resolve(),
        (tmp_path / "department_scripts").resolve(),
    )
    assert config.runtime.default_timeout_seconds == CUSTOM_TIMEOUT_SECONDS
    assert config.logging.level == "DEBUG"
    assert config.logging.directory == (tmp_path / "runtime_logs").resolve()
    assert config.logging.jsonl_enabled is True
    assert config.sap.connection_name == "PRD"
    assert config.sap.client == "100"
    assert config.sap.language == "EN"


def test_load_config_preserves_absolute_paths(tmp_path: Path) -> None:
    script_dir = (tmp_path / "absolute_scripts").resolve()
    log_dir = (tmp_path / "absolute_logs").resolve()
    config_path = tmp_path / "saphive.toml"
    config_path.write_text(
        f"""
[paths]
scripts = ["{script_dir.as_posix()}"]

[logging]
directory = "{log_dir.as_posix()}"
""".strip(),
        encoding="utf-8",
    )

    config = load_config(config_path)

    assert config.paths.scripts == (script_dir,)
    assert config.logging.directory == log_dir


def test_load_config_raises_for_missing_file(tmp_path: Path) -> None:
    missing_path = tmp_path / "missing.toml"

    with pytest.raises(ConfigurationError, match="does not exist") as exc_info:
        load_config(missing_path)

    assert exc_info.value.details == {"path": str(missing_path)}


def test_load_config_raises_for_invalid_toml(tmp_path: Path) -> None:
    config_path = tmp_path / "saphive.toml"
    config_path.write_text("[paths", encoding="utf-8")

    with pytest.raises(ConfigurationError, match="valid TOML"):
        load_config(config_path)


def test_load_config_raises_for_invalid_value(tmp_path: Path) -> None:
    config_path = tmp_path / "saphive.toml"
    config_path.write_text(
        """
[runtime]
default_timeout_seconds = 0
""".strip(),
        encoding="utf-8",
    )

    with pytest.raises(ConfigurationError, match="validation failed") as exc_info:
        load_config(config_path)

    assert "errors" in exc_info.value.details


def test_find_default_config_searches_parent_directories(tmp_path: Path) -> None:
    config_path = tmp_path / "saphive.toml"
    nested_dir = tmp_path / "one" / "two"
    nested_dir.mkdir(parents=True)
    config_path.write_text("", encoding="utf-8")

    assert find_default_config(nested_dir) == config_path


def test_load_default_config_raises_when_missing(tmp_path: Path) -> None:
    with pytest.raises(ConfigurationError, match="No default"):
        load_default_config(tmp_path)
