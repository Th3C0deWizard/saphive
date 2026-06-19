# SAPHive

SAPHive is a lightweight Python runtime and SDK for SAP GUI Scripting automation. It discovers, validates, and executes typed SAPHive bots while keeping SAP connection resolution, logging, configuration, and error handling in Core.

## Status

SAPHive is pre-alpha internal software. The current implementation includes:

- A typed Core runtime and Bot contract.
- Import-based Bot discovery, loading, validation, and execution.
- A Typer CLI exposed as `saphive`.
- SAP connection modes: `auto`, `attach`, and `open`.
- Connection-scoped script APIs through `ctx.sap`.
- `.saphive.auth.toml` support using `password_env` or `password_prompt`.
- Local run logs and structured execution results.

## Install For Development

From WSL, use the project virtual environment Python executable:

```bash
./venv/Scripts/python.exe -m pip install -e ".[dev]"
```

Run checks:

```bash
./venv/Scripts/python.exe -m pytest
./venv/Scripts/python.exe -m ruff check .
./venv/Scripts/python.exe -m mypy src tests
```

## CLI Basics

```bash
./venv/Scripts/python.exe -m saphive scripts list --config examples/scripts/saphive.toml
./venv/Scripts/python.exe -m saphive scripts validate create_sessions --config examples/scripts/saphive.toml
./venv/Scripts/python.exe -m saphive scripts run create_sessions --config examples/scripts/saphive.toml --input-json '{"transaction":"IW32"}'
```

On Windows runtime machines, prefer:

```powershell
.\venv\Scripts\python.exe -m saphive scripts run create_sessions --config examples\scripts\saphive.toml
```

## Configuration Lookup

Configuration and auth are resolved in this order:

1. CLI value flags such as `--sap-mode` and `--sap-connection` override loaded config values.
2. Explicit file flags: `--config` and `--sap-auth-file`.
3. Files beside the runtime-executed script: `saphive.toml` and `.saphive.auth.toml`.
4. Files in the OS-specific SAPHive CLI config directory.
5. Built-in default values from code.

## Logging

Each run writes a local log file and returns its path in the execution result. Set the logging
level to `DEBUG` when a run needs full failure diagnostics, including exception type, SAPHive
error details, current script outputs, and traceback.

```toml
[logging]
level = "DEBUG"
directory = "logs"
```

## SAP Auth

Do not put raw passwords in `saphive.toml` or CLI arguments. Use `.saphive.auth.toml`:

```toml
[connections.prd]
username = "MY_SAP_USER"
password_prompt = true
```

For unattended scheduler runs, prefer an environment variable reference:

```toml
[connections.prd]
username = "MY_SAP_USER"
password_env = "SAPHIVE_PRD_PASSWORD"
```

## SAP Cleanup

By default, SAPHive closes SAP sessions created through `ctx.sap.create_session()` after a run.
Use `--sap-cleanup` to change the policy:

```bash
./venv/Scripts/python.exe -m saphive run notificar.py --sap-cleanup none
./venv/Scripts/python.exe -m saphive run notificar.py --sap-cleanup connection
```

Connection cleanup only closes connections opened by SAPHive. Add `--sap-cleanup-force` to close
an attached/pre-existing connection intentionally.

## Bot Contract

```python
from pydantic import BaseModel

from saphive import SapContext, bot

class CreateSessionsInput(BaseModel):
    transaction: str = "IW32"

class CreateSessionsOutput(BaseModel):
    transaction: str

@bot(
    name="create_sessions",
    description="Create SAP GUI sessions inside the selected connection.",
    input_model=CreateSessionsInput,
    output_model=CreateSessionsOutput,
)
def run(ctx: SapContext, data: CreateSessionsInput) -> CreateSessionsOutput:
    session = ctx.sap.create_session()
    session.start_transaction(data.transaction)
    return CreateSessionsOutput(transaction=data.transaction)
```

Bots should not choose or open SAP connections directly. Core/CLI selects the connection, and bots manage sessions only through `ctx.sap`.
For independent bots sharing one SAP connection, create one dedicated session with `ctx.sap.create_session()`, run all automation through the returned session object, and let the default `created-sessions` cleanup close it after the run.
Use `ctx.sap.attach_session(index=...)` only when intentionally taking control of an existing session.
When a bot needs a raw SAP GUI connection COM operation, use `ctx.sap.with_connection(...)`; SAPHive does not retry, rebind, or recover COM proxies automatically.

Python services can import and execute bots directly:

```python
from saphive import SapRuntime
from my_project.bots import create_sessions

runtime = SapRuntime(...)
result = runtime.run_bot(create_sessions.BOT, inputs={"transaction": "IW32"})
```
