from pathlib import Path

from typer.testing import CliRunner

from saphive import SapCleanupMode
from saphive.cli.app import VALIDATION_FAILED_EXIT_CODE, _load_cli_config, app

runner = CliRunner()
EXPLICIT_TIMEOUT_SECONDS = 240
OS_CONFIG_TIMEOUT_SECONDS = 180


def test_cli_scripts_list_shows_discovered_scripts(tmp_path: Path) -> None:
    script_path = tmp_path / "create_notifications.py"
    _write_script(script_path, "create_notifications")
    config_path = _write_config(tmp_path)

    result = runner.invoke(app, ["scripts", "list", "--config", str(config_path)])

    assert result.exit_code == 0
    assert "create_notifications" in result.output
    assert "Runtime test script." in result.output
    assert str(script_path.resolve()) in result.output


def test_cli_scripts_list_handles_empty_registry(tmp_path: Path) -> None:
    config_path = _write_config(tmp_path)

    result = runner.invoke(app, ["scripts", "list", "--config", str(config_path)])

    assert result.exit_code == 0
    assert "No SAPHive scripts discovered." in result.output


def test_cli_scripts_inspect_shows_metadata(tmp_path: Path) -> None:
    _write_script(tmp_path / "inspect_me.py", "inspect_me")
    config_path = _write_config(tmp_path)

    result = runner.invoke(app, ["scripts", "inspect", "inspect_me", "--config", str(config_path)])

    assert result.exit_code == 0
    assert "name: inspect_me" in result.output
    assert "description: Runtime test script." in result.output
    assert "source_kind: file" in result.output
    assert "version: 0.1.0" in result.output


def test_cli_scripts_validate_calls_core_runtime(tmp_path: Path) -> None:
    _write_script(
        tmp_path / "validate_me.py",
        "validate_me",
        validate_body='ctx.set_output("validated", ctx.inputs["order"])',
    )
    config_path = _write_config(tmp_path)

    result = runner.invoke(
        app,
        [
            "scripts",
            "validate",
            "validate_me",
            "--config",
            str(config_path),
            "--input",
            "order=4000001",
        ],
    )

    assert result.exit_code == 0
    assert "status: success" in result.output
    assert "output.validated: 4000001" in result.output


def test_cli_scripts_run_calls_core_runtime(tmp_path: Path) -> None:
    _write_script(
        tmp_path / "run_me.py",
        "run_me",
        validate_body='ctx.set_output("validated", True)',
        run_body='ctx.set_output("ran", True)',
    )
    config_path = _write_config(tmp_path)

    result = runner.invoke(app, ["scripts", "run", "run_me", "--config", str(config_path)])

    assert result.exit_code == 0
    assert "run_id:" in result.output
    assert "status: success" in result.output
    assert "output.validated: True" in result.output
    assert "output.ran: True" in result.output


def test_cli_root_run_accepts_explicit_script_path(tmp_path: Path) -> None:
    script_path = tmp_path / "path_script.py"
    _write_script(script_path, "path_script", run_body='ctx.set_output("ran_from_path", True)')

    result = runner.invoke(app, ["run", str(script_path)])

    assert result.exit_code == 0
    assert "run_id:" in result.output
    assert "script: path_script" in result.output
    assert "output.ran_from_path: True" in result.output


def test_cli_root_run_loads_config_from_script_directory(tmp_path: Path) -> None:
    script_dir = tmp_path / "script-dir"
    script_dir.mkdir()
    script_path = script_dir / "path_script.py"
    _write_script(
        script_path,
        "path_script",
        run_body='ctx.set_output("timeout", ctx.config.runtime.default_timeout_seconds)',
    )
    (script_dir / "saphive.toml").write_text(
        """
[runtime]
default_timeout_seconds = 120
""".strip(),
        encoding="utf-8",
    )

    result = runner.invoke(app, ["run", str(script_path)])

    assert result.exit_code == 0
    assert "output.timeout: 120" in result.output


