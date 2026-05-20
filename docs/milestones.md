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

## Milestone 11: Logging and Result Files

Status: not started

Checklist:

- [ ] Define standard log fields.
- [ ] Add console logging.
- [ ] Add local file logging.
- [ ] Decide whether JSONL execution records are required initially.
- [ ] Include log path in execution result.
- [ ] Add tests for result shape.

Exit criteria:

- Runs are traceable by run ID.
- Results are useful for CLI users and schedulers.

## Milestone 12: Build and Install

Status: not started

Checklist:

- [ ] Confirm package metadata.
- [ ] Confirm build backend works.
- [ ] Build source distribution.
- [ ] Build wheel distribution.
- [ ] Install wheel in a clean environment.
- [ ] Verify `import saphive`.
- [ ] Verify CLI entry point.
- [ ] Confirm WSL development is not blocked by Windows-only dependencies.

Exit criteria:

- SAPHive can be distributed internally as one package.
- Installed package exposes both Core imports and CLI command.

## Milestone 13: First Windows SAP Pilot

Status: not started

Checklist:

- [ ] Select one real automation candidate.
- [ ] Keep the automation script outside SAPHive Core.
- [ ] Configure script discovery path.
- [ ] Validate script contract.
- [ ] Validate script input.
- [ ] Run on a Windows machine with SAP GUI installed.
- [ ] Document SAP session assumptions.
- [ ] Document gaps found during pilot.

Exit criteria:

- One real automation script runs through SAPHive.
- Core abstractions are adjusted based on real SAP usage, not guesses.

## Milestone 14: Scheduler Examples

Status: not started

Checklist:

- [ ] Document Windows Task Scheduler command.
- [ ] Document Prefect usage.
- [ ] Document Airflow usage.
- [ ] Document exit code behavior.
- [ ] Document logs and outputs expected by schedulers.

Exit criteria:

- SAPHive can be called by external schedulers.
- SAPHive remains outside scheduling ownership.

## Milestone 15: Stabilization

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
