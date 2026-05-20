# SAPHive Packaging Plan

This document defines the initial packaging and distribution plan for SAPHive.

The current decision is to keep SAPHive simple as one Python distribution named `saphive`. The distribution contains SAPHive Core, the CLI frontend, SAP abstractions, script runtime modules, and supporting utilities.

## Packaging Decision

Initial package model:

```text
saphive distribution
  src/saphive/core
  src/saphive/sap
  src/saphive/scripts
  src/saphive/cli
  src/saphive/utils
```

This means one package is built and installed:

```bash
pip install saphive
```

The CLI is exposed by the same distribution:

```text
saphive = "saphive.cli.app:main"
```

## Why Keep One Distribution Initially

- The project is still early and architecture is still being validated.
- One package reduces build, versioning, and deployment complexity.
- Internal users can install one artifact and get both SDK and CLI behavior.
- The architectural boundary between Core and CLI can still be enforced in code.
- A future split remains possible if there is a concrete need.

## Boundary Rules Inside the Single Package

Even though Core and CLI ship together, they must remain internally separated.

Allowed dependency direction:

```text
saphive.cli -> saphive.core
saphive.cli -> saphive.scripts through Core APIs only
saphive.cli -> saphive.sap through Core APIs only
```

Disallowed dependency direction:

```text
saphive.core -> saphive.cli
saphive.sap -> saphive.cli
saphive.scripts -> saphive.cli
```

The CLI must not own runtime behavior. It should parse arguments, call Core, format output, and map errors to process exit codes.

## Dependency Strategy

Base runtime dependencies should remain lightweight.

Current dependency categories:

| Category | Purpose |
| --- | --- |
| `pydantic` | Typed data models and validation. |
| `pydantic-settings` | Runtime configuration loading. |
| `platformdirs` | Cross-platform configuration and data paths. |
| `structlog` | Structured logging. |
| `typer` | CLI implementation. |
| `rich` | CLI output formatting. |
| `pywin32` | Windows-only SAP GUI Scripting bridge. |

Windows-only dependency rule:

```text
pywin32 must remain guarded by platform_system == 'Windows'
```

This prevents WSL development installs from failing because SAP GUI-specific Windows packages are unavailable.

## Optional Dependency Groups

Optional dependencies should be used for capabilities that not every installation needs.

Current optional groups:

| Group | Purpose |
| --- | --- |
| `dev` | Testing, linting, formatting, and type checking. |
| `excel` | Excel file support for automation scripts that process spreadsheets. |
| `prefect` | Prefect integration examples or adapters. |
| `api` | Future REST API experimentation. |

Do not move optional capabilities into base dependencies unless they are required by the Core runtime.

## Build Plan

Build commands must use the project virtual environment Python executable.

From WSL:

```bash
./venv/Scripts/python.exe -m build
```

Expected build outputs:

```text
dist/saphive-<version>.tar.gz
dist/saphive-<version>-py3-none-any.whl
```

If the `build` module is not installed, install the development dependencies or add `build` to the development dependency group before formalizing release commands.

## Local Install Verification

After building a wheel, validate installation in a clean environment.

Checks:

```bash
./venv/Scripts/python.exe -m pip install dist/saphive-<version>-py3-none-any.whl
./venv/Scripts/python.exe -c "import saphive"
./venv/Scripts/python.exe -m saphive --help
```

The exact CLI smoke command may change once the CLI implementation is added.

## Versioning Plan

Use conservative internal versioning while the project is pre-alpha.

Suggested version stages:

| Version | Meaning |
| --- | --- |
| `0.1.x` | Planning, skeleton, and first proof of concept. |
| `0.2.x` | Script contract, discovery, loading, and validation. |
| `0.3.x` | Runtime execution and structured results. |
| `0.4.x` | CLI commands and local logging. |
| `0.5.x` | First Windows SAP pilot. |
| `1.0.0` | Stable internal runtime contract. |

Do not commit to `1.0.0` until Core APIs, script contract, and CLI behavior are stable enough for internal automation scripts.

## Distribution Channels

Potential internal distribution options:

```text
Local wheel file
Internal package index
Internal Git repository install
Shared network artifact location
```

Recommended starting point:

```text
Build wheel locally and install it on Windows SAP worker machines.
```

Later, move to an internal package index if multiple machines or teams need repeatable installs.

## Windows Runtime Installation

Runtime machines must use a Windows Python environment because SAP GUI Scripting requires SAP GUI.

Expected Windows setup pattern:

```powershell
.\venv\Scripts\python.exe -m pip install saphive-<version>-py3-none-any.whl
.\venv\Scripts\python.exe -m saphive scripts run create_notifications
```

Operational requirements:

- SAP GUI must be installed.
- SAP GUI Scripting must be enabled.
- The scheduler account must be able to open SAP GUI.
- The runtime machine must have access to automation script directories.
- The runtime machine must have access to input and output locations.

## Future Split Option

The initial package remains single-distribution. A future split should only happen if there is a concrete reason.

Possible future split:

```text
saphive-core
saphive-cli
saphive
```

Reasons that may justify a split:

- Core must be embedded in systems that should not install CLI dependencies.
- CLI release cadence becomes different from Core release cadence.
- Future APIs or workers require smaller deployment artifacts.
- Multiple internal tools depend on Core but not the command-line frontend.

Until then, keep the package simple.

## Packaging Acceptance Criteria

- `pyproject.toml` remains valid TOML.
- The package builds a wheel and source distribution.
- The wheel installs in a clean Windows Python environment.
- The package import works after installation.
- The CLI entry point is available after installation.
- WSL development is not blocked by Windows-only dependencies.
- Core and CLI remain internally separated despite being distributed together.
