"""
Enhanced Task Manager for OctopusScraper.

This module provides comprehensive task management capabilities including
task queuing, execution, monitoring, and result tracking.
"""

import asyncio
import itertools
import threading
import time
from collections import defaultdict, deque
from concurrent.futures import Future, ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta
from queue import Empty, PriorityQueue
from typing import Any, Callable, Dict, List, Optional

import structlog

from octopus_scraper.scraper import Content, Scraper
from octopus_scraper.task_manager.models import (
    ScraperTask,
    TaskBatch,
    TaskPriority,
    TaskResult,
    TaskStatus,
)
from octopus_scraper.task_manager.task_result_store import TaskResultStore

logger = structlog.get_logger(__name__)


class TaskManager:
    """Enhanced task manager with queuing, prioritization, and monitoring capabilities."""

    def __init__(
        self,
        max_concurrent_tasks: int = 5,
        max_queue_size: int = 1000,
        result_retention_hours: int = 24,
        persistence_path: Optional[str] = None,
    ):
        """
        Initialize TaskManager.

        Args:
            max_concurrent_tasks: Maximum number of concurrent tasks
            max_queue_size: Maximum queue size for pending tasks
            result_retention_hours: How long to keep task results in memory
            persistence_path: Optional SQLite database path for task results
        """
        self.max_concurrent_tasks = max_concurrent_tasks
        self.max_queue_size = max_queue_size
        self.result_retention_hours = result_retention_hours
        self.persistence_path = persistence_path

        # Task queues and tracking
        self._task_queue = PriorityQueue(maxsize=max_queue_size)
        self._task_counter = itertools.count()  # Unique counter for queue ordering
        self._state_lock = threading.RLock()
        self._running_tasks: Dict[str, Future] = {}
        self._task_results: Dict[str, TaskResult] = {}
        self._task_history: deque = deque(maxlen=10000)  # Keep last 10k tasks

        # Task execution
        self._executor = ThreadPoolExecutor(max_workers=max_concurrent_tasks)
        self._stop_event = threading.Event()
        self._worker_thread: Optional[threading.Thread] = None

        # Statistics and monitoring
        self._stats = {
            "total_tasks": 0,
            "completed_tasks": 0,
            "failed_tasks": 0,
            "cancelled_tasks": 0,
            "current_queue_size": 0,
            "running_tasks_count": 0,
            "persisted_task_results_count": 0,
        }

        # Task lifecycle hooks
        self._pre_execution_hooks: List[Callable] = []
        self._post_execution_hooks: List[Callable] = []

        # Storage reference for content deduplication
        self._storage = None

        self._result_store = (
            TaskResultStore(persistence_path) if persistence_path else None
        )
        if self._result_store:
            self._load_persisted_results()

        # Start worker thread
        self.start()

    def set_storage(self, storage):
        """Set storage for content deduplication."""
        self._storage = storage

    def start(self):
        """Start the task manager worker thread."""
        if self._worker_thread is None or not self._worker_thread.is_alive():
            self._stop_event.clear()
            self._worker_thread = threading.Thread(
                target=self._worker_loop, daemon=True
            )
            self._worker_thread.start()
            logger.info("TaskManager started")

    def stop(self):
        """Stop the task manager and wait for current tasks to complete."""
        logger.info("Stopping TaskManager...")
        self._stop_event.set()

        # Cancel pending tasks
        pending_tasks = []
        while not self._task_queue.empty():
            try:
                _, _, task = self._task_queue.get_nowait()
                pending_tasks.append(task)
                self._mark_task_cancelled(task.task_id)
            except Empty:
                break

        # Wait for running tasks to complete
        with self._state_lock:
            running_futures = list(self._running_tasks.values())

        for future in running_futures:
            future.cancel()

        # Shutdown executor
        self._executor.shutdown(wait=True)

        # Wait for worker thread
        if self._worker_thread and self._worker_thread.is_alive():
            self._worker_thread.join(timeout=5)

        logger.info(
            f"TaskManager stopped. Cancelled {len(pending_tasks)} pending tasks"
        )

    def submit_task(self, task: ScraperTask) -> str:
        """
        Submit a task for execution.

        Args:
            task: ScraperTask to execute

        Returns:
            Task ID

        Raises:
            RuntimeError: If queue is full
        """
        if self._task_queue.full():
            raise RuntimeError("Task queue is full")

        # Priority queue uses (priority, counter, task) tuple to avoid task comparison
        # Lower priority number = higher priority
        priority_value = 10 - task.priority.value  # Invert for proper ordering

        try:
            self._task_queue.put(
                (priority_value, next(self._task_counter), task), block=False
            )
            with self._state_lock:
                self._task_results.setdefault(
                    task.task_id,
                    TaskResult(
                        task_id=task.task_id,
                        status=TaskStatus.PENDING,
                        start_time=datetime.now(),
                    ),
                )
                self._stats["total_tasks"] += 1
                self._stats["current_queue_size"] = self._task_queue.qsize()

            logger.info(
                "Task submitted",
                task_id=task.task_id,
                scraper_name=task.scraper_name,
                priority=task.priority.name,
                queue_size=self._task_queue.qsize(),
            )

            return task.task_id

        except Exception as e:
            logger.error("Failed to submit task", task_id=task.task_id, error=str(e))
            raise

    def submit_batch(self, batch: TaskBatch) -> List[str]:
        """Submit a batch of tasks."""
        submitted_ids = []
        for task in batch.tasks:
            try:
                task_id = self.submit_task(task)
                submitted_ids.append(task_id)
            except Exception as e:
                logger.error(
                    "Failed to submit task in batch",
                    batch_id=batch.batch_id,
                    task_id=task.task_id,
                    error=str(e),
                )

        logger.info(
            "Batch submitted",
            batch_id=batch.batch_id,
            total_tasks=len(batch.tasks),
            submitted_tasks=len(submitted_ids),
        )

        return submitted_ids

    def cancel_task(self, task_id: str) -> bool:
        """Cancel a task if it's still pending or running."""
        with self._state_lock:
            future = self._running_tasks.get(task_id)

        if future:
            cancelled = future.cancel()
            if cancelled:
                self._mark_task_cancelled(task_id)
            return cancelled

        with self._state_lock:
            result = self._task_results.get(task_id)
            if result and result.status == TaskStatus.PENDING:
                self._mark_task_cancelled(task_id)
                return True

        return False

    def get_task_result(self, task_id: str) -> Optional[TaskResult]:
        """Get task result by ID."""
        with self._state_lock:
            return self._task_results.get(task_id)

    def get_task_status(self, task_id: str) -> Optional[TaskStatus]:
        """Get task status by ID."""
        with self._state_lock:
            result = self._task_results.get(task_id)
        return result.status if result else None

    def list_tasks(
        self, status: Optional[TaskStatus] = None, limit: int = 100
    ) -> List[TaskResult]:
        """List tasks, optionally filtered by status."""
        with self._state_lock:
            results = list(self._task_results.values())

        if status:
            results = [r for r in results if r.status == status]

        # Sort by start time, most recent first
        results.sort(key=lambda x: x.start_time, reverse=True)

        return results[:limit]

    def get_statistics(self) -> Dict[str, Any]:
        """Get task manager statistics."""
        with self._state_lock:
            # Update current counts
            self._stats["current_queue_size"] = self._task_queue.qsize()
            self._stats["running_tasks_count"] = len(self._running_tasks)
            stats = dict(self._stats)
            task_results = list(self._task_results.values())

        # Calculate success rate
        total_finished = stats["completed_tasks"] + stats["failed_tasks"]
        success_rate = (
            (stats["completed_tasks"] / total_finished * 100)
            if total_finished > 0
            else 0
        )

        # Recent task performance
        recent_tasks = [
            r
            for r in task_results
            if r.end_time and r.end_time > datetime.now() - timedelta(hours=1)
        ]

        avg_duration = 0
        if recent_tasks:
            durations = [r.duration_seconds for r in recent_tasks if r.duration_seconds]
            avg_duration = sum(durations) / len(durations) if durations else 0

        return {
            **stats,
            "success_rate_percent": round(success_rate, 2),
            "average_task_duration_seconds": round(avg_duration, 2),
            "recent_tasks_count": len(recent_tasks),
            "queue_capacity": self.max_queue_size,
            "max_concurrent_tasks": self.max_concurrent_tasks,
        }

    def cleanup_old_results(self):
        """Clean up old task results to prevent memory leaks."""
        cutoff_time = datetime.now() - timedelta(hours=self.result_retention_hours)

        with self._state_lock:
            to_remove = []
            for task_id, result in self._task_results.items():
                if result.end_time and result.end_time < cutoff_time:
                    to_remove.append(task_id)

            for task_id in to_remove:
                del self._task_results[task_id]

        if to_remove:
            logger.debug(f"Cleaned up {len(to_remove)} old task results")

        if self._result_store:
            deleted_count = self._result_store.delete_results_older_than(cutoff_time)
            if deleted_count:
                logger.debug("Cleaned up persisted task results", count=deleted_count)

    def add_pre_execution_hook(self, hook: Callable[[ScraperTask], None]):
        """Add a pre-execution hook."""
        self._pre_execution_hooks.append(hook)

    def add_post_execution_hook(self, hook: Callable[[ScraperTask, TaskResult], None]):
        """Add a post-execution hook."""
        self._post_execution_hooks.append(hook)

    def _worker_loop(self):
        """Main worker loop for processing tasks."""
        logger.info("TaskManager worker loop started")

        while not self._stop_event.is_set():
            try:
                # Get next task from queue (blocks for up to 1 second)
                try:
                    priority, counter, task = self._task_queue.get(timeout=1.0)
                    with self._state_lock:
                        self._stats["current_queue_size"] = self._task_queue.qsize()
                except Empty:
                    # Cleanup old results periodically
                    self.cleanup_old_results()
                    continue

                # Check if we have capacity to run the task
                with self._state_lock:
                    running_task_count = len(self._running_tasks)
                if running_task_count >= self.max_concurrent_tasks:
                    # Put task back and wait
                    self._task_queue.put((priority, counter, task))
                    time.sleep(0.1)
                    continue

                with self._state_lock:
                    result = self._task_results.get(task.task_id)
                    if result is None:
                        result = TaskResult(
                            task_id=task.task_id,
                            status=TaskStatus.PENDING,
                            start_time=datetime.now(),
                        )
                        self._task_results[task.task_id] = result

                    if result.status == TaskStatus.CANCELLED:
                        self._persist_result(result)
                        continue

                    self._persist_result(result)

                # Submit task to executor
                future = self._executor.submit(self._execute_task, task, result)
                with self._state_lock:
                    self._running_tasks[task.task_id] = future
                    self._stats["running_tasks_count"] = len(self._running_tasks)
                    running_tasks_count = len(self._running_tasks)

                logger.info(
                    "Task started",
                    task_id=task.task_id,
                    scraper_name=task.scraper_name,
                    running_tasks=running_tasks_count,
                )

            except Exception as e:
                logger.error("Error in worker loop", error=str(e), exc_info=True)
                time.sleep(1)

        logger.info("TaskManager worker loop stopped")

    def _execute_task(self, task: ScraperTask, result: TaskResult):
        """Execute a single scraper task."""
        try:
            # Run pre-execution hooks
            for hook in self._pre_execution_hooks:
                try:
                    hook(task)
                except Exception as e:
                    logger.warning("Pre-execution hook failed", error=str(e))

            # Mark task as running
            with self._state_lock:
                result.status = TaskStatus.RUNNING
                self._persist_result(result)

            # Create scraper instance
            scraper = Scraper(task.scraper_config)
            if self._storage:
                scraper.set_storage(self._storage)

            # Execute scraping
            start_time = time.time()
            contents = scraper.scrap_contents(task.fetch_params)
            execution_time = time.time() - start_time

            # Stamp each content with the scraper source name for tracking
            # NOTE: This MUST happen BEFORE mark_completed() to avoid a
            # race condition where trigger_upload sees the task as COMPLETED
            # but the contents are not yet stamped or stored in metadata.
            for content_item in contents:
                if not content_item.scraper_name:
                    content_item.scraper_name = task.scraper_name

            # Prepend default keywords from scraper config
            if task.default_keywords:
                for content_item in contents:
                    existing = content_item.keywords or []
                    seen = set()
                    merged = []
                    for kw in list(task.default_keywords) + existing:
                        stripped = kw.strip() if kw else ""
                        if stripped and stripped not in seen:
                            seen.add(stripped)
                            merged.append(stripped)
                    content_item.keywords = merged

            # Verify all contents have scraper_name set
            missing_source_count = sum(1 for c in contents if not c.scraper_name)
            if missing_source_count > 0:
                logger.warning(
                    "Some contents still missing scraper_name after stamping",
                    task_id=task.task_id,
                    missing_count=missing_source_count,
                    total_count=len(contents),
                )

            # Store contents in metadata BEFORE marking completed
            with self._state_lock:
                result.metadata.update(
                    {
                        "execution_time_seconds": execution_time,
                        "scraper_config": task.scraper_name,
                        "fetch_params": task.fetch_params,
                        "contents": contents,
                    }
                )

                # Mark completed AFTER contents are stamped and stored,
                # so trigger_upload never sees a COMPLETED task without contents.
                result.mark_completed(
                    items_fetched=len(contents),
                    items_processed=len(contents),
                    items_uploaded=0,  # Upload happens separately
                )

                self._stats["completed_tasks"] += 1
                self._persist_result(result)

            logger.info(
                "Task completed successfully",
                task_id=task.task_id,
                scraper_name=task.scraper_name,
                items_fetched=len(contents),
                duration_seconds=result.duration_seconds,
            )

        except Exception as e:
            # Handle task failure
            error_msg = f"Task execution failed: {str(e)}"
            with self._state_lock:
                result.mark_failed(error_msg)
                self._stats["failed_tasks"] += 1
                self._persist_result(result)

            logger.error(
                "Task failed",
                task_id=task.task_id,
                scraper_name=task.scraper_name,
                error=error_msg,
                retry_count=task.retry_count,
                max_retries=task.max_retries,
            )

            # Handle retries
            if task.should_retry():
                task.retry_count += 1
                retry_task = ScraperTask(
                    task_id=f"{task.task_id}_retry_{task.retry_count}",
                    scraper_name=task.scraper_name,
                    scraper_config=task.scraper_config,
                    fetch_params=task.fetch_params,
                    priority=task.priority,
                    max_retries=task.max_retries,
                    retry_count=task.retry_count,
                    scheduled_at=task.get_next_retry_time(),
                    default_keywords=task.default_keywords,
                    metadata={**task.metadata, "original_task_id": task.task_id},
                )

                # Schedule retry (this is simplified - in production you'd want a proper scheduler)
                threading.Timer(
                    task.retry_delay_seconds, lambda: self.submit_task(retry_task)
                ).start()

                logger.info(
                    "Task scheduled for retry",
                    original_task_id=task.task_id,
                    retry_task_id=retry_task.task_id,
                    retry_count=retry_task.retry_count,
                    retry_delay=task.retry_delay_seconds,
                )

        finally:
            # Run post-execution hooks
            for hook in self._post_execution_hooks:
                try:
                    hook(task, result)
                except Exception as e:
                    logger.warning("Post-execution hook failed", error=str(e))

            # Clean up running task tracking
            with self._state_lock:
                if task.task_id in self._running_tasks:
                    del self._running_tasks[task.task_id]
                self._stats["running_tasks_count"] = len(self._running_tasks)

                # Add to history
                self._task_history.append(result)

    def _mark_task_cancelled(self, task_id: str):
        """Mark a task as cancelled."""
        with self._state_lock:
            result = self._task_results.get(task_id)
            if result and result.status in {
                TaskStatus.CANCELLED,
                TaskStatus.COMPLETED,
                TaskStatus.FAILED,
            }:
                return

            if result:
                result.status = TaskStatus.CANCELLED
                result.end_time = datetime.now()
                if result.start_time:
                    result.duration_seconds = (
                        result.end_time - result.start_time
                    ).total_seconds()

            self._stats["cancelled_tasks"] += 1
            if result:
                self._persist_result(result)
        logger.info("Task cancelled", task_id=task_id)

    def _persist_result(self, result: TaskResult) -> None:
        """Persist a task result if result persistence is configured."""
        if not self._result_store:
            return

        try:
            self._result_store.save_result(result)
        except Exception as e:
            logger.error(
                "Failed to persist task result",
                task_id=result.task_id,
                error=str(e),
                exc_info=True,
            )

    def _load_persisted_results(self) -> None:
        """Load recent task results from persistent storage."""
        if not self._result_store:
            return

        try:
            persisted_results = self._result_store.load_recent_results(
                self.result_retention_hours
            )
        except Exception as e:
            logger.error("Failed to load persisted task results", error=str(e))
            return

        with self._state_lock:
            for result in persisted_results:
                self._task_results[result.task_id] = result
                self._task_history.append(result)

            self._stats["persisted_task_results_count"] = len(persisted_results)

        logger.info(
            "Loaded persisted task results",
            result_count=len(persisted_results),
            persistence_path=self.persistence_path,
        )
