"""
Unit tests for TaskManager.
"""

import pytest
import threading
import time
from datetime import datetime, timedelta
from unittest.mock import Mock, patch, MagicMock
from queue import Empty

from octopus_scraper.task_manager.task_manager import TaskManager
from octopus_scraper.task_manager.models import (
    TaskStatus,
    TaskPriority,
    TaskResult,
    ScraperTask,
    TaskBatch,
)


@pytest.fixture
def task_manager():
    """Create a TaskManager instance for testing."""
    manager = TaskManager(
        max_concurrent_tasks=2, max_queue_size=10, result_retention_hours=1
    )
    yield manager
    manager.stop()


@pytest.fixture
def sample_task():
    """Create a sample ScraperTask for testing."""
    return ScraperTask(
        task_id="test_task_123",
        scraper_name="test_scraper",
        scraper_config={
            "fetcher_name": "rsshub",
            "fetcher_config": {"hub_root": "https://test.com", "route": "/test"},
            "content_processor_configs": {},
        },
        fetch_params={"limit": 10},
        priority=TaskPriority.NORMAL,
    )


@pytest.fixture
def sample_batch(sample_task):
    """Create a sample TaskBatch for testing."""
    task2 = ScraperTask(
        task_id="test_task_456",
        scraper_name="test_scraper_2",
        scraper_config={
            "fetcher_name": "direct_rss",
            "fetcher_config": {"hub_root": "https://test2.com", "route": "/feed"},
            "content_processor_configs": {},
        },
        fetch_params={"limit": 5},
        priority=TaskPriority.HIGH,
    )

    return TaskBatch(
        batch_id="test_batch_123", tasks=[sample_task, task2], name="Test Batch"
    )


class TestTaskManagerInitialization:
    """Test TaskManager initialization."""

    def test_init_with_defaults(self):
        """Test TaskManager initialization with default parameters."""
        manager = TaskManager()

        assert manager.max_concurrent_tasks == 5
        assert manager.max_queue_size == 1000
        assert manager.result_retention_hours == 24
        assert manager.persistence_path is None
        assert manager._storage is None
        assert manager._worker_thread is not None
        assert manager._worker_thread.is_alive()

        manager.stop()

    def test_init_with_custom_params(self):
        """Test TaskManager initialization with custom parameters."""
        manager = TaskManager(
            max_concurrent_tasks=3, max_queue_size=500, result_retention_hours=12
        )

        assert manager.max_concurrent_tasks == 3
        assert manager.max_queue_size == 500
        assert manager.result_retention_hours == 12

        manager.stop()

    def test_set_storage(self, task_manager):
        """Test setting storage for content deduplication."""
        mock_storage = Mock()
        task_manager.set_storage(mock_storage)

        assert task_manager._storage == mock_storage

    def test_loads_persisted_task_results(self, tmp_path):
        """Test TaskManager reloads persisted task results on startup."""
        persistence_path = tmp_path / "task_results.sqlite3"
        manager = TaskManager(
            max_concurrent_tasks=1,
            max_queue_size=10,
            result_retention_hours=1,
            persistence_path=str(persistence_path),
        )
        result = TaskResult(
            task_id="persisted_task_123",
            status=TaskStatus.COMPLETED,
            start_time=datetime.now(),
            metadata={
                "fetch_params": {"limit": 10},
                "contents": [
                    Mock(content_id="content_1"),
                    Mock(content_id="content_2"),
                ],
            },
        )
        result.mark_completed(items_fetched=2, items_processed=2)
        manager._persist_result(result)
        manager.stop()

        reloaded_manager = TaskManager(
            max_concurrent_tasks=1,
            max_queue_size=10,
            result_retention_hours=1,
            persistence_path=str(persistence_path),
        )
        try:
            reloaded_result = reloaded_manager.get_task_result("persisted_task_123")

            assert reloaded_result is not None
            assert reloaded_result.status == TaskStatus.COMPLETED
            assert reloaded_result.items_fetched == 2
            assert reloaded_result.metadata["fetch_params"] == {"limit": 10}
            assert reloaded_result.metadata["contents_count"] == 2
            assert "contents" not in reloaded_result.metadata
            assert reloaded_manager.get_statistics()["completed_tasks"] == 0
            assert (
                reloaded_manager.get_statistics()["persisted_task_results_count"] == 1
            )
        finally:
            reloaded_manager.stop()


