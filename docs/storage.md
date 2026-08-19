# PostgreSQL storage and Notion synchronization

PostgreSQL is the canonical store for processed content. A scrape task is
successful after its content transaction commits; Notion availability does not
affect that task result.

The service creates the current schema at startup and records schema version
`1` in `schema_migrations`. Back up the external PostgreSQL database before
deploying a version that changes the schema.

## Synchronization states

Each content row records `pending`, `processing`, `retry`, `synced`, or
`failed`, plus attempt count, last error, next attempt time, and a worker lease.
Workers claim rows with `FOR UPDATE SKIP LOCKED` on PostgreSQL, so concurrent
service instances do not process the same row at the same time. Expired leases
are reclaimed after a worker interruption.

`POST /trigger_upload` runs one incremental batch manually. When
`NOTION_SYNC_ENABLED=true`, the service also runs batches every
`NOTION_SYNC_INTERVAL_SECONDS`.

## Required settings

```env
POSTGRES_DB=octopus
POSTGRES_USER=octopus
POSTGRES_PASSWORD=replace-with-a-strong-password
DB_HOST=host.docker.internal
DB_PORT=5432
NOTION_SYNC_ENABLED=true
NOTION_API_KEY=secret
NOTION_CONTENT_DATABASE_ID=database-id
NOTION_CONTENT_DATA_SOURCE_ID=data-source-id
NOTION_SYNC_INTERVAL_SECONDS=60
NOTION_SYNC_BATCH_SIZE=100
NOTION_SYNC_MAX_ATTEMPTS=10
NOTION_SYNC_LEASE_SECONDS=300
```

Set `NOTION_SYNC_ENABLED=false` to retain content only in PostgreSQL. In that
mode the service does not construct a Notion client or call the Notion API.

Docker Compose runs `task-results-init` before the service to make existing
SQLite task-result volumes writable by the non-root runtime user.
Task results survive restarts. Any persisted `pending`, `running`, or
`retrying` result from an interrupted process is finalized as failed during
startup so admin APIs do not report work that is no longer executing. If the
optional task-history SQLite file cannot be opened, read, or repaired, the
service logs the degradation and continues scraping without persisted history.

The service uses Notion API version `2026-03-11`. A database containing one
data source is resolved automatically. Set `NOTION_CONTENT_DATA_SOURCE_ID`
when the database contains multiple data sources. An ambiguous target fails
the first synchronization attempt explicitly without blocking service startup
or canonical PostgreSQL scraping. If a full Notion query reaches the 10,000
result cap, deduplication detects the incomplete response and verifies each
candidate content ID with an exact query before creating a page.

`DATABASE_URL` may override the discrete PostgreSQL settings for local or
managed databases. Credentials in a manually supplied URL must be percent
encoded. Python-era `postgresql+psycopg://` and
`postgresql+psycopg2://` URLs are normalized automatically. SQLite URLs are
rejected with a migration error because PostgreSQL is the canonical store in
the Go runtime.

`host.docker.internal` addresses PostgreSQL running on the Docker host. Set
`DB_HOST` to the database hostname or IP when using another external server.
