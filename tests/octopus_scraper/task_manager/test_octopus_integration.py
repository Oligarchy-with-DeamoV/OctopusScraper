"""
Integration tests for enhanced Octopus with TaskManager.
"""

import threading
import time
from datetime import datetime
from unittest.mock import Mock, patch

import pytest

from octopus_scraper.octopus import Octopus
from octopus_scraper.scraper import Content
from octopus_scraper.task_manager.models import TaskPriority, TaskStatus
from octopus_scraper.task_manager.task_manager import TaskManager


@pytest.fixture
def octopus_config_with_task_manager():
    """Create Octopus configuration with TaskManager enabled."""
    return {
        "scrapers_config_with_fetch_params": [
            {
                "scraper_config": {
                    "fetcher_name": "rsshub",
                    "fetcher_config": {
                        "hub_root": "https://rsshub.app",
                        "route": "/test",
                        "fetch_params": {},
                    },
                    "content_processor_configs": {},
                },
                "fetch_params": {"limit": 10},
            },
            {
                "scraper_config": {
                    "fetcher_name": "direct_rss",
                    "fetcher_config": {
                        "hub_root": "https://example.com",
                        "route": "/feed.xml",
                        "fetch_params": {},
                    },
                    "content_processor_configs": {},
                },
                "fetch_params": {"limit": 5},
            },
        ],
        "notion_api_config": {
            "api_key": "test_api_key",
            "database_id": "test_database_id",
        },
        "max_concurrent_scrapers": 3,
        "use_task_manager": True,
        "task_manager_config": {
            "max_concurrent_tasks": 4,
            "max_queue_size": 100,
            "result_retention_hours": 2,
        },
    }


@pytest.fixture
def mock_notion_storage():
    """Create mock NotionStorage."""
    mock_storage = Mock()
    mock_storage.store_contents_with_dedup.return_value = [True, True, True]
    mock_storage.get_all_content_ids.return_value = set()
    return mock_storage


@pytest.fixture
def sample_contents():
    """Create sample content for testing."""
    return [
        Content(
            content_id="content_1",
            title="Test Article 1",
            link="https://example.com/1",
            summary="Test summary 1",
            content="Test content 1",
            published="2025-07-18T10:00:00Z",
        ),
        Content(
            content_id="content_2",
            title="Test Article 2",
            link="https://example.com/2",
            summary="Test summary 2",
            content="Test content 2",
            published="2025-07-18T11:00:00Z",
        ),
    ]


