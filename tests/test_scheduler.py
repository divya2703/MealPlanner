"""Tests for app.services.scheduler — job registration."""

from unittest.mock import MagicMock, patch, PropertyMock

from app.services.scheduler import scheduler, start_scheduler, stop_scheduler


@patch.object(scheduler, "start")
@patch.object(scheduler, "add_job")
def test_start_scheduler_registers_jobs(mock_add_job, mock_start):
    start_scheduler()

    job_ids = [call.kwargs["id"] for call in mock_add_job.call_args_list]
    assert "weekly_reminder" in job_ids
    assert "daily_confirmation" in job_ids
    assert "morning_summary" in job_ids
    assert "low_stock_alert" in job_ids
    assert mock_add_job.call_count == 4
    mock_start.assert_called_once()


@patch.object(scheduler, "shutdown")
def test_stop_scheduler_when_running(mock_shutdown):
    # Temporarily make it look running
    original = scheduler.running
    try:
        # Force scheduler into a state where .running returns True
        # by starting with a mock
        with patch.object(type(scheduler), "running", new_callable=PropertyMock, return_value=True):
            stop_scheduler()
            mock_shutdown.assert_called_once()
    finally:
        pass


@patch.object(scheduler, "shutdown")
def test_stop_scheduler_when_not_running(mock_shutdown):
    with patch.object(type(scheduler), "running", new_callable=PropertyMock, return_value=False):
        stop_scheduler()
        mock_shutdown.assert_not_called()
