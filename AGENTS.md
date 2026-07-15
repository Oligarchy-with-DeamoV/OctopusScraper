# AGENTS.md

This file provides guidance to AI coding agents when working with code in this repository.

## Project Overview

OctopusScraper (`octopus-scraper`, v0.2.0) is a multi-functional information
scraping tool that fetches, processes, and persists web content via RSS feeds
with Notion as the canonical storage backend. It provides:

- RSS-based content acquisition through pluggable fetchers (RSSHub or direct
  RSS endpoints)
- A configurable content-processing pipeline (HTML extraction, LLM
  summarization, keyword & tag generation)
- Notion-backed persistence with deduplication, retry logic, and concurrency
  control
- A Sanic web service (`octopus_service`) exposing trigger endpoints, plus a
  Docker Compose stack bundling RSSHub, Redis, a cron scheduler, and a Vector
  log-monitoring sidecar that pushes alerts to Feishu

## Commands

```bash
# Install dependencies
poetry install

# Run the web service (entry point defined in pyproject.toml)
poetry run octopus_service

# Run all unit tests (excludes external/integration tests) — default dev run
poetry run pytest -m "not need_external_service and not integrate_test" ./tests/ -n auto

# Run a single test file
poetry run pytest tests/octopus_scraper/task_manager/test_task_manager.py

# Run a single test by name
poetry run pytest -k "test_function_name"

# Run with coverage
poetry run pytest --cov=src tests/

# Format code (Black uses its default line length of 88; CI checks the same)
poetry run black src/ tests/

# Run the full Docker Compose stack (octopus-service + rsshub + redis + scheduler + vector-alert)
docker compose up -d
```

> The project does **not** use ruff or mypy. Black 24.10.0 is the sole
> formatter, enforced via `.pre-commit-config.yaml`.

## Architecture

### Source layout: `src/octopus_scraper/`

**Entry point**: `cli/__init__.py` — defines `run_octopus_service`, the
`octopus_service` console script. It parses CLI / env config, configures
structlog (plain console or JSON via `OCTOPUS_LOG_FORMAT`), and starts the
Sanic app from `service/app.py`.

**Main modules:**

1. **`task_manager/`** — Concurrent task scheduling
   - `task_manager.py` — `TaskManager`: PriorityQueue-based scheduler backed by
     a `ThreadPoolExecutor`. Supports pre/post-execution hooks, retry logic,
     and result retention. Emits the structured `"Task failed"` log entry that
     downstream alerting (Vector) keys on.
   - `models.py` — `ScraperTask`, `TaskResult`, `TaskStatus` (`PENDING`,
     `RUNNING`, `COMPLETED`, `FAILED`).

2. **`processors/`** — Ordered content processing pipeline
   - `processor_base.py` — `ProcessorBase` abstract class
   - `processor_pipeline.py` — Composes processors in order
   - `html_content_processor.py`, `llm_summary_processor.py`,
     `llm_keywords_processor.py`, `llm_tags_processor.py` — Concrete
     processors, registered in `AVAILABLE_PROCESSOR`
   - `llm_processor.py` — Shared LLM invocation logic

3. **`storages/`** — Persistence layer
   - `base_storage.py` — Abstract storage interface with retry/skip accounting
   - `postgres_storage.py` — canonical PostgreSQL content persistence,
     deduplication, sync state, retry metadata, and worker leases
   - `notion_storage.py` — optional downstream Notion API writes
   - `markdown_to_notion.py` — Markdown → Notion block converter

4. **`config/`** — Scraper configuration
   - `config_manager.py` — `ConfigManager`: loads one scraper per YAML file,
     polls with content fingerprints, and preserves the last valid file on
     parse or validation failures
   - `yaml_config.py`, `models.py` — strict YAML parsing and config schemas

5. **`service/`** — Sanic web service
   - `app.py` — App factory, route registration
   - `routes.py` — `/trigger_scraper`, `/trigger_upload`, etc.
   - `admin.py`, `health.py`, `lifecycle.py` — Admin endpoints, liveness
     check, startup/shutdown hooks
   - `config_helpers.py` — structlog configuration helpers (chooses JSON vs
     console renderer based on `LOG_FORMAT`)

6. **`utils/`** — Cross-cutting helpers
   - `rsshub.py`, `direct_rss.py` — Fetchers, registered in
     `AVAILABLE_FETCHERS`
   - `text_processor.py`, `tools.py`, `validators.py`

