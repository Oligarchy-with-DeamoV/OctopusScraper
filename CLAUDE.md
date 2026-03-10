# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

OctopusScraper (v0.2.0) is a multi-functional information scraping tool that fetches, processes, and stores web content via RSS feeds with Notion database integration. Python 3.9-3.10, managed with Poetry.

## Common Commands

```bash
# Install dependencies
poetry install

# Run all unit tests (excludes external/integration tests)
poetry run pytest -m "not need_external_service and not integrate_test" ./tests/ -n auto

# Run a single test file
poetry run pytest tests/octopus_scraper/task_manager/test_task_manager.py

# Run a single test by name
poetry run pytest -k "test_function_name"

# Run with coverage
poetry run pytest --cov=src tests/

# Format code
black src/ tests/

# Run the web service
poetry run octopus_service
```

## Test Markers

- `@pytest.mark.need_external_service` — tests requiring external APIs (Notion, LLM, etc.)
- `@pytest.mark.integrate_test` — full integration tests against real RSS sources
- Tests use `pytest-asyncio` with `asyncio_mode = "auto"` (no need for `@pytest.mark.asyncio`)
- Attention: normal dev run pytest DO NOT mark need_external_service or integrate_test

## Code Style

- **Formatter**: Black, 120 char line length
- **Indentation**: 4 spaces
- **Classes over standalone functions**: wrap logic in classes
- **Docstrings**: Google Python Style Guide format
- **Logging**: Use `structlog` throughout

## Architecture

### Core Pipeline: Fetch → Process → Store

1. **Octopus** (`src/octopus_scraper/octopus.py`) — Main orchestrator. Manages scraper configs, delegates scraping to TaskManager, handles upload to Notion with a threading lock for concurrency control.

2. **TaskManager** (`src/octopus_scraper/task_manager/task_manager.py`) — PriorityQueue-based task scheduler with ThreadPoolExecutor. Supports pre/post-execution hooks and result retention.

3. **Scraper** (`src/octopus_scraper/scraper.py`) — Fetches content using pluggable fetchers, runs it through a processor pipeline, and deduplicates against storage.

4. **Processors** (`src/octopus_scraper/processors/`) — Ordered pipeline of content processors (HTML extraction, LLM summarization, keyword extraction, tag generation). Each extends `ProcessorBase`. Registered in `AVALIABLE_PROCESSOR` dict.

5. **Storages** (`src/octopus_scraper/storages/`) — Persistence layer. `NotionStorage` handles Notion API writes with retry logic (tenacity).

6. **ConfigManager** (`src/octopus_scraper/config/`) — Loads scraper configurations from a Notion database. Supports hot-reload with change detection via `set_on_config_changed()`.

### Fetchers

Pluggable data sources registered in `AVALIABLE_FETCHERS`:

- `rsshub` — fetches via RSSHub instance
- `direct_rss` — fetches RSS feeds directly

### Web Service

`octopus_service.py` provides a Sanic web API with endpoints like `/trigger_scraper` and `/trigger_upload`. Entry point: `octopus_scraper.cli:run_octopus_service`.

### Data Model

`Content` dataclass (`src/octopus_scraper/protos.py`) is the core data transfer object flowing through the pipeline.

## Environment Variables

Required in `.env` (loaded via python-dotenv):

- `NOTION_API_KEY` — Notion integration token
- `NOTION_SCRAPERS_DATABASE_ID` — Notion DB for scraper configurations
- `NOTION_CONTENT_DATABASE_ID` — Notion DB for scraped content storage

Service config: `OCTOPUS_HOST`, `OCTOPUS_PORT`, `OCTOPUS_DEBUG`, `OCTOPUS_LOG_LEVEL`, `OCTOPUS_LOG_FORMAT`

## Key Patterns

- **Strategy pattern** for fetchers and processors (pluggable via registry dicts)
- **Non-blocking lock** in `Octopus.trigger_upload()` to prevent concurrent uploads
- **Tenacity retry** decorators on Notion API calls
- **Config hot-reload** via observer callback on ConfigManager
- Custom `doraemon` wheel in `resources/whls/` provides internal utilities
