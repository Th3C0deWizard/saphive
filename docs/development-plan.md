# SAPHive Development Plan

This document defines the step-by-step development plan for SAPHive. It keeps the current single-package strategy: one Python distribution named `saphive` containing Core, CLI, SAP abstractions, and script runtime modules.

The plan is intentionally incremental. Each phase should produce a small, testable result before moving to the next phase.

## Current Status

Phases 1 through 13 are implemented. SAPHive currently has a working Core runtime, CLI, SAP connection resolver, auth-file handling, local logging, and Windows SAP GUI boundary. Current work is focused on internal publication readiness: packaging, documentation, examples, and distribution hygiene.

## Development Rules

- Keep SAPHive Core as the owner of runtime behavior.
- Keep the CLI as a thin frontend over Core.
- Keep automation scripts external to SAPHive.
- Avoid scheduler responsibilities inside SAPHive.
- Keep SAP GUI-specific code isolated behind interfaces.
- Use the project virtual environment Python executable for all Python commands.
- Do not require SAP GUI for generic unit tests.

From WSL, use:

```bash
./venv/Scripts/python.exe -m pytest
./venv/Scripts/python.exe -m ruff check .
./venv/Scripts/python.exe -m ruff format .
./venv/Scripts/python.exe -m mypy src tests
./venv/Scripts/python.exe -m build
```

## Phase 0: Planning Baseline

Goal: establish the design boundaries before implementation begins.

Steps:

1. Keep `docs/architecture.md` as the architecture source of truth.
2. Keep `AGENTS.md` aligned with terminology and environment rules.
3. Keep `pyproject.toml` configured for a single `saphive` distribution.
4. Confirm that SAPHive scripts are called automation scripts, not plugins.
5. Confirm that scheduling is external to SAPHive.

Exit criteria:

- Architecture responsibilities are documented.
- WSL development and Windows runtime assumptions are documented.
- Packaging strategy is documented.

## Phase 1: Repository Skeleton

Goal: create the minimum source and test structure without implementing SAP behavior yet.

Planned structure:

```text
src/
  saphive/
    __init__.py
    core/
    sap/
    scripts/
    cli/
    utils/
tests/
  unit/
```

Steps:

1. Create the `src/saphive` package structure.
2. Add placeholder module files only when they are needed by the first implementation slice.
3. Create the `tests` structure.
4. Add a minimal import smoke test.
5. Run formatting, linting, type checking, and tests through `./venv/Scripts/python.exe`.

Exit criteria:

- Package imports cleanly.
- Tooling commands can run from WSL.
- No SAP GUI dependency is required for tests.

## Phase 2: Core Domain Types

Goal: define stable Core types before building execution behavior.

Initial objects:

```text
SapContext
SapRuntime
ScriptMetadata
ScriptExecutionResult
ExecutionStatus
SAPHiveError
```

Steps:

1. Define the error hierarchy.
2. Define execution status values.
3. Define script metadata shape.
4. Define execution result shape.
5. Define the minimal `SapContext` fields required by automation scripts.
6. Export only deliberate public objects from `saphive.__init__`.

Exit criteria:

- Core types are typed and documented in code.
- Unit tests cover construction and basic validation.
- Public imports match the script contract expectations.

## Phase 3: Configuration Model

Goal: provide a typed configuration model used by Core and CLI.

Configuration areas:

```text
paths
runtime
logging
sap
```

Steps:

1. Define configuration models.
2. Support loading configuration from a default project file.
3. Support explicit config file paths for CLI and Python callers.
4. Normalize script directory paths.
5. Keep secrets out of the first configuration model unless there is a concrete secure storage decision.

Exit criteria:

- Configuration can be loaded and validated without SAP GUI.
- Invalid configuration produces clear domain errors.
- Tests cover missing files, invalid fields, and path normalization.

## Phase 4: Script Contract

Goal: formalize what makes a Python file or package a valid SAPHive script.

Required contract:

```python
SCRIPT_NAME = "create_notifications"
DESCRIPTION = "Create SAP maintenance notifications from an Excel file."

def validate(ctx: SapContext) -> None:
    ...

def run(ctx: SapContext) -> None:
    ...
```