7. **`llm/`** — LLM client wrapper
   - `client.py`, `prompts.py`, `schemas.py`, `utils.py`

**Top-level modules:**

- `octopus.py` — `Octopus`: main orchestrator. Holds scraper configs, delegates
  scraping to `TaskManager`, handles upload to Notion with a threading lock to
  serialize concurrent uploads.
- `octopus_service.py` — Sanic service glue retained at package root
- `scraper.py` — `Scraper`: runs fetch → process → dedupe pipeline for a
  single scraper config
- `protos.py` — `Content` dataclass, the DTO flowing through the pipeline
- `logging_config.py` — `LoggingConfigurator`: sets root log level and quiets
  `httpx` / `httpcore`

### Key patterns

- **Configuration**: Scrapers come from `SCRAPER_CONFIG_DIR`; one `.yml` or
  `.yaml` file defines one scraper. Runtime settings come from `.env` (loaded
  with `python-dotenv`). PostgreSQL uses `DATABASE_URL`; optional Notion sync
  uses `NOTION_SYNC_ENABLED`, `NOTION_API_KEY`, and
  `NOTION_CONTENT_DATABASE_ID`. Service tuning:
  `SERVICE_HOST`, `SERVICE_PORT`, `OCTOPUS_LOG_LEVEL`, `OCTOPUS_LOG_FORMAT`,
  `LOG_LEVEL`, `LOG_FORMAT`, `USE_TASK_MANAGER`,
  `TASK_MANAGER_MAX_CONCURRENT`,   `TASK_MANAGER_MAX_QUEUE_SIZE`, `SCRAPER_CONFIG_POLL_INTERVAL`,
  `SCRAPER_CONFIG_DEBOUNCE_SECONDS`, `NOTION_SYNC_INTERVAL_SECONDS`, and
  `NOTION_SYNC_BATCH_SIZE`. Alerting: `FEISHU_WEBHOOK_URL`.
- **Data storage**: PostgreSQL is canonical for scraped content. Notion is an
  optional downstream synchronization target. Redis is used only by the
  bundled RSSHub instance for caching.
- **Service architecture**: HTTP routes → `Octopus` orchestrator →
  `TaskManager` (ThreadPoolExecutor) → `Scraper` → fetchers + processor
  pipeline → `PostgresStorage`. `NotionSyncService` claims due rows with
  database leases for periodic or manual incremental synchronization.
- **Background / async work**: `TaskManager` (thread pool + priority queue).
  Periodic triggering is performed by the `scheduler` container (BusyBox
  `crond`) reading `scheduler/crontab` and calling the HTTP trigger
  endpoints.
- **Logging**: `structlog.get_logger()` throughout, with named keyword
  arguments for structured context. Renderer is chosen at startup —
  `ConsoleRenderer` for `LOG_FORMAT=plain` (default), `JSONRenderer` for
  `LOG_FORMAT=json`. Level via `OCTOPUS_LOG_LEVEL` / `LOG_LEVEL`. The
  `"Task failed"` event in `task_manager.py` is the stable signal Vector
  uses for alerting; do not rename it without updating `vector.toml`.
- **Error handling**: External calls (Notion, LLM, HTTP) wrapped in
  try/except and re-tried with `tenacity` where appropriate. Failures are
  logged with structured context (`task_id`, `scraper_name`, `error`,
  `retry_count`, `max_retries`).
- **No legacy code**: Deprecated or replaced code MUST be deleted, not left
  behind "for reference". When a module is superseded, remove the old files
  entirely and update all imports, tests, and documentation.

### Infrastructure

- **Docker Compose** (`docker-compose.yml`):
  - `octopus-service` — the Sanic app (built from `dockerfiles/Dockerfile`)
  - `scheduler` — Alpine + `crond` reading `scheduler/crontab`
  - `rsshub` — RSSHub instance (custom `info-channel:1.0.0` image by default)
  - `redis` — cache for RSSHub
  - `vector-alert` — Vector sidecar reading `vector.toml`; tails Docker
    container logs and forwards matched error events to Feishu via webhook
- **Dockerfiles** live in `dockerfiles/`
- **Scheduler**: `scheduler/crontab` controls all periodic triggers
- **Vector config**: `vector.toml` defines log sources, filters, Feishu card
  formatting, and the HTTP sink for `FEISHU_WEBHOOK_URL`

