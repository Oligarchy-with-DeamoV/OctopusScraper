# AGENTS.md

Guidance for coding agents working on OctopusScraper.

## Project

OctopusScraper is a Go service that:

- fetches RSS/Atom content from RSSHub or direct feed URLs;
- applies optional HTML and OpenAI-compatible processors;
- stores canonical content and synchronization state in PostgreSQL;
- synchronizes PostgreSQL rows to Notion with leases and retries;
- exposes trigger, health, admin, and Prometheus endpoints;
- runs with RSSHub, Redis, a cron scheduler, and Vector in Docker Compose.

The repository only covers information collection and persistence. Business
analysis belongs outside this project.

## Commands

```bash
go mod download
gofmt -w .
go vet ./...
go test ./...
go test -race ./...
go test -coverprofile=coverage.out ./...
go run ./tools/changelog check
go run ./cmd/octopus_service serve
docker compose up -d
```

Build the production image:

```bash
docker build -f dockerfiles/Dockerfile -t octopus-scraper:latest .
```

## Layout

- `cmd/octopus_service/` — service and container-healthcheck entry point.
- `internal/bootstrap/` — dependency construction and process lifecycle.
- `internal/config/` — environment settings and strict YAML polling.
- `internal/fetcher/` — RSSHub and direct RSS acquisition.
- `internal/processor/` — ordered HTML and LLM processing pipeline.
- `internal/storage/` — PostgreSQL canonical store and migrations.
- `internal/exporter/` — target-isolated export scheduling, leases, and retries.
- `internal/exporter/notion/` — Notion REST client and block conversion.
- `internal/task/` — bounded priority queue, workers, retries, and SQLite results.
- `internal/httpapi/` — trigger, health, admin, and metrics routes.
- `internal/observability/` — `slog` handlers and Prometheus metrics.
- `contracts/` — language-neutral compatibility fixtures.

## Runtime invariants

- PostgreSQL is canonical. A scrape succeeds after its database write commits.
- Notion failure must not roll back canonical content.
- Preserve schema version `1` unless a migration is explicitly requested.
- Scraper config uses one YAML document per file. Reject aliases, duplicate
  keys, unknown fields, invalid URLs, duplicate IDs/names, and unsupported
  fetchers/processors.
- Invalid changes to an accepted YAML file retain that file's last valid value.
- Path-only config renames transfer the accepted last-good snapshot to the new
  path before later invalid edits are evaluated.
- Config reload swaps immutable scraper snapshots without cancelling submitted
  tasks.
- Processor and custom-category insertion order affects behavior and must be
  included in config fingerprints and reload diffs.
- Task submission is bounded and priority ordered. Retries are bounded.
- Queue saturation may delay a scheduled retry but must not discard it.
- Graceful shutdown rejects new work, cancels queued work, and lets running
  tasks drain until the shutdown deadline before forcing cancellation.
- PostgreSQL closes only after task and Notion workers report a complete stop.
- `SCRAPER_TIMEOUT` controls task execution deadlines.
- Persisted non-terminal task results must be finalized during startup; never
  expose stale `pending`, `running`, or `retrying` work after a restart.
- Task-result SQLite persistence is optional and must not prevent PostgreSQL
  scraping from starting when history cannot be read or written.
- Notion workers claim rows with leases and PostgreSQL
  `FOR UPDATE SKIP LOCKED`.
- Losing a Notion lease cancels the active writer before another worker can
  reclaim the row.
- Notion deduplication must treat `request_status.type=incomplete` as a
  truncated query and verify misses with exact content-ID queries.
- A YAML-selected LLM endpoint must not inherit a global API key configured
  for a different endpoint.
- The structured `"Task failed"` event and error-level output are stable Vector
  alert signals.
- Fatal startup errors emitted before logger initialization must also match the
  Vector error filter.
- Browser rendering uses remote Browserless/CDP. Do not add Chromium to the
  service image.
- Deprecated Python compatibility aliases and placeholder providers must not
  be reintroduced.

## Go style

- Go 1.26.6.
- Run `gofmt`; CI rejects formatting drift.
- Prefer the standard library for HTTP, concurrency, and contexts. Logging uses
  Zap behind injected `*slog.Logger`; Lumberjack is limited to optional file
  rotation.
- Keep interfaces at consumer boundaries and concrete types elsewhere.
- Propagate `context.Context` through blocking and external operations.
- Bound goroutines, queues, response bodies, retries, and external timeouts.
- Return explicit wrapped errors; do not log-and-return-success.
- Use structured `slog` attributes. Do not log credentials or full database
  URLs.
- Add comments only for exported APIs or non-obvious invariants.
- Avoid global mutable state.

## Testing

- Unit tests use `httptest`, temporary directories, and local fakes.
- Tests must not call real RSS, Browserless, OpenAI, Notion, or PostgreSQL
  services unless explicitly marked as integration tests.
- Compatibility fixtures cover YAML, RSS normalization, API JSON, Notion
  blocks, metrics, and stable log events.
- Run the race detector for concurrent code.
- CI requires at least 70% coverage.

## Dependencies

- Go modules only.
- `pgx/v5` is the PostgreSQL driver; use explicit SQL rather than an ORM.
- Notion uses its REST API directly; do not add an unofficial SDK.
- SQLite must remain pure Go so release builds use `CGO_ENABLED=0`.
- Review new dependencies for maintenance, license, binary-size impact, and
  whether the standard library already covers the requirement.

## No legacy code

Delete superseded code, tests, packaging, and documentation in the same
cutover. Do not keep old implementations for reference.

## Mandatory change workflow

Direct pushes to `main` are forbidden.

1. Branch from latest `main`:

   ```bash
   git checkout main
   git pull --ff-only origin main
   git checkout -b <type>/<slug>
   ```

2. Verify locally:

   ```bash
   test -z "$(gofmt -l .)"
   go vet ./...
   go test -race -coverprofile=coverage.out ./...
   docker build -f dockerfiles/Dockerfile -t octopus-scraper:verify .
   ```

   If `vector.toml` changes:

   ```bash
   docker run --rm \
     -v "$PWD/vector.toml:/etc/vector/vector.toml:ro" \
     -v /var/run/docker.sock:/var/run/docker.sock:ro \
     timberio/vector:latest-alpine \
     validate /etc/vector/vector.toml
   ```

3. Commit with Conventional Commits and this trailer:

   ```text
   Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>
   ```

4. Push and open a PR against `main`. The PR body must contain a
   `## Verification` section listing exact commands and outcomes.

5. Watch CI and fix failures on the same branch. Stop after three failed fix
   pushes and report the remaining failure.

6. Stop after green CI. Do not merge automatically.
