from dataclasses import dataclass
from typing import Dict, Optional, Any


@dataclass
class TriggerScraperResponse:
    status: str  # "success" | "error"
    message: str
    data: Optional[Dict[str, int]]  # {"source_count": int, "item_count": int}


@dataclass
class TriggerUploadResponse:
    status: str
    message: str
    data: Optional[Dict[str, int]]  # {"uploaded_count": int}


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
