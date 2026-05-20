# Agent Instructions for SAPHive

SAPHive is a lightweight internal Python runtime and SDK for SAP GUI Scripting automation. The project is developed from WSL, but production SAP automation is intended to run on Windows machines with SAP GUI installed.

## Current Phase

The project is in the pre-alpha implementation and internal publication preparation phase.

Runtime code, package modules, docs, and example automation scripts may be updated when explicitly requested by the user.

## Architectural Rules

- SAPHive Core owns script discovery, loading, validation, execution, logging, configuration, error handling, and SAP abstraction.
- SAPHive CLI must remain a thin frontend over SAPHive Core.
- Automation scripts are external runtime-executed SAPHive scripts.
- Core/CLI should resolve the SAP connection for a script run using `auto`, `attach`, or `open` mode.
- User-written SAPHive scripts should manage SAP sessions explicitly through connection-scoped APIs exposed on `ctx.sap`.
- Scripts should not choose or open SAP connections directly unless a later explicit requirement changes this boundary.
- For independent automation bots, prefer creating or attaching to a dedicated SAP session inside the selected connection rather than relying on one global runtime-owned session.
- Do not describe automation scripts as plugins.
- Do not introduce plugin system, marketplace, or plugin architecture terminology.
- Scheduling belongs to external schedulers or orchestrators.
- SAPHive should remain compatible with Windows Task Scheduler, Prefect, Airflow, and future custom schedulers.
- Future web frontends, REST APIs, workers, and distributed execution should call Core instead of duplicating runtime behavior.

## Preferred Terminology

Use these terms:

- Automation scripts
- SAPHive scripts
- Runtime-executed scripts
- Script loader
- Script registry
- SAPHive runtime

Avoid these terms:

- Plugins
- Marketplace
- Plugin system

## Development Environment

This repository is developed from WSL. Actual SAP GUI automation is expected to run on Windows because SAP GUI Scripting depends on SAP GUI.

Always use the project virtual environment Python executable for Python commands.

The current repository virtual environment is Windows-style and lives under `venv/Scripts`. From WSL, prefer:

```bash
./venv/Scripts/python.exe -m pytest
./venv/Scripts/python.exe -m ruff check .
./venv/Scripts/python.exe -m ruff format .
./venv/Scripts/python.exe -m mypy src
```

Do not use bare commands such as:

```bash
python -m pytest
pytest
ruff check .
mypy src
```

On Windows runtime machines, prefer the project virtual environment Python executable:

```powershell
.\venv\Scripts\python.exe -m saphive scripts run create_notifications
```

If a native WSL virtual environment is created later, use `./venv/bin/python` and update this file and project documentation before changing command examples elsewhere.

## Windows Runtime Constraints

- SAP automation workers must run on Windows machines with SAP GUI installed.
- SAP GUI Scripting must be enabled and permitted by SAP policy.
- Scheduler accounts need access to SAP GUI and target SAP systems.
- Interactive desktop/session constraints may affect unattended execution.
- Keep SAP GUI-specific code isolated so non-SAP logic can be tested from WSL.
- Keep SAP connection resolution APIs in Core/SAP abstractions so Core/CLI can attach to existing connections or open new connections before script execution.
- Keep SAP session lifecycle APIs connection-scoped so scripts can list sessions, attach to existing sessions, create sessions, and run SAP GUI Scripting code over a selected session.
- Initial SAP authentication should remain simple: username/password for opening connections, with passwords resolved via `.saphive.auth.toml` references such as `password_env` or `password_prompt`, not raw password CLI arguments.
- CLI config/auth lookup order is: explicit value flags, explicit config/auth file flags, files beside the runtime-executed script, OS-specific SAPHive CLI config directory, then built-in defaults.
- Generic unit tests should not require SAP GUI.

## Coding Standards

- Prefer small, typed, maintainable modules.
- Keep architecture simple before adding framework-like abstractions.
- Use `src/` layout when implementation begins.
- Keep public Core APIs deliberate and stable.
- Do not duplicate Core behavior in CLI or future interfaces.
- Use clear domain errors for configuration, loading, validation, SAP connection, SAP session, SAP GUI, and script execution failures.

## Documentation Rules

- Keep `docs/architecture.md` aligned with major design decisions.
- Update documentation when changing terminology, runtime responsibilities, or execution boundaries.
- Document Windows-specific runtime assumptions explicitly.
- Document WSL development commands using the project virtual environment Python executable.

## Dependency Rules

- Keep runtime dependencies lightweight.
- Use Windows-only dependency markers for SAP GUI-specific packages such as `pywin32`.
- Put development tools under optional development dependencies.
- Prefer optional dependency groups for Excel, scheduling, or API integrations instead of forcing them into the base runtime.