class TestOctopusTaskManagerIntegration:
    """Test Octopus integration with TaskManager."""

    @patch("octopus_scraper.octopus.NotionStorage")
    def test_octopus_initialization_with_task_manager(
        self, mock_notion_class, octopus_config_with_task_manager
    ):
        """Test Octopus initialization with TaskManager enabled."""
        mock_notion_class.return_value = Mock()

        octopus = Octopus(octopus_config_with_task_manager)

        # Verify TaskManager is initialized
        assert octopus._task_manager is not None
        assert octopus._task_manager.max_concurrent_tasks == 4
        assert octopus._task_manager.max_queue_size == 100
        assert octopus._task_manager.result_retention_hours == 2

        # Verify storage is set
        assert octopus._task_manager._storage is not None

        # Clean up
        octopus.cleanup_task_manager()

    @patch("octopus_scraper.octopus.NotionStorage")
    @patch("octopus_scraper.scraper.Scraper")
    def test_trigger_scraper_with_task_manager(
        self,
        mock_scraper_class,
        mock_notion_class,
        octopus_config_with_task_manager,
        sample_contents,
    ):
        """Test triggering scraper with TaskManager."""
        mock_notion_class.return_value = Mock()
        mock_scraper = Mock()
        mock_scraper.scrap_contents.return_value = sample_contents
        mock_scraper_class.return_value = mock_scraper

        octopus = Octopus(octopus_config_with_task_manager)

        # Trigger scraper
        batch_id = octopus.trigger_scraper()

        # Verify batch ID is returned
        assert batch_id is not None
        assert batch_id.startswith("scraper_batch_")

        # Verify tasks were submitted to TaskManager
        stats = octopus.get_task_manager_statistics()
        assert stats["total_tasks"] == 2  # Two scrapers configured

        # Clean up
        octopus.cleanup_task_manager()

    @patch("octopus_scraper.octopus.NotionStorage")
    def test_get_task_manager_methods(
        self, mock_notion_class, octopus_config_with_task_manager
    ):
        """Test TaskManager-related methods."""
        mock_notion_class.return_value = Mock()

        octopus = Octopus(octopus_config_with_task_manager)

        # Test get_task_manager
        task_manager = octopus.get_task_manager()
        assert task_manager is not None
        assert task_manager == octopus._task_manager

        # Test get_task_manager_statistics
        stats = octopus.get_task_manager_statistics()
        assert isinstance(stats, dict)
        assert "total_tasks" in stats
        assert "completed_tasks" in stats
        assert "failed_tasks" in stats

        # Test list_tasks
        tasks = octopus.list_tasks()
        assert isinstance(tasks, list)

        # Test with status filter
        pending_tasks = octopus.list_tasks(status="pending")
        assert isinstance(pending_tasks, list)

        # Clean up
        octopus.cleanup_task_manager()

    @patch("octopus_scraper.octopus.NotionStorage")
    @patch("octopus_scraper.scraper.Scraper")
    def test_submit_individual_scraper_task(
        self,
        mock_scraper_class,
        mock_notion_class,
        octopus_config_with_task_manager,
        sample_contents,
    ):
        """Test submitting individual scraper task."""
        mock_notion_class.return_value = Mock()
        mock_scraper = Mock()
        mock_scraper.scrap_contents.return_value = sample_contents
        mock_scraper_class.return_value = mock_scraper

        octopus = Octopus(octopus_config_with_task_manager)

        # Submit individual task
        scraper_config = {
            "fetcher_name": "rsshub",
            "fetcher_config": {
                "hub_root": "https://rsshub.app",
                "route": "/individual",
                "fetch_params": {},
            },
            "content_processor_configs": {},
        }
        fetch_params = {"limit": 15}

        task_id = octopus.submit_individual_scraper_task(
            "individual_scraper", scraper_config, fetch_params
        )

        assert task_id is not None

        # Verify task was submitted
        stats = octopus.get_task_manager_statistics()
        assert stats["total_tasks"] >= 1

        # Clean up
        octopus.cleanup_task_manager()

    @patch("octopus_scraper.octopus.NotionStorage")
    def test_task_status_tracking(
        self, mock_notion_class, octopus_config_with_task_manager
    ):
        """Test task status tracking functionality."""
        mock_notion_class.return_value = Mock()

        octopus = Octopus(octopus_config_with_task_manager)

        # Submit a task and get its status
        scraper_config = {
            "fetcher_name": "rsshub",
            "fetcher_config": {
                "hub_root": "https://rsshub.app",
                "route": "/status_test",
                "fetch_params": {},
            },
            "content_processor_configs": {},
        }

        task_id = octopus.submit_individual_scraper_task(
            "status_test_scraper", scraper_config, {}
        )

        # Get task status (might be pending or running)
        status_dict = octopus.get_task_status(task_id)
        if status_dict:  # Task might complete very quickly
            assert status_dict["task_id"] == task_id
            assert "status" in status_dict
            assert "start_time" in status_dict

        # Clean up
        octopus.cleanup_task_manager()

    @patch("octopus_scraper.octopus.NotionStorage")
    def test_task_cancellation(
        self, mock_notion_class, octopus_config_with_task_manager
    ):
        """Test task cancellation functionality."""
        mock_notion_class.return_value = Mock()

        octopus = Octopus(octopus_config_with_task_manager)

        # Submit a task
        scraper_config = {
            "fetcher_name": "rsshub",
            "fetcher_config": {
                "hub_root": "https://rsshub.app",
                "route": "/cancel_test",
                "fetch_params": {},
            },
            "content_processor_configs": {},
        }

        task_id = octopus.submit_individual_scraper_task(
            "cancel_test_scraper", scraper_config, {}
        )

        # Try to cancel the task
        cancelled = octopus.cancel_task(task_id)
        # Result depends on timing - task might already be running or completed
        assert isinstance(cancelled, bool)

        # Clean up
        octopus.cleanup_task_manager()


class TestOctopusTaskManagerConfiguration:
    """Test various TaskManager configurations."""

    @patch("octopus_scraper.octopus.NotionStorage")
    def test_task_manager_with_default_config(self, mock_notion_class):
        """Test TaskManager with default configuration."""
        config = {
            "scrapers_config_with_fetch_params": [],
            "notion_api_config": {
                "api_key": "test_api_key",
                "database_id": "test_database_id",
            },
            "use_task_manager": True,
            # No task_manager_config provided
        }

        mock_notion_class.return_value = Mock()

        octopus = Octopus(config)

        # Should use default values
        assert (
            octopus._task_manager.max_concurrent_tasks == 5
        )  # Default max_concurrent_scrapers
        assert octopus._task_manager.max_queue_size == 1000  # Default
        assert octopus._task_manager.result_retention_hours == 24  # Default

        # Clean up
        octopus.cleanup_task_manager()

    @patch("octopus_scraper.octopus.NotionStorage")
    def test_task_manager_with_partial_config(self, mock_notion_class):
        """Test TaskManager with partial configuration."""
        config = {
            "scrapers_config_with_fetch_params": [],
            "notion_api_config": {
                "api_key": "test_api_key",
                "database_id": "test_database_id",
            },
            "max_concurrent_scrapers": 3,
            "use_task_manager": True,
            "task_manager_config": {
                "max_concurrent_tasks": 6,
                # max_queue_size and result_retention_hours not specified
            },
        }

        mock_notion_class.return_value = Mock()

        octopus = Octopus(config)

        # Should use mix of provided and default values
        assert octopus._task_manager.max_concurrent_tasks == 6  # Provided
        assert octopus._task_manager.max_queue_size == 1000  # Default
        assert octopus._task_manager.result_retention_hours == 24  # Default

        # Clean up
        octopus.cleanup_task_manager()


