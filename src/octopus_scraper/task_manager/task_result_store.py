"""SQLite persistence for task manager results."""

import json
import sqlite3
import threading
from dataclasses import asdict, is_dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

import structlog

from octopus_scraper.task_manager.models import TaskResult, TaskStatus

logger = structlog.get_logger(__name__)


class TaskResultStore:
    """Persist task results to a local SQLite database."""

    def __init__(self, database_path: str):
        self.database_path = Path(database_path).expanduser()
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._initialize_schema()

    def save_result(self, result: TaskResult) -> None:
        """Insert or update a task result."""
        metadata = self._sanitize_metadata(result.metadata)
        with self._lock, sqlite3.connect(self.database_path) as connection:
            connection.execute(
                """
                INSERT INTO task_results (
                    task_id, status, start_time, end_time, duration_seconds,
                    items_fetched, items_processed, items_uploaded,
                    error_message, metadata_json, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(task_id) DO UPDATE SET
                    status = excluded.status,
                    start_time = excluded.start_time,
                    end_time = excluded.end_time,
                    duration_seconds = excluded.duration_seconds,
                    items_fetched = excluded.items_fetched,
                    items_processed = excluded.items_processed,
                    items_uploaded = excluded.items_uploaded,
                    error_message = excluded.error_message,
                    metadata_json = excluded.metadata_json,
                    updated_at = excluded.updated_at
                """,
                (
                    result.task_id,
                    result.status.value,
                    self._datetime_to_text(result.start_time),
                    self._datetime_to_text(result.end_time),
                    result.duration_seconds,
                    result.items_fetched,
                    result.items_processed,
                    result.items_uploaded,
                    result.error_message,
                    json.dumps(metadata, ensure_ascii=False, sort_keys=True),
                    self._datetime_to_text(datetime.now()),
                ),
            )

    def load_recent_results(self, retention_hours: int) -> List[TaskResult]:
        """Load task results newer than the retention window."""
        cutoff = datetime.now() - timedelta(hours=retention_hours)
        with self._lock, sqlite3.connect(self.database_path) as connection:
            connection.row_factory = sqlite3.Row
            rows = connection.execute(
                """
                SELECT *
                FROM task_results
                WHERE COALESCE(end_time, start_time) >= ?
                ORDER BY start_time DESC
                """,
                (self._datetime_to_text(cutoff),),
            ).fetchall()

        return [self._row_to_task_result(row) for row in rows]

    def delete_results_older_than(self, cutoff_time: datetime) -> int:
        """Delete persisted task results older than the cutoff."""
        with self._lock, sqlite3.connect(self.database_path) as connection:
            cursor = connection.execute(
                """
                DELETE FROM task_results
                WHERE end_time IS NOT NULL AND end_time < ?
                """,
                (self._datetime_to_text(cutoff_time),),
            )
            return cursor.rowcount

    def _initialize_schema(self) -> None:
        with self._lock, sqlite3.connect(self.database_path) as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS task_results (
                    task_id TEXT PRIMARY KEY,
                    status TEXT NOT NULL,
                    start_time TEXT NOT NULL,
                    end_time TEXT,
                    duration_seconds REAL,
                    items_fetched INTEGER NOT NULL DEFAULT 0,
                    items_processed INTEGER NOT NULL DEFAULT 0,
                    items_uploaded INTEGER NOT NULL DEFAULT 0,
                    error_message TEXT,
                    metadata_json TEXT NOT NULL DEFAULT '{}',
                    updated_at TEXT NOT NULL
                )
                """
            )

    def _row_to_task_result(self, row: sqlite3.Row) -> TaskResult:
        try:
            metadata = json.loads(row["metadata_json"] or "{}")
        except json.JSONDecodeError:
            metadata = {}

        return TaskResult(
            task_id=row["task_id"],
            status=TaskStatus(row["status"]),
            start_time=self._text_to_datetime(row["start_time"]),
            end_time=self._text_to_datetime(row["end_time"]),
            duration_seconds=row["duration_seconds"],
            items_fetched=row["items_fetched"],
            items_processed=row["items_processed"],
            items_uploaded=row["items_uploaded"],
            error_message=row["error_message"],
            metadata=metadata,
        )

    def _sanitize_metadata(self, metadata: Dict[str, Any]) -> Dict[str, Any]:
        sanitized: Dict[str, Any] = {}
        for key, value in metadata.items():
            if key == "contents" and isinstance(value, list):
                sanitized["contents_count"] = len(value)
                continue
            sanitized[key] = self._to_json_safe(value)
        return sanitized

    def _to_json_safe(self, value: Any) -> Any:
        if isinstance(value, (str, int, float, bool)) or value is None:
            return value
        if isinstance(value, datetime):
            return self._datetime_to_text(value)
        if isinstance(value, list):
            return [self._to_json_safe(item) for item in value]
        if isinstance(value, tuple):
            return [self._to_json_safe(item) for item in value]
        if isinstance(value, dict):
            return {str(key): self._to_json_safe(item) for key, item in value.items()}
        if is_dataclass(value):
            return self._to_json_safe(asdict(value))
        return str(value)

    def _datetime_to_text(self, value: Optional[datetime]) -> Optional[str]:
        return value.isoformat() if value else None

    def _text_to_datetime(self, value: Optional[str]) -> Optional[datetime]:
        if not value:
            return None
        return datetime.fromisoformat(value)