## Code Style

- **Formatter**: Black, default 88 char line length (pinned to 24.10.0 in
  `.pre-commit-config.yaml`; `pyproject.toml` has no `[tool.black]`
  override, and CI runs `poetry run black --check src/ tests/`)
- Always use classes instead of standalone functions
- Google Python Style Guide for docstrings
- 4-space indentation, PEP 8 compliance
- Type hints required on all public functions/methods
- Descriptive names; comments for non-obvious logic only

## Testing

- Tests mirror source structure under `tests/`
- Markers (defined in `pyproject.toml`):
  - `need_external_service` — requires external APIs (Notion, LLM, …)
  - `integrate_test` — full integration against real RSS sources
- The default local / pre-commit run excludes both markers:
  `poetry run pytest -m "not need_external_service and not integrate_test" ./tests/ -n auto`
- `pytest-asyncio` with `asyncio_mode = "auto"` — no `@pytest.mark.asyncio`
  needed
- External APIs / network calls MUST be mocked in non-integration tests
- `pythonpath = "src"` — imports use `from octopus_scraper.xxx import ...`

## Dependencies

- **Poetry** for all dependency management — never use pip directly
- Python `>3.9, <3.11` (3.9 or 3.10 only)
- Notable runtime deps: `sanic >=21.3.0`, `feedparser ^6.0.11`,
  `notion_client ^2.3.0`, `tenacity ^9.0.0`, `httpx ^0.27.0` (with `socks`),
  `playwright ^1.40.0`, `python-dotenv ^1.1.0`, `readability-lxml`,
  `markdownify`, `mistune`
- `doraemon` is a vendored internal wheel at
  `resources/whls/doraemon-0.0.5b0-py3-none-any.whl` — do not replace it
  with a PyPI package
- Primary package source is the Aliyun PyPI mirror

## Iteration Workflow (MANDATORY for AI agents)

Every code change — feature, fix, refactor, docs, even one-line typos —
must go through this loop. **Direct pushes to `main` are forbidden**,
no exceptions. The loop ensures CI is the single source of truth for
"is this change safe to merge".

### The 6-step loop

1. **Branch from latest `main`**

   ```bash
   git checkout main && git pull --ff-only origin main
   git checkout -b <type>/<slug>
   ```

   `<type>` ∈ {`feat`, `fix`, `docs`, `refactor`, `test`, `chore`} —
   matches Conventional Commits.
   `<slug>` is 2–5 word kebab-case (e.g. `fix/login-redirect-loop`,
   `feat/csv-export`).

2. **Implement and verify locally** before pushing:

   ```bash
   poetry run black --check src/ tests/
   poetry run pytest -m "not need_external_service and not integrate_test" ./tests/ -n auto
   ```

   If you touched `vector.toml`, also validate it:

   ```bash
   docker run --rm -v "$PWD/vector.toml:/etc/vector/vector.toml:ro" \
     timberio/vector:latest-alpine validate /etc/vector/vector.toml
   ```

3. **Commit** with Conventional Commits format. Every commit message
   must include the trailer:

   ```
   Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>
   ```

4. **Push the branch and open a PR**:

   ```bash
   git push -u origin HEAD
   gh pr create --fill --base main
   ```

   The PR body must include a `## Verification` section listing
   exactly what was run locally (the commands from step 2 plus their
   outcomes).

5. **Watch CI and self-heal until green**:

   ```bash
   gh run watch --exit-status        # blocks until the run finishes
   # if it fails:
   gh run view <run-id> --log-failed # diagnose
   # push fix commits to the same branch, repeat
   ```

   **Hard limit: 3 fix attempts.** If CI is still red after the third
   push, stop. Summarize what was tried and surface the failure to the
   human — do NOT keep guessing. Suspected-flaky failures count toward
   this budget; if you believe a failure is flaky, say so explicitly
   in the PR and stop.

6. **Stop after the PR is green. Do NOT auto-merge.** Report the PR URL
   and the final green CI run ID. Merging is the human's call.

### Why no direct pushes to `main`

Changes that "look clean locally" can still fail on CI's cold
environment. The PR + CI loop catches those before they land on `main`,
and gives reviewers a single artifact (the PR diff) to inspect rather
than a moving `main`.
