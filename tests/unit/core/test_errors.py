from saphive import (
    AutomationError,
    BusinessAutomationError,
    ComRuntimeError,
    ConfigurationError,
    ExcelInfrastructureError,
    FatalAutomationError,
    InfrastructureError,
    SAPAutomationError,
    SapConnectionError,
    SapGuiError,
    SAPHiveError,
    SapInfrastructureError,
    SapSessionError,
    ScriptContractError,
    ScriptDiscoveryError,
    ScriptExecutionError,
    ScriptLoadError,
    ScriptValidationError,
)


def test_saphive_error_stores_message_and_details() -> None:
    error = SAPHiveError("Something failed", details={"script_name": "create_notifications"})

    assert str(error) == "Something failed"
    assert error.message == "Something failed"
    assert error.details == {"script_name": "create_notifications"}


def test_domain_errors_share_base_type() -> None:
    error_types = [
        AutomationError,
        FatalAutomationError,
        InfrastructureError,
        ComRuntimeError,
        SapInfrastructureError,
        ExcelInfrastructureError,
        BusinessAutomationError,
        SAPAutomationError,
        ConfigurationError,
        ScriptDiscoveryError,
        ScriptLoadError,
        ScriptContractError,
        ScriptValidationError,
        SapConnectionError,
        SapSessionError,
        SapGuiError,
        ScriptExecutionError,
    ]

    for error_type in error_types:
        assert isinstance(error_type("failed"), SAPHiveError)
