from importlib import import_module

from saphive import SapContext


def test_package_imports() -> None:
    package = import_module("saphive")

    assert package.__version__ == "0.1.4"


def test_public_script_contract_import_is_available() -> None:
    assert SapContext.__name__ == "SapContext"
