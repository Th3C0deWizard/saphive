"""Automation script runtime package for SAPHive."""

from saphive.scripts.contract import (
    REQUIRED_FUNCTION_ATTRIBUTES,
    REQUIRED_METADATA_ATTRIBUTES,
    ScriptContract,
    ScriptFunction,
    extract_script_metadata,
    validate_script_contract,
)

__all__ = [
    "REQUIRED_FUNCTION_ATTRIBUTES",
    "REQUIRED_METADATA_ATTRIBUTES",
    "ScriptContract",
    "ScriptFunction",
    "extract_script_metadata",
    "validate_script_contract",
]
