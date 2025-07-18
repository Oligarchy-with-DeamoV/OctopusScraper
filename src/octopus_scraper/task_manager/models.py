"""
Task models for OctopusScraper task management.
"""

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Dict, List, Optional, Union
import uuid


class TaskStatus(Enum):
    """Task execution status."""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    RETRYING = "retrying"


class TaskPriority(Enum):
    """Task priority levels."""

    LOW = 1
    NORMAL = 5
    HIGH = 8
    CRITICAL = 10


@dataclass
class TaskResult:
    """Result of a task execution."""

    task_id: str
    status: TaskStatus
    start_time: datetime
    end_time: Optional[datetime] = None
    duration_seconds: Optional[float] = None
    items_fetched: int = 0
    items_processed: int = 0
    items_uploaded: int = 0
    error_message: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def mark_completed(
        self, items_fetched: int = 0, items_processed: int = 0, items_uploaded: int = 0
    ):
        """Mark task as completed with results."""
        self.end_time = datetime.now()
        self.duration_seconds = (self.end_time - self.start_time).total_seconds()
        self.status = TaskStatus.COMPLETED
        self.items_fetched = items_fetched
        self.items_processed = items_processed
        self.items_uploaded = items_uploaded

    def mark_failed(self, error_message: str):
        """Mark task as failed with error message."""
        self.end_time = datetime.now()
        self.duration_seconds = (self.end_time - self.start_time).total_seconds()
        self.status = TaskStatus.FAILED
        self.error_message = error_message


@dataclass
class ScraperTask:
    """A scraper task to be executed."""

    task_id: str
    scraper_name: str
    scraper_config: Dict[str, Any]
    fetch_params: Dict[str, Any] = field(default_factory=dict)
    priority: TaskPriority = TaskPriority.NORMAL
    max_retries: int = 3
    retry_count: int = 0
    retry_delay_seconds: int = 60
    timeout_seconds: int = 300
    created_at: datetime = field(default_factory=datetime.now)
    scheduled_at: Optional[datetime] = None
    depends_on: Optional[List[str]] = None
    tags: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __lt__(self, other):
        """Support for ordering in priority queue."""
        if not isinstance(other, ScraperTask):
            return NotImplemented
        # First compare by priority (higher priority first)
        if self.priority != other.priority:
            return self.priority.value > other.priority.value
        # Then by creation time (older first)
        return self.created_at < other.created_at

    @classmethod
    def from_scraper_config(
        cls, scraper_config: Dict[str, Any], fetch_params: Dict[str, Any]
    ) -> "ScraperTask":
        """Create a ScraperTask from scraper configuration."""
        task_id = str(uuid.uuid4())
        scraper_name = scraper_config.get("name", f"scraper_{task_id[:8]}")
        priority_value = scraper_config.get("priority", 5)

        # Convert priority value to TaskPriority enum
        priority_mapping = {
            1: TaskPriority.LOW,
            2: TaskPriority.LOW,
            3: TaskPriority.LOW,
            4: TaskPriority.NORMAL,
            5: TaskPriority.NORMAL,
            6: TaskPriority.NORMAL,
            7: TaskPriority.HIGH,
            8: TaskPriority.HIGH,
            9: TaskPriority.CRITICAL,
            10: TaskPriority.CRITICAL,
        }
        priority = priority_mapping.get(priority_value, TaskPriority.NORMAL)

        return cls(
            task_id=task_id,
            scraper_name=scraper_name,
            scraper_config=scraper_config,
            fetch_params=fetch_params,
            priority=priority,
            tags=[scraper_config.get("fetcher", "unknown")],
            metadata={
                "hub_root": scraper_config.get("hub_root", ""),
                "route": scraper_config.get("route", ""),
                "fetcher": scraper_config.get("fetcher", ""),
            },
        )

    def should_retry(self) -> bool:
        """Check if task should be retried."""
        return self.retry_count < self.max_retries

    def get_next_retry_time(self) -> datetime:
        """Calculate next retry time with exponential backoff."""
        delay = self.retry_delay_seconds * (2**self.retry_count)
        return datetime.now() + timedelta(seconds=min(delay, 3600))  # Max 1 hour


@dataclass
class TaskBatch:
    """A batch of related tasks."""

    batch_id: str
    tasks: List[ScraperTask]
    created_at: datetime = field(default_factory=datetime.now)
    name: Optional[str] = None
    description: Optional[str] = None

    def get_task_by_id(self, task_id: str) -> Optional[ScraperTask]:
        """Get task by ID from this batch."""
        return next((task for task in self.tasks if task.task_id == task_id), None)


@dataclass
class TaskScheduleConfig:
    """Configuration for scheduled tasks."""

    schedule_id: str
    scraper_name: str
    cron_expression: str  # e.g., "0 */6 * * *" for every 6 hours
    enabled: bool = True
    max_concurrent_runs: int = 1
    timeout_seconds: int = 300
    retry_config: Dict[str, Any] = field(default_factory=dict)
    fetch_params: Dict[str, Any] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=datetime.now)
    last_run: Optional[datetime] = None
    next_run: Optional[datetime] = None
