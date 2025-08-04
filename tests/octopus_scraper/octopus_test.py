import time
from unittest.mock import Mock, patch

import pytest
import structlog

from octopus_scraper.octopus import Octopus
from octopus_scraper.scrapers.scraper import Content
from octopus_scraper.task_manager.models import TaskScheduleConfig

logger = structlog.getLogger()


@pytest.mark.need_external_service
def test_octopus_initialization(octopus_config, patch_notion):
    octopus = Octopus(octopus_config)
    assert len(octopus._scrapers) == 1
    # Verify TaskManager is always initialized
    assert octopus._task_manager is not None
    # Verify TaskScheduler is not initialized by default
    assert octopus._task_scheduler is None


@pytest.mark.need_external_service
def test_octopus_initialization_with_scheduler(octopus_config, patch_notion):
    """Test Octopus initialization with scheduler enabled."""
    # Enable scheduler in config
    octopus_config["enable_scheduler"] = True
    octopus_config["auto_start_scheduler"] = False  # Don't auto-start for tests

    octopus = Octopus(octopus_config)
    assert len(octopus._scrapers) == 1
    assert octopus._task_manager is not None
    # Verify TaskScheduler is initialized when enabled
    assert octopus._task_scheduler is not None

    # Clean up
    octopus.cleanup_task_manager()


@pytest.mark.need_external_service
def test_octopus_initialization_with_auto_start_scheduler(octopus_config, patch_notion):
    """Test Octopus initialization with auto-start scheduler."""
    # Enable scheduler with auto-start
    octopus_config["enable_scheduler"] = True
    octopus_config["auto_start_scheduler"] = True

    octopus = Octopus(octopus_config)
    assert octopus._task_scheduler is not None

    # Verify scheduler status shows running
    status = octopus.get_scheduler_status()
    assert status["enabled"] is True
    assert status["status"] == "running"

    # Clean up
    octopus.cleanup_task_manager()


def test_trigger_scraper(octopus_config, patch_scraper_scrap, patch_notion):
    octopus = Octopus(octopus_config)
    logger.error(octopus_config)

    # Trigger scraper returns batch_id now
    batch_id = octopus.trigger_scraper()
    assert batch_id is not None
    assert batch_id.startswith("scraper_batch_")

    # Wait for task completion
    time.sleep(0.5)  # Give tasks time to complete

    # Check task manager statistics
    stats = octopus.get_task_manager_statistics()
    assert stats["total_tasks"] >= 1
    assert stats["completed_tasks"] >= 1


def test_trigger_upload(octopus_config, patch_scraper_scrap, patch_notion):
    octopus = Octopus(octopus_config)

    # Trigger scraper first
    batch_id = octopus.trigger_scraper()
    time.sleep(0.5)  # Wait for completion

    # Now test upload - but since TaskManager handles content separately,
    # we need to manually add some content for upload test
    from octopus_scraper.scrapers.scraper import Content

    test_content = Content(
        title="Test Title",
        link="https://example.com",
        summary="Test Summary",
        content="Test Content",
        content_id="test_id",
        published="2025-04-06T13:50:59+08:00",
    )
    octopus._fetched_contents.append(test_content)

    result = octopus.trigger_upload()
    assert result >= 0  # Should return success count
    assert len(octopus._fetched_contents) == 0  # Should be cleared after upload


def test_set_max_concurrent_scrapers(octopus_config, patch_notion):
    """测试动态设置最大并发数"""
    octopus = Octopus(octopus_config)

    # 测试设置不同的并发数
    octopus.set_max_concurrent_scrapers(3)
    assert octopus._config.max_concurrent_scrapers == 3

    octopus.set_max_concurrent_scrapers(10)
    assert octopus._config.max_concurrent_scrapers == 10


def test_concurrent_scraping(octopus_config, patch_scraper_scrap, patch_notion):
    """测试并发抓取功能"""
    # 添加多个scraper配置用于测试并发
    octopus_config["scrapers_config_with_fetch_params"].extend(
        [
            {
                "scraper_config": octopus_config["scrapers_config_with_fetch_params"][
                    0
                ]["scraper_config"],
                "fetch_params": {"limit": 5},
            },
            {
                "scraper_config": octopus_config["scrapers_config_with_fetch_params"][
                    0
                ]["scraper_config"],
                "fetch_params": {"limit": 3},
            },
        ]
    )

    octopus = Octopus(octopus_config)
    assert len(octopus._scrapers) == 3  # 现在应该有3个scraper

    # Trigger scraper returns batch_id
    batch_id = octopus.trigger_scraper()
    assert batch_id is not None

    # Wait for all tasks to complete
    time.sleep(1.0)

    # Check task manager statistics - should have 3 completed tasks
    stats = octopus.get_task_manager_statistics()
    assert stats["total_tasks"] == 3
    assert stats["completed_tasks"] == 3


