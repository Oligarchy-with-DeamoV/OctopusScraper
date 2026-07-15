"""PostgreSQL-backed canonical content storage."""

import json
import threading
from dataclasses import asdict
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Iterable, List, Optional, Sequence, Set

import structlog
from sqlalchemy import (
    DateTime,
    Integer,
    String,
    Text,
    create_engine,
    func,
    or_,
    select,
    text,
    update,
)
from sqlalchemy.dialects.postgresql import insert as postgresql_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column
from sqlalchemy.pool import StaticPool

from octopus_scraper.config.models import DatabaseConfig
from octopus_scraper.protos import Content
from octopus_scraper.storages.base_storage import BaseStorage

logger = structlog.get_logger(__name__)

SYNC_PENDING = "pending"
SYNC_PROCESSING = "processing"
SYNC_RETRY = "retry"
SYNC_SYNCED = "synced"
SYNC_FAILED = "failed"
SCHEMA_VERSION = 1


class Base(DeclarativeBase):
    """SQLAlchemy declarative base."""


class SchemaMigration(Base):
    """Applied database schema version."""

    __tablename__ = "schema_migrations"

    version: Mapped[int] = mapped_column(Integer, primary_key=True)
    applied_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )


class ContentRecord(Base):
    """Canonical persisted content and downstream synchronization state."""

    __tablename__ = "contents"

    content_id: Mapped[str] = mapped_column(Text, primary_key=True)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    link: Mapped[str] = mapped_column(Text, nullable=False)
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    published: Mapped[str] = mapped_column(Text, nullable=False)
    author: Mapped[Optional[str]] = mapped_column(Text)
    keywords_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    tags_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    scraper_name: Mapped[Optional[str]] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    notion_sync_status: Mapped[str] = mapped_column(
        String(32), nullable=False, default=SYNC_PENDING, index=True
    )
    notion_synced_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True)
    )
    notion_sync_attempts: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0
    )
    notion_sync_error: Mapped[Optional[str]] = mapped_column(Text)
    notion_next_attempt_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )
    notion_claimed_by: Mapped[Optional[str]] = mapped_column(String(128), index=True)
    notion_claimed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True)
    )
    notion_lease_expires_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), index=True
    )

    def to_content(self) -> Content:
        """Convert the database row into the pipeline DTO."""
        return Content(
            content_id=self.content_id,
            title=self.title,
            link=self.link,
            summary=self.summary,
            content=self.content,
            published=self.published,
            author=self.author,
            keywords=json.loads(self.keywords_json),
            tags=json.loads(self.tags_json),
            scraper_name=self.scraper_name,
        )


