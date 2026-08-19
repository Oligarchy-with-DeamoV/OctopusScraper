# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.3.1] - 2026-08-19

### Fixed
- Bounded scheduler, RSSHub, Redis, and Vector resource usage in Docker Compose and made Redis evict cache entries before reaching its container memory limit.

## [0.3.0] - 2026-08-19

### Added
- Added pluggable exporter targets with independent PostgreSQL synchronization state, leases, and retries.
- Added token-protected, read-only MCP tools for listing and retrieving canonical content.

### Changed
- Reimplemented the service in Go 1.26.
- Replaced Sanic, Poetry, SQLAlchemy, and Python worker threads with `net/http`,
  Go modules, `pgx`, and bounded goroutine workers.
- Replaced the Python runtime image with a statically linked distroless image.
- Updated Notion synchronization for API version `2026-03-11` and data sources.
- Changed service logging to structured Zap output with optional rotating compressed file logs and runtime level control.
- Formal versions now come from validated Git tags, and user-visible changes are collected as changelog fragments.

### Removed
- Removed the Python runtime, tests, packaging, vendored `doraemon` wheel,
  deprecated `llm` processor, misspelled fetcher alias, and placeholder
  provider implementations.
- Removed the Notion Data Source ID setting and now require each configured database to expose exactly one data source.

## [0.2.0] - 2025-05-07

### Added
- TaskManager with PriorityQueue-based task scheduling and ThreadPoolExecutor
- LLM-powered processors: summary, keywords, and tags extraction
- ProcessorRegistry and ProcessorFactory for pluggable processor management
- ProcessorPipeline for chaining multiple processors with priority ordering
- ConfigManager with hot-reload and change detection via Notion database
- Docker Compose deployment with full service stack (OctopusScraper + RSSHub + Redis)
- Vector-based log monitoring with Feishu webhook alerts
- Health check endpoints with caching and comprehensive system status
- CLI with argparse for service configuration
- Batch-level retry for Notion uploads to prevent duplicates
- Content ID generation using stable URL + published + GUID hashing
- Keywords column support in scraper configuration
- Markdown-to-Notion block converter with rich text support
- Data validation utilities with JSON schema validation
- Text processing utilities for content cleanup

### Changed
- Migrated from setup.py to pyproject.toml with Poetry
- Replaced simple sequential scraping with concurrent TaskManager
- Improved Notion API rate limiting with configurable intervals
- Enhanced content deduplication with batch-internal dedup and caching

### Fixed
- Split list/heading rich_text to respect Notion 100-element limit
- Prevented duplicate page creation during upload retries
- Fixed content_ids cache invalidation after successful page creation

## [0.1.0] - 2024-01-01

### Added
- Initial release with RSS feed scraping via RSSHub and direct RSS
- Notion database integration for content storage
- HTML content processor with readability extraction
- Basic LLM processor for content analysis
- Sanic web service with trigger endpoints
- Environment-based configuration with python-dotenv
