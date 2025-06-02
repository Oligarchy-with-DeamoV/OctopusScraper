from dataclasses import dataclass
from typing import Dict, Optional


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
    status: str  # always "ok" if healthy
