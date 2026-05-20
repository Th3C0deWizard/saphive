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
from saphive.scripts.registry import ScriptRegistry, ScriptRegistryEntry, ScriptSourceKind

__all__ = [
    "REQUIRED_FUNCTION_ATTRIBUTES",
    "REQUIRED_METADATA_ATTRIBUTES",
    "ScriptContract",
    "ScriptFunction",
    "ScriptRegistry",
    "ScriptRegistryEntry",
    "ScriptSourceKind",
    "discover_scripts",
    "extract_script_metadata",
    "validate_script_contract",
]
