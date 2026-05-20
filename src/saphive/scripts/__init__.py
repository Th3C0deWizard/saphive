"""Automation script runtime package for SAPHive."""

from saphive.scripts.contract import (
    REQUIRED_FUNCTION_ATTRIBUTES,
    REQUIRED_METADATA_ATTRIBUTES,
    ScriptContract,
    ScriptFunction,
    extract_script_metadata,
    validate_script_contract,
)
from saphive.scripts.discovery import discover_scripts
from saphive.scripts.loader import (
    LoadedScript,
    load_script_from_entry,
    load_script_from_path,
    load_script_from_registry,
)
from saphive.scripts.registry import ScriptRegistry, ScriptRegistryEntry, ScriptSourceKind

__all__ = [
    "REQUIRED_FUNCTION_ATTRIBUTES",
    "REQUIRED_METADATA_ATTRIBUTES",
    "LoadedScript",
    "ScriptContract",
    "ScriptFunction",
    "ScriptRegistry",
    "ScriptRegistryEntry",
    "ScriptSourceKind",
    "discover_scripts",
    "extract_script_metadata",
    "load_script_from_entry",
    "load_script_from_path",
    "load_script_from_registry",
    "validate_script_contract",
]