class TestOctopusScheduler:
    """Test TaskScheduler integration in Octopus class."""

    @pytest.fixture
    def scheduler_config(self, octopus_config):
        """Create config with scheduler enabled."""
        config = octopus_config.copy()
        config["enable_scheduler"] = True
        config["auto_start_scheduler"] = False  # Don't auto-start for tests
        return config

    @pytest.fixture
    def octopus_with_scheduler(self, scheduler_config, patch_notion):
        """Create Octopus instance with scheduler enabled."""
        octopus = Octopus(scheduler_config)
        yield octopus
        octopus.cleanup_task_manager()

    def test_scheduler_disabled_by_default(self, octopus_config, patch_notion):
        """Test that scheduler is disabled by default."""
        octopus = Octopus(octopus_config)

        assert octopus._task_scheduler is None
        assert octopus.get_task_scheduler() is None

        status = octopus.get_scheduler_status()
        assert status["enabled"] is False
        assert status["status"] == "disabled"

        # Scheduler operations should return False/None
        assert octopus.start_scheduler() is False
        assert octopus.stop_scheduler() is False
        assert octopus.add_schedule(Mock()) is None
        assert octopus.list_schedules() == []

        octopus.cleanup_task_manager()

    def test_scheduler_enabled(self, octopus_with_scheduler):
        """Test scheduler when enabled."""
        octopus = octopus_with_scheduler

        assert octopus._task_scheduler is not None
        assert octopus.get_task_scheduler() is not None

        status = octopus.get_scheduler_status()
        assert status["enabled"] is True

    def test_start_stop_scheduler(self, octopus_with_scheduler):
        """Test starting and stopping scheduler."""
        octopus = octopus_with_scheduler

        # Start scheduler
        assert octopus.start_scheduler() is True
        status = octopus.get_scheduler_status()
        assert status["status"] == "running"

        # Stop scheduler
        assert octopus.stop_scheduler() is True
        status = octopus.get_scheduler_status()
        assert status["status"] == "stopped"

    @patch("octopus_scraper.task_manager.scheduler.croniter")
    def test_add_schedule(self, mock_croniter, octopus_with_scheduler):
        """Test adding a schedule."""
        octopus = octopus_with_scheduler

        # Mock croniter for cron validation
        mock_cron_instance = Mock()
        mock_croniter.return_value = mock_cron_instance
        mock_cron_instance.get_next.return_value = Mock()

        schedule_config = TaskScheduleConfig(
            schedule_id="test_schedule",
            scraper_name="test_scraper",
            cron_expression="0 */6 * * *",
            enabled=True,
            fetch_params={"limit": 10},
        )

        schedule_id = octopus.add_schedule(schedule_config)
        assert schedule_id == "test_schedule"

        # Verify schedule was added
        schedules = octopus.list_schedules()
        assert len(schedules) == 1
        assert schedules[0]["schedule_id"] == "test_schedule"

    @patch("octopus_scraper.task_manager.scheduler.croniter")
    def test_add_scraper_schedule(self, mock_croniter, octopus_with_scheduler):
        """Test adding schedule for existing scraper."""
        octopus = octopus_with_scheduler

        # Mock croniter
        mock_cron_instance = Mock()
        mock_croniter.return_value = mock_cron_instance
        mock_cron_instance.get_next.return_value = Mock()

        # Get the scraper name from configuration
        scraper_name = "rsshub"  # Based on the test config

        schedule_id = octopus.add_scraper_schedule(
            schedule_id="scraper_schedule",
            scraper_name=scraper_name,
            cron_expression="0 9 * * *",
            fetch_params={"limit": 20},
            max_concurrent_runs=1,
            timeout_seconds=1800,
        )

        assert schedule_id == "scraper_schedule"

        # Verify schedule details
        schedule = octopus.get_schedule("scraper_schedule")
        assert schedule is not None
        assert schedule["scraper_name"] == scraper_name
        assert schedule["cron_expression"] == "0 9 * * *"
        assert schedule["fetch_params"]["limit"] == 20

    def test_add_scraper_schedule_nonexistent_scraper(self, octopus_with_scheduler):
        """Test adding schedule for non-existent scraper."""
        octopus = octopus_with_scheduler

        schedule_id = octopus.add_scraper_schedule(
            schedule_id="invalid_schedule",
            scraper_name="nonexistent_scraper",
            cron_expression="0 9 * * *",
        )

        assert schedule_id is None

    @patch("octopus_scraper.task_manager.scheduler.croniter")
    def test_schedule_management_operations(
        self, mock_croniter, octopus_with_scheduler
    ):
        """Test various schedule management operations."""
        octopus = octopus_with_scheduler

        # Mock croniter
        mock_cron_instance = Mock()
        mock_croniter.return_value = mock_cron_instance
        mock_cron_instance.get_next.return_value = Mock()

        # Add a schedule
        schedule_config = TaskScheduleConfig(
            schedule_id="management_test",
            scraper_name="test_scraper",
            cron_expression="0 12 * * *",
            enabled=True,
        )

        schedule_id = octopus.add_schedule(schedule_config)
        assert schedule_id == "management_test"

        # Test get_schedule
        schedule = octopus.get_schedule("management_test")
        assert schedule is not None
        assert schedule["schedule_id"] == "management_test"

        # Test disable_schedule
        assert octopus.disable_schedule("management_test") is True
        schedule = octopus.get_schedule("management_test")
        assert schedule["enabled"] is False

        # Test enable_schedule
        assert octopus.enable_schedule("management_test") is True
        schedule = octopus.get_schedule("management_test")
        assert schedule["enabled"] is True

        # Test remove_schedule
        assert octopus.remove_schedule("management_test") is True
        assert octopus.get_schedule("management_test") is None

        # Test operations on non-existent schedule
        assert octopus.remove_schedule("nonexistent") is False
        assert octopus.enable_schedule("nonexistent") is False
        assert octopus.disable_schedule("nonexistent") is False

    @patch("octopus_scraper.task_manager.scheduler.croniter")
    def test_trigger_schedule_now(
        self, mock_croniter, octopus_with_scheduler, patch_scraper_scrap
    ):
        """Test manually triggering a schedule."""
        octopus = octopus_with_scheduler

        # Mock croniter
        mock_cron_instance = Mock()
        mock_croniter.return_value = mock_cron_instance
        mock_cron_instance.get_next.return_value = Mock()

        # Add a schedule
        schedule_config = TaskScheduleConfig(
            schedule_id="trigger_test",
            scraper_name="test_scraper",
            cron_expression="0 15 * * *",
            enabled=True,
            fetch_params={"limit": 5},
        )

        schedule_id = octopus.add_schedule(schedule_config)
        assert schedule_id == "trigger_test"

        # Trigger the schedule
        task_id = octopus.trigger_schedule_now("trigger_test")
        assert task_id is not None
        assert task_id.startswith("scheduled_trigger_test_")

    def test_list_schedules_filtering(self, octopus_with_scheduler):
        """Test listing schedules with filtering."""
        octopus = octopus_with_scheduler

        with patch("octopus_scraper.task_manager.scheduler.croniter") as mock_croniter:
            mock_cron_instance = Mock()
            mock_croniter.return_value = mock_cron_instance
            mock_cron_instance.get_next.return_value = Mock()

            # Add enabled schedule
            enabled_schedule = TaskScheduleConfig(
                schedule_id="enabled_test",
                scraper_name="test_scraper",
                cron_expression="0 9 * * *",
                enabled=True,
            )
            octopus.add_schedule(enabled_schedule)

            # Add disabled schedule
            disabled_schedule = TaskScheduleConfig(
                schedule_id="disabled_test",
                scraper_name="test_scraper",
                cron_expression="0 18 * * *",
                enabled=False,
            )
            octopus.add_schedule(disabled_schedule)

            # Test list all schedules
            all_schedules = octopus.list_schedules()
            assert len(all_schedules) == 2

            # Test list only enabled schedules
            enabled_schedules = octopus.list_schedules(enabled_only=True)
            assert len(enabled_schedules) == 1
            assert enabled_schedules[0]["schedule_id"] == "enabled_test"

    def test_cleanup_with_scheduler(self, scheduler_config, patch_notion):
        """Test cleanup includes scheduler cleanup."""
        octopus = Octopus(scheduler_config)

        # Start scheduler
        octopus.start_scheduler()
        status = octopus.get_scheduler_status()
        assert status["status"] == "running"

        # Cleanup should stop scheduler
        octopus.cleanup_task_manager()

        # After cleanup, scheduler should be stopped
        status = octopus.get_scheduler_status()
        assert status["status"] == "stopped"