def test_cli_run_accepts_sap_cleanup_options(tmp_path: Path) -> None:
    script_path = tmp_path / "cleanup_options.py"
    _write_script(script_path, "cleanup_options", run_body='ctx.set_output("ran", True)')

    result = runner.invoke(
        app,
        [
            "run",
            str(script_path),
            "--sap-cleanup",
            SapCleanupMode.NONE.value,
            "--sap-cleanup-force",
        ],
    )

    assert result.exit_code == 0
    assert "status: success" in result.output


def test_cli_config_file_flag_overrides_script_directory_config(tmp_path: Path) -> None:
    script_dir = tmp_path / "script-dir"
    explicit_dir = tmp_path / "explicit"
    script_dir.mkdir()
    explicit_dir.mkdir()
    script_path = script_dir / "job.py"
    script_config = script_dir / "saphive.toml"
    explicit_config = explicit_dir / "custom.toml"
    script_config.write_text("[runtime]\ndefault_timeout_seconds = 120", encoding="utf-8")
    explicit_config.write_text(
        f"[runtime]\ndefault_timeout_seconds = {EXPLICIT_TIMEOUT_SECONDS}",
        encoding="utf-8",
    )

    config, resolved_path = _load_cli_config(explicit_config, script_path=script_path)

    assert resolved_path == explicit_config
    assert config.runtime.default_timeout_seconds == EXPLICIT_TIMEOUT_SECONDS


def test_cli_loads_config_from_os_config_directory(tmp_path: Path) -> None:
    config_dir = tmp_path / "cli-config"
    config_dir.mkdir()
    config_path = config_dir / "saphive.toml"
    config_path.write_text(
        f"[runtime]\ndefault_timeout_seconds = {OS_CONFIG_TIMEOUT_SECONDS}",
        encoding="utf-8",
    )

    config, resolved_path = _load_cli_config(None, config_dir=config_dir)

    assert resolved_path == config_path
    assert config.runtime.default_timeout_seconds == OS_CONFIG_TIMEOUT_SECONDS


def test_cli_returns_validation_exit_code_for_validation_failure(tmp_path: Path) -> None:
    _write_script(
        tmp_path / "invalid_input.py",
        "invalid_input",
        imports="from saphive import ScriptValidationError",
        validate_body='raise ScriptValidationError("Input file missing")',
    )
    config_path = _write_config(tmp_path)

    result = runner.invoke(
        app,
        ["scripts", "validate", "invalid_input", "--config", str(config_path)],
    )

    assert result.exit_code == VALIDATION_FAILED_EXIT_CODE
    assert "status: validation_failed" in result.output
    assert "error: Input file missing" in result.output


def test_cli_returns_failure_for_missing_named_script(tmp_path: Path) -> None:
    config_path = _write_config(tmp_path)

    result = runner.invoke(app, ["scripts", "run", "missing", "--config", str(config_path)])

    assert result.exit_code == 1
    assert "status: failed" in result.output
    assert "error: SAPHive script was not found in the registry." in result.output


def test_cli_rejects_invalid_input_format(tmp_path: Path) -> None:
    _write_script(tmp_path / "input_script.py", "input_script")
    config_path = _write_config(tmp_path)

    result = runner.invoke(
        app,
        ["scripts", "validate", "input_script", "--config", str(config_path), "--input", "bad"],
    )

    assert result.exit_code != 0
    assert "Runtime inputs must use KEY=VALUE format." in result.output


def _write_config(script_dir: Path) -> Path:
    config_path = script_dir / "saphive.toml"
    config_path.write_text(
        f'''
[paths]
scripts = ["{script_dir.as_posix()}"]
'''.strip(),
        encoding="utf-8",
    )
    return config_path


def _write_script(
    path: Path,
    script_name: str,
    *,
    imports: str = "",
    validate_body: str = "pass",
    run_body: str = "pass",
) -> None:
    path.write_text(
        f'''
{imports}

SCRIPT_NAME = "{script_name}"
DESCRIPTION = "Runtime test script."
VERSION = "0.1.0"

def validate(ctx):
    {validate_body}

def run(ctx):
    {run_body}
'''.strip(),
        encoding="utf-8",
    )
