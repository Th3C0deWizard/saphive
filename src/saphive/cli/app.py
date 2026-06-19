"""Command-line frontend for SAPHive."""

import json
from pathlib import Path
from typing import Annotated
from uuid import uuid4

import typer
from dotenv import find_dotenv, load_dotenv

from saphive.core import (
    ConfigurationError,
    ExecutionStatus,
    SapCleanupMode,
    SapConnectionMode,
    SAPHiveConfig,
    SAPHiveError,
    SapRuntime,
    find_cli_config,
    load_config,
)
from saphive.core.results import ScriptExecutionResult

SUCCESS_EXIT_CODE = 0
FAILURE_EXIT_CODE = 1
VALIDATION_FAILED_EXIT_CODE = 2

app = typer.Typer(help="SAPHive command-line frontend.", no_args_is_help=True)
scripts_app = typer.Typer(help="Discover, inspect, validate, and run SAPHive scripts.")
app.add_typer(scripts_app, name="scripts")


ConfigOption = Annotated[
    Path | None,
    typer.Option(
        "--config",
        "-c",
        help="Path to a SAPHive TOML configuration file.",
        exists=True,
        dir_okay=False,
        readable=True,
    ),
]
InputOption = Annotated[
    list[str] | None,
    typer.Option(
        "--input",
        "-i",
        help="Runtime input as KEY=VALUE. Can be provided multiple times.",
    ),
]
InputJsonOption = Annotated[
    str | None,
    typer.Option(
        "--input-json",
        help="Runtime input as a JSON object.",
    ),
]
InputFileOption = Annotated[
    Path | None,
    typer.Option(
        "--input-file",
        help="Path to a JSON file containing runtime input.",
        exists=True,
        dir_okay=False,
        readable=True,
    ),
]
SapModeOption = Annotated[
    SapConnectionMode | None,
    typer.Option("--sap-mode", help="SAP connection mode override: auto, attach, or open."),
]
SapConnectionOption = Annotated[
    str | None,
    typer.Option("--sap-connection", help="SAP connection profile name override."),
]
SapAuthFileOption = Annotated[
    Path | None,
    typer.Option(
        "--sap-auth-file",
        help="Path to .saphive.auth.toml for opening SAP connections.",
        exists=True,
        dir_okay=False,
        readable=True,
    ),
]
SapCleanupOption = Annotated[
    SapCleanupMode | None,
    typer.Option(
        "--sap-cleanup",
        help="SAP cleanup after run: none, created-sessions, connection, or application.",
    ),
]
SapCleanupForceOption = Annotated[
    bool,
    typer.Option(
        "--sap-cleanup-force",
        help="Allow connection cleanup for attached/pre-existing SAP connections.",
    ),
]


@scripts_app.command("list")
def list_scripts(config: ConfigOption = None) -> None:
    """List discovered SAPHive scripts."""
    runtime = _build_runtime(config)
    try:
        registry = runtime.discover_scripts()
    except SAPHiveError as exc:
        _exit_with_error(exc)

    entries = registry.entries()
    if not entries:
        typer.echo("No SAPHive scripts discovered.")
        raise typer.Exit(SUCCESS_EXIT_CODE)

    for entry in entries:
        typer.echo(f"{entry.name}\t{entry.bot.description}\t{entry.source_path}")


@scripts_app.command("inspect")
def inspect_script(script_name: str, config: ConfigOption = None) -> None:
    """Inspect metadata for a discovered SAPHive script."""
    runtime = _build_runtime(config)
    try:
        entry = runtime.discover_scripts().get(script_name)
    except SAPHiveError as exc:
        _exit_with_error(exc)

    bot = entry.bot
    typer.echo(f"name: {bot.name}")
    typer.echo(f"description: {bot.description}")
    typer.echo(f"path: {entry.source_path}")
    typer.echo(f"source_kind: {entry.source_kind.value}")
    if bot.version is not None:
        typer.echo(f"version: {bot.version}")
    if bot.author is not None:
        typer.echo(f"author: {bot.author}")
    if bot.tags:
        typer.echo(f"tags: {', '.join(bot.tags)}")
    typer.echo("input_schema:")
    typer.echo(json.dumps(bot.input_model.model_json_schema(), indent=2, ensure_ascii=False))
    typer.echo("output_schema:")
    typer.echo(json.dumps(bot.output_model.model_json_schema(), indent=2, ensure_ascii=False))


