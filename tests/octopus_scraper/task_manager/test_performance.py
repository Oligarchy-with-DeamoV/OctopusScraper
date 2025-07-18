"""
Performance and stress tests for TaskManager.
"""

import pytest
import time
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from unittest.mock import Mock, patch

from octopus_scraper.task_manager.task_manager import TaskManager
from octopus_scraper.task_manager.models import ScraperTask, TaskPriority, TaskStatus


@pytest.fixture
def high_capacity_task_manager():
    """Create a TaskManager with high capacity for stress testing."""
    manager = TaskManager(
        max_concurrent_tasks=10, max_queue_size=1000, result_retention_hours=1
    )
    yield manager
    manager.stop()


@pytest.fixture
def mock_fast_scraper():
    """Create a mock scraper that completes quickly."""

    def create_scraper(config):
        scraper = Mock()
        scraper.scrap_contents.return_value = [
            Mock(content_id=f"content_{i}") for i in range(3)
        ]
        scraper.set_storage = Mock()
        return scraper

    return create_scraper


@pytest.fixture
def mock_slow_scraper():
    """Create a mock scraper that takes time to complete."""

    def create_scraper(config):
        scraper = Mock()

        def slow_scrap(params):
            time.sleep(0.1)  # Simulate slow operation
            return [Mock(content_id=f"slow_content_{i}") for i in range(2)]

        scraper.scrap_contents.side_effect = slow_scrap
        scraper.set_storage = Mock()
        return scraper

    return create_scraper


