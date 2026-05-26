# SAPHive Milestones

This document is a practical checklist for moving SAPHive from planning to a working internal runtime.

Each milestone should be completed with tests and documentation updates before moving to the next one.

## Milestone 0: Planning Foundation

Status: in progress

Checklist:

- [x] Define project purpose.
- [x] Define SAPHive Core responsibility.
- [x] Define SAPHive CLI responsibility.
- [x] Define automation script terminology.
- [x] Define external scheduler boundary.
- [x] Document WSL development and Windows runtime constraints.
- [x] Create initial `pyproject.toml`.
- [x] Create `AGENTS.md`.
- [x] Create architecture document.
- [x] Create development plan.
- [x] Create packaging plan.

Exit criteria:

- The team can explain what SAPHive owns and what it does not own.
- The team can explain how development happens from WSL and runtime execution happens on Windows.

## Milestone 1: Project Skeleton

Status: complete

Checklist:

- [x] Create `src/saphive` package.
- [x] Create package subdirectories for `core`, `sap`, `scripts`, `cli`, and `utils`.
- [x] Create `tests` directory.
- [x] Add basic package import test.
- [x] Confirm package can be imported through the virtual environment Python executable.
- [x] Run `ruff`, `mypy`, and `pytest` through `./venv/Scripts/python.exe`.

Exit criteria:

- The package skeleton imports correctly.
- Tooling runs from WSL using the project virtual environment.

## Milestone 2: Core Types and Errors

Status: complete

Checklist:

- [x] Define SAPHive domain error hierarchy.
- [x] Define execution status values.
- [x] Define script metadata model.
- [x] Define execution result model.
- [x] Define initial `SapContext` model.
- [x] Export deliberate public Core objects.
- [x] Add unit tests for types and errors.

Exit criteria:

- Core has stable initial data structures.
- Scripts can type against `SapContext`.
- Errors are typed and meaningful.

## Milestone 3: Configuration

Status: complete

Checklist:

- [x] Define configuration model.
- [x] Define script path configuration.
- [x] Define runtime configuration.
- [x] Define logging configuration.
- [x] Define SAP connection configuration fields.
- [x] Implement config loading from explicit path.
- [x] Implement default config lookup if needed.
- [x] Add validation tests.

Exit criteria:

- Configuration can be loaded without SAP GUI.
- Invalid configuration produces a SAPHive configuration error.

## Milestone 4: Script Contract Validation

Status: complete

Checklist:

- [x] Define required script attributes.
- [x] Define required script functions.
- [x] Validate `SCRIPT_NAME`.
- [x] Validate `DESCRIPTION`.
- [x] Validate `validate(ctx)` signature.
- [x] Validate `run(ctx)` signature.
- [x] Extract script metadata.
- [x] Add valid and invalid script test cases.

Exit criteria:

- SAPHive can identify valid and invalid automation scripts.
- Contract validation does not run business logic.

## Milestone 5: Script Discovery and Registry

Status: complete

Checklist:

- [x] Discover single-file scripts from configured directories.
- [x] Discover package-directory scripts from configured directories.
- [x] Build script registry.
- [x] Detect duplicate script names.
- [x] Support metadata listing.
- [x] Add tests for empty directories.
- [x] Add tests for invalid scripts.
- [x] Add tests for duplicate names.

Exit criteria:

- SAPHive can list known automation scripts.
- Discovery does not execute automation logic.

## Milestone 6: Script Loading

Status: complete

Checklist:

- [x] Load script by registry name.
- [x] Load script by explicit file path.
- [x] Load script by package directory.
- [x] Validate contract after loading.
- [x] Return loaded script object or equivalent runtime representation.
- [x] Add tests for load success and load failure paths.

Exit criteria:

- SAPHive can load a selected automation script safely.
- Invalid scripts fail before runtime execution.

## Milestone 7: Runtime Context

Status: complete

Checklist:

- [x] Create `SapContext` from runtime inputs.
- [x] Attach config to context.
- [x] Attach script metadata to context.
- [x] Attach logger to context.
- [x] Attach run ID to context.
- [x] Attach working paths to context.
- [x] Attach SAP abstraction placeholder or lazy session object.
- [x] Add unit tests for context construction.

Exit criteria:

- Every execution path gets a consistent context.
- Validation can run without forcing a SAP GUI connection.

## Milestone 8: SAP GUI Boundary

Status: complete

Checklist:

- [x] Define SAP abstraction interface.
- [x] Define Windows-specific SAP GUI implementation boundary.
- [x] Guard `pywin32` imports from generic WSL test paths.
- [x] Define SAP connection errors.
- [x] Define SAP session errors.
- [x] Define SAP GUI operation errors.
- [x] Add test doubles for SAP sessions.

Exit criteria:

- Generic tests do not require SAP GUI.
- Windows SAP implementation is isolated.
- SAP failures map to SAPHive domain errors.

## Milestone 9: Core Runtime Executor

Status: complete

Checklist:

- [x] Implement validation-only flow.
- [x] Implement full run flow.
- [x] Call script `validate(ctx)`.
- [x] Call script `run(ctx)`.
- [x] Capture successful result.
- [x] Capture validation failure result.
- [x] Capture execution failure result.
- [x] Add tests with fake automation scripts.

Exit criteria:

- Core can validate and run test automation scripts.
- Execution returns structured results.
- Runtime errors are normalized.

## Milestone 10: CLI Frontend

Status: complete

Checklist:

- [x] Implement CLI entry point.
- [x] Implement `saphive scripts list`.
- [x] Implement `saphive scripts inspect <name>`.
- [x] Implement `saphive scripts validate <name>`.
- [x] Implement `saphive scripts run <name>`.
- [x] Implement `saphive run <path>`.
- [x] Map domain errors to exit codes.
- [x] Add CLI tests with fake automation scripts.

