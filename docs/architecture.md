# SAPHive Architecture Plan

SAPHive is a lightweight internal RPA runtime and SDK specialized in SAP GUI Scripting automation. Its purpose is to replace scattered Excel VBA macros with a maintainable, typed, Python-based architecture for discovering, validating, and executing SAP automation scripts.

This document defines the initial planning architecture. It intentionally avoids implementation details that should be decided later during proof-of-concept work.

## Project Goals

- Provide a clean Python runtime for SAP GUI Scripting automation.
- Treat business automations as external runtime-executed SAPHive scripts.
- Allow scripts to be executed from Python code, a CLI, and future external interfaces.
- Keep scheduling and orchestration outside SAPHive at first.
- Support Windows execution because SAP GUI Scripting depends on SAP GUI.
- Support development from WSL while ensuring all Python execution uses the project virtual environment.
- Keep the first architecture simple, modular, typed, and maintainable.
- Leave room for future web, REST API, worker, and distributed execution models.

## Non-Goals

- SAPHive is not a full scheduler in the initial design.
- SAPHive is not a monitoring dashboard.
- SAPHive is not a script marketplace.
- SAPHive scripts are not plugins.
- SAPHive should not duplicate orchestration responsibilities handled by tools such as Prefect, Airflow, or Windows Task Scheduler.

## Terminology

Preferred terms:

- Automation scripts
- SAPHive scripts
- Runtime-executed scripts
- Script loader
- Script registry
- SAPHive runtime

Avoided terms:

- Plugins
- Marketplace
- Plugin system

## High-Level Architecture

```text
External Scheduler / User / Future API
                |
                v
        SAPHive CLI / Future API
                |
                v
          SAPHive Core
                |
                v
   Script Loader / Registry / Runtime
                |
                v
      External SAPHive Scripts
                |
                v
       SAP GUI Scripting / SAP GUI
```

SAPHive Core is the center of the architecture. CLI, schedulers, future APIs, and worker services should call Core instead of duplicating runtime behavior.

## Component Responsibilities

| Component | Responsibility |
| --- | --- |
| SAPHive Core | Owns runtime behavior, SAP abstractions, configuration, validation, logging, error handling, script discovery, script loading, and script execution. |
| SAPHive CLI | Thin command-line frontend over Core. |
| Automation Scripts | External Python files or packages following the SAPHive script contract. |
| Scheduler / Orchestrator | Owns timing, retries, monitoring, dependencies, and scheduled execution. |
| Future API / Web UI / Workers | Additional frontends over Core, not separate runtimes. |

## Proposed Source Layout

```text
saphive/
  core/
    context.py
    runtime.py
    config.py
    logging.py
    errors.py
    validation.py
    results.py

  sap/
    session.py
    gui.py
    waits.py
    selectors.py
    exceptions.py

  scripts/
    contract.py
    discovery.py
    loader.py
    registry.py
    metadata.py
    executor.py

  cli/
    app.py
    commands.py
    formatters.py

  utils/
    paths.py
    imports.py
    typing.py
```

The initial implementation should prefer a `src/` layout once code is added:

```text
src/
  saphive/
    ...
tests/
docs/
```

## SAPHive Core

SAPHive Core should act as both SDK and runtime.

Core owns:

- SAP GUI Scripting session management.
- Runtime context construction.
- Script discovery from configured directories.
- Script loading from file paths or package directories.
- Script contract validation.
- Script input validation.
- Script metadata inspection.
- Script execution.
- Structured logging.
- Runtime configuration.
- Error normalization.
- Execution result reporting.

Core does not own:

- Scheduling.
- Full job retry policy.
- Long-running orchestration.
- Monitoring dashboards.
- CLI-specific formatting.
- Web routing.

Potential public Core objects:

```text
SapContext
SapRuntime
ScriptRegistry
ScriptLoader
ScriptMetadata
ScriptExecutionResult
SapSessionManager
SapGuiClient
```

## SAPHive CLI

The CLI should be a thin frontend over SAPHive Core.

Suggested commands:

```text
saphive scripts list
saphive scripts inspect create_notifications
saphive scripts validate create_notifications --input input.xlsx
saphive scripts run create_notifications --input input.xlsx
saphive run path/to/script.py --input input.xlsx
```

CLI responsibilities:

- Parse command-line arguments.
- Load SAPHive configuration.
- Call Core runtime methods.
- Print user-friendly output.
- Return meaningful process exit codes.

The CLI should not:

