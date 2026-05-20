from pathlib import Path
from types import ModuleType

import pytest

from saphive import SapContext, ScriptContractError
from saphive.scripts import (
    REQUIRED_FUNCTION_ATTRIBUTES,
    REQUIRED_METADATA_ATTRIBUTES,
    ScriptContract,
    extract_script_metadata,
    validate_script_contract,
)

EXPECTED_REQUIRED_FUNCTIONS = ("validate", "run")
EXPECTED_REQUIRED_METADATA = ("SCRIPT_NAME", "DESCRIPTION")


def test_required_contract_constants_are_public() -> None:
    assert REQUIRED_FUNCTION_ATTRIBUTES == EXPECTED_REQUIRED_FUNCTIONS
    assert REQUIRED_METADATA_ATTRIBUTES == EXPECTED_REQUIRED_METADATA


def test_validate_script_contract_returns_contract_and_metadata() -> None:
    module = _valid_script_module()
    script_path = Path("automations/create_notifications.py")

    contract = validate_script_contract(module, path=script_path)

    assert isinstance(contract, ScriptContract)
    assert contract.metadata.name == "create_notifications"
    assert contract.metadata.description == "Create SAP maintenance notifications."
    assert contract.metadata.path == script_path
    assert contract.metadata.version == "0.1.0"
    assert contract.metadata.author == "Maintenance Team"
    assert contract.metadata.tags == ("maintenance", "notifications")


def test_extract_script_metadata_returns_only_metadata() -> None:
    metadata = extract_script_metadata(_valid_script_module())

    assert metadata.name == "create_notifications"
    assert metadata.description == "Create SAP maintenance notifications."


def test_contract_validation_does_not_execute_script_functions() -> None:
    module = _base_module()

    def validate(ctx: SapContext) -> None:
        raise AssertionError("validate should not be executed")

    def run(ctx: SapContext) -> None:
        raise AssertionError("run should not be executed")

    module.__dict__["validate"] = validate
    module.__dict__["run"] = run

    contract = validate_script_contract(module)

    assert contract.metadata.name == "create_notifications"


@pytest.mark.parametrize("attribute_name", ["SCRIPT_NAME", "DESCRIPTION"])
def test_contract_requires_non_empty_metadata_attributes(attribute_name: str) -> None:
    module = _valid_script_module()
    setattr(module, attribute_name, "")

    with pytest.raises(ScriptContractError, match="non-empty string") as exc_info:
        validate_script_contract(module)

    assert exc_info.value.details["attribute"] == attribute_name


@pytest.mark.parametrize("function_name", ["validate", "run"])
def test_contract_requires_callable_functions(function_name: str) -> None:
    module = _valid_script_module()
    setattr(module, function_name, None)

    with pytest.raises(ScriptContractError, match="requires a callable") as exc_info:
        validate_script_contract(module)

    assert exc_info.value.details["function"] == function_name


@pytest.mark.parametrize("function_name", ["validate", "run"])
def test_contract_rejects_functions_without_ctx(function_name: str) -> None:
    module = _valid_script_module()

    def invalid_function() -> None:
        return None

    setattr(module, function_name, invalid_function)

    with pytest.raises(ScriptContractError, match="exactly one ctx"):
        validate_script_contract(module)


@pytest.mark.parametrize("function_name", ["validate", "run"])
def test_contract_rejects_functions_with_extra_parameters(function_name: str) -> None:
    module = _valid_script_module()

    def invalid_function(ctx: SapContext, extra: object) -> None:
        return None

    setattr(module, function_name, invalid_function)

    with pytest.raises(ScriptContractError, match="exactly one ctx"):
        validate_script_contract(module)


@pytest.mark.parametrize("function_name", ["validate", "run"])
def test_contract_rejects_keyword_only_ctx(function_name: str) -> None:
    module = _valid_script_module()

    def invalid_function(*, ctx: SapContext) -> None:
        return None

    setattr(module, function_name, invalid_function)

    with pytest.raises(ScriptContractError, match="positional"):
        validate_script_contract(module)


@pytest.mark.parametrize("function_name", ["validate", "run"])
def test_contract_rejects_default_ctx(function_name: str) -> None:
    module = _valid_script_module()

    def invalid_function(ctx: SapContext | None = None) -> None:
        return None

    setattr(module, function_name, invalid_function)

    with pytest.raises(ScriptContractError, match="default value"):
        validate_script_contract(module)


@pytest.mark.parametrize("function_name", ["validate", "run"])
def test_contract_rejects_non_none_return_annotation(function_name: str) -> None:
    module = _valid_script_module()

    def invalid_function(ctx: SapContext) -> str:
        return "invalid"

    setattr(module, function_name, invalid_function)

    with pytest.raises(ScriptContractError, match="return None"):
        validate_script_contract(module)


def test_contract_rejects_invalid_optional_version() -> None:
    module = _valid_script_module()
    module.__dict__["VERSION"] = ""

    with pytest.raises(ScriptContractError, match="VERSION"):
        validate_script_contract(module)


def test_contract_rejects_invalid_optional_author() -> None:
    module = _valid_script_module()
    module.__dict__["AUTHOR"] = ""

    with pytest.raises(ScriptContractError, match="AUTHOR"):
        validate_script_contract(module)


def test_contract_rejects_string_tags() -> None:
    module = _valid_script_module()
    module.__dict__["TAGS"] = "maintenance"

    with pytest.raises(ScriptContractError, match="TAGS"):
        validate_script_contract(module)


def test_contract_rejects_empty_tags() -> None:
    module = _valid_script_module()
    module.__dict__["TAGS"] = ["maintenance", ""]

    with pytest.raises(ScriptContractError, match="TAGS"):
        validate_script_contract(module)


def _valid_script_module() -> ModuleType:
    module = _base_module()

    def validate(ctx: SapContext) -> None:
        return None

    def run(ctx: SapContext) -> None:
        return None

    module.__dict__["validate"] = validate
    module.__dict__["run"] = run
    return module


def _base_module() -> ModuleType:
    module = ModuleType("valid_saphive_script")
    module.__dict__["SCRIPT_NAME"] = "create_notifications"
    module.__dict__["DESCRIPTION"] = "Create SAP maintenance notifications."
    module.__dict__["VERSION"] = "0.1.0"
    module.__dict__["AUTHOR"] = "Maintenance Team"
    module.__dict__["TAGS"] = ("maintenance", "notifications")
    return module
