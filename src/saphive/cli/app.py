"""Command-line frontend for SAPHive."""

from pathlib import Path
from typing import Annotated
from uuid import uuid4

import typer

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
        typer.echo(f"{entry.name}\t{entry.metadata.description}\t{entry.source_path}")


@scripts_app.command("inspect")
def inspect_script(script_name: str, config: ConfigOption = None) -> None:
    """Inspect metadata for a discovered SAPHive script."""
    runtime = _build_runtime(config)
    try:
        entry = runtime.discover_scripts().get(script_name)
    except SAPHiveError as exc:
        _exit_with_error(exc)

    metadata = entry.metadata
    typer.echo(f"name: {metadata.name}")
    typer.echo(f"description: {metadata.description}")
    typer.echo(f"path: {entry.source_path}")
    typer.echo(f"source_kind: {entry.source_kind.value}")
    if metadata.version is not None:
        typer.echo(f"version: {metadata.version}")
    if metadata.author is not None:
        typer.echo(f"author: {metadata.author}")
    if metadata.tags:
        typer.echo(f"tags: {', '.join(metadata.tags)}")


@scripts_app.command("validate")
def validate_named_script(
    script_name: str,
    config: ConfigOption = None,
    inputs: InputOption = None,
    sap_mode: SapModeOption = None,
    sap_connection: SapConnectionOption = None,
    sap_auth_file: SapAuthFileOption = None,
) -> None:
    """Validate a discovered SAPHive script."""
    runtime = _build_runtime(config, sap_mode, sap_connection, sap_auth_file)
    result = runtime.validate_script(script_name, inputs=_parse_inputs(inputs))
    _print_result(result)
    raise typer.Exit(_exit_code_for_result(result))


@scripts_app.command("run")
def run_named_script(
    script_name: str,
    config: ConfigOption = None,
    inputs: InputOption = None,
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
    result = runtime.run_script(script_name, inputs=_parse_inputs(inputs), run_id=run_id)
    _print_result(result, include_run_id=False)
    raise typer.Exit(_exit_code_for_result(result))


@app.command("run")
def run_script_path(
    script_path: Path,
    config: ConfigOption = None,
    inputs: InputOption = None,
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
    result = runtime.run_script(script_path, inputs=_parse_inputs(inputs), run_id=run_id)
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


def _parse_inputs(raw_inputs: list[str] | None) -> dict[str, object]:
    inputs: dict[str, object] = {}
    for raw_input in raw_inputs or []:
        key, separator, value = raw_input.partition("=")
        if separator == "" or key.strip() == "":
            raise typer.BadParameter("Runtime inputs must use KEY=VALUE format.")

        inputs[key] = value

    return inputs


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
