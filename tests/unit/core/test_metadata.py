from pathlib import Path

from saphive import ScriptMetadata


def test_script_metadata_defaults_optional_fields() -> None:
    metadata = ScriptMetadata(
        name="update_orders",
        description="Update SAP maintenance orders.",
    )

    assert metadata.name == "update_orders"
    assert metadata.description == "Update SAP maintenance orders."
    assert metadata.path is None
    assert metadata.version is None
    assert metadata.author is None
    assert metadata.tags == ()


def test_script_metadata_accepts_optional_fields() -> None:
    metadata = ScriptMetadata(
        name="load_operations",
        description="Load operations into a SAP order.",
        path=Path("automations/load_operations.py"),
        version="0.1.0",
        author="Maintenance Team",
        tags=("maintenance", "orders"),
    )

    assert metadata.path == Path("automations/load_operations.py")
    assert metadata.version == "0.1.0"
    assert metadata.author == "Maintenance Team"
    assert metadata.tags == ("maintenance", "orders")
