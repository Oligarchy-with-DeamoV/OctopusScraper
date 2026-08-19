# Contributing to OctopusScraper

## Prerequisites

- Go 1.26.6
- Docker
- PostgreSQL for integration testing

## Setup

```bash
git clone https://github.com/Oligarchy-with-DeamoV/OctopusScraper.git
cd OctopusScraper
go mod download
cp .env.example .env
```

## Development checks

```bash
gofmt -w .
go vet ./...
go test ./...
go test -race ./...
go test -race -coverprofile=coverage.out ./...
```

External RSS, Browserless, OpenAI, Notion, and PostgreSQL calls must use local
fixtures or fakes in the default test suite. Integration tests must be
explicitly opt-in.

## Code style

- Prefer the standard library for HTTP, contexts, concurrency, and logging.
- Keep goroutines, retries, queues, response bodies, and timeouts bounded.
- Wrap errors with operation context.
- Use structured `slog` attributes without credentials.
- Add interfaces at consumer boundaries.
- Add tests for failure and cancellation paths.

## Pull requests

1. Create a focused branch from the latest `main`.
2. Add or update tests and documentation.
3. Run formatting, vet, race tests, coverage, and the Docker build.
4. Open a PR against `main` with a `## Verification` section.
5. Wait for green CI. Maintainers perform the merge.
