"""
Unit tests for TaskScheduler.
"""

import pytest
import time
from datetime import datetime, timedelta
from unittest.mock import Mock, patch, MagicMock

from octopus_scraper.task_manager.scheduler import (
    TaskScheduler,
    create_hourly_schedule,
    create_daily_schedule,
    create_weekly_schedule,
)
from octopus_scraper.task_manager.models import TaskScheduleConfig
from octopus_scraper.task_manager.task_manager import TaskManager


@pytest.fixture
def mock_task_manager():
    """Create a mock TaskManager for testing."""
    mock_manager = Mock(spec=TaskManager)
    mock_manager.submit_task.return_value = "task_123"
    mock_manager.add_pre_execution_hook = Mock()
    mock_manager.add_post_execution_hook = Mock()
    return mock_manager


@pytest.fixture
def task_scheduler(mock_task_manager):
    """Create a TaskScheduler instance for testing."""
    scheduler = TaskScheduler(mock_task_manager)
    yield scheduler
    scheduler.stop()


@pytest.fixture
def sample_schedule():
    """Create a sample TaskScheduleConfig for testing."""
    return TaskScheduleConfig(
        schedule_id="test_schedule_123",
        scraper_name="test_scraper",
        cron_expression="0 */6 * * *",  # Every 6 hours
        enabled=True,
        max_concurrent_runs=2,
        timeout_seconds=600,
        fetch_params={"limit": 50},
        metadata={"source": "github"},
    )


class TestTaskSchedulerInitialization:
    """Test TaskScheduler initialization."""

    def test_init(self, mock_task_manager):
        """Test TaskScheduler initialization."""
        scheduler = TaskScheduler(mock_task_manager)

        assert scheduler.task_manager == mock_task_manager
        assert scheduler._schedules == {}
        assert scheduler._running_scheduled_tasks == {}
        assert scheduler._check_interval == 60
        assert scheduler._scheduler_thread is None

        scheduler.stop()

    def test_start_and_stop(self, mock_task_manager):
        """Test starting and stopping scheduler."""
        scheduler = TaskScheduler(mock_task_manager)

        # Start scheduler
        scheduler.start()
        assert scheduler._scheduler_thread is not None
        assert scheduler._scheduler_thread.is_alive()
        assert not scheduler._stop_event.is_set()

        # Stop scheduler
        scheduler.stop()
        assert scheduler._stop_event.is_set()