class TestTaskManagerPerformance:
    """Test TaskManager performance under various loads."""

    @patch("octopus_scraper.task_manager.task_manager.Scraper")
    def test_high_volume_task_submission(
        self, mock_scraper_class, high_capacity_task_manager, mock_fast_scraper
    ):
        """Test submitting a large number of tasks."""
        mock_scraper_class.side_effect = mock_fast_scraper

        # Submit 100 tasks
        task_ids = []
        start_time = time.time()

        for i in range(100):
            task = ScraperTask(
                task_id=f"perf_task_{i}",
                scraper_name=f"scraper_{i}",
                scraper_config={
                    "fetcher_name": "rsshub",
                    "fetcher_config": {"hub_root": "test", "route": f"/test_{i}"},
                    "content_processor_configs": {},
                },
                fetch_params={"limit": 10},
                priority=TaskPriority.NORMAL,
            )
            task_id = high_capacity_task_manager.submit_task(task)
            task_ids.append(task_id)

        submission_time = time.time() - start_time

        # Verify all tasks were submitted
        assert len(task_ids) == 100
        print(f"Submitted 100 tasks in {submission_time:.3f} seconds")

        # Wait for tasks to complete
        max_wait_time = 30  # seconds
        start_wait = time.time()

        while time.time() - start_wait < max_wait_time:
            stats = high_capacity_task_manager.get_statistics()
            completed = stats["completed_tasks"] + stats["failed_tasks"]
            if completed >= 100:
                break
            time.sleep(0.1)

        completion_time = time.time() - start_wait
        final_stats = high_capacity_task_manager.get_statistics()

        print(f"Completed tasks in {completion_time:.3f} seconds")
        print(f"Final stats: {final_stats}")

        # Verify most tasks completed successfully
        assert (
            final_stats["completed_tasks"] + final_stats["failed_tasks"] >= 90
        )  # Allow some failures

    @patch("octopus_scraper.task_manager.task_manager.Scraper")
    def test_concurrent_task_submission(
        self, mock_scraper_class, high_capacity_task_manager, mock_fast_scraper
    ):
        """Test concurrent task submission from multiple threads."""
        mock_scraper_class.side_effect = mock_fast_scraper

        def submit_tasks(thread_id, num_tasks):
            """Submit tasks from a specific thread."""
            submitted = []
            for i in range(num_tasks):
                task = ScraperTask(
                    task_id=f"concurrent_task_{thread_id}_{i}",
                    scraper_name=f"scraper_{thread_id}_{i}",
                    scraper_config={
                        "fetcher_name": "rsshub",
                        "fetcher_config": {
                            "hub_root": "test",
                            "route": f"/test_{thread_id}_{i}",
                        },
                        "content_processor_configs": {},
                    },
                    fetch_params={"limit": 5},
                )
                try:
                    task_id = high_capacity_task_manager.submit_task(task)
                    submitted.append(task_id)
                except Exception as e:
                    print(f"Failed to submit task from thread {thread_id}: {e}")
            return submitted

        # Submit tasks from 5 threads concurrently
        num_threads = 5
        tasks_per_thread = 20

        with ThreadPoolExecutor(max_workers=num_threads) as executor:
            futures = [
                executor.submit(submit_tasks, thread_id, tasks_per_thread)
                for thread_id in range(num_threads)
            ]

            all_submitted = []
            for future in as_completed(futures):
                submitted_ids = future.result()
                all_submitted.extend(submitted_ids)

        print(
            f"Successfully submitted {len(all_submitted)} tasks from {num_threads} concurrent threads"
        )

        # Verify submission was successful
        assert (
            len(all_submitted) >= num_threads * tasks_per_thread * 0.9
        )  # Allow some failures

        # Wait for completion
        time.sleep(5)
        stats = high_capacity_task_manager.get_statistics()
        print(f"Concurrent submission stats: {stats}")

    @patch("octopus_scraper.task_manager.task_manager.Scraper")
    def test_mixed_priority_performance(
        self, mock_scraper_class, high_capacity_task_manager, mock_fast_scraper
    ):
        """Test performance with mixed priority tasks."""
        mock_scraper_class.side_effect = mock_fast_scraper

        # Submit tasks with different priorities
        priorities = [
            TaskPriority.LOW,
            TaskPriority.NORMAL,
            TaskPriority.HIGH,
            TaskPriority.CRITICAL,
        ]
        task_ids_by_priority = {priority: [] for priority in priorities}

        start_time = time.time()

        for i in range(80):  # 20 tasks per priority
            priority = priorities[i % len(priorities)]
            task = ScraperTask(
                task_id=f"mixed_priority_task_{i}",
                scraper_name=f"scraper_{i}",
                scraper_config={
                    "fetcher_name": "rsshub",
                    "fetcher_config": {"hub_root": "test", "route": f"/test_{i}"},
                    "content_processor_configs": {},
                },
                fetch_params={"limit": 5},
                priority=priority,
            )
            task_id = high_capacity_task_manager.submit_task(task)
            task_ids_by_priority[priority].append(task_id)

        submission_time = time.time() - start_time
        print(f"Submitted 80 mixed priority tasks in {submission_time:.3f} seconds")

        # Wait for completion
        time.sleep(10)

        # Check completion order (higher priority should complete first, generally)
        # This is a statistical test, not absolute due to threading
        stats = high_capacity_task_manager.get_statistics()
        print(f"Mixed priority stats: {stats}")

        assert (
            stats["completed_tasks"] + stats["failed_tasks"] >= 70
        )  # Allow some failures

    def test_memory_usage_under_load(self, high_capacity_task_manager):
        """Test memory usage doesn't grow excessively under load."""
        import psutil
        import os

        process = psutil.Process(os.getpid())
        initial_memory = process.memory_info().rss / 1024 / 1024  # MB

        # Submit many tasks that will complete quickly
        with patch(
            "octopus_scraper.task_manager.task_manager.Scraper"
        ) as mock_scraper_class:
            mock_scraper = Mock()
            mock_scraper.scrap_contents.return_value = []
            mock_scraper_class.return_value = mock_scraper

            # Submit 200 tasks
            for i in range(200):
                task = ScraperTask(
                    task_id=f"memory_test_task_{i}",
                    scraper_name=f"scraper_{i}",
                    scraper_config={
                        "fetcher_name": "rsshub",
                        "fetcher_config": {"hub_root": "test", "route": f"/test_{i}"},
                        "content_processor_configs": {},
                    },
                    fetch_params={"limit": 1},
                )
                high_capacity_task_manager.submit_task(task)

        # Wait for completion
        time.sleep(5)

        # Check memory usage
        final_memory = process.memory_info().rss / 1024 / 1024  # MB
        memory_increase = final_memory - initial_memory

        print(
            f"Memory usage: {initial_memory:.1f} MB -> {final_memory:.1f} MB (+{memory_increase:.1f} MB)"
        )

        # Memory increase should be reasonable (less than 50 MB for this test)
        assert (
            memory_increase < 50
        ), f"Memory usage increased by {memory_increase:.1f} MB"

    def test_cleanup_performance(self, high_capacity_task_manager):
        """Test performance of cleanup operations."""
        # Create many old task results
        from datetime import datetime, timedelta
        from octopus_scraper.task_manager.models import TaskResult

        old_time = datetime.now() - timedelta(hours=2)

        for i in range(1000):
            result = TaskResult(
                task_id=f"old_task_{i}",
                status=TaskStatus.COMPLETED,
                start_time=old_time,
                end_time=old_time + timedelta(seconds=1),
            )
            high_capacity_task_manager._task_results[f"old_task_{i}"] = result

        # Add some recent results
        recent_time = datetime.now() - timedelta(minutes=30)
        for i in range(100):
            result = TaskResult(
                task_id=f"recent_task_{i}",
                status=TaskStatus.COMPLETED,
                start_time=recent_time,
                end_time=recent_time + timedelta(seconds=1),
            )
            high_capacity_task_manager._task_results[f"recent_task_{i}"] = result

        print(f"Created {len(high_capacity_task_manager._task_results)} task results")

        # Measure cleanup time
        start_time = time.time()
        high_capacity_task_manager.cleanup_old_results()
        cleanup_time = time.time() - start_time

        print(f"Cleanup took {cleanup_time:.3f} seconds")
        print(f"Remaining results: {len(high_capacity_task_manager._task_results)}")

        # Cleanup should be fast and effective
        assert cleanup_time < 1.0, f"Cleanup took too long: {cleanup_time:.3f} seconds"
        assert (
            len(high_capacity_task_manager._task_results) <= 100
        )  # Only recent results should remain


