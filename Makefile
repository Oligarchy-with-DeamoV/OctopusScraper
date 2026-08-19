.DEFAULT_GOAL := help

GIT_DESCRIPTION := $(shell git describe --tags --always --dirty 2>/dev/null || echo unknown)
ifeq ($(filter v%,$(GIT_DESCRIPTION)),)
DETECTED_VERSION := dev-$(GIT_DESCRIPTION)
else
DETECTED_VERSION := $(patsubst v%,%,$(GIT_DESCRIPTION))
endif
VERSION ?= $(DETECTED_VERSION)
COMMIT ?= $(shell git rev-parse HEAD 2>/dev/null || echo unknown)
BUILD_DATE ?= $(shell date -u +%Y-%m-%dT%H:%M:%SZ)
VERSION_PACKAGE := github.com/Oligarchy-with-DeamoV/OctopusScraper/internal/version

.PHONY: help install format format-check vet test test-race test-cov changelog-check changelog-release run build compose-up compose-down compose-logs clean

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

changelog-check: ## Validate changelog fragments
	go run ./tools/changelog check

changelog-release: ## Aggregate fragments with VERSION=x.y.z
	go run ./tools/changelog release --version "$(VERSION)"

run: ## Start the service
	go run ./cmd/octopus_service serve

build: ## Build the service binary
	CGO_ENABLED=0 go build -trimpath \
		-ldflags="-s -w \
		  -X $(VERSION_PACKAGE).Version=$(VERSION) \
		  -X $(VERSION_PACKAGE).Commit=$(COMMIT) \
		  -X $(VERSION_PACKAGE).Date=$(BUILD_DATE)" \
		-o octopus_service \
		./cmd/octopus_service

compose-up: ## Start the Docker Compose stack
	docker compose up -d

compose-down: ## Stop the Docker Compose stack
	docker compose down

compose-logs: ## Follow Docker Compose logs
	docker compose logs -f

clean: ## Remove generated Go artifacts
	rm -f octopus_service coverage.out
