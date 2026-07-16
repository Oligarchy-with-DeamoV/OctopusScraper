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
NOTION_SYNC_INTERVAL_SECONDS=60
NOTION_SYNC_BATCH_SIZE=100
NOTION_SYNC_MAX_ATTEMPTS=10
NOTION_SYNC_LEASE_SECONDS=300
```

Set `NOTION_SYNC_ENABLED=false` to retain content only in PostgreSQL. In that
mode the service does not construct a Notion client or call the Notion API.

`DATABASE_URL` may override the discrete PostgreSQL settings for local or
managed databases. Credentials in a manually supplied URL must be percent
encoded.

`host.docker.internal` addresses PostgreSQL running on the Docker host. Set
`DB_HOST` to the database hostname or IP when using another external server.
