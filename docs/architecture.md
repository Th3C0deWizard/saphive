# SAPHive Architecture

SAPHive is a lightweight internal RPA runtime and SDK specialized in SAP GUI Scripting automation. Its purpose is to replace scattered Excel VBA macros with a maintainable, typed, Python-based architecture for discovering, validating, and executing SAP automation scripts.

This document defines the current pre-alpha architecture and the boundaries that should remain stable as SAPHive moves toward internal publication.

## Current Implementation

The current implementation provides SAPHive Core, a thin Typer CLI, script discovery/loading/validation/execution, local file logging, SAP connection resolution, SAP auth-file handling, and Windows SAP GUI Scripting integration behind isolated interfaces.

Implemented runtime behavior:

- `saphive scripts list`, `inspect`, `validate`, and `run` call Core APIs.
- `saphive run <path>` runs a script file or package by explicit path.
- `validate(ctx)` runs before SAP connection resolution.
- `run(ctx)` receives connection-scoped `ctx.sap` after Core resolves the SAP connection.
- Optional `cleanup(ctx)` runs after `run(ctx)` for script-owned resource cleanup.
- SAP connection modes are `auto`, `attach`, and `open`.
- `auto` attaches first, then opens the configured SAP Logon connection when attach is not available.
- SAP cleanup defaults to closing sessions created through `ctx.sap.create_session()`.
- Auth uses `.saphive.auth.toml` with `password_env` or `password_prompt`.
- Local auth files, logs, caches, and build artifacts are excluded from version control and source distributions.

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

## Source Layout

```text
src/saphive/
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

tests/
docs/
examples/
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
saphive scripts inspect create_sessions
saphive scripts validate create_sessions --config examples/scripts/saphive.toml
saphive scripts run create_sessions --config examples/scripts/saphive.toml
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

def cleanup(ctx: SapContext) -> None:
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
9. Run optional script cleanup(ctx).
10. Apply configured SAP cleanup policy.
11. Capture the result.
12. Log the outcome.
13. Return a structured execution result.
```

This flow should be the same regardless of whether execution comes from Python code, the CLI, Windows Task Scheduler, Prefect, Airflow, a future REST API, or a future worker service.

## SapContext

`SapContext` is the main object passed into automation scripts.

It should provide access to:

- Runtime configuration.
- Script metadata.
- Input parameters.
- Logger.
- SAP client/session management APIs.
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

Core and the CLI own SAP connection selection. A run chooses one SAP connection using configuration plus CLI overrides before the script executes. The selected connection is then exposed to the script as `ctx.sap`.

Scripts should manage sessions only within that selected connection. For each independent automation bot, the recommended pattern is to create one dedicated SAP session inside the script, execute all SAP GUI Scripting work over that returned session object, and let SAPHive close the created session during cleanup. Attaching to an existing session should be an explicit operational choice.

## SAP GUI Abstraction

Core should wrap SAP GUI Scripting enough to make scripts consistent and safer. Core/CLI should resolve the connection, and user-written SAPHive scripts should manage sessions explicitly within that resolved connection.

Potential abstractions:

```text
SapConnectionResolver
SapGuiClient
SapConnection
SapSession
SapElement
SapTransaction
SapWaiter
```

Responsibilities:

- Initialize access to SAP GUI Scripting.
- Attach to an existing SAP GUI application.
- Resolve the run connection using `auto`, `attach`, or `open` mode.
- Open a SAP Logon connection by configured connection profile.
- Attach to an existing connection by configured connection profile.
- Create a new session from an existing connection.
- Attach to an existing session within the selected connection.
- Select a system, client, and connection before script execution.
- Start transactions.
- Find controls.
- Set field values.
- Press buttons.
- Read values.
- Wait for screens.
- Handle SAP status bar messages.
- Normalize common SAP GUI Scripting errors.

The first implementation should not try to fully model SAP GUI. It should provide practical helpers around the real SAP GUI Scripting API.

Recommended script pattern:

```python
from saphive import SapContext

SCRIPT_NAME = "create_notifications"
DESCRIPTION = "Create SAP maintenance notifications."

def validate(ctx: SapContext) -> None:
    ...

def run(ctx: SapContext) -> None:
    session = ctx.sap.create_session()

    session.start_transaction("IW21")
    session.set_text("wnd[0]/usr/ctxtQMART", "M1")
    session.press("wnd[0]/tbar[0]/btn[11]")
```

`ctx.sap.create_session()` must identify a newly created SAP GUI session. If SAP GUI does not expose exactly one new session, SAPHive fails the run instead of returning another existing session.

Alternative attach pattern:

```python
def run(ctx: SapContext) -> None:
    session = ctx.sap.attach_session(index=0)
    session.start_transaction("IW22")
```

Core should support these flows without forcing one global runtime-owned SAP session. The connection is runtime-owned; sessions are script-managed.
SAPHive does not automatically rebind stale session wrappers to a different session index or refresh stale connection proxies. Scripts should keep using the session object returned by `create_session()` or `attach_session()`. COM lifecycle conflicts should be isolated by running conflicting COM owners on separate threads or explicit COM boundaries instead of relying on implicit SAP proxy recovery.

Scripts may define `cleanup(ctx)` for script-owned resources such as downloaded files,
workbooks, or custom COM objects. SAPHive always runs `cleanup(ctx)` after `run(ctx)`, including
when `run(ctx)` fails. SAPHive then applies its SAP cleanup policy.

## SAP Connection Resolution

SAPHive should keep connection selection simple. The runtime should support three connection modes:

| Mode | Behavior |
| --- | --- |
| `auto` | Try to attach to an existing matching SAP connection. If none exists, open a new connection using configured auth. |
| `attach` | Attach only. Fail if no matching SAP connection exists. |
| `open` | Always open a new SAP Logon connection using configured auth. |

Default mode should be `auto`.

The connection profile should live in `saphive.toml` because it is runtime configuration, not script code:

```toml
[sap]
mode = "auto"
connection = "prd"
cleanup = "created-sessions"
cleanup_force = false

[sap.connections.prd]
sap_logon_name = "PRD"
client = "100"
language = "EN"
```

CLI flags should override config for operational flexibility:

```bash
saphive scripts run create_notifications \
  --config saphive.toml \
  --sap-mode auto \
  --sap-connection prd
```

The runtime should resolve the connection before script `run(ctx)` executes. After resolution, `ctx.sap` should be a connection-scoped object that exposes session APIs only:

```text
ctx.sap.connection_name
ctx.sap.list_sessions()
ctx.sap.attach_session(index=0)
ctx.sap.create_session()
ctx.sap.with_connection(callback)
ctx.sap.close_created_sessions()
ctx.sap.close_connection(force=False)
ctx.sap.close_application()
```

MVP connection resolution timing:

```text
1. Load runtime configuration.
2. Load and validate the SAPHive script contract.
3. Build a validation context without opening SAP.
4. Run script validate(ctx).
5. If validation succeeds, resolve SAP connection using auto, attach, or open mode.
6. Build or update runtime context with connection-scoped ctx.sap.
7. Run script run(ctx).
8. Run optional script cleanup(ctx).
9. Apply SAP cleanup policy.
10. Return structured execution result and logs.
```

This avoids opening SAP GUI when script input validation fails.

Cleanup policies are:

| Policy | Behavior |
| --- | --- |
| `none` | Do not close SAP resources automatically. |
| `created-sessions` | Close sessions created through `ctx.sap.create_session()` during the run. This is the default. |
| `connection` | Close the selected connection only if SAPHive opened it, unless forced. |
| `application` | Close the SAP GUI application explicitly. |

CLI `--sap-cleanup-force` allows connection cleanup for attached/pre-existing connections and
should be used deliberately.

Exact mode behavior:

```text
auto:
  try attach existing matching connection
  if not found, open new connection using auth

attach:
  attach existing matching connection
  fail if not found

open:
  always open new connection using auth
```