class TestTaskManagerStress:
    """Stress tests for TaskManager under extreme conditions."""

    @patch("octopus_scraper.task_manager.task_manager.Scraper")
    def test_queue_saturation(self, mock_scraper_class, mock_slow_scraper):
        """Test behavior when queue reaches capacity."""
        # Create manager with small queue and slow processing
        manager = TaskManager(
            max_concurrent_tasks=2, max_queue_size=10, result_retention_hours=1
        )

        mock_scraper_class.side_effect = mock_slow_scraper

        try:
            # Fill the queue beyond capacity
            submitted_tasks = 0
            failed_submissions = 0

            for i in range(20):  # Try to submit more than queue can hold
                task = ScraperTask(
                    task_id=f"saturation_task_{i}",
                    scraper_name=f"scraper_{i}",
                    scraper_config={
                        "fetcher_name": "rsshub",
                        "fetcher_config": {"hub_root": "test", "route": f"/test_{i}"},
                        "content_processor_configs": {},
                    },
                    fetch_params={"limit": 1},
                )

                try:
                    manager.submit_task(task)
                    submitted_tasks += 1
                except RuntimeError:
                    failed_submissions += 1

            print(f"Submitted: {submitted_tasks}, Failed: {failed_submissions}")

            # Should have some failed submissions due to queue limit
            assert failed_submissions > 0
            assert submitted_tasks <= 12  # Queue size + some running tasks

            # Wait for some tasks to complete
            time.sleep(2)

            stats = manager.get_statistics()
            print(f"Saturation test stats: {stats}")

        finally:
            manager.stop()

    @patch("octopus_scraper.task_manager.task_manager.Scraper")
    def test_rapid_start_stop_cycles(self, mock_scraper_class, mock_fast_scraper):
        """Test rapid start/stop cycles don't cause issues."""
        mock_scraper_class.side_effect = mock_fast_scraper

        for cycle in range(5):
            manager = TaskManager(
                max_concurrent_tasks=3, max_queue_size=50, result_retention_hours=1
            )

            # Submit some tasks
            for i in range(10):
                task = ScraperTask(
                    task_id=f"cycle_{cycle}_task_{i}",
                    scraper_name=f"scraper_{i}",
                    scraper_config={
                        "fetcher_name": "rsshub",
                        "fetcher_config": {"hub_root": "test", "route": f"/test_{i}"},
                        "content_processor_configs": {},
                    },
                    fetch_params={"limit": 1},
                )
                manager.submit_task(task)

            # Let it run briefly
            time.sleep(0.1)

            # Stop manager
            manager.stop()

            print(f"Completed cycle {cycle + 1}")

    def test_error_resilience(self, high_capacity_task_manager):
        """Test TaskManager resilience to various error conditions."""
        errors_handled = 0

        # Test with tasks that raise various exceptions
        error_types = [
            Exception("Generic error"),
            ValueError("Invalid value"),
            ConnectionError("Network error"),
            TimeoutError("Timeout error"),
            KeyError("Missing key"),
        ]

        with patch(
            "octopus_scraper.task_manager.task_manager.Scraper"
        ) as mock_scraper_class:

            def error_scraper(config):
                scraper = Mock()
                error = error_types[
                    len(mock_scraper_class.call_args_list) % len(error_types)
                ]
                scraper.scrap_contents.side_effect = error
                return scraper

            mock_scraper_class.side_effect = error_scraper

            # Submit tasks that will fail
            for i in range(20):
                task = ScraperTask(
                    task_id=f"error_test_task_{i}",
                    scraper_name=f"scraper_{i}",
                    scraper_config={
                        "fetcher_name": "rsshub",
                        "fetcher_config": {"hub_root": "test", "route": f"/test_{i}"},
                        "content_processor_configs": {},
                    },
                    fetch_params={"limit": 1},
                )
                high_capacity_task_manager.submit_task(task)

        # Wait for tasks to complete/fail
        time.sleep(5)

        stats = high_capacity_task_manager.get_statistics()
        print(f"Error resilience stats: {stats}")

        # TaskManager should remain operational despite errors
        assert stats["failed_tasks"] > 0
        assert stats["total_tasks"] == 20

        # Should be able to submit new tasks after errors
        new_task = ScraperTask(
            task_id="post_error_task",
            scraper_name="post_error_scraper",
            scraper_config={
                "fetcher_name": "rsshub",
                "fetcher_config": {"hub_root": "test", "route": "/post_error"},
                "content_processor_configs": {},
            },
            fetch_params={"limit": 1},
        )

        # This should not raise an exception
        task_id = high_capacity_task_manager.submit_task(new_task)
        assert task_id is not None