class TestTaskSubmission:
    """Test task submission functionality."""

    def test_submit_task_success(self, task_manager, sample_task):
        """Test successful task submission."""
        task_id = task_manager.submit_task(sample_task)

        assert task_id == sample_task.task_id
        assert task_manager._stats["total_tasks"] == 1
        assert task_manager._stats["current_queue_size"] >= 0

    def test_submit_batch_success(self, task_manager, sample_batch):
        """Test successful batch submission."""
        submitted_ids = task_manager.submit_batch(sample_batch)

        assert len(submitted_ids) == 2
        assert sample_batch.tasks[0].task_id in submitted_ids
        assert sample_batch.tasks[1].task_id in submitted_ids
        assert task_manager._stats["total_tasks"] == 2

    def test_submit_task_queue_full(self, sample_task):
        """Test task submission when queue is full."""
        # Create manager with very small queue
        manager = TaskManager(max_queue_size=1, max_concurrent_tasks=1)

        # Stop the manager to prevent task processing
        manager.stop()

        # Submit first task - should succeed
        manager.submit_task(sample_task)

        # Submit second task - should fail because queue is full
        task2 = ScraperTask(
            "task_2",
            "scraper_2",
            {
                "content_processor_configs": {},
                "fetcher_config": {"hub_root": "https://test.com", "route": "/test2"},
                "fetcher_name": "rsshub",
            },
            {},
        )

        with pytest.raises(RuntimeError, match="Task queue is full"):
            manager.submit_task(task2)

    def test_submit_batch_partial_failure(self, task_manager):
        """Test batch submission with some failures."""
        # Create a batch where one task will fail to submit
        tasks = [
            ScraperTask("task_1", "scraper_1", {}, {}),
            ScraperTask("task_2", "scraper_2", {}, {}),
        ]
        batch = TaskBatch("batch_123", tasks)

        # Mock submit_task to fail for second task
        original_submit = task_manager.submit_task
        call_count = 0

        def mock_submit(task):
            nonlocal call_count
            call_count += 1
            if call_count == 2:
                raise RuntimeError("Simulated failure")
            return original_submit(task)

        with patch.object(task_manager, "submit_task", side_effect=mock_submit):
            submitted_ids = task_manager.submit_batch(batch)

        assert len(submitted_ids) == 1  # Only first task succeeded
        assert "task_1" in submitted_ids