class PostgresStorage(BaseStorage):
    """Canonical content repository with retryable Notion sync state."""

    def __init__(self, config: Dict[str, Any]):
        database_config = DatabaseConfig(**config)
        engine_options: Dict[str, Any] = {"future": True, "pool_pre_ping": True}
        if database_config.url.startswith("sqlite"):
            engine_options.update(
                {
                    "connect_args": {"check_same_thread": False},
                    "poolclass": StaticPool,
                }
            )
        else:
            engine_options.update(
                {
                    "pool_size": database_config.pool_size,
                    "max_overflow": database_config.max_overflow,
                    "connect_args": {
                        "connect_timeout": database_config.connect_timeout_seconds
                    },
                }
            )
        self.config = database_config
        self.engine = create_engine(database_config.url, **engine_options)
        self._sqlite_lock = threading.RLock()

    def initialize(self) -> None:
        """Create or upgrade the current database schema."""
        with self._write_lock(), self.engine.begin() as connection:
            if self.engine.dialect.name == "postgresql":
                connection.execute(
                    text("SELECT pg_advisory_xact_lock(:lock_key)"),
                    {"lock_key": 739102001},
                )
            Base.metadata.create_all(connection)
            values = {
                "version": SCHEMA_VERSION,
                "applied_at": self._now(),
            }
            if self.engine.dialect.name == "postgresql":
                statement = postgresql_insert(SchemaMigration).values(values)
            elif self.engine.dialect.name == "sqlite":
                statement = sqlite_insert(SchemaMigration).values(values)
            else:
                raise RuntimeError(
                    f"Unsupported database dialect: {self.engine.dialect.name}"
                )
            connection.execute(
                statement.on_conflict_do_nothing(
                    index_elements=[SchemaMigration.version]
                )
            )
        logger.info("Canonical storage initialized", schema_version=SCHEMA_VERSION)

    def ping(self) -> bool:
        """Return whether the canonical database is reachable."""
        try:
            with self.engine.connect() as connection:
                connection.execute(select(1))
            return True
        except Exception as error:
            logger.error("Canonical storage health check failed", error=str(error))
            return False

    def dispose(self) -> None:
        """Release database connections."""
        self.engine.dispose()

    def _store_content(self, content: Content) -> bool:
        """Store one content item; duplicates are successful no-ops."""
        return self.store_contents([content])[0]

    def store_contents(
        self, contents: List[Content], deduplicate: bool = True
    ) -> List[bool]:
        """Persist contents atomically with database-enforced deduplication."""
        self._insert_contents(contents)
        return [True] * len(contents)

    def _insert_contents(self, contents: List[Content]) -> int:
        """Insert unique contents and return the database row count."""
        if not contents:
            return 0

        now = self._now()
        unique_contents: Dict[str, Content] = {}
        for content in contents:
            unique_contents.setdefault(content.content_id, content)

        values = [
            {
                "content_id": content.content_id,
                "title": content.title,
                "link": content.link,
                "summary": content.summary,
                "content": content.content,
                "published": content.published,
                "author": content.author,
                "keywords_json": json.dumps(content.keywords or []),
                "tags_json": json.dumps(content.tags or []),
                "scraper_name": content.scraper_name,
                "created_at": now,
                "updated_at": now,
                "notion_sync_status": SYNC_PENDING,
                "notion_sync_attempts": 0,
                "notion_next_attempt_at": now,
            }
            for content in unique_contents.values()
        ]

        with self._write_lock(), Session(self.engine) as session, session.begin():
            dialect = self.engine.dialect.name
            if dialect == "postgresql":
                statement = postgresql_insert(ContentRecord).values(values)
                statement = statement.on_conflict_do_nothing(
                    index_elements=[ContentRecord.content_id]
                )
            elif dialect == "sqlite":
                statement = sqlite_insert(ContentRecord).values(values)
                statement = statement.on_conflict_do_nothing(
                    index_elements=[ContentRecord.content_id]
                )
            else:
                raise RuntimeError(f"Unsupported database dialect: {dialect}")
            result = session.execute(statement)
            inserted_count = result.rowcount if result.rowcount >= 0 else 0

        logger.info(
            "Canonical content batch stored",
            requested_count=len(contents),
            unique_count=len(unique_contents),
            inserted_count=inserted_count,
            duplicate_count=len(contents) - inserted_count,
        )
        return inserted_count

    def store_contents_with_stats(self, contents: List[Content]) -> Dict[str, int]:
        """Store contents and return inserted/duplicate counts."""
        inserted = self._insert_contents(contents)
        return {
            "requested": len(contents),
            "inserted": inserted,
            "duplicates": len(contents) - inserted,
        }

    def get_existing_content_ids(self, content_ids: Iterable[str]) -> Set[str]:
        """Return the subset of candidate IDs already persisted."""
        ids = list(dict.fromkeys(content_ids))
        if not ids:
            return set()
        with Session(self.engine) as session:
            return set(
                session.scalars(
                    select(ContentRecord.content_id).where(
                        ContentRecord.content_id.in_(ids)
                    )
                ).all()
            )

    def get_all_content_ids(self) -> set:
        """Return all canonical content IDs."""
        with Session(self.engine) as session:
            return set(session.scalars(select(ContentRecord.content_id)).all())

    def claim_contents(
        self,
        worker_id: str,
        batch_size: int,
        lease_seconds: int,
        max_attempts: int,
    ) -> List[Content]:
        """Claim a disjoint due batch for one synchronization worker."""
        with self._write_lock(), Session(self.engine) as session, session.begin():
            now = self._lease_now(session)
            due = or_(
                (
                    ContentRecord.notion_sync_status.in_([SYNC_PENDING, SYNC_RETRY])
                    & (ContentRecord.notion_sync_attempts < max_attempts)
                    & (ContentRecord.notion_next_attempt_at <= now)
                ),
                (
                    (ContentRecord.notion_sync_status == SYNC_PROCESSING)
                    & (ContentRecord.notion_lease_expires_at <= now)
                ),
            )
            statement = (
                select(ContentRecord)
                .where(due)
                .order_by(ContentRecord.created_at, ContentRecord.content_id)
                .limit(batch_size)
            )
            if self.engine.dialect.name == "postgresql":
                statement = statement.with_for_update(skip_locked=True)
            records = list(session.scalars(statement).all())
            lease_expires = now + timedelta(seconds=lease_seconds)
            for record in records:
                record.notion_sync_status = SYNC_PROCESSING
                record.notion_claimed_by = worker_id
                record.notion_claimed_at = now
                record.notion_lease_expires_at = lease_expires
                record.updated_at = now
            contents = [record.to_content() for record in records]

        logger.info(
            "Claimed contents for Notion synchronization",
            worker_id=worker_id,
            claimed_count=len(contents),
        )
        return contents

    def mark_synced(self, content_id: str, worker_id: str) -> bool:
        """Mark a claimed item as synchronized."""
        with self._write_lock(), Session(self.engine) as session, session.begin():
            now = self._lease_now(session)
            result = session.execute(
                update(ContentRecord)
                .where(
                    ContentRecord.content_id == content_id,
                    ContentRecord.notion_claimed_by == worker_id,
                    ContentRecord.notion_sync_status == SYNC_PROCESSING,
                )
                .values(
                    notion_sync_status=SYNC_SYNCED,
                    notion_synced_at=now,
                    notion_sync_error=None,
                    notion_claimed_by=None,
                    notion_claimed_at=None,
                    notion_lease_expires_at=None,
                    updated_at=now,
                )
            )
            return result.rowcount == 1

    def renew_claim(
        self,
        content_id: str,
        worker_id: str,
        lease_seconds: int,
    ) -> bool:
        """Renew a processing lease only if the claim token is still current."""
        with self._write_lock(), Session(self.engine) as session, session.begin():
            now = self._lease_now(session)
            result = session.execute(
                update(ContentRecord)
                .where(
                    ContentRecord.content_id == content_id,
                    ContentRecord.notion_claimed_by == worker_id,
                    ContentRecord.notion_sync_status == SYNC_PROCESSING,
                )
                .values(
                    notion_lease_expires_at=now + timedelta(seconds=lease_seconds),
                    updated_at=now,
                )
            )
            return result.rowcount == 1

    def mark_sync_failed(
        self,
        content_id: str,
        worker_id: str,
        error: str,
        max_attempts: int,
    ) -> bool:
        """Record a failed attempt and schedule retry with exponential backoff."""
        with self._write_lock(), Session(self.engine) as session, session.begin():
            now = self._lease_now(session)
            statement = select(ContentRecord.notion_sync_attempts).where(
                ContentRecord.content_id == content_id,
                ContentRecord.notion_claimed_by == worker_id,
                ContentRecord.notion_sync_status == SYNC_PROCESSING,
            )
            if self.engine.dialect.name == "postgresql":
                statement = statement.with_for_update()
            attempts_before = session.scalar(statement)
            if attempts_before is None:
                return False
            attempts = attempts_before + 1
            result = session.execute(
                update(ContentRecord)
                .where(
                    ContentRecord.content_id == content_id,
                    ContentRecord.notion_claimed_by == worker_id,
                    ContentRecord.notion_sync_status == SYNC_PROCESSING,
                    ContentRecord.notion_sync_attempts == attempts_before,
                )
                .values(
                    notion_sync_attempts=attempts,
                    notion_sync_status=(
                        SYNC_FAILED if attempts >= max_attempts else SYNC_RETRY
                    ),
                    notion_sync_error=error[:2000],
                    notion_next_attempt_at=now
                    + timedelta(seconds=min(60 * (2 ** max(attempts - 1, 0)), 3600)),
                    notion_claimed_by=None,
                    notion_claimed_at=None,
                    notion_lease_expires_at=None,
                    updated_at=now,
                )
            )
            return result.rowcount == 1

    def get_sync_counts(self) -> Dict[str, int]:
        """Return synchronization counts grouped by state."""
        with Session(self.engine) as session:
            rows: Sequence = session.execute(
                select(
                    ContentRecord.notion_sync_status,
                    func.count(ContentRecord.content_id),
                ).group_by(ContentRecord.notion_sync_status)
            ).all()
        counts = {
            SYNC_PENDING: 0,
            SYNC_PROCESSING: 0,
            SYNC_RETRY: 0,
            SYNC_SYNCED: 0,
            SYNC_FAILED: 0,
        }
        counts.update({status: count for status, count in rows})
        return counts

    def get_record(self, content_id: str) -> Optional[ContentRecord]:
        """Return a detached record for diagnostics and tests."""
        with Session(self.engine) as session:
            record = session.get(ContentRecord, content_id)
            if record is not None:
                session.expunge(record)
            return record

    def _now(self) -> datetime:
        return datetime.now(timezone.utc)

    def _lease_now(self, session: Session) -> datetime:
        if self.engine.dialect.name == "postgresql":
            return session.scalar(select(func.now()))
        return self._now()

    def _write_lock(self):
        if self.engine.dialect.name == "sqlite":
            return self._sqlite_lock
        return _NullLock()


class _NullLock:
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        return False
