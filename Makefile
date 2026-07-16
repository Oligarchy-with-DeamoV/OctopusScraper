.DEFAULT_GOAL := help

.PHONY: help install format format-check test test-cov run compose-up compose-down compose-logs clean

FIND_PRUNE := \( -path './.git' -o -path './.venv' -o -path './venv' -o -path './env' -o -path './ENV' -o -path './env.bak' -o -path './venv.bak' -o -path './__pypackages__' \) -prune -o

help: ## Show available targets
	@awk 'BEGIN {FS = ":.*## "; printf "Usage: make <target>\n\nTargets:\n"} /^[a-zA-Z0-9_-]+:.*## / {printf "  %-14s %s\n", $$1, $$2}' $(MAKEFILE_LIST)

install: ## Install project dependencies
	poetry install

format: ## Format source and test files with Black
	poetry run black src/ tests/

format-check: ## Check formatting with Black
	poetry run black --check src/ tests/

test: ## Run unit tests without external or integration tests
	poetry run pytest -m "not need_external_service and not integrate_test" ./tests/ -n auto

test-cov: ## Run the CI test suite with coverage reports
	poetry run pytest -m "not need_external_service and not integrate_test" ./tests/ -n auto --cov=src --cov-report=xml --cov-report=term-missing -q

run: ## Start the OctopusScraper service
	poetry run octopus_service

compose-up: ## Start the Docker Compose stack
	docker compose up -d

compose-down: ## Stop the Docker Compose stack
	docker compose down

compose-logs: ## Follow Docker Compose logs
	docker compose logs -f

clean: ## Remove reproducible caches and build artifacts
	find . $(FIND_PRUNE) -type d -name '__pycache__' -exec rm -rf {} +
	find . $(FIND_PRUNE) -type f \( -name '*.pyc' -o -name '*.pyo' -o -name '*.pyd' \) -exec rm -f {} +
	find . $(FIND_PRUNE) -type d -name '*.egg-info' -exec rm -rf {} +
	rm -rf .pytest_cache htmlcov build dist
	rm -f .coverage .coverage.* coverage.xml