The connection profile matching rules should be simple for the MVP:

- Match by configured SAP Logon entry name when possible.
- Match by client when available.
- Match by system name/description when available from SAP GUI Scripting.
- If multiple matches exist, use the first match and log enough metadata to diagnose ambiguity.

## SAP Authentication and Secrets

For the initial implementation, authentication should be username/password only for opening a connection. `attach` mode should not need credentials because it attaches to an already authenticated SAP GUI connection.

SAPHive should not store raw SAP passwords in `saphive.toml` or require passwords through normal CLI flags. Connection details stay in `saphive.toml`; credentials live in a separate auth file or are resolved through environment variables/prompt.

Recommended auth file name:

```text
.saphive.auth.toml
```

Auth file lookup order:

1. Explicit path from `--sap-auth-file`.
2. Same directory as the active `saphive.toml`.
3. Same directory as the runtime-executed script.
4. OS-specific SAPHive CLI config directory.

CLI configuration lookup order:

1. Explicit path from `--config`.
2. Same directory as the runtime-executed script, for explicit script-path runs.
3. OS-specific SAPHive CLI config directory.
4. Built-in default config values.

Example configuration:

```toml
[sap]
mode = "auto"
connection = "prd"

[sap.connections.prd]
sap_logon_name = "PRD"
client = "100"
language = "EN"
```

Example `.saphive.auth.toml`:

```toml
[connections.prd]
username = "MY_SAP_USER"
password_env = "SAPHIVE_PRD_PASSWORD"
```

Example CLI override:

```bash
saphive scripts run create_notifications \
  --config saphive.toml \
  --sap-mode auto \
  --sap-connection prd \
  --sap-auth-file .saphive.auth.toml
```

Avoid this pattern:

```bash
saphive scripts run create_notifications --sap-password secret
```

Passwords passed as CLI arguments can leak through shell history, process lists, logs, and scheduler definitions.

For manual local usage, SAPHive may support `password_prompt = true` in the auth file. For unattended scheduler usage, prefer `password_env` initially.

MVP auth rules:

- `attach` mode must not require auth details.
- `open` mode requires `username` and either `password_env` or `password_prompt`.
- `auto` mode requires auth details only when attach fails and Core must open a new connection.
- Raw password values must not be accepted in `saphive.toml`.
- Raw password CLI flags must not be implemented.
- Missing auth for a required open must fail with a clear `SapConnectionError`.

## MVP SAP Runtime Acceptance Criteria

The MVP is complete when a Windows machine with SAP GUI installed can run a custom SAPHive script over a real SAP connection.

Required manual command:

```bash
saphive scripts run create_notifications \
  --config saphive.toml \
  --sap-mode auto \
  --sap-connection prd \
  --sap-auth-file .saphive.auth.toml
```

Required script behavior:

```python
from saphive import SapContext

SCRIPT_NAME = "create_notifications"
DESCRIPTION = "Create SAP maintenance notifications."

def validate(ctx: SapContext) -> None:
    ...

def run(ctx: SapContext) -> None:
    session = ctx.sap.create_session()
    session.start_transaction("IW21")
    ctx.set_output("status", session.status_bar_text())
```

The MVP must prove these capabilities:

- `auto` attaches to an existing matching SAP connection when available.
- `auto` opens a new SAP connection when no match exists and auth is available.
- `attach` fails clearly when no matching SAP connection exists.
- `open` opens a new SAP connection using username/password auth.
- Script `validate(ctx)` can run without opening SAP.
- Script `run(ctx)` receives a connection-scoped `ctx.sap`.
- Script can list, attach, or create sessions within the selected connection.
- Script can execute SAP GUI Scripting operations over a session.
- Failures are normalized into SAPHive domain errors and structured results.
- Generic WSL unit tests still do not require SAP GUI.

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
mode = "auto"
connection = "prd"

[sap.connections.prd]
sap_logon_name = "PRD"
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