class TestOctopusErrorHandling:
    """Test error handling in Octopus with TaskManager."""

    @patch("octopus_scraper.octopus.NotionStorage")
    def test_invalid_task_status_filter(
        self, mock_notion_class, octopus_config_with_task_manager
    ):
        """Test handling of invalid task status filter."""
        mock_notion_class.return_value = Mock()

        octopus = Octopus(octopus_config_with_task_manager)

        # Should handle invalid status gracefully
        tasks = octopus.list_tasks(status="invalid_status")
        assert isinstance(tasks, list)
        assert len(tasks) == 0  # Should return empty list for invalid status

        # Clean up
        octopus.cleanup_task_manager()


class TestOctopusUploadConcurrency:
    """Test that concurrent trigger_upload calls are serialized by the lock."""

    @patch("octopus_scraper.octopus.NotionStorage")
    def test_concurrent_upload_only_runs_once(
        self, mock_notion_class, octopus_config_with_task_manager
    ):
        """Two threads calling trigger_upload concurrently: only one should
        actually execute the upload (call store_contents), the other should
        return immediately with zero counts."""
        mock_storage = Mock()
        # Simulate a slow upload so the second thread arrives while the first
        # is still holding the lock.
        upload_event = threading.Event()

        def slow_store_contents(contents, deduplicate=False):
            upload_event.set()  # signal that upload has started
            time.sleep(0.3)
            return [True] * len(contents)

        mock_storage.store_contents.side_effect = slow_store_contents
        mock_storage.get_all_content_ids.return_value = set()
        mock_notion_class.return_value = mock_storage

        octopus = Octopus(octopus_config_with_task_manager)

        # Manually inject a completed task with pending contents
        from octopus_scraper.task_manager.models import TaskResult, TaskStatus

        fake_result = TaskResult(
            task_id="test_task_1",
            status=TaskStatus.COMPLETED,
            start_time=datetime.now(),
            items_uploaded=0,
            metadata={
                "contents": [
                    {
                        "content_id": "c1",
                        "title": "Article 1",
                        "link": "https://example.com/1",
                        "summary": "s",
                        "content": "c",
                        "published": "2025-01-01",
                    }
                ]
            },
        )
        octopus._task_manager._task_results["test_task_1"] = fake_result

        results = [None, None]

        def run_upload(index):
            results[index] = octopus.trigger_upload()

        t1 = threading.Thread(target=run_upload, args=(0,))
        t2 = threading.Thread(target=run_upload, args=(1,))

        t1.start()
        # Wait until the first thread actually starts uploading before
        # launching the second thread, to ensure lock contention.
        upload_event.wait(timeout=2)
        t2.start()

        t1.join(timeout=5)
        t2.join(timeout=5)

        # One thread should have done the upload, the other should have skipped
        tasks_processed = [r["tasks_processed"] for r in results]

        # Exactly one thread should have processed the task
        assert sorted(tasks_processed) == [0, 1]
        # store_contents should only have been called once
        assert mock_storage.store_contents.call_count == 1

        # Clean up
        octopus.cleanup_task_manager()

    @patch("octopus_scraper.octopus.NotionStorage")
    def test_upload_lock_released_on_exception(
        self, mock_notion_class, octopus_config_with_task_manager
    ):
        """Verify that the lock is released even when upload raises an exception,
        so subsequent calls are not permanently blocked."""
        mock_storage = Mock()
        mock_storage.store_contents.side_effect = RuntimeError("Notion API error")
        mock_storage.get_all_content_ids.return_value = set()
        mock_notion_class.return_value = mock_storage

        octopus = Octopus(octopus_config_with_task_manager)

        # Inject a completed task
        from octopus_scraper.task_manager.models import TaskResult, TaskStatus

        fake_result = TaskResult(
            task_id="test_task_err",
            status=TaskStatus.COMPLETED,
            start_time=datetime.now(),
            items_uploaded=0,
            metadata={
                "contents": [
                    {
                        "content_id": "c_err",
                        "title": "Error Article",
                        "link": "https://example.com/err",
                        "summary": "s",
                        "content": "c",
                        "published": "2025-01-01",
                    }
                ]
            },
        )
        octopus._task_manager._task_results["test_task_err"] = fake_result

        # First call should raise
        with pytest.raises(RuntimeError, match="Failed to upload"):
            octopus.trigger_upload()

        # Lock should be released — second call should NOT block
        assert not octopus._upload_lock.locked()

        # Clean up
        octopus.cleanup_task_manager()
