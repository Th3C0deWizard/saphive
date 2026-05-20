# SAPHive Examples

This directory contains a minimal SAPHive script setup for testing SAP connection and session behavior.

## Files

- `scripts/create_sessions_dry_run.py`: SAPHive script named `create_sessions` that creates two sessions in the selected SAP connection.
- `scripts/saphive.toml`: script-local runtime config with SAP connection profiles.
- `scripts/.saphive.auth.toml`: local auth file used on this machine. It is intentionally ignored by version control.
- `logs/`: local runtime logs. Ignored by version control.

## Config

`scripts/saphive.toml` selects `prd` by default:

```toml
[sap]
mode = "auto"
connection = "prd"

[sap.connections.prd]
sap_logon_name = "3 PRODUCTIVO (PRD)"
client = "300"
language = "ES"
```

`auto` first tries to attach to an existing SAP GUI connection. If the selected connection is not available, it tries to open the configured SAP Logon connection and uses `scripts/.saphive.auth.toml`.

## Auth

The local auth file uses prompt-based auth for manual testing:

```toml
[connections.prd]
username = "INV10018"
password_prompt = true
```

For scheduled runs, replace `password_prompt = true` with an environment variable reference:

```toml
[connections.prd]
username = "INV10018"
password_env = "SAPHIVE_PRD_PASSWORD"
```

Then set the variable in the scheduler account before running SAPHive.

## Validate From WSL

Validation does not connect to SAP:

```bash
./venv/Scripts/python.exe -m saphive scripts validate create_sessions --config examples/scripts/saphive.toml
```

## Run On Windows

Run from a Windows machine with SAP GUI installed and SAP GUI Scripting enabled:

```powershell
.\venv\Scripts\python.exe -m saphive scripts run create_sessions --config examples\scripts\saphive.toml
```

You can force attach-only mode when SAP GUI is already open and authenticated:

```powershell
.\venv\Scripts\python.exe -m saphive scripts run create_sessions --config examples\scripts\saphive.toml --sap-mode attach
```

You can force open mode to test login and prompt-based auth:

```powershell
.\venv\Scripts\python.exe -m saphive scripts run create_sessions --config examples\scripts\saphive.toml --sap-mode open
```

## Notes

- Local auth files and logs are ignored by `.gitignore`.
- SAP GUI Scripting must be enabled in SAP GUI and allowed by SAP server policy.
- The Windows account running the command must have access to an interactive desktop session.
