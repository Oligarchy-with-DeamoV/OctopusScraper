from dataclasses import dataclass
from typing import Any, Dict, List, Optional


@dataclass
class TriggerScraperResponse:
    status: str  # "success" | "error"
    message: str
    data: Optional[Dict[str, Any]] = None  # {"batch_id": str, "source_count": int}


@dataclass
class TriggerUploadResponse:
    status: str
    message: str
    data: Optional[Dict[str, Any]] = (
        None  # {"uploaded_count": int, "tasks_processed": int, "errors": list}
    )


@dataclass
class HealthCheckResponse:
    status: str  # "healthy" | "unhealthy" | "error"
    timestamp: str
    service: Dict[str, Any]
    dependencies: Dict[str, Any]
    configuration: Dict[str, Any]
    performance: Dict[str, Any]


@dataclass
class LivenessResponse:
    status: str  # "alive"
    timestamp: str


@dataclass
class ReadinessResponse:
    status: str  # "ready" | "not_ready"
    timestamp: str
    checks: Dict[str, Any]


# ===> Admin Interface Response Models
@dataclass
class ConfigStatusResponse:
    status: str
    config_status: Dict[str, Any]


@dataclass
class ConfigRefreshResponse:
    status: str
    message: str
    config_changed: bool
    current_version: Optional[str]
    scrapers_count: int


@dataclass
class ConfigValidationResponse:
    status: str
    is_valid: bool
    validation_errors: List[str]
    scrapers_count: int
    scrapers: List[Dict[str, str]]


@dataclass
class SystemInfoResponse:
    status: str
    system_info: Dict[str, Any]


@dataclass
class ScrapersListResponse:
    status: str
    scrapers: List[Dict[str, Any]]
    summary: Dict[str, Any]


@dataclass
class ScraperTestResponse:
    status: str
    message: str
    test_results: Dict[str, Any]
    timestamp: str


@dataclass
class TaskStatsResponse:
    status: str
    statistics: Dict[str, Any]


@dataclass
class TaskListResponse:
    status: str
    tasks: List[Dict[str, Any]]
    filters: Dict[str, Any]
    total_returned: int
    task_manager_enabled: bool


@dataclass
class TaskDetailsResponse:
    status: str
    task: Dict[str, Any]


@dataclass
class TaskCancelResponse:
    status: str
    message: str
    task_id: str
    cancelled: bool


@dataclass
class TaskSubmitResponse:
    status: str
    message: str
    task_id: str
    scraper_name: str
    fetch_params: Dict[str, Any]


@dataclass
class MonitoringMetricsResponse:
    status: str
    metrics: Dict[str, Any]


@dataclass
class CacheClearResponse:
    status: str
    message: str
    cleared_caches: List[str]
    timestamp: str


@dataclass
class GarbageCollectionResponse:
    status: str
    message: str
    results: Dict[str, Any]
    timestamp: str


@dataclass
class ConfigWatcherResponse:
    status: str
    watcher_status: Optional[Dict[str, Any]] = None
    message: Optional[str] = None
    action: Optional[str] = None
    timestamp: Optional[str] = None


@dataclass
class StateDumpResponse:
    status: str
    state_dump: Dict[str, Any]
    dump_options: Dict[str, bool]