Steps:

1. Define required module attributes.
2. Define accepted function signatures.
3. Define contract validation errors.
4. Define metadata extraction behavior.
5. Decide which optional metadata fields are accepted but not required.

Exit criteria:

- Valid scripts pass contract validation.
- Invalid scripts fail with actionable errors.
- Contract validation does not execute business logic.

## Phase 5: Script Discovery and Registry

Goal: discover configured automation scripts and expose them through a registry.

Steps:

1. Discover scripts from configured directories.
2. Support single-file scripts.
3. Support package-directory scripts.
4. Build a registry keyed by script name.
5. Detect duplicate script names.
6. Keep discovery separate from execution.

Exit criteria:

- Registry can list available scripts.
- Registry can return metadata without running scripts.
- Discovery errors are clear and typed.

## Phase 6: Script Loader

Goal: load a specific SAPHive script from a registry entry or explicit path.

Steps:

1. Load a script by registry name.
2. Load a script by explicit file path.
3. Load a script by package directory.
4. Validate the contract after loading.
5. Avoid leaking temporary import names into user-facing behavior.

Exit criteria:

- Loaded scripts expose metadata, `validate(ctx)`, and `run(ctx)`.
- Invalid scripts fail before runtime execution.
- Tests cover named loading and explicit path loading.

## Phase 7: Runtime Context Construction

Goal: build `SapContext` consistently for every execution entry point.

Steps:

1. Define runtime input handling.
2. Attach configuration to the context.
3. Attach script metadata to the context.
4. Attach a logger to the context.
5. Attach run identifiers and working paths.
6. Attach a SAP abstraction object without forcing an active SAP GUI connection during validation.

Exit criteria:

- Context construction is deterministic.
- Validation can run without connecting to SAP unless explicitly required by the script.
- Tests verify context fields.

## Phase 8: SAP Abstraction Boundary

Goal: create the boundary between SAPHive Core and SAP GUI Scripting.

Steps:

1. Define a SAP session interface used by scripts.
2. Define Windows-specific implementation boundaries.
3. Normalize common SAP connection and session errors.
4. Keep `pywin32` usage inside Windows-specific modules.
5. Provide test doubles for generic unit tests.

Exit criteria:

- Core can be tested without SAP GUI.
- Windows-specific behavior is isolated.
- SAP GUI failures map to SAPHive domain errors.

## Phase 9: Script Executor

Goal: implement the runtime execution flow in Core.

Execution sequence:

```text
load config
resolve script
load script
validate contract
build context
run script validate(ctx)
connect to SAP when needed
run script run(ctx)
capture result
log outcome
return execution result
```

Steps:

1. Implement validation-only execution.
2. Implement full script execution.
3. Capture successful results.
4. Capture validation failures.
5. Capture execution failures.
6. Return structured results instead of raw exceptions where appropriate.

Exit criteria:

- Core can validate and run test scripts.
- Results are structured and typed.
- Errors are logged and normalized.

## Phase 10: CLI Frontend

Goal: expose Core through command-line commands without duplicating runtime logic.

Planned commands:

```text
saphive scripts list
saphive scripts inspect <name>
saphive scripts validate <name>
saphive scripts run <name>
saphive run <path>
```

Steps:

1. Implement CLI app entry point.
2. Implement `scripts list` by calling Core registry behavior.
3. Implement `scripts inspect` by calling Core metadata behavior.
4. Implement `scripts validate` by calling Core validation behavior.
5. Implement `scripts run` by calling Core execution behavior.
6. Map Core errors to clear terminal output and exit codes.

Exit criteria:

- CLI contains no duplicated runtime behavior.
- CLI commands work with fake/test scripts.
- CLI tests do not require SAP GUI.

## Phase 11: SAP Connection Resolution

Goal: let Core and CLI determine which SAP connection a script run executes over, using a simple `auto | attach | open` model.

Connection modes:

```text
auto   -> attach to a matching existing connection, otherwise open a new one
attach -> attach to a matching existing connection only
open   -> always open a new SAP Logon connection
```

The default mode should be `auto`.

