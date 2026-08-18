.DEFAULT_GOAL := help

.PHONY: help install format format-check vet test test-race test-cov run build compose-up compose-down compose-logs clean

help: ## Show available targets
	@awk 'BEGIN {FS = ":.*## "; printf "Usage: make <target>\n\nTargets:\n"} /^[a-zA-Z0-9_-]+:.*## / {printf "  %-14s %s\n", $$1, $$2}' $(MAKEFILE_LIST)

install: ## Download Go modules
	go mod download

format: ## Format Go source
	gofmt -w .

format-check: ## Check Go formatting
	test -z "$$(gofmt -l .)"

vet: ## Run Go static checks
	go vet ./...

test: ## Run unit tests
	go test ./...

test-race: ## Run tests with the race detector
	go test -race ./...

test-cov: ## Run tests and write coverage.out
	go test -race -coverprofile=coverage.out ./...
	go tool cover -func=coverage.out

run: ## Start the service
	go run ./cmd/octopus_service serve

build: ## Build the service binary
	CGO_ENABLED=0 go build -trimpath -o octopus_service ./cmd/octopus_service

compose-up: ## Start the Docker Compose stack
	docker compose up -d

compose-down: ## Stop the Docker Compose stack
	docker compose down

compose-logs: ## Follow Docker Compose logs
	docker compose logs -f

clean: ## Remove generated Go artifacts
	rm -f octopus_service coverage.out