- Discover scripts directly.
- Load Python files directly.
- Execute script functions directly.
- Manage SAP sessions independently.
- Duplicate validation logic.

## Automation Script Model

Automation scripts are external runtime-executed SAPHive scripts. They are not part of SAPHive Core and should not be treated as plugins.

A script may be:

- A single Python file.
- A Python package directory.
- Loaded from a configured script directory.
- Loaded from an explicit file path.

Recommended initial contract:

```python
from saphive import SapContext

SCRIPT_NAME = "create_notifications"
DESCRIPTION = "Create SAP maintenance notifications from an Excel file."

def validate(ctx: SapContext) -> None:
    pass

def run(ctx: SapContext) -> None:
    pass
```

Optional future metadata:

```text
VERSION
AUTHOR
INPUT_SCHEMA
TAGS
REQUIRES_SAP_TRANSACTION
```

The first implementation should keep the script contract simple and stable.

## Runtime Execution Flow

```text
1. Load configuration.
2. Resolve the script reference.
3. Discover or load the script.
4. Validate the script contract.
5. Build SapContext.
6. Run script validate(ctx).
7. Establish or reuse a SAP session.
8. Run script run(ctx).
9. Capture the result.
10. Log the outcome.
11. Return a structured execution result.
```

This flow should be the same regardless of whether execution comes from Python code, the CLI, Windows Task Scheduler, Prefect, Airflow, a future REST API, or a future worker service.

## SapContext

`SapContext` is the main object passed into automation scripts.

It should provide access to:

- Runtime configuration.
- Script metadata.
- Input parameters.
- Logger.
- SAP session abstraction.
- Execution identifiers.
- Working directories.
- Validation helpers.
- Result and output helpers.

Conceptual shape:

```text
SapContext
  config
  logger
  sap
  inputs
  script
  run_id
  workdir
  output
```

Scripts should interact with SAP through `ctx.sap` rather than creating their own raw SAP GUI session objects unless there is a clear escape-hatch requirement.

## SAP GUI Abstraction

Core should wrap SAP GUI Scripting enough to make scripts consistent and safer.

Potential abstractions:

```text
SapSessionManager
SapGuiClient
SapSession
SapElement
SapTransaction
SapWaiter
```

Responsibilities:

- Connect to an active SAP GUI instance.
- Select a system, client, and session.
- Start transactions.
- Find controls.
- Set field values.
- Press buttons.
- Read values.
- Wait for screens.
- Handle SAP status bar messages.
- Normalize common SAP GUI Scripting errors.

The first implementation should not try to fully model SAP GUI. It should provide practical helpers around the real SAP GUI Scripting API.

## Script Discovery

Core should support configured script directories.

Example conceptual configuration:

```toml
[paths]
scripts = [
  "automations",
  "department_scripts"
]

[runtime]
default_timeout_seconds = 300
log_level = "INFO"

[sap]
connection_name = "PRD"
client = "100"
language = "EN"
```

Script discovery should produce a script registry.

The registry should know:

- Script name.
- Script path.
- Description.
- Metadata.
- Contract validity.
- How to load the script when requested.

Discovery should not execute business logic.

## Script Loading

The script loader should handle:

- Explicit `.py` file paths.
- Package directories.
- Named scripts from the registry.
- Import isolation concerns.
- Clear errors for invalid contracts.

Loading should validate that:

- `SCRIPT_NAME` exists.
- `DESCRIPTION` exists.
- `validate(ctx)` exists.
- `run(ctx)` exists.
- Function signatures are compatible with the expected contract.

## Validation Model

There are two validation levels.

| Validation Type | Purpose |
| --- | --- |
| Contract validation | Checks whether the SAPHive script follows the expected structure. |
| Input validation | Checks whether runtime inputs are valid for a specific script. |

The script's own `validate(ctx)` should validate business input, not runtime internals.

Examples:

- Excel file exists.
- Required columns exist.
- SAP order number format is valid.
- Required parameters are present.
- Target SAP transaction is allowed.

## Logging

Core should provide structured logging.

Recommended fields:

```text
run_id
script_name
script_path
user
machine
sap_connection
transaction
status
started_at
finished_at
duration
```

Initial logging outputs:

- Console logs.
- Rotating local log files.
- Optional JSONL execution logs.

Future-compatible logging outputs:

- Database.
- REST API.
- Central logging service.
- Worker telemetry.

## Error Handling

Use normalized SAPHive errors so external callers can respond consistently.