This phase establishes the connection boundary: Core/CLI owns connection selection and connection creation/attachment. Scripts receive a connection-scoped `ctx.sap` and manage sessions only within that connection.

Steps:

1. Add typed SAP connection profile configuration.
2. Add SAP connection mode values: `auto`, `attach`, and `open`.
3. Add CLI overrides for SAP mode and connection profile.
4. Define SAP GUI application/client abstraction.
5. Define SAP connection abstraction.
6. Implement attach to existing SAP GUI connection by configured profile.
7. Implement open SAP Logon connection by configured profile.
8. Implement `auto` mode: attach first, open if not found.
9. Build `SapContext` with a connection-scoped `ctx.sap` object before script `run(ctx)`.
10. Add fake SAP GUI objects for WSL-safe unit tests.

Detailed implementation flow:

```text
load config and CLI overrides
load script and validate contract
build validation context without SAP connection
run script validate(ctx)
if validation failed, return validation_failed result
resolve SAP connection only after validation succeeds
build run context with connection-scoped ctx.sap
run script run(ctx)
return structured result
```

Connection profile config shape:

```toml
[sap]
mode = "auto"
connection = "prd"

[sap.connections.prd]
sap_logon_name = "PRD"
client = "100"
language = "EN"
```

CLI overrides planned for this phase:

```text
--sap-mode auto|attach|open
--sap-connection <profile-name>
```

Mode behavior:

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

Windows implementation requirements:

- Attach to SAP GUI Scripting engine.
- Enumerate existing SAP GUI connections.
- Match existing connections by SAP Logon name, client, system name, or description where available.
- Open SAP Logon connection by `sap_logon_name`.
- Return a connection-scoped wrapper suitable for session operations.
- Map COM failures to SAPHive domain errors.
- Keep all COM imports guarded and Windows-specific.

Exit criteria:

- Core/CLI can select the SAP connection for a script run.
- `auto`, `attach`, and `open` modes are implemented.
- Scripts do not open or choose SAP connections directly.
- Generic tests do not require SAP GUI.
- Windows-specific COM usage remains isolated.

## Phase 12: SAP Auth File and Session APIs

Goal: support simple username/password authentication for opening SAP connections, while exposing session-management APIs to scripts within the already-selected connection.

Auth rules:

```text
auth is only needed for open or auto-open
credentials are not stored in saphive.toml
passwords are not accepted as normal CLI arguments
initial password sources are password_env and password_prompt
```

Steps:

1. Define `.saphive.auth.toml` format.
2. Implement auth file lookup: explicit `--sap-auth-file`, config directory, script directory, then OS-specific SAPHive CLI config directory.
3. Add typed auth profile configuration with `username`, `password_env`, and `password_prompt`.
4. Resolve password from environment variable for unattended usage.
5. Resolve password from prompt for manual usage.
6. Use username/password only when opening a new SAP connection.
7. Define connection-scoped `ctx.sap` session APIs.
8. Implement `ctx.sap.list_sessions()`.
9. Implement `ctx.sap.attach_session(index=0)`.
10. Implement `ctx.sap.create_session()`.
11. Implement `ctx.sap.active_session()` if SAP GUI exposes an active session reliably.
12. Explicitly avoid password CLI arguments.

Auth file shape:

```toml
[connections.prd]
username = "MY_SAP_USER"
password_env = "SAPHIVE_PRD_PASSWORD"
```

Manual auth shape:

```toml
[connections.prd]
username = "MY_SAP_USER"
password_prompt = true
```

Auth lookup rules:

```text
1. Use explicit --sap-auth-file when provided.
2. Otherwise look for .saphive.auth.toml beside the active saphive.toml.
3. Otherwise look for .saphive.auth.toml beside the runtime-executed script.
4. Otherwise look for .saphive.auth.toml in the OS-specific SAPHive CLI config directory.
```

Auth behavior:

```text
attach:
  no auth required

open:
  username required
  password_env or password_prompt required

auto:
  no auth required if attach succeeds
  auth required if open fallback is needed
```

Connection-scoped script API:

```text
ctx.sap.connection_name
ctx.sap.list_sessions()
ctx.sap.attach_session(index=0)
ctx.sap.create_session()
ctx.sap.active_session()
```

