"""
Task Scheduler for OctopusScraper.

This module provides cron-like scheduling capabilities for automatic
task execution at specified intervals.
"""

import asyncio
import threading
import time
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Callable
import structlog

try:
    from croniter import croniter

    CRONITER_AVAILABLE = True
except ImportError:
    CRONITER_AVAILABLE = False
    # Create a dummy croniter class for graceful degradation
    class croniter:
        def __init__(self, cron_expr, base_time=None):
            if not CRONITER_AVAILABLE:
                raise ImportError(
                    "croniter package is required for scheduling functionality"
                )

        def get_next(self, ret_type=datetime):
            return datetime.now() + timedelta(hours=1)


from octopus_scraper.task_manager.models import (
    TaskScheduleConfig,
    ScraperTask,
    TaskPriority,
)
from octopus_scraper.task_manager.task_manager import TaskManager

logger = structlog.get_logger(__name__)


class TaskScheduler:
    """Cron-like scheduler for automatic task execution."""

    def __init__(self, task_manager: TaskManager):
        """
        Initialize TaskScheduler.

        Args:
            task_manager: TaskManager instance to submit tasks to
        """
        self.task_manager = task_manager
        self._schedules: Dict[str, TaskScheduleConfig] = {}
        self._stop_event = threading.Event()
        self._scheduler_thread: Optional[threading.Thread] = None
        self._running_scheduled_tasks: Dict[str, int] = {}  # schedule_id -> count

        # Scheduler configuration
        self._check_interval = 60  # Check every minute

    def start(self):
        """Start the scheduler."""
        if self._scheduler_thread is None or not self._scheduler_thread.is_alive():
            self._stop_event.clear()
            self._scheduler_thread = threading.Thread(
                target=self._scheduler_loop, daemon=True
            )
            self._scheduler_thread.start()
            logger.info("TaskScheduler started")

    def stop(self):
        """Stop the scheduler."""
        logger.info("Stopping TaskScheduler...")
        self._stop_event.set()

        if self._scheduler_thread and self._scheduler_thread.is_alive():
            self._scheduler_thread.join(timeout=5)

        logger.info("TaskScheduler stopped")

    def add_schedule(self, schedule: TaskScheduleConfig) -> str:
        """
        Add a new schedule.

        Args:
            schedule: TaskScheduleConfig to add

        Returns:
            Schedule ID
        """
        # Validate cron expression
        try:
            croniter(schedule.cron_expression)
        except Exception as e:
            raise ValueError(
                f"Invalid cron expression: {schedule.cron_expression}"
            ) from e

        self._schedules[schedule.schedule_id] = schedule
        self._running_scheduled_tasks[schedule.schedule_id] = 0

        # Calculate next run time
        if schedule.enabled:
            cron = croniter(schedule.cron_expression, datetime.now())
            schedule.next_run = cron.get_next(datetime)

        logger.info(
            "Schedule added",
            schedule_id=schedule.schedule_id,
            scraper_name=schedule.scraper_name,
            cron_expression=schedule.cron_expression,
            next_run=schedule.next_run.isoformat() if schedule.next_run else None,
        )

        return schedule.schedule_id

    def remove_schedule(self, schedule_id: str) -> bool:
        """Remove a schedule."""
        if schedule_id in self._schedules:
            del self._schedules[schedule_id]
            if schedule_id in self._running_scheduled_tasks:
                del self._running_scheduled_tasks[schedule_id]
            logger.info("Schedule removed", schedule_id=schedule_id)
            return True
        return False

    def enable_schedule(self, schedule_id: str) -> bool:
        """Enable a schedule."""
        if schedule_id in self._schedules:
            schedule = self._schedules[schedule_id]
            schedule.enabled = True

            # Calculate next run time
            cron = croniter(schedule.cron_expression, datetime.now())
            schedule.next_run = cron.get_next(datetime)

            logger.info(
                "Schedule enabled", schedule_id=schedule_id, next_run=schedule.next_run
            )
            return True
        return False

    def disable_schedule(self, schedule_id: str) -> bool:
        """Disable a schedule."""
        if schedule_id in self._schedules:
            schedule = self._schedules[schedule_id]
            schedule.enabled = False
            schedule.next_run = None
            logger.info("Schedule disabled", schedule_id=schedule_id)
            return True
        return False

    def list_schedules(self, enabled_only: bool = False) -> List[TaskScheduleConfig]:
        """List all schedules."""
        schedules = list(self._schedules.values())
        if enabled_only:
            schedules = [s for s in schedules if s.enabled]
        return schedules

    def get_schedule(self, schedule_id: str) -> Optional[TaskScheduleConfig]:
        """Get a specific schedule."""
        return self._schedules.get(schedule_id)

    def trigger_schedule_now(self, schedule_id: str) -> Optional[str]:
        """Manually trigger a schedule immediately."""
        schedule = self._schedules.get(schedule_id)
        if not schedule:
            return None

        task_id = self._execute_schedule(schedule, manual_trigger=True)
        logger.info(
            "Schedule triggered manually", schedule_id=schedule_id, task_id=task_id
        )
        return task_id

    def get_scheduler_status(self) -> Dict:
        """Get scheduler status and statistics."""
        total_schedules = len(self._schedules)
        enabled_schedules = len([s for s in self._schedules.values() if s.enabled])
        running_tasks = sum(self._running_scheduled_tasks.values())

        # Next scheduled run
        next_runs = [s.next_run for s in self._schedules.values() if s.next_run]
        next_run = min(next_runs) if next_runs else None

        return {
            "status": "running" if not self._stop_event.is_set() else "stopped",
            "total_schedules": total_schedules,
            "enabled_schedules": enabled_schedules,
            "running_scheduled_tasks": running_tasks,
            "next_run": next_run.isoformat() if next_run else None,
            "schedules_by_status": {
                schedule_id: {
                    "enabled": schedule.enabled,
                    "next_run": schedule.next_run.isoformat()
                    if schedule.next_run
                    else None,
                    "last_run": schedule.last_run.isoformat()
                    if schedule.last_run
                    else None,
                    "running_tasks": self._running_scheduled_tasks.get(schedule_id, 0),
                }
                for schedule_id, schedule in self._schedules.items()
            },
        }

    def _scheduler_loop(self):
        """Main scheduler loop."""
        logger.info("TaskScheduler loop started")

        while not self._stop_event.is_set():
            try:
                current_time = datetime.now()

                # Check each enabled schedule
                for schedule_id, schedule in self._schedules.items():
                    if not schedule.enabled or not schedule.next_run:
                        continue

                    # Check if it's time to run
                    if current_time >= schedule.next_run:
                        # Check concurrent run limit
                        running_count = self._running_scheduled_tasks.get(
                            schedule_id, 0
                        )
                        if running_count >= schedule.max_concurrent_runs:
                            logger.warning(
                                "Schedule skipped due to concurrent run limit",
                                schedule_id=schedule_id,
                                running_count=running_count,
                                max_concurrent=schedule.max_concurrent_runs,
                            )
                            # Calculate next run time anyway
                            self._update_next_run_time(schedule)
                            continue

                        # Execute the schedule
                        try:
                            task_id = self._execute_schedule(schedule)
                            logger.info(
                                "Scheduled task executed",
                                schedule_id=schedule_id,
                                task_id=task_id,
                                scraper_name=schedule.scraper_name,
                            )
                        except Exception as e:
                            logger.error(
                                "Failed to execute scheduled task",
                                schedule_id=schedule_id,
                                error=str(e),
                                exc_info=True,
                            )

                        # Update last run and calculate next run
                        schedule.last_run = current_time
                        self._update_next_run_time(schedule)

                # Sleep until next check
                time.sleep(self._check_interval)

            except Exception as e:
                logger.error("Error in scheduler loop", error=str(e), exc_info=True)
                time.sleep(self._check_interval)

        logger.info("TaskScheduler loop stopped")

    def _execute_schedule(
        self, schedule: TaskScheduleConfig, manual_trigger: bool = False
    ) -> str:
        """Execute a scheduled task."""
        # Create task from schedule
        task = ScraperTask(
            task_id=f"scheduled_{schedule.schedule_id}_{int(time.time())}",
            scraper_name=schedule.scraper_name,
            scraper_config={
                "name": schedule.scraper_name,
                "fetcher_name": "rsshub",  # Default - should be configurable
                "fetcher_config": {},
                "content_processor_configs": {},
                **schedule.metadata,
            },
            fetch_params=schedule.fetch_params,
            priority=TaskPriority.NORMAL,
            timeout_seconds=schedule.timeout_seconds,
            metadata={
                "scheduled": True,
                "schedule_id": schedule.schedule_id,
                "manual_trigger": manual_trigger,
                **schedule.metadata,
            },
        )

        # Add pre and post execution hooks for tracking
        def pre_hook(task: ScraperTask):
            schedule_id = task.metadata.get("schedule_id")
            if schedule_id:
                self._running_scheduled_tasks[schedule_id] = (
                    self._running_scheduled_tasks.get(schedule_id, 0) + 1
                )

        def post_hook(task: ScraperTask, result):
            schedule_id = task.metadata.get("schedule_id")
            if schedule_id and schedule_id in self._running_scheduled_tasks:
                self._running_scheduled_tasks[schedule_id] = max(
                    0, self._running_scheduled_tasks[schedule_id] - 1
                )

        self.task_manager.add_pre_execution_hook(pre_hook)
        self.task_manager.add_post_execution_hook(post_hook)

        # Submit task
        return self.task_manager.submit_task(task)

    def _update_next_run_time(self, schedule: TaskScheduleConfig):
        """Update the next run time for a schedule."""
        if schedule.enabled:
            cron = croniter(schedule.cron_expression, datetime.now())
            schedule.next_run = cron.get_next(datetime)
        else:
            schedule.next_run = None


# Convenience functions for common schedules
def create_hourly_schedule(
    schedule_id: str, scraper_name: str, minute: int = 0, **kwargs
) -> TaskScheduleConfig:
    """Create an hourly schedule."""
    return TaskScheduleConfig(
        schedule_id=schedule_id,
        scraper_name=scraper_name,
        cron_expression=f"{minute} * * * *",
        **kwargs,
    )


def create_daily_schedule(
    schedule_id: str, scraper_name: str, hour: int = 0, minute: int = 0, **kwargs
) -> TaskScheduleConfig:
    """Create a daily schedule."""
    return TaskScheduleConfig(
        schedule_id=schedule_id,
        scraper_name=scraper_name,
        cron_expression=f"{minute} {hour} * * *",
        **kwargs,
    )


def create_weekly_schedule(
    schedule_id: str,
    scraper_name: str,
    day_of_week: int = 0,
    hour: int = 0,
    minute: int = 0,
    **kwargs,
) -> TaskScheduleConfig:
    """Create a weekly schedule."""
    return TaskScheduleConfig(
        schedule_id=schedule_id,
        scraper_name=scraper_name,
        cron_expression=f"{minute} {hour} * * {day_of_week}",
        **kwargs,
    )
