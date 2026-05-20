"""Script contract validation for SAPHive automation scripts."""

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from inspect import Parameter, Signature, signature
from pathlib import Path
from types import ModuleType
from typing import TypeAlias, cast

from saphive.core import SapContext, ScriptContractError, ScriptMetadata

ScriptFunction: TypeAlias = Callable[[SapContext], None]

REQUIRED_METADATA_ATTRIBUTES = ("SCRIPT_NAME", "DESCRIPTION")
REQUIRED_FUNCTION_ATTRIBUTES = ("validate", "run")


@dataclass(frozen=True, slots=True)
class ScriptContract:
    """Validated contract for a SAPHive automation script module."""

    metadata: ScriptMetadata
    validate: ScriptFunction
    run: ScriptFunction


def validate_script_contract(
    module: ModuleType,
    *,
    path: str | Path | None = None,
) -> ScriptContract:
    """Validate a module against the SAPHive script contract."""
    script_name = _required_non_empty_string(module, "SCRIPT_NAME")
    description = _required_non_empty_string(module, "DESCRIPTION")
    validate_function = _required_function(module, "validate")
    run_function = _required_function(module, "run")

    _validate_script_function_signature(validate_function, "validate", module)
    _validate_script_function_signature(run_function, "run", module)

    return ScriptContract(
        metadata=ScriptMetadata(
            name=script_name,
            description=description,
            path=None if path is None else Path(path),
            version=_optional_non_empty_string(module, "VERSION"),
            author=_optional_non_empty_string(module, "AUTHOR"),
            tags=_optional_string_tags(module),
        ),
        validate=cast(ScriptFunction, validate_function),
        run=cast(ScriptFunction, run_function),
    )


def extract_script_metadata(
    module: ModuleType,
    *,
    path: str | Path | None = None,
) -> ScriptMetadata:
    """Validate the contract and return only the script metadata."""
    return validate_script_contract(module, path=path).metadata


def _required_non_empty_string(module: ModuleType, attribute_name: str) -> str:
    value = getattr(module, attribute_name, None)
    if not isinstance(value, str) or value.strip() == "":
        raise ScriptContractError(
            f"SAPHive script requires a non-empty string {attribute_name} attribute.",
            details={"module": module.__name__, "attribute": attribute_name},
        )

    return value


def _optional_non_empty_string(module: ModuleType, attribute_name: str) -> str | None:
    value = getattr(module, attribute_name, None)
    if value is None:
        return None

    if not isinstance(value, str) or value.strip() == "":
        raise ScriptContractError(
            f"Optional SAPHive script attribute {attribute_name} must be a non-empty string.",
            details={"module": module.__name__, "attribute": attribute_name},
        )

    return value


def _optional_string_tags(module: ModuleType) -> tuple[str, ...]:
    value = getattr(module, "TAGS", None)
    if value is None:
        return ()

    if isinstance(value, str) or not isinstance(value, Sequence):
        raise ScriptContractError(
            "Optional SAPHive script attribute TAGS must be a sequence of strings.",
            details={"module": module.__name__, "attribute": "TAGS"},
        )

    tags = tuple(value)
    if not all(isinstance(tag, str) and tag.strip() != "" for tag in tags):
        raise ScriptContractError(
            "Optional SAPHive script attribute TAGS must contain only non-empty strings.",
            details={"module": module.__name__, "attribute": "TAGS"},
        )

    return tags


def _required_function(module: ModuleType, function_name: str) -> Callable[..., object]:
    value = getattr(module, function_name, None)
    if not callable(value):
        raise ScriptContractError(
            f"SAPHive script requires a callable {function_name}(ctx) function.",
            details={"module": module.__name__, "function": function_name},
        )

    return cast(Callable[..., object], value)


def _validate_script_function_signature(
    function: Callable[..., object],
    function_name: str,
    module: ModuleType,
) -> None:
    try:
        function_signature = signature(function)
    except (TypeError, ValueError) as exc:
        raise ScriptContractError(
            f"SAPHive could not inspect {function_name}(ctx) signature.",
            details={"module": module.__name__, "function": function_name},
        ) from exc

    parameters = tuple(function_signature.parameters.values())
    if len(parameters) != 1:
        raise ScriptContractError(
            f"SAPHive script function {function_name} must accept exactly one ctx parameter.",
            details={"module": module.__name__, "function": function_name},
        )

    parameter = parameters[0]
    if parameter.kind not in (Parameter.POSITIONAL_ONLY, Parameter.POSITIONAL_OR_KEYWORD):
        raise ScriptContractError(
            f"SAPHive script function {function_name} ctx parameter must be positional.",
            details={"module": module.__name__, "function": function_name},
        )

    if parameter.default is not Parameter.empty:
        raise ScriptContractError(
            f"SAPHive script function {function_name} ctx parameter must not have a default value.",
            details={"module": module.__name__, "function": function_name},
        )

    _validate_return_annotation(function_signature, function_name, module)


def _validate_return_annotation(
    function_signature: Signature,
    function_name: str,
    module: ModuleType,
) -> None:
    return_annotation = function_signature.return_annotation
    if return_annotation in (Signature.empty, None, "None"):
        return

    raise ScriptContractError(
        f"SAPHive script function {function_name} must return None.",
        details={"module": module.__name__, "function": function_name},
    )
