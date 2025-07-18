"""
Unit tests for task manager models.
"""

import pytest
from datetime import datetime, timedelta
from unittest.mock import patch

from octopus_scraper.task_manager.models import (
    TaskStatus,
    TaskPriority,
    TaskResult,
    ScraperTask,
    TaskBatch,
    TaskScheduleConfig,
)


class TestTaskStatus:
    """Test TaskStatus enum."""

    def test_task_status_values(self):
        """Test all task status values."""
        assert TaskStatus.PENDING.value == "pending"
        assert TaskStatus.RUNNING.value == "running"
        assert TaskStatus.COMPLETED.value == "completed"
        assert TaskStatus.FAILED.value == "failed"
        assert TaskStatus.CANCELLED.value == "cancelled"
        assert TaskStatus.RETRYING.value == "retrying"


class TestTaskPriority:
    """Test TaskPriority enum."""

    def test_task_priority_values(self):
        """Test all task priority values."""
        assert TaskPriority.LOW.value == 1
        assert TaskPriority.NORMAL.value == 5
        assert TaskPriority.HIGH.value == 8
        assert TaskPriority.CRITICAL.value == 10

    def test_priority_ordering(self):
        """Test priority ordering for queue management."""
        assert TaskPriority.CRITICAL.value > TaskPriority.HIGH.value
        assert TaskPriority.HIGH.value > TaskPriority.NORMAL.value
        assert TaskPriority.NORMAL.value > TaskPriority.LOW.value


class TestTaskResult:
    """Test TaskResult dataclass."""

    def test_task_result_creation(self):
        """Test basic TaskResult creation."""
        start_time = datetime.now()
        result = TaskResult(
            task_id="test_task_123", status=TaskStatus.PENDING, start_time=start_time
        )

        assert result.task_id == "test_task_123"
        assert result.status == TaskStatus.PENDING
        assert result.start_time == start_time
        assert result.end_time is None
        assert result.duration_seconds is None
        assert result.items_fetched == 0
        assert result.items_processed == 0
        assert result.items_uploaded == 0
        assert result.error_message is None
        assert result.metadata == {}

    def test_mark_completed(self):
        """Test marking task as completed."""
        start_time = datetime.now()
        result = TaskResult(
            task_id="test_task_123", status=TaskStatus.RUNNING, start_time=start_time
        )

        with patch("octopus_scraper.task_manager.models.datetime") as mock_datetime:
            end_time = start_time + timedelta(seconds=10)
            mock_datetime.now.return_value = end_time

            result.mark_completed(items_fetched=5, items_processed=4, items_uploaded=3)

        assert result.status == TaskStatus.COMPLETED
        assert result.end_time == end_time
        assert result.duration_seconds == 10.0
        assert result.items_fetched == 5
        assert result.items_processed == 4
        assert result.items_uploaded == 3
        assert result.error_message is None

    def test_mark_failed(self):
        """Test marking task as failed."""
        start_time = datetime.now()
        result = TaskResult(
            task_id="test_task_123", status=TaskStatus.RUNNING, start_time=start_time
        )

        error_message = "Connection timeout"

        with patch("octopus_scraper.task_manager.models.datetime") as mock_datetime:
            end_time = start_time + timedelta(seconds=5)
            mock_datetime.now.return_value = end_time

            result.mark_failed(error_message)

        assert result.status == TaskStatus.FAILED
        assert result.end_time == end_time
        assert result.duration_seconds == 5.0
        assert result.error_message == error_message


