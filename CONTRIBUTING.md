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
make changelog-check
```

External RSS, Browserless, OpenAI, Notion, and PostgreSQL calls must use local
fixtures or fakes in the default test suite. Integration tests must be
explicitly opt-in.

## Code style

- Prefer the standard library for HTTP, contexts, and concurrency; logging uses
  Zap only as the injected `slog` core and Lumberjack only for optional file
  rotation.
- Keep goroutines, retries, queues, response bodies, and timeouts bounded.
- Wrap errors with operation context.
- Use structured `slog` attributes without credentials.
- Add interfaces at consumer boundaries.
- Add tests for failure and cancellation paths.

## Pull requests

1. Create a focused branch from the latest `dev`.
2. Add or update tests and documentation. Add one changelog fragment for each
   user-visible change:

   ```text
   changelog.d/<issue-or-slug>.<type>.md
   ```

   Valid types are `added`, `changed`, `fixed`, `removed`, and `security`.
   Each fragment contains one concise user-visible change without a Markdown
   bullet. Internal refactors, tests, and maintenance with no behavior change
   do not require a fragment.
3. Run formatting, vet, race tests, coverage, and the Docker build.
4. Open a PR against `dev` with a `## Verification` section. Release and
   hotfix PRs may target `main`.
5. Wait for green CI. Maintainers perform the merge.

## Version tags

Git tags are the only source of formal versions. To prepare a version:

1. Run `make changelog-release VERSION=x.y.z`.
2. Commit the generated changelog update and fragment removals through a PR.
3. After the PR merges and CI passes, run the `Create version tag` workflow
   from `main` with the same version.

The workflow creates an annotated `vx.y.z` or `vx.y.z-rc.N` tag. It does not
create a GitHub Release or publish binaries or images.
