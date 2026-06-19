from importlib import import_module

from saphive import Bot, SapContext, bot


def test_package_imports() -> None:
    package = import_module("saphive")

    assert package.__version__ == "0.2.0"


def test_public_script_contract_import_is_available() -> None:
    assert SapContext.__name__ == "SapContext"
    assert Bot.__name__ == "Bot"
    assert callable(bot)
