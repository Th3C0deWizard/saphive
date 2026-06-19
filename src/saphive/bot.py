"""Bot contract primitives for SAPHive."""

from __future__ import annotations

import sys
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from inspect import Parameter, Signature, signature
from types import ModuleType
from typing import TypeVar

from pydantic import BaseModel

RunFunction = Callable[..., BaseModel]
ValidateFunction = Callable[..., None]

_Run = TypeVar("_Run", bound=RunFunction)


@dataclass(frozen=True, slots=True)
class Bot:
    """Executable SAPHive bot contract."""

    name: str
    description: str
    input_model: type[BaseModel]
    output_model: type[BaseModel]
    run: RunFunction
    version: str | None = None
    author: str | None = None
    tags: tuple[str, ...] = field(default_factory=tuple)
    validate: ValidateFunction | None = None


def bot(
    *,
    name: str,
    description: str,
    input_model: type[BaseModel],
    output_model: type[BaseModel],
    version: str | None = None,
    author: str | None = None,
    tags: Sequence[str] = (),
    validate: ValidateFunction | None = None,
) -> Callable[[_Run], _Run]:
    """Decorate a run function and attach a SAPHive Bot instance to it."""

    def decorator(run: _Run) -> _Run:
        instance = Bot(
            name=name,
            description=description,
            input_model=input_model,
            output_model=output_model,
            run=run,
            version=version,
            author=author,
            tags=tuple(tags),
            validate=validate,
        )
        validate_bot_contract(instance)
        run.__dict__["__saphive_bot__"] = instance
        module = sys.modules.get(run.__module__)
        if module is not None:
            module.__dict__["BOT"] = instance
        return run

    return decorator


def bot_from_module(module: ModuleType) -> Bot:
    """Extract a Bot instance from an imported module."""
    value = getattr(module, "BOT", None)
    if isinstance(value, Bot):
        validate_bot_contract(value)
        return value
    if value is not None:
        raise _bot_contract_error(
            "SAPHive module attribute BOT must be a Bot instance.",
            details={"module": module.__name__, "attribute": "BOT"},
        )

    for candidate in vars(module).values():
        decorated = getattr(candidate, "__saphive_bot__", None)
        if isinstance(decorated, Bot):
            validate_bot_contract(decorated)
            module.__dict__["BOT"] = decorated
            return decorated

    raise _bot_contract_error(
        "SAPHive bot module must expose BOT or a function decorated with @bot(...).",
        details={"module": module.__name__},
    )


def validate_bot_contract(instance: Bot) -> None:
    """Validate a Bot instance without executing it."""
    _non_empty_string(instance.name, "name")
    _non_empty_string(instance.description, "description")
    if instance.version is not None:
        _non_empty_string(instance.version, "version")
    if instance.author is not None:
        _non_empty_string(instance.author, "author")
    if not all(isinstance(tag, str) and tag.strip() for tag in instance.tags):
        raise _bot_contract_error("Bot tags must contain only non-empty strings.")

    _base_model_type(instance.input_model, "input_model")
    _base_model_type(instance.output_model, "output_model")
    _callable(instance.run, "run")
    _validate_function_signature(instance.run, "run", expected_parameters=2, allow_return=True)
    if instance.validate is not None:
        _callable(instance.validate, "validate")
        _validate_function_signature(instance.validate, "validate", expected_parameters=1)


def _non_empty_string(value: str, name: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise _bot_contract_error(
            f"Bot {name} must be a non-empty string.",
            details={"field": name},
        )


def _base_model_type(value: object, name: str) -> None:
    if not isinstance(value, type) or not issubclass(value, BaseModel):
        raise _bot_contract_error(
            f"Bot {name} must be a pydantic BaseModel type.",
            details={"field": name},
        )


def _callable(value: object, name: str) -> None:
    if not callable(value):
        raise _bot_contract_error(f"Bot {name} must be callable.", details={"field": name})


def _validate_function_signature(
    function: Callable[..., object],
    function_name: str,
    *,
    expected_parameters: int,
    allow_return: bool = False,
) -> None:
    try:
        function_signature = signature(function)
    except (TypeError, ValueError) as exc:
        raise _bot_contract_error(
            f"SAPHive could not inspect Bot {function_name} signature.",
            details={"function": function_name},
        ) from exc

    parameters = tuple(function_signature.parameters.values())
    if len(parameters) != expected_parameters:
        raise _bot_contract_error(
            f"Bot {function_name} must accept exactly {expected_parameters} positional parameters.",
            details={"function": function_name},
        )

    for parameter in parameters:
        if parameter.kind not in (Parameter.POSITIONAL_ONLY, Parameter.POSITIONAL_OR_KEYWORD):
            raise _bot_contract_error(
                f"Bot {function_name} parameters must be positional.",
                details={"function": function_name},
            )
        if parameter.default is not Parameter.empty:
            raise _bot_contract_error(
                f"Bot {function_name} parameters must not have default values.",
                details={"function": function_name},
            )

    if allow_return:
        return

    return_annotation = function_signature.return_annotation
    if return_annotation not in (Signature.empty, None, "None"):
        raise _bot_contract_error(
            f"Bot {function_name} must return None.",
            details={"function": function_name},
        )


def get_decorated_bot(function: Callable[..., object]) -> Bot | None:
    """Return a Bot attached by @bot(...), when present."""
    value = getattr(function, "__saphive_bot__", None)
    return value if isinstance(value, Bot) else None


def _bot_contract_error(message: str, *, details: dict[str, object] | None = None) -> Exception:
    from saphive.core.errors import BotContractError  # noqa: PLC0415

    return BotContractError(message, details=details)