class TestScheduleManagement:
    """Test schedule management functionality."""

    def test_add_schedule_valid(self, task_scheduler, sample_schedule):
        """Test adding a valid schedule."""
        # Mock croniter directly since it's imported conditionally
        with patch(
            "octopus_scraper.task_manager.scheduler.croniter"
        ) as mock_croniter_class:
            # Mock croniter class constructor
            mock_cron_instance = Mock()
            mock_croniter_class.return_value = mock_cron_instance
            mock_cron_instance.get_next.return_value = datetime.now() + timedelta(
                hours=6
            )

            schedule_id = task_scheduler.add_schedule(sample_schedule)

        assert schedule_id == sample_schedule.schedule_id
        assert sample_schedule.schedule_id in task_scheduler._schedules
        assert sample_schedule.schedule_id in task_scheduler._running_scheduled_tasks
        assert task_scheduler._running_scheduled_tasks[sample_schedule.schedule_id] == 0
        assert sample_schedule.next_run is not None

    def test_add_schedule_invalid_cron(self, task_scheduler):
        """Test adding a schedule with invalid cron expression."""
        invalid_schedule = TaskScheduleConfig(
            schedule_id="invalid_schedule",
            scraper_name="test_scraper",
            cron_expression="invalid cron",
            enabled=True,
        )

        with patch(
            "octopus_scraper.task_manager.scheduler.croniter"
        ) as mock_croniter_class:
            mock_croniter_class.side_effect = ValueError("Invalid cron expression")

            with pytest.raises(ValueError, match="Invalid cron expression"):
                task_scheduler.add_schedule(invalid_schedule)

    def test_remove_schedule(self, task_scheduler, sample_schedule):
        """Test removing a schedule."""
        # Add schedule first
        with patch("octopus_scraper.task_manager.scheduler.croniter"):
            task_scheduler.add_schedule(sample_schedule)

        # Remove schedule
        removed = task_scheduler.remove_schedule(sample_schedule.schedule_id)

        assert removed is True
        assert sample_schedule.schedule_id not in task_scheduler._schedules
        assert (
            sample_schedule.schedule_id not in task_scheduler._running_scheduled_tasks
        )

    def test_remove_nonexistent_schedule(self, task_scheduler):
        """Test removing a nonexistent schedule."""
        removed = task_scheduler.remove_schedule("nonexistent")
        assert removed is False

    def test_enable_schedule(self, task_scheduler, sample_schedule):
        """Test enabling a schedule."""
        # Add disabled schedule
        sample_schedule.enabled = False
        with patch("octopus_scraper.task_manager.scheduler.croniter"):
            task_scheduler.add_schedule(sample_schedule)

        # Enable schedule
        with patch("octopus_scraper.task_manager.scheduler.croniter") as mock_croniter:
            mock_cron_instance = Mock()
            mock_croniter.return_value = mock_cron_instance
            mock_cron_instance.get_next.return_value = datetime.now() + timedelta(
                hours=6
            )

            enabled = task_scheduler.enable_schedule(sample_schedule.schedule_id)

        assert enabled is True
        assert sample_schedule.enabled is True
        assert sample_schedule.next_run is not None

    def test_disable_schedule(self, task_scheduler, sample_schedule):
        """Test disabling a schedule."""
        # Add enabled schedule
        with patch("octopus_scraper.task_manager.scheduler.croniter"):
            task_scheduler.add_schedule(sample_schedule)

        # Disable schedule
        disabled = task_scheduler.disable_schedule(sample_schedule.schedule_id)

        assert disabled is True
        assert sample_schedule.enabled is False
        assert sample_schedule.next_run is None

    def test_list_schedules(self, task_scheduler):
        """Test listing schedules."""
        # Add multiple schedules
        schedule1 = TaskScheduleConfig(
            "sched1", "scraper1", "0 */6 * * *", enabled=True
        )
        schedule2 = TaskScheduleConfig("sched2", "scraper2", "0 0 * * *", enabled=False)

        with patch("octopus_scraper.task_manager.scheduler.croniter"):
            task_scheduler.add_schedule(schedule1)
            task_scheduler.add_schedule(schedule2)

        # List all schedules
        all_schedules = task_scheduler.list_schedules()
        assert len(all_schedules) == 2

        # List only enabled schedules
        enabled_schedules = task_scheduler.list_schedules(enabled_only=True)
        assert len(enabled_schedules) == 1
        assert enabled_schedules[0].schedule_id == "sched1"

    def test_get_schedule(self, task_scheduler, sample_schedule):
        """Test getting a specific schedule."""
        with patch("octopus_scraper.task_manager.scheduler.croniter"):
            task_scheduler.add_schedule(sample_schedule)

        retrieved = task_scheduler.get_schedule(sample_schedule.schedule_id)
        assert retrieved == sample_schedule

        nonexistent = task_scheduler.get_schedule("nonexistent")
        assert nonexistent is None


class TestScheduleExecution:
    """Test schedule execution functionality."""

    def test_trigger_schedule_now(
        self, task_scheduler, sample_schedule, mock_task_manager
    ):
        """Test manually triggering a schedule."""
        with patch("octopus_scraper.task_manager.scheduler.croniter"):
            task_scheduler.add_schedule(sample_schedule)

        with patch.object(task_scheduler, "_execute_schedule") as mock_execute:
            mock_execute.return_value = "task_123"

            task_id = task_scheduler.trigger_schedule_now(sample_schedule.schedule_id)

        assert task_id == "task_123"
        mock_execute.assert_called_once_with(sample_schedule, manual_trigger=True)

    def test_trigger_nonexistent_schedule(self, task_scheduler):
        """Test triggering a nonexistent schedule."""
        task_id = task_scheduler.trigger_schedule_now("nonexistent")
        assert task_id is None

    @patch("octopus_scraper.task_manager.scheduler.time")
    def test_execute_schedule(
        self, mock_time, task_scheduler, sample_schedule, mock_task_manager
    ):
        """Test executing a schedule."""
        mock_time.time.return_value = 1234567890

        with patch("octopus_scraper.task_manager.scheduler.croniter"):
            task_scheduler.add_schedule(sample_schedule)

        task_id = task_scheduler._execute_schedule(sample_schedule)

        # Verify task was submitted to task manager
        mock_task_manager.submit_task.assert_called_once()
        call_args = mock_task_manager.submit_task.call_args[0][0]

        assert call_args.scraper_name == sample_schedule.scraper_name
        assert call_args.fetch_params == sample_schedule.fetch_params
        assert call_args.metadata["scheduled"] is True
        assert call_args.metadata["schedule_id"] == sample_schedule.schedule_id
        assert call_args.metadata["manual_trigger"] is False

    def test_execute_schedule_manual_trigger(
        self, task_scheduler, sample_schedule, mock_task_manager
    ):
        """Test executing a schedule with manual trigger."""
        with patch("octopus_scraper.task_manager.scheduler.croniter"):
            task_scheduler.add_schedule(sample_schedule)

        with patch("octopus_scraper.task_manager.scheduler.time") as mock_time:
            mock_time.time.return_value = 1234567890

            task_id = task_scheduler._execute_schedule(
                sample_schedule, manual_trigger=True
            )

        # Verify task was submitted
        mock_task_manager.submit_task.assert_called_once()
        call_args = mock_task_manager.submit_task.call_args[0][0]

        assert call_args.metadata["manual_trigger"] is True

    def test_update_next_run_time_enabled(self, task_scheduler, sample_schedule):
        """Test updating next run time for enabled schedule."""
        with patch("octopus_scraper.task_manager.scheduler.croniter") as mock_croniter:
            mock_cron_instance = Mock()
            mock_croniter.return_value = mock_cron_instance
            next_run = datetime.now() + timedelta(hours=6)
            mock_cron_instance.get_next.return_value = next_run

            sample_schedule.enabled = True
            task_scheduler._update_next_run_time(sample_schedule)

        assert sample_schedule.next_run == next_run

    def test_update_next_run_time_disabled(self, task_scheduler, sample_schedule):
        """Test updating next run time for disabled schedule."""
        sample_schedule.enabled = False
        sample_schedule.next_run = datetime.now()  # Set some value

        task_scheduler._update_next_run_time(sample_schedule)

        assert sample_schedule.next_run is None


