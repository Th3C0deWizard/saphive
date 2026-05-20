from datetime import UTC, datetime, timedelta

from saphive import ExecutionStatus, ScriptExecutionResult

EXPECTED_DURATION_SECONDS = 42


def test_execution_status_values_match_runtime_contract() -> None:
    assert ExecutionStatus.SUCCESS.value == "success"
    assert ExecutionStatus.VALIDATION_FAILED.value == "validation_failed"
    assert ExecutionStatus.FAILED.value == "failed"
    assert ExecutionStatus.CANCELLED.value == "cancelled"


def test_script_execution_result_reports_duration() -> None:
    started_at = datetime(2026, 5, 20, 10, 0, tzinfo=UTC)
    finished_at = started_at + timedelta(seconds=EXPECTED_DURATION_SECONDS)
    result = ScriptExecutionResult(
        script_name="create_notifications",
        run_id="run-003",
        status=ExecutionStatus.SUCCESS,
        started_at=started_at,
        finished_at=finished_at,
        outputs={"created": 10},
    )

    assert result.duration_seconds == EXPECTED_DURATION_SECONDS
    assert result.outputs == {"created": 10}


def test_script_execution_result_duration_is_none_until_finished() -> None:
    result = ScriptExecutionResult(
        script_name="create_notifications",
        run_id="run-004",
        status=ExecutionStatus.FAILED,
        started_at=datetime(2026, 5, 20, 10, 0, tzinfo=UTC),
        error="SAP session unavailable",
    )

    assert result.duration_seconds is None
    assert result.error == "SAP session unavailable"