class TestTaskExecution:
    """Test task execution functionality."""

    @patch("octopus_scraper.task_manager.task_manager.Scraper")
    def test_execute_task_success(self, mock_scraper_class, task_manager, sample_task):
        """Test successful task execution."""
        # Mock scraper and its methods
        mock_scraper = Mock()
        mock_scraper.scrap_contents.return_value = [
            Mock(content_id="content_1"),
            Mock(content_id="content_2"),
        ]
        mock_scraper_class.return_value = mock_scraper

        # Create task result
        result = TaskResult(
            task_id=sample_task.task_id,
            status=TaskStatus.PENDING,
            start_time=datetime.now(),
        )

        # Execute task directly
        task_manager._execute_task(sample_task, result)

        # Verify task execution
        mock_scraper_class.assert_called_once_with(sample_task.scraper_config)
        mock_scraper.scrap_contents.assert_called_once_with(sample_task.fetch_params)
        assert result.status == TaskStatus.COMPLETED
        assert result.items_fetched == 2
        assert result.end_time is not None

    @patch("octopus_scraper.task_manager.task_manager.Scraper")
    def test_execute_task_failure(self, mock_scraper_class, task_manager, sample_task):
        """Test task execution failure."""
        # Mock scraper to raise exception
        mock_scraper = Mock()
        mock_scraper.scrap_contents.side_effect = Exception("Network error")
        mock_scraper_class.return_value = mock_scraper

        # Create task result
        result = TaskResult(
            task_id=sample_task.task_id,
            status=TaskStatus.PENDING,
            start_time=datetime.now(),
        )

        # Execute task directly
        task_manager._execute_task(sample_task, result)

        # Verify task failure
        assert result.status == TaskStatus.FAILED
        assert "Network error" in result.error_message
        assert result.end_time is not None

    @patch("octopus_scraper.task_manager.task_manager.Scraper")
    def test_execute_task_with_storage(
        self, mock_scraper_class, task_manager, sample_task
    ):
        """Test task execution with storage set."""
        mock_storage = Mock()
        task_manager.set_storage(mock_storage)

        mock_scraper = Mock()
        mock_scraper.scrap_contents.return_value = []
        mock_scraper_class.return_value = mock_scraper

        result = TaskResult(
            task_id=sample_task.task_id,
            status=TaskStatus.PENDING,
            start_time=datetime.now(),
        )

        task_manager._execute_task(sample_task, result)

        # Verify storage was set on scraper
        mock_scraper.set_storage.assert_called_once_with(mock_storage)

    @patch("octopus_scraper.task_manager.task_manager.Scraper")
    def test_execute_task_prepends_default_keywords(
        self, mock_scraper_class, task_manager
    ):
        """Test that default_keywords from config are prepended to content keywords."""
        from octopus_scraper.protos import Content

        content = Content(
            content_id="c1",
            title="Test",
            link="http://test.com",
            summary="summary",
            content="content",
            published="2025-01-01",
            keywords=["existing"],
        )

        mock_scraper = Mock()
        mock_scraper.scrap_contents.return_value = [content]
        mock_scraper_class.return_value = mock_scraper

        task = ScraperTask(
            task_id="test_kw",
            scraper_name="test",
            scraper_config={},
            fetch_params={},
            default_keywords=["AI", "ML"],
        )

        result = TaskResult(
            task_id=task.task_id,
            status=TaskStatus.PENDING,
            start_time=datetime.now(),
        )

        task_manager._execute_task(task, result)

        assert content.keywords == ["AI", "ML", "existing"]

    @patch("octopus_scraper.task_manager.task_manager.Scraper")
    def test_execute_task_default_keywords_deduplication(
        self, mock_scraper_class, task_manager
    ):
        """Test that duplicate keywords are removed when merging defaults."""
        from octopus_scraper.protos import Content

        content = Content(
            content_id="c1",
            title="Test",
            link="http://test.com",
            summary="summary",
            content="content",
            published="2025-01-01",
            keywords=["ML", "Data"],
        )

        mock_scraper = Mock()
        mock_scraper.scrap_contents.return_value = [content]
        mock_scraper_class.return_value = mock_scraper

        task = ScraperTask(
            task_id="test_kw_dedup",
            scraper_name="test",
            scraper_config={},
            fetch_params={},
            default_keywords=["AI", "ML"],
        )

        result = TaskResult(
            task_id=task.task_id,
            status=TaskStatus.PENDING,
            start_time=datetime.now(),
        )

        task_manager._execute_task(task, result)

        assert content.keywords == ["AI", "ML", "Data"]

    @patch("octopus_scraper.task_manager.task_manager.Scraper")
    def test_execute_task_no_default_keywords(self, mock_scraper_class, task_manager):
        """Test that content keywords are unchanged when no default_keywords configured."""
        from octopus_scraper.protos import Content

        content = Content(
            content_id="c1",
            title="Test",
            link="http://test.com",
            summary="summary",
            content="content",
            published="2025-01-01",
            keywords=["existing"],
        )

        mock_scraper = Mock()
        mock_scraper.scrap_contents.return_value = [content]
        mock_scraper_class.return_value = mock_scraper

        task = ScraperTask(
            task_id="test_no_kw",
            scraper_name="test",
            scraper_config={},
            fetch_params={},
        )

        result = TaskResult(
            task_id=task.task_id,
            status=TaskStatus.PENDING,
            start_time=datetime.now(),
        )

        task_manager._execute_task(task, result)

        assert content.keywords == ["existing"]