Suggested error hierarchy:

```text
SAPHiveError
ConfigurationError
ScriptDiscoveryError
ScriptLoadError
ScriptContractError
ScriptValidationError
SapConnectionError
SapSessionError
SapGuiError
ScriptExecutionError
```

The CLI should map these errors to clear messages and meaningful exit codes.

## Execution Results

Core should return a structured result object.

Conceptual fields:

```text
script_name
run_id
status
started_at
finished_at
duration
logs_path
outputs
error
```

Suggested statuses:

```text
success
validation_failed
failed
cancelled
```

Structured results make SAPHive easier to call from schedulers, Python code, future APIs, and worker services.

## Scheduler Integration

SAPHive should be scheduler-compatible, not scheduler-owned.

Recommended integration models:

```text
Windows Task Scheduler -> saphive scripts run create_notifications
Prefect -> Python task calls SapRuntime.run(...)
Airflow -> BashOperator or PythonOperator calls SAPHive
Future scheduler -> Calls CLI, REST API, or worker queue
```

The scheduler owns:

- Timing.
- Retries.
- Monitoring.
- Dependencies.
- Notifications.
- Job history.
- Concurrency policy.

SAPHive owns:

- Script execution.
- SAP session abstraction.
- Script validation.
- Logging.
- Runtime result reporting.

## WSL Development and Windows Runtime

This project is currently developed from WSL, but the SAP GUI automation runtime is intended to run on Windows because SAP GUI Scripting requires SAP GUI.

Development rules:

- Use the Python executable from the project virtual environment for all Python commands.
- Do not rely on the system Python from WSL or Windows.
- Run tests, linters, formatters, type checkers, and local scripts through the virtual environment.
- Keep SAP GUI-specific code isolated so non-SAP parts can be tested from WSL.
- Avoid assuming SAP GUI is available during generic unit tests.

The current repository virtual environment is Windows-style and lives under `venv/Scripts`. From WSL, use the project virtual environment executable directly:

```bash
./venv/Scripts/python.exe -m pytest
./venv/Scripts/python.exe -m ruff check .
./venv/Scripts/python.exe -m ruff format .
./venv/Scripts/python.exe -m mypy src
```

If a native WSL virtual environment is created later, use `./venv/bin/python` and update this document before changing command examples elsewhere.

Expected Windows runtime command pattern once deployed on Windows:

```powershell
.\venv\Scripts\python.exe -m saphive scripts run create_notifications
```

Important runtime constraints:

- Actual SAP execution must happen on Windows machines with SAP GUI installed.
- SAP GUI Scripting must be enabled on the client and permitted by SAP/server policy.
- Scheduler service accounts need access to SAP GUI and the required SAP systems.
- Interactive desktop/session constraints may affect unattended execution.
- Multiple SAP sessions on a single worker machine should be controlled carefully.

## Future Evolution

Future interfaces should call the same Core runtime.

Possible future architecture:

```text
REST API -> Core
Web frontend -> REST API -> Core
Worker service -> Core
Queue consumer -> Core
Distributed SAP workers -> Core
```

Future distributed model:

```text
Web UI / API
     |
     v
Job Queue
     |
     v
Windows SAP Worker Machines
     |
     v
SAPHive Core + SAP GUI
```

This allows SAPHive to grow without turning the initial codebase into a full orchestration platform.

## Initial Milestones

1. Finalize architecture and terminology.
2. Define the Core public API boundary.
3. Define `SapContext` responsibilities.
4. Define the SAPHive script contract.
5. Define script discovery and loading behavior.
6. Define CLI commands as thin Core wrappers.
7. Define local logging and execution result models.
8. Define Windows SAP session constraints.
9. Build a minimal proof-of-concept runtime.
10. Add scheduler integration examples after Core is stable.

## Key Decisions

| Decision | Recommendation |
| --- | --- |
| Main runtime owner | SAPHive Core |
| CLI role | Thin frontend |
| Script model | External runtime-executed SAPHive scripts |
| Script discovery | Owned by Core |
| Script execution | Owned by Core |
| SAP abstraction | Owned by Core |
| Scheduling | External scheduler |
| Initial execution target | Windows |
| Current development environment | WSL |
| Future frontend support | Web/API/worker should call Core |
| Initial complexity | Keep small and typed |

## Project Description

SAPHive is a lightweight Python runtime and SDK for discovering, validating, and executing SAP GUI Scripting automation scripts in a maintainable, scheduler-friendly way.