@scripts_app.command("validate")
def validate_named_script(
    script_name: str,
    config: ConfigOption = None,
    inputs: InputOption = None,
    input_json: InputJsonOption = None,
    input_file: InputFileOption = None,
    sap_mode: SapModeOption = None,
    sap_connection: SapConnectionOption = None,
    sap_auth_file: SapAuthFileOption = None,
) -> None:
    """Validate a discovered SAPHive script."""
    runtime = _build_runtime(config, sap_mode, sap_connection, sap_auth_file)
    result = runtime.validate_bot(script_name, inputs=_parse_inputs(inputs, input_json, input_file))
    _print_result(result)
    raise typer.Exit(_exit_code_for_result(result))


@scripts_app.command("run")
def run_named_script(
    script_name: str,
    config: ConfigOption = None,
    inputs: InputOption = None,
    input_json: InputJsonOption = None,
    input_file: InputFileOption = None,
    sap_mode: SapModeOption = None,
    sap_connection: SapConnectionOption = None,
    sap_auth_file: SapAuthFileOption = None,
    sap_cleanup: SapCleanupOption = None,
    sap_cleanup_force: SapCleanupForceOption = False,
) -> None:
    """Run a discovered SAPHive script."""
    runtime = _build_runtime(
        config,
        sap_mode,
        sap_connection,
        sap_auth_file,
        sap_cleanup=sap_cleanup,
        sap_cleanup_force=sap_cleanup_force,
    )
    run_id = uuid4().hex
    typer.echo(f"run_id: {run_id}")
    result = runtime.run_bot(
        script_name,
        inputs=_parse_inputs(inputs, input_json, input_file),
        run_id=run_id,
    )
    _print_result(result, include_run_id=False)
    raise typer.Exit(_exit_code_for_result(result))


@app.command("run")
def run_script_path(
    script_path: Path,
    config: ConfigOption = None,
    inputs: InputOption = None,
    input_json: InputJsonOption = None,
    input_file: InputFileOption = None,
    sap_mode: SapModeOption = None,
    sap_connection: SapConnectionOption = None,
    sap_auth_file: SapAuthFileOption = None,
    sap_cleanup: SapCleanupOption = None,
    sap_cleanup_force: SapCleanupForceOption = False,
) -> None:
    """Run a SAPHive script from an explicit file or package path."""
    runtime = _build_runtime(
        config,
        sap_mode,
        sap_connection,
        sap_auth_file,
        script_path,
        sap_cleanup=sap_cleanup,
        sap_cleanup_force=sap_cleanup_force,
    )
    run_id = uuid4().hex
    typer.echo(f"run_id: {run_id}")
    result = runtime.run_bot(
        script_path,
        inputs=_parse_inputs(inputs, input_json, input_file),
        run_id=run_id,
    )
    _print_result(result, include_run_id=False)
    raise typer.Exit(_exit_code_for_result(result))


def main() -> None:
    """Run the SAPHive CLI application."""
    app()


def _build_runtime(
    config_path: Path | None,
    sap_mode: SapConnectionMode | None = None,
    sap_connection: str | None = None,
    sap_auth_file: Path | None = None,
    script_path: Path | None = None,
    *,
    sap_cleanup: SapCleanupMode | None = None,
    sap_cleanup_force: bool = False,
) -> SapRuntime:
    try:
        config, resolved_config_path = _load_cli_config(config_path, script_path=script_path)
        _load_cli_environment(config_path=resolved_config_path, script_path=script_path)
    except ConfigurationError as exc:
        _exit_with_error(exc)

    return SapRuntime(
        config=config,
        config_path=resolved_config_path,
        auth_file=sap_auth_file,
        sap_mode=sap_mode,
        sap_connection=sap_connection,
        sap_cleanup=sap_cleanup,
        sap_cleanup_force=sap_cleanup_force,
    )