class TestScraperTask:
    """Test ScraperTask dataclass."""

    def test_scraper_task_creation(self):
        """Test basic ScraperTask creation."""
        task = ScraperTask(
            task_id="task_123",
            scraper_name="test_scraper",
            scraper_config={"fetcher": "rsshub"},
            fetch_params={"limit": 10},
        )

        assert task.task_id == "task_123"
        assert task.scraper_name == "test_scraper"
        assert task.scraper_config == {"fetcher": "rsshub"}
        assert task.fetch_params == {"limit": 10}
        assert task.priority == TaskPriority.NORMAL
        assert task.max_retries == 3
        assert task.retry_count == 0
        assert task.retry_delay_seconds == 60
        assert task.timeout_seconds == 300
        assert isinstance(task.created_at, datetime)
        assert task.scheduled_at is None
        assert task.depends_on is None
        assert task.tags == []
        assert task.metadata == {}

    def test_from_scraper_config(self):
        """Test creating ScraperTask from scraper configuration."""
        scraper_config = {
            "name": "test_scraper",
            "fetcher": "rsshub",
            "hub_root": "https://rsshub.app",
            "route": "/test",
            "priority": 8,
        }
        fetch_params = {"limit": 20}

        with patch("octopus_scraper.task_manager.models.uuid.uuid4") as mock_uuid:
            mock_uuid.return_value.hex = "abc123"
            mock_uuid.return_value.__str__ = lambda x: "abc123-uuid"

            task = ScraperTask.from_scraper_config(scraper_config, fetch_params)

        assert task.task_id == "abc123-uuid"
        assert task.scraper_name == "test_scraper"
        assert task.scraper_config == scraper_config
        assert task.fetch_params == fetch_params
        assert task.priority == TaskPriority.HIGH  # priority 8 maps to HIGH
        assert task.tags == ["rsshub"]
        assert task.metadata["hub_root"] == "https://rsshub.app"
        assert task.metadata["route"] == "/test"
        assert task.metadata["fetcher"] == "rsshub"

    def test_priority_mapping(self):
        """Test priority value to TaskPriority enum mapping."""
        test_cases = [
            (1, TaskPriority.LOW),
            (3, TaskPriority.LOW),
            (5, TaskPriority.NORMAL),
            (6, TaskPriority.NORMAL),
            (8, TaskPriority.HIGH),
            (10, TaskPriority.CRITICAL),
            (99, TaskPriority.NORMAL),  # Invalid priority defaults to NORMAL
        ]

        for priority_value, expected_priority in test_cases:
            scraper_config = {"name": "test_scraper", "priority": priority_value}
            task = ScraperTask.from_scraper_config(scraper_config, {})
            assert task.priority == expected_priority

    def test_should_retry(self):
        """Test retry logic."""
        task = ScraperTask(
            task_id="task_123",
            scraper_name="test_scraper",
            scraper_config={},
            fetch_params={},
            max_retries=3,
            retry_count=0,
        )

        # Should retry when retry_count < max_retries
        assert task.should_retry() is True

        task.retry_count = 2
        assert task.should_retry() is True

        task.retry_count = 3
        assert task.should_retry() is False

        task.retry_count = 5
        assert task.should_retry() is False

    def test_get_next_retry_time(self):
        """Test exponential backoff retry timing."""
        task = ScraperTask(
            task_id="task_123",
            scraper_name="test_scraper",
            scraper_config={},
            fetch_params={},
            retry_delay_seconds=60,
            retry_count=0,
        )

        with patch("octopus_scraper.task_manager.models.datetime") as mock_datetime:
            now = datetime.now()
            mock_datetime.now.return_value = now

            # First retry: 60 seconds
            task.retry_count = 0
            next_retry = task.get_next_retry_time()
            assert next_retry == now + timedelta(seconds=60)

            # Second retry: 120 seconds
            task.retry_count = 1
            next_retry = task.get_next_retry_time()
            assert next_retry == now + timedelta(seconds=120)

            # Third retry: 240 seconds
            task.retry_count = 2
            next_retry = task.get_next_retry_time()
            assert next_retry == now + timedelta(seconds=240)

            # Very high retry count should cap at 1 hour
            task.retry_count = 10
            next_retry = task.get_next_retry_time()
            assert next_retry == now + timedelta(seconds=3600)


class TestTaskBatch:
    """Test TaskBatch dataclass."""

    def test_task_batch_creation(self):
        """Test basic TaskBatch creation."""
        tasks = [
            ScraperTask("task_1", "scraper_1", {}, {}),
            ScraperTask("task_2", "scraper_2", {}, {}),
        ]

        batch = TaskBatch(
            batch_id="batch_123",
            tasks=tasks,
            name="Test Batch",
            description="Test batch description",
        )

        assert batch.batch_id == "batch_123"
        assert len(batch.tasks) == 2
        assert batch.name == "Test Batch"
        assert batch.description == "Test batch description"
        assert isinstance(batch.created_at, datetime)

    def test_get_task_by_id(self):
        """Test finding task by ID in batch."""
        task1 = ScraperTask("task_1", "scraper_1", {}, {})
        task2 = ScraperTask("task_2", "scraper_2", {}, {})

        batch = TaskBatch(batch_id="batch_123", tasks=[task1, task2])

        found_task = batch.get_task_by_id("task_1")
        assert found_task == task1

        found_task = batch.get_task_by_id("task_2")
        assert found_task == task2

        found_task = batch.get_task_by_id("nonexistent")
        assert found_task is None


class TestTaskScheduleConfig:
    """Test TaskScheduleConfig dataclass."""

    def test_task_schedule_config_creation(self):
        """Test basic TaskScheduleConfig creation."""
        schedule = TaskScheduleConfig(
            schedule_id="schedule_123",
            scraper_name="test_scraper",
            cron_expression="0 */6 * * *",
            enabled=True,
            max_concurrent_runs=2,
            timeout_seconds=600,
            retry_config={"max_retries": 3},
            fetch_params={"limit": 50},
            metadata={"source": "github"},
        )

        assert schedule.schedule_id == "schedule_123"
        assert schedule.scraper_name == "test_scraper"
        assert schedule.cron_expression == "0 */6 * * *"
        assert schedule.enabled is True
        assert schedule.max_concurrent_runs == 2
        assert schedule.timeout_seconds == 600
        assert schedule.retry_config == {"max_retries": 3}
        assert schedule.fetch_params == {"limit": 50}
        assert schedule.metadata == {"source": "github"}
        assert isinstance(schedule.created_at, datetime)
        assert schedule.last_run is None
        assert schedule.next_run is None

    def test_default_values(self):
        """Test default values for TaskScheduleConfig."""
        schedule = TaskScheduleConfig(
            schedule_id="schedule_123",
            scraper_name="test_scraper",
            cron_expression="0 0 * * *",
        )

        assert schedule.enabled is True
        assert schedule.max_concurrent_runs == 1
        assert schedule.timeout_seconds == 300
        assert schedule.retry_config == {}
        assert schedule.fetch_params == {}
        assert schedule.metadata == {}
