"""Prometheus metrics for OctopusScraper."""

import time
from importlib.metadata import PackageNotFoundError, version
from typing import Any, Optional

from prometheus_client import (
    CollectorRegistry,
    Counter,
    Gauge,
    Histogram,
    Info,
    generate_latest,
)


class OctopusMetrics:
    """Own and update the service Prometheus metric registry."""

    TASK_DURATION_BUCKETS = (1, 5, 15, 30, 60, 120, 300, 600, 1200, 2400)
    EXTERNAL_DURATION_BUCKETS = (0.1, 0.5, 1, 2.5, 5, 10, 30, 60, 120, 300, 1200)
    ITEM_BUCKETS = (0, 1, 5, 10, 25, 50, 100, 250, 500, 1000)
    DEPENDENCIES = frozenset({"rss", "notion", "llm"})

    def __init__(self, registry: Optional[CollectorRegistry] = None) -> None:
        self.registry = registry or CollectorRegistry()
        self._start_time = time.time()

        self.build_info = Info(
            "octopus_build",
            "OctopusScraper build information.",
            registry=self.registry,
        )
        self.service_start_time = Gauge(
            "octopus_service_start_time_seconds",
            "Unix timestamp when the service process started.",
            registry=self.registry,
        )
        self.service_uptime = Gauge(
            "octopus_service_uptime_seconds",
            "Service process uptime in seconds.",
            registry=self.registry,
        )

        self.tasks_submitted = Counter(
            "octopus_tasks_submitted_total",
            "Task attempts accepted by the task manager.",
            registry=self.registry,
        )
        self.tasks_completed = Counter(
            "octopus_tasks_completed_total",
            "Task attempts completed successfully.",
            registry=self.registry,
        )
        self.tasks_failed = Counter(
            "octopus_tasks_failed_total",
            "Task attempts that failed.",
            registry=self.registry,
        )
        self.task_retries = Counter(
            "octopus_task_retries_total",
            "Retry task attempts successfully re-enqueued.",
            registry=self.registry,
        )
        self.tasks_cancelled = Counter(
            "octopus_tasks_cancelled_total",
            "Task attempts cancelled before completion.",
            registry=self.registry,
        )
        self.tasks_running = Gauge(
            "octopus_tasks_running",
            "Task attempts currently running.",
            registry=self.registry,
        )
        self.tasks_queued = Gauge(
            "octopus_tasks_queued",
            "Task attempts currently waiting in the queue.",
            registry=self.registry,
        )
        self.queue_capacity = Gauge(
            "octopus_task_queue_capacity",
            "Maximum number of queued task attempts.",
            registry=self.registry,
        )
        self.worker_capacity = Gauge(
            "octopus_task_worker_capacity",
            "Maximum number of concurrent task workers.",
            registry=self.registry,
        )
        self.task_duration = Histogram(
            "octopus_task_duration_seconds",
            "Task attempt execution duration.",
            buckets=self.TASK_DURATION_BUCKETS,
            registry=self.registry,
        )
        self.task_items_fetched = Histogram(
            "octopus_task_items_fetched",
            "Items fetched by a completed task attempt.",
            buckets=self.ITEM_BUCKETS,
            registry=self.registry,
        )

        self.upload_items = Counter(
            "octopus_upload_items_total",
            "Items processed by upload operations.",
            labelnames=("outcome",),
            registry=self.registry,
        )
        self.upload_batch_size = Histogram(
            "octopus_upload_batch_items",
            "Items included in an upload operation.",
            buckets=self.ITEM_BUCKETS,
            registry=self.registry,
        )

        self.config_healthy = Gauge(
            "octopus_config_healthy",
            "Whether the current scraper configuration is healthy.",
            registry=self.registry,
        )
        self.config_refresh_successes = Counter(
            "octopus_config_refresh_success_total",
            "Successful configuration load or refresh operations.",
            registry=self.registry,
        )
        self.config_refresh_failures = Counter(
            "octopus_config_refresh_failure_total",
            "Failed configuration load or refresh operations.",
            registry=self.registry,
        )
        self.config_last_success = Gauge(
            "octopus_config_last_success_timestamp_seconds",
            "Unix timestamp of the last successful configuration load or refresh.",
            registry=self.registry,
        )

        self.external_requests = Counter(
            "octopus_external_requests_total",
            "External dependency operations.",
            labelnames=("dependency",),
            registry=self.registry,
        )
        self.external_failures = Counter(
            "octopus_external_request_failures_total",
            "Failed external dependency operations.",
            labelnames=("dependency",),
            registry=self.registry,
        )
        self.external_duration = Histogram(
            "octopus_external_request_duration_seconds",
            "External dependency operation duration.",
            labelnames=("dependency",),
            buckets=self.EXTERNAL_DURATION_BUCKETS,
            registry=self.registry,
        )

        try:
            package_version = version("octopus-scraper")
        except PackageNotFoundError:
            package_version = "unknown"
        self.build_info.info({"version": package_version})
        self.set_service_start_time(self._start_time)
        self.tasks_running.set(0)
        self.tasks_queued.set(0)
        self.config_healthy.set(0)

    def set_service_start_time(self, timestamp: Optional[float] = None) -> None:
        """Set the process start timestamp used by service metrics."""
        self._start_time = timestamp or time.time()
        self.service_start_time.set(self._start_time)

    def configure_task_manager(self, queue_capacity: int, workers: int) -> None:
        """Set task manager capacities."""
        self.queue_capacity.set(queue_capacity)
        self.worker_capacity.set(workers)

    def set_task_state(self, queued: int, running: int) -> None:
        """Update current task queue and worker usage."""
        self.tasks_queued.set(queued)
        self.tasks_running.set(running)

    def record_task_completed(self, duration: float, items_fetched: int) -> None:
        """Record a successful task attempt."""
        self.tasks_completed.inc()
        self.task_duration.observe(duration)
        self.task_items_fetched.observe(items_fetched)

    def record_task_failed(self, duration: float) -> None:
        """Record a failed task attempt."""
        self.tasks_failed.inc()
        self.task_duration.observe(duration)

    def record_upload(self, requested: int, processed: int, failed: int) -> None:
        """Record one upload operation using the storage result contract."""
        self.upload_batch_size.observe(requested)
        if processed:
            self.upload_items.labels(outcome="processed").inc(processed)
        if failed:
            self.upload_items.labels(outcome="failed").inc(failed)

    def record_config_refresh(self, success: bool) -> None:
        """Record a configuration load or refresh outcome."""
        self.config_healthy.set(1 if success else 0)
        if success:
            self.config_refresh_successes.inc()
            self.config_last_success.set_to_current_time()
        else:
            self.config_refresh_failures.inc()

    def record_external_request(
        self, dependency: str, duration: float, success: bool
    ) -> None:
        """Record one high-level external dependency operation."""
        if dependency not in self.DEPENDENCIES:
            raise ValueError(f"Unsupported metrics dependency: {dependency}")
        self.external_requests.labels(dependency=dependency).inc()
        self.external_duration.labels(dependency=dependency).observe(duration)
        if not success:
            self.external_failures.labels(dependency=dependency).inc()

    def refresh_app_state(self, app: Any) -> None:
        """Refresh scrape-time gauges from stable service state."""
        self.service_uptime.set(max(0, time.time() - self._start_time))
        if hasattr(app.ctx, "config_manager"):
            status = app.ctx.config_manager.get_status()
            self.config_healthy.set(1 if status.is_healthy else 0)

    def render(self) -> bytes:
        """Render the registry in Prometheus exposition format."""
        return generate_latest(self.registry)


metrics = OctopusMetrics()