def _load_cli_environment(
    *,
    config_path: Path | None = None,
    script_path: Path | None = None,
) -> tuple[Path, ...]:
    candidates: list[Path] = []
    if script_path is not None:
        candidates.append(_script_env_path(script_path))
    if config_path is not None:
        candidates.append(config_path.parent / ".env")

    discovered = find_dotenv(usecwd=True)
    if discovered:
        candidates.append(Path(discovered))

    loaded_paths: list[Path] = []
    seen_paths: set[Path] = set()
    for candidate in candidates:
        path = candidate.resolve()
        if path in seen_paths or not path.is_file():
            continue

        seen_paths.add(path)
        load_dotenv(path, override=False)
        loaded_paths.append(path)

    return tuple(loaded_paths)


def _script_env_path(script_path: Path) -> Path:
    return (script_path if script_path.is_dir() else script_path.parent) / ".env"


def _load_cli_config(
    config_path: Path | None,
    *,
    script_path: Path | None = None,
    config_dir: Path | None = None,
) -> tuple[SAPHiveConfig, Path | None]:
    if config_path is not None:
        return load_config(config_path), config_path

    default_config_path = find_cli_config(script_path=script_path, config_dir=config_dir)
    if default_config_path is None:
        return SAPHiveConfig(), None

    return load_config(default_config_path), default_config_path


def _parse_inputs(
    raw_inputs: list[str] | None,
    input_json: str | None = None,
    input_file: Path | None = None,
) -> dict[str, object]:
    inputs: dict[str, object] = {}
    if input_file is not None:
        inputs.update(_json_object(input_file.read_text(encoding="utf-8"), source=str(input_file)))
    if input_json is not None:
        inputs.update(_json_object(input_json, source="--input-json"))
    for raw_input in raw_inputs or []:
        key, separator, value = raw_input.partition("=")
        if separator == "" or key.strip() == "":
            raise typer.BadParameter("Runtime inputs must use KEY=VALUE format.")

        inputs[key] = value

    return inputs


def _json_object(raw_value: str, *, source: str) -> dict[str, object]:
    try:
        value = json.loads(raw_value)
    except json.JSONDecodeError as exc:
        raise typer.BadParameter(f"{source} must be valid JSON.") from exc
    if not isinstance(value, dict):
        raise typer.BadParameter(f"{source} must contain a JSON object.")
    return value


def _print_result(result: ScriptExecutionResult, *, include_run_id: bool = True) -> None:
    typer.echo(f"script: {result.script_name}")
    if include_run_id:
        typer.echo(f"run_id: {result.run_id}")
    typer.echo(f"status: {result.status.value}")
    if result.error is not None:
        typer.echo(f"error: {result.error}", err=True)
    if result.outputs:
        for key, value in sorted(result.outputs.items()):
            typer.echo(f"output.{key}: {value}")
    if result.logs_path is not None:
        typer.echo(f"logs: {result.logs_path}")


def _exit_code_for_result(result: ScriptExecutionResult) -> int:
    if result.status is ExecutionStatus.SUCCESS:
        return SUCCESS_EXIT_CODE
    if result.status is ExecutionStatus.VALIDATION_FAILED:
        return VALIDATION_FAILED_EXIT_CODE

    return FAILURE_EXIT_CODE


def _exit_with_error(error: SAPHiveError) -> None:
    typer.echo(f"error: {error.message}", err=True)
    raise typer.Exit(FAILURE_EXIT_CODE)


if __name__ == "__main__":
    main()