class TestSchedulerStatus:
    """Test scheduler status and statistics."""

    def test_get_scheduler_status_empty(self, task_scheduler):
        """Test getting scheduler status with no schedules."""
        status = task_scheduler.get_scheduler_status()

        assert status["status"] == "running"
        assert status["total_schedules"] == 0
        assert status["enabled_schedules"] == 0
        assert status["running_scheduled_tasks"] == 0
        assert status["next_run"] is None
        assert status["schedules_by_status"] == {}

    def test_get_scheduler_status_with_schedules(self, task_scheduler):
        """Test getting scheduler status with schedules."""
        schedule1 = TaskScheduleConfig(
            "sched1", "scraper1", "0 */6 * * *", enabled=True
        )
        schedule2 = TaskScheduleConfig("sched2", "scraper2", "0 0 * * *", enabled=False)

        with patch("octopus_scraper.task_manager.scheduler.croniter") as mock_croniter:
            mock_cron_instance = Mock()
            mock_croniter.return_value = mock_cron_instance
            mock_cron_instance.get_next.return_value = datetime.now() + timedelta(
                hours=1
            )

            task_scheduler.add_schedule(schedule1)
            task_scheduler.add_schedule(schedule2)

        status = task_scheduler.get_scheduler_status()

        assert status["total_schedules"] == 2
        assert status["enabled_schedules"] == 1
        assert status["next_run"] is not None
        assert len(status["schedules_by_status"]) == 2
        assert "sched1" in status["schedules_by_status"]
        assert "sched2" in status["schedules_by_status"]

    def test_get_scheduler_status_stopped(self, task_scheduler):
        """Test getting scheduler status when stopped."""
        task_scheduler.stop()

        status = task_scheduler.get_scheduler_status()
        assert status["status"] == "stopped"


class TestConvenienceFunctions:
    """Test convenience functions for creating schedules."""

    def test_create_hourly_schedule(self):
        """Test creating hourly schedule."""
        schedule = create_hourly_schedule(
            schedule_id="hourly_test", scraper_name="test_scraper", minute=30
        )

        assert schedule.schedule_id == "hourly_test"
        assert schedule.scraper_name == "test_scraper"
        assert schedule.cron_expression == "30 * * * *"

    def test_create_daily_schedule(self):
        """Test creating daily schedule."""
        schedule = create_daily_schedule(
            schedule_id="daily_test", scraper_name="test_scraper", hour=8, minute=15
        )

        assert schedule.schedule_id == "daily_test"
        assert schedule.scraper_name == "test_scraper"
        assert schedule.cron_expression == "15 8 * * *"

    def test_create_weekly_schedule(self):
        """Test creating weekly schedule."""
        schedule = create_weekly_schedule(
            schedule_id="weekly_test",
            scraper_name="test_scraper",
            day_of_week=1,  # Monday
            hour=9,
            minute=0,
        )

        assert schedule.schedule_id == "weekly_test"
        assert schedule.scraper_name == "test_scraper"
        assert schedule.cron_expression == "0 9 * * 1"

    def test_convenience_functions_with_kwargs(self):
        """Test convenience functions with additional kwargs."""
        schedule = create_hourly_schedule(
            schedule_id="hourly_test",
            scraper_name="test_scraper",
            minute=30,
            enabled=False,
            max_concurrent_runs=3,
            fetch_params={"limit": 100},
        )

        assert schedule.enabled is False
        assert schedule.max_concurrent_runs == 3
        assert schedule.fetch_params == {"limit": 100}