Session API required for MVP:

```text
session.start_transaction(transaction_code)
session.set_text(element_id, value)
session.get_text(element_id)
session.press(element_id)
session.status_bar_text()
```

The script-facing `ctx.sap` object must not expose APIs for opening or choosing SAP connections in the MVP.

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

Exit criteria:

- Users can configure SAP connection defaults in `saphive.toml`.
- Users can configure SAP auth references in `.saphive.auth.toml`.
- CLI can override non-secret SAP connection options.
- Scripts can create, attach, list, and use sessions inside the selected connection.
- Secrets are not stored in plain runtime config or passed as normal CLI arguments.
- Scheduler accounts can use documented environment-variable password flow.

MVP manual acceptance command:

```bash
saphive scripts run create_notifications \
  --config saphive.toml \
  --sap-mode auto \
  --sap-connection prd \
  --sap-auth-file .saphive.auth.toml
```

MVP acceptance script shape:

```python
def run(ctx: SapContext) -> None:
    session = ctx.sap.create_session()
    session.start_transaction("IW21")
    ctx.set_output("status", session.status_bar_text())
```

## Phase 13: Logging and Results

Goal: make execution auditable and scheduler-friendly, including SAP session metadata where available.

Steps:

1. Define standard log fields.
2. Include SAP connection, client, system, and session identifiers where available.
3. Add console logging for local usage.
4. Add local file logging.
5. Optionally add JSONL execution records.
6. Include log paths in execution results.
7. Keep logging configured through Core configuration.

Exit criteria:

- Each run has a run identifier.
- Each run returns a result object.
- SAP session metadata can be traced when scripts use SAP APIs.
- Failures include enough detail for a scheduler or operator.

## Phase 14: Packaging and Local Distribution

Goal: build and install SAPHive as one simple internal package.

Steps:

1. Keep the single distribution name `saphive`.
2. Keep the CLI entry point in the same package.
3. Build source and wheel distributions locally.
4. Install the wheel into a clean environment.
5. Verify import and CLI smoke checks.

Exit criteria:

- The package builds successfully.
- The installed package exposes the `saphive` command.
- Windows-only dependencies do not block WSL development.

## Phase 15: First External Automation Script Pilot

Goal: validate the runtime with one real-world automation script kept outside SAPHive Core.

Candidate script:

```text
create_notifications
```

Steps:

1. Create the script outside the SAPHive package.
2. Configure its directory as a script source.
3. Validate its contract.
4. Validate its input file.
5. Configure the connection profile and auth file.
6. Let Core/CLI resolve the SAP connection with `auto`, `attach`, or `open` mode.
7. In `run(ctx)`, create or attach to a dedicated SAP session through `ctx.sap`.
8. Run it manually on a Windows SAP machine.
9. Capture runtime gaps and update Core abstractions only when needed.

Exit criteria:

- One real automation runs through SAPHive runtime with Core/CLI-managed connection resolution and script-managed sessions.
- The script remains external to Core.
- Runtime gaps are documented before broadening the framework.

## Phase 16: Scheduler Integration Examples

Goal: prove that external schedulers can call SAPHive without SAPHive becoming a scheduler.

Planned examples:

```text
Windows Task Scheduler command
Prefect task calling SapRuntime
Airflow BashOperator command
```

Steps:

1. Document Windows Task Scheduler usage.
2. Document a Prefect integration example.
3. Document an Airflow integration example.
4. Document expected exit codes and result files.
5. Keep retry policy and monitoring outside SAPHive.

Exit criteria:

- Scheduler examples call the CLI or Core.
- SAPHive does not implement scheduling logic.
- Windows runtime constraints are documented.

## Phase 17: Hardening and Future Interfaces

Goal: prepare for future API, worker, and distributed execution without overbuilding now.

Steps:

1. Review Core API stability.
2. Review error categories.
3. Review configuration extensibility.
4. Review logging and execution result completeness.
5. Document API and worker boundaries before implementation.

Exit criteria:

- Core remains usable by CLI and Python callers.
- Future interfaces can call Core without duplicating runtime behavior.
- No full scheduler is introduced inside SAPHive.