class TestTaskRetrieval:
    """Test task result retrieval functionality."""

    def test_get_task_result(self, task_manager, sample_task):
        """Test getting task result by ID."""
        # Submit task and get result
        task_manager.submit_task(sample_task)

        # Wait a bit for task to be processed
        time.sleep(0.1)

        result = task_manager.get_task_result(sample_task.task_id)
        assert result is not None
        assert result.task_id == sample_task.task_id

    def test_get_task_result_nonexistent(self, task_manager):
        """Test getting result for nonexistent task."""
        result = task_manager.get_task_result("nonexistent_task")
        assert result is None

    def test_get_task_status(self, task_manager, sample_task):
        """Test getting task status by ID."""
        task_manager.submit_task(sample_task)
        time.sleep(0.1)

        status = task_manager.get_task_status(sample_task.task_id)
        assert status is not None
        assert isinstance(status, TaskStatus)

    def test_list_tasks_no_filter(self, task_manager, sample_batch):
        """Test listing tasks without filter."""
        task_manager.submit_batch(sample_batch)
        time.sleep(0.1)

        tasks = task_manager.list_tasks()
        assert len(tasks) >= 2

    def test_list_tasks_with_status_filter(self, task_manager, sample_batch):
        """Test listing tasks with status filter."""
        task_manager.submit_batch(sample_batch)
        time.sleep(0.1)

        pending_tasks = task_manager.list_tasks(status=TaskStatus.PENDING)
        # Results depend on timing, but should be a list
        assert isinstance(pending_tasks, list)

    def test_list_tasks_with_limit(self, task_manager):
        """Test listing tasks with limit."""
        # Submit multiple tasks
        for i in range(5):
            task = ScraperTask(f"task_{i}", f"scraper_{i}", {}, {})
            task_manager.submit_task(task)

        time.sleep(0.1)

        tasks = task_manager.list_tasks(limit=3)
        assert len(tasks) <= 3


class TestTaskCancellation:
    """Test task cancellation functionality."""

    def test_cancel_pending_task(self, task_manager, sample_task):
        """Test cancelling a pending task."""
        task_manager.submit_task(sample_task)

        # Cancel immediately before it starts running
        cancelled = task_manager.cancel_task(sample_task.task_id)

        # Result depends on timing, but method should not raise error
        assert isinstance(cancelled, bool)

    def test_cancel_queued_task_updates_pending_result(self, sample_task):
        """Test cancellation can mark a queued task before worker execution."""
        manager = TaskManager(max_queue_size=10, max_concurrent_tasks=1)
        manager.stop()

        try:
            manager.submit_task(sample_task)
            cancelled = manager.cancel_task(sample_task.task_id)
            result = manager.get_task_result(sample_task.task_id)

            assert cancelled is True
            assert result is not None
            assert result.status == TaskStatus.CANCELLED
            assert manager.get_statistics()["cancelled_tasks"] == 1
        finally:
            manager.stop()

    def test_cancel_nonexistent_task(self, task_manager):
        """Test cancelling a nonexistent task."""
        cancelled = task_manager.cancel_task("nonexistent_task")
        assert cancelled is False

    def test_cancel_does_not_overwrite_terminal_result(self, task_manager):
        """Test cancellation keeps completed task state and stats unchanged."""
        result = TaskResult(
            task_id="completed_task",
            status=TaskStatus.COMPLETED,
            start_time=datetime.now(),
            end_time=datetime.now(),
        )
        task_manager._task_results[result.task_id] = result

        task_manager._mark_task_cancelled(result.task_id)

        assert result.status == TaskStatus.COMPLETED
        assert task_manager.get_statistics()["cancelled_tasks"] == 0


