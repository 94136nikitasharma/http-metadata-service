.PHONY: up down build test logs lint clean

# ───────────────── Quick Start ─────────────────

up: ## Start all services (API + MongoDB)
	docker compose up --build -d

down: ## Stop all services and remove volumes
	docker compose down -v

build: ## Rebuild the API image
	docker compose build api

# ───────────────── Testing ─────────────────────

test: ## Run the full test suite inside Docker
	docker compose run --rm api python -m pytest tests/ -v

test-unit: ## Run only unit tests (no MongoDB required)
	docker compose run --rm api python -m pytest tests/test_collector.py tests/test_background.py -v

test-integration: ## Run integration tests (requires MongoDB)
	docker compose run --rm api python -m pytest tests/test_api.py tests/test_repository.py -v

# ───────────────── Utilities ───────────────────

logs: ## Tail logs from all services
	docker compose logs -f

logs-api: ## Tail logs from the API only
	docker compose logs -f api

lint: ## Run ruff linter
	docker compose run --rm api ruff check app/ tests/

clean: ## Remove all containers, images, and volumes
	docker compose down -v --rmi all

# ───────────────── Help ────────────────────────

help: ## Show this help message
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-20s\033[0m %s\n", $$1, $$2}'

.DEFAULT_GOAL := help