Exit criteria:

- CLI calls Core for runtime behavior.
- CLI does not duplicate script discovery, loading, validation, or execution.

## Milestone 11: SAP Connection Resolution

Status: complete

Checklist:

- [x] Add typed SAP connection profile configuration.
- [x] Add SAP connection mode values: `auto`, `attach`, and `open`.
- [x] Add CLI overrides for SAP mode and connection profile.
- [x] Define SAP GUI application/client abstraction.
- [x] Define SAP connection abstraction.
- [x] Implement attach to existing SAP GUI connection by configured profile.
- [x] Implement open SAP Logon connection by configured profile.
- [x] Implement `auto` mode: attach first, open if not found.
- [x] Build `SapContext` with a connection-scoped `ctx.sap` before script `run(ctx)`.
- [x] Ensure script `validate(ctx)` runs before SAP connection resolution.
- [x] Match existing SAP connections by profile fields where SAP GUI exposes them.
- [x] Map COM connection failures to SAPHive domain errors.
- [x] Add fake SAP GUI objects for WSL-safe unit tests.

Exit criteria:

- Core/CLI can select the SAP connection for a script run.
- `auto`, `attach`, and `open` modes are implemented.
- Scripts do not open or choose SAP connections directly.
- SAP is not opened when script validation fails.
- Windows-specific COM usage remains isolated.
- Generic tests do not require SAP GUI.

## Milestone 12: SAP Auth File and Session APIs

Status: complete

Checklist:

- [x] Define `.saphive.auth.toml` format.
- [x] Implement auth file lookup by explicit path, config directory, script directory, then OS-specific SAPHive CLI config directory.
- [x] Add typed auth profile configuration with `username`, `password_env`, and `password_prompt`.
- [x] Resolve password from environment variable for unattended usage.
- [x] Resolve password from prompt for manual usage.
- [x] Use username/password only when opening a new SAP connection.
- [x] Require auth only for `open` and `auto` fallback-to-open.
- [x] Define connection-scoped `ctx.sap` session APIs.
- [x] Implement `ctx.sap.list_sessions()`.
- [x] Implement `ctx.sap.attach_session(index=0)`.
- [x] Implement `ctx.sap.create_session()`.
- [x] Remove implicit `ctx.sap.active_session()` default-session selection.
- [x] Explicitly avoid password CLI arguments.
- [x] Document scheduler-safe environment-variable password usage.
- [x] Add a Windows manual acceptance test command to docs.

Exit criteria:

- Users can configure SAP connection defaults in `saphive.toml`.
- Users can configure SAP auth references in `.saphive.auth.toml`.
- Scripts can manage sessions only inside the selected connection.
- Secrets are not stored in plain runtime config or passed as normal CLI arguments.
- MVP can run a custom script over a real SAP connection on Windows.

## Milestone 13: Logging and Result Files

Status: complete

Checklist:

- [x] Define standard log fields.
- [x] Include SAP connection/session metadata where available.
- [x] Add console logging.
- [x] Add local file logging.
- [x] Decide whether JSONL execution records are required initially.
- [x] Include log path in execution result.
- [x] Add tests for result shape.

Exit criteria:

- Runs are traceable by run ID.
- Results are useful for CLI users and schedulers.
- SAP session usage can be traced when scripts use SAP APIs.

## Milestone 14: Build and Install

Status: complete

Checklist:

- [x] Confirm package metadata.
- [x] Confirm build backend works.
- [x] Build source distribution.
- [x] Build wheel distribution.
- [x] Install wheel in a clean environment.
- [x] Verify `import saphive`.
- [x] Verify CLI entry point.
- [x] Confirm WSL development is not blocked by Windows-only dependencies.

Exit criteria:

- SAPHive can be distributed internally as one package.
- Installed package exposes both Core imports and CLI command.

## Milestone 15: First Windows SAP Pilot

Status: not started

Checklist:

- [ ] Select one real automation candidate.
- [ ] Keep the automation script outside SAPHive Core.
- [ ] Configure script discovery path.
- [ ] Validate script contract.
- [ ] Validate script input.
- [ ] Configure the connection profile and auth file.
- [ ] Let Core/CLI resolve the SAP connection with `auto`, `attach`, or `open` mode.
- [ ] In `run(ctx)`, create or attach to a dedicated SAP session through `ctx.sap`.
- [ ] Run on a Windows machine with SAP GUI installed.
- [ ] Document SAP session assumptions.
- [ ] Document gaps found during pilot.

Exit criteria:

- One real automation script runs through SAPHive.
- Core/CLI resolves the SAP connection.
- The script manages sessions within the selected connection through Core APIs.
- Core abstractions are adjusted based on real SAP usage, not guesses.

## Milestone 16: Scheduler Examples

Status: not started

Checklist:

- [ ] Document Windows Task Scheduler command.
- [ ] Document Prefect usage.
- [ ] Document Airflow usage.
- [ ] Document exit code behavior.
- [ ] Document logs and outputs expected by schedulers.
- [ ] Document scheduler-safe SAP authentication/session configuration.

Exit criteria:

- SAPHive can be called by external schedulers.
- SAPHive remains outside scheduling ownership.
- Scheduler examples use safe SAP session/auth configuration.

## Milestone 17: Stabilization

Status: not started

Checklist:

- [ ] Review public Core API.
- [ ] Review script contract stability.
- [ ] Review CLI command stability.
- [ ] Review logging and result format.
- [ ] Review Windows runtime constraints.
- [ ] Decide whether future API or worker planning should begin.

Exit criteria:

- SAPHive is ready for broader internal usage.
- Future interfaces can be planned without changing Core ownership.
