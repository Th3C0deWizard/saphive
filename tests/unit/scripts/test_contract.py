from types import ModuleType

import pytest
from pydantic import BaseModel

from saphive import Bot, BotContractError, SapContext, bot
from saphive.bot import bot_from_module, get_decorated_bot, validate_bot_contract


class Input(BaseModel):
    value: str


class Output(BaseModel):
    result: str


def test_bot_contract_accepts_valid_bot() -> None:
    instance = Bot(
        name="create_notifications",
        description="Create SAP maintenance notifications.",
        input_model=Input,
        output_model=Output,
        run=_run,
        version="0.1.0",
        author="Maintenance Team",
        tags=("maintenance",),
    )

    validate_bot_contract(instance)


def test_bot_decorator_attaches_bot_to_function() -> None:
    @bot(name="decorated", description="Decorated bot.", input_model=Input, output_model=Output)
    def run(ctx: SapContext, data: Input) -> Output:
        return Output(result=data.value)

    instance = get_decorated_bot(run)

    assert instance is not None
    assert instance.name == "decorated"
    assert instance.run is run


def test_bot_from_module_accepts_explicit_bot() -> None:
    module = ModuleType("explicit_bot")
    instance = Bot(
        name="explicit",
        description="Explicit bot.",
        input_model=Input,
        output_model=Output,
        run=_run,
    )
    module.__dict__["BOT"] = instance

    assert bot_from_module(module) is instance


def test_bot_from_module_accepts_decorated_run_function() -> None:
    module = ModuleType("decorated_module")

    @bot(
        name="decorated_module",
        description="Decorated module.",
        input_model=Input,
        output_model=Output,
    )
    def run(ctx: SapContext, data: Input) -> Output:
        return Output(result=data.value)

    module.__dict__["run"] = run

    assert bot_from_module(module).name == "decorated_module"


def test_bot_contract_rejects_missing_bot() -> None:
    module = ModuleType("missing_bot")

    with pytest.raises(BotContractError, match="must expose BOT"):
        bot_from_module(module)


def test_bot_contract_rejects_invalid_input_model() -> None:
    instance = Bot(
        name="invalid_input",
        description="Invalid input model.",
        input_model=dict,  # type: ignore[arg-type]
        output_model=Output,
        run=_run,
    )

    with pytest.raises(BotContractError, match="input_model"):
        validate_bot_contract(instance)


def test_bot_contract_rejects_invalid_run_signature() -> None:
    def invalid_run(ctx: SapContext) -> Output:
        return Output(result="invalid")

    instance = Bot(
        name="invalid_run",
        description="Invalid run signature.",
        input_model=Input,
        output_model=Output,
        run=invalid_run,
    )

    with pytest.raises(BotContractError, match="exactly 2"):
        validate_bot_contract(instance)


def _run(ctx: SapContext, data: Input) -> Output:
    return Output(result=data.value)
