# Contributing to OctopusScraper

Thank you for your interest in contributing to OctopusScraper! This guide will help you get started.

## Development Setup

### Prerequisites

- Python 3.9 or 3.10
- [Poetry](https://python-poetry.org/docs/#installation) for dependency management

### Getting Started

```bash
# Clone the repository
git clone https://github.com/Oligarchy-with-DeamoV/OctopusScraper.git
cd OctopusScraper

# Install dependencies
poetry install

# Set up environment variables
cp .env.example .env
# Edit .env with your configuration

# Install pre-commit hooks
poetry run pre-commit install
```

## Development Workflow

### Make Targets

If `make` is available, use the repository targets for common development
tasks:

```bash
make help          # List all available targets
make install       # Install dependencies
make format        # Format source and test files
make format-check  # Check formatting without changing files
make test          # Run the default unit test suite
make test-cov      # Run the CI test suite with coverage reports
make run           # Start octopus_service
make compose-up    # Start the Docker Compose stack
make compose-down  # Stop the Docker Compose stack
make compose-logs  # Follow Docker Compose logs
make clean         # Remove reproducible caches and build artifacts
```

The Poetry commands below remain available in environments without `make`.

### Running Tests

```bash
# Run all unit tests (excludes external/integration tests)
poetry run pytest -m "not need_external_service and not integrate_test" ./tests/ -n auto

# Run a specific test file
poetry run pytest tests/octopus_scraper/scraper_test.py

# Run the CI test suite with coverage reports
poetry run pytest -m "not need_external_service and not integrate_test" ./tests/ -n auto --cov=src --cov-report=xml --cov-report=term-missing -q
```

### Code Style

We use [Black](https://black.readthedocs.io/) with its default 88-character line
length.

```bash
# Format code
poetry run black src/ tests/

# Check formatting exactly as CI does
poetry run black --check src/ tests/
```

### Pre-commit Hooks

Pre-commit hooks run automatically on `git commit` and include:
- Black formatting
- YAML validation
- Trailing whitespace removal
- Test execution

### Writing Tests

- Place tests in `tests/` mirroring the `src/` structure
- Use `pytest` fixtures and `pytest-mock` for mocking
- Use `pytest-asyncio` for async tests (auto mode enabled)
- Mark external service tests with `@pytest.mark.need_external_service`
- Mark integration tests with `@pytest.mark.integrate_test`
- Aim for 80%+ test coverage

## Pull Request Process

1. **Fork** the repository and create a feature branch
2. **Write tests** for your changes
3. **Ensure all tests pass** locally
4. **Format code** with Black
5. **Submit a PR** with a clear description of changes

### PR Guidelines

- Keep PRs focused on a single change
- Include tests for new functionality
- Update documentation if needed
- Reference any related issues

## Project Structure

```
src/octopus_scraper/
├── cli/                 # CLI entry point
├── config/              # Configuration management
├── llm/                 # LLM client and utilities
├── processors/          # Content processing pipeline
├── storages/            # Storage backends (Notion)
├── task_manager/        # Task scheduling and execution
├── utils/               # Shared utilities
├── octopus.py           # Main orchestrator
├── octopus_service.py   # Sanic web service
├── protos.py            # Core data models
└── scraper.py           # Scraper with fetcher integration
```

## Code of Conduct

Please be respectful and constructive in all interactions. We are committed to providing a welcoming and inclusive experience for everyone.

## Questions?

Feel free to open an issue for questions, bug reports, or feature requests.