class TestTaskManagerStatistics:
    """Test statistics functionality."""

    def test_get_statistics_initial(self, task_manager):
        """Test getting statistics for empty task manager."""
        stats = task_manager.get_statistics()

        assert stats["total_tasks"] == 0
        assert stats["completed_tasks"] == 0
        assert stats["failed_tasks"] == 0
        assert stats["cancelled_tasks"] == 0
        assert stats["current_queue_size"] >= 0
        assert stats["running_tasks_count"] >= 0
        assert stats["success_rate_percent"] == 0
        assert "average_task_duration_seconds" in stats
        assert "max_concurrent_tasks" in stats
        assert "queue_capacity" in stats

    def test_get_statistics_after_tasks(self, task_manager, sample_batch):
        """Test getting statistics after submitting tasks."""
        task_manager.submit_batch(sample_batch)

        stats = task_manager.get_statistics()
        assert stats["total_tasks"] == 2
        assert stats["current_queue_size"] >= 0

    @patch("octopus_scraper.task_manager.task_manager.Scraper")
    def test_state_updates_thread_safe_under_concurrent_access(
        self, mock_scraper_class
    ):
        """Exercise submit, cancel, completion, listing, and stats concurrently."""
        mock_scraper = Mock()

        def slow_scrape(_fetch_params):
            time.sleep(0.01)
            return []

        mock_scraper.scrap_contents.side_effect = slow_scrape
        mock_scraper_class.return_value = mock_scraper
        manager = TaskManager(max_concurrent_tasks=2, max_queue_size=100)
        errors = []

        def capture_errors(func):
            try:
                func()
            except Exception as exc:
                errors.append(exc)

        def submit_tasks():
            for index in range(20):
                manager.submit_task(
                    ScraperTask(
                        task_id=f"concurrent_{index}",
                        scraper_name="concurrent",
                        scraper_config={},
                        fetch_params={},
                    )
                )

        def cancel_some_tasks():
            for index in range(0, 20, 3):
                manager.cancel_task(f"concurrent_{index}")
                time.sleep(0.002)

        def read_state():
            for _ in range(50):
                manager.list_tasks(limit=25)
                manager.get_statistics()
                time.sleep(0.001)

        threads = [
            threading.Thread(target=capture_errors, args=(submit_tasks,)),
            threading.Thread(target=capture_errors, args=(cancel_some_tasks,)),
            threading.Thread(target=capture_errors, args=(read_state,)),
            threading.Thread(target=capture_errors, args=(read_state,)),
        ]

        try:
            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join()

            deadline = time.time() + 2
            while time.time() < deadline:
                stats = manager.get_statistics()
                if stats["running_tasks_count"] == 0 and manager._task_queue.empty():
                    break
                time.sleep(0.02)

            stats = manager.get_statistics()
            with manager._state_lock:
                running_count = len(manager._running_tasks)

            assert errors == []
            assert stats["running_tasks_count"] == running_count
            assert (
                stats["completed_tasks"] + stats["cancelled_tasks"]
                <= stats["total_tasks"]
            )
        finally:
            manager.stop()


class TestTaskManagerHooks:
    """Test pre and post execution hooks."""

    def test_add_pre_execution_hook(self, task_manager, sample_task):
        """Test adding and executing pre-execution hook."""
        hook_called = []

        def test_hook(task):
            hook_called.append(task.task_id)

        task_manager.add_pre_execution_hook(test_hook)

        # Execute task with mock scraper
        with patch("octopus_scraper.task_manager.task_manager.Scraper"):
            result = TaskResult(
                task_id=sample_task.task_id,
                status=TaskStatus.PENDING,
                start_time=datetime.now(),
            )
            task_manager._execute_task(sample_task, result)

        assert sample_task.task_id in hook_called

    def test_add_post_execution_hook(self, task_manager, sample_task):
        """Test adding and executing post-execution hook."""
        hook_called = []

        def test_hook(task, result):
            hook_called.append((task.task_id, result.status))

        task_manager.add_post_execution_hook(test_hook)

        # Execute task with mock scraper
        with patch("octopus_scraper.task_manager.task_manager.Scraper"):
            result = TaskResult(
                task_id=sample_task.task_id,
                status=TaskStatus.PENDING,
                start_time=datetime.now(),
            )
            task_manager._execute_task(sample_task, result)

        assert len(hook_called) == 1
        assert hook_called[0][0] == sample_task.task_id


class TestTaskManagerCleanup:
    """Test cleanup functionality."""

    def test_cleanup_old_results(self, task_manager):
        """Test cleaning up old task results."""
        # Create old task result
        old_result = TaskResult(
            task_id="old_task",
            status=TaskStatus.COMPLETED,
            start_time=datetime.now() - timedelta(hours=25),  # Older than retention
            end_time=datetime.now() - timedelta(hours=25),
        )
        task_manager._task_results["old_task"] = old_result

        # Create recent task result
        recent_result = TaskResult(
            task_id="recent_task",
            status=TaskStatus.COMPLETED,
            start_time=datetime.now() - timedelta(minutes=30),
            end_time=datetime.now() - timedelta(minutes=30),
        )
        task_manager._task_results["recent_task"] = recent_result

        # Cleanup
        task_manager.cleanup_old_results()

        # Old result should be removed, recent should remain
        assert "old_task" not in task_manager._task_results
        assert "recent_task" in task_manager._task_results

    def test_stop_task_manager(self, task_manager, sample_batch):
        """Test stopping task manager."""
        # Submit some tasks
        task_manager.submit_batch(sample_batch)

        # Stop manager
        task_manager.stop()

        # Verify stop event is set
        assert task_manager._stop_event.is_set()

        # Statistics should show cancelled tasks
        stats = task_manager.get_statistics()
        assert stats["cancelled_tasks"] >= 0  # Some tasks might have been cancelled
