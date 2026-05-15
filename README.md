# HTTP Metadata Inventory Service

A high-performance, production-ready RESTful service that collects, stores, and retrieves HTTP metadata (headers, cookies, page source) for any given URL. Built with **FastAPI**, **MongoDB**, and **Docker Compose**.

## Features

- **Synchronous Collection** — `POST` a URL to immediately fetch and store its metadata
- **Inventory Lookup** — `GET` stored metadata with automatic background fetching on cache misses
- **Asynchronous Background Worker** — Non-blocking metadata collection using `asyncio.create_task()`
- **Request Deduplication** — In-flight URL tracking prevents duplicate background fetches
- **System Resilience** — MongoDB connection retry with exponential backoff for container startup delays
- **Request Tracing** — Unique `X-Request-ID` header on every response for observability
- **Deep Health Checks** — `/health` endpoint verifies both API and database connectivity
- **Auto-generated API Docs** — Interactive Swagger UI at `/docs`
- **Comprehensive Test Suite** — 28 tests covering unit, integration, and edge cases
- **One-command Setup** — `docker compose up` starts everything

---

## Quick Start

### Prerequisites

- [Docker](https://docs.docker.com/get-docker/) (with Docker Compose)

### Run the Service

```bash
git clone https://github.com/94136nikitasharma/http-metadata-service.git
cd http-metadata-service
docker compose up --build
```

The API will be available at **http://localhost:8000**.

> **Note:** No `.env` file or manual configuration is needed — all defaults are baked into `docker-compose.yml`.

### Using the Makefile

```bash
make up          # Start services
make test        # Run full test suite
make logs        # Tail service logs
make down        # Stop and clean up
make help        # Show all available commands
```

### Interactive API Documentation

| URL | Description |
|-----|-------------|
| http://localhost:8000/docs | Swagger UI (interactive testing) |
| http://localhost:8000/redoc | ReDoc (read-only documentation) |
| http://localhost:8000/health | Deep health check (API + MongoDB) |

---

## Architecture

```
┌──────────────────────────────────────────────────────────────┐
│                      FastAPI Application                     │
│                                                              │
│  ┌─────────────┐    ┌──────────────┐    ┌────────────────┐   │
│  │   Routes     │───▸│   Services   │───▸│   Repository   │   │
│  │  (Transport) │    │  (Business)  │    │    (Data)      │   │
│  └─────────────┘    └──────────────┘    └───────┬────────┘   │
│        │                  │                     │            │
│        │             ┌────┴──────┐              │            │
│        │             │ Background│              │            │
│        │             │  Worker   │──────────────┘            │
│        │             └───────────┘                           │
│        │                                                     │
│  ┌─────┴──────────────────────────────────────────────────┐  │
│  │            Middleware (Request ID, CORS)                │  │
│  └────────────────────────────────────────────────────────┘  │
└────────┬─────────────────────────────────────────┬───────────┘
         │                                         │
     HTTP Clients                              MongoDB
```

**Layer Responsibilities:**

| Layer | Module | Responsibility |
|-------|--------|----------------|
| **Transport** | `app/api/routes.py` | Request validation, HTTP response mapping |
| **Business Logic** | `app/services/collector.py` | HTTP metadata extraction via `httpx` |
| **Orchestration** | `app/services/background.py` | Async task scheduling with deduplication |
| **Data Access** | `app/repositories/metadata_repo.py` | MongoDB CRUD with indexed lookups |
| **Models** | `app/models/metadata.py` | Pydantic schemas for validation & serialisation |
| **Configuration** | `app/config.py` | Environment-based settings via `pydantic-settings` |
| **Infrastructure** | `app/database.py` | Connection pooling with retry/backoff |

---

## API Reference

### `POST /api/v1/metadata`

Collect and store metadata for a URL.

**Request:**
```json
{
  "url": "https://example.com"
}
```

**Response `201 Created`:**
```json
{
  "message": "Metadata collected and stored successfully.",
  "url": "https://example.com/",
  "collected_at": "2026-05-14T10:30:00.000Z"
}
```

**Error `400 Bad Request`** — URL unreachable / timeout:
```json
{
  "detail": "Request timed out for URL: https://unreachable-site.com"
}
```

**Error `422 Unprocessable Entity`** — Malformed URL:
```json
{
  "detail": [{"msg": "Invalid URL", "type": "url_parsing"}]
}
```

---

### `GET /api/v1/metadata?url=<URL>`

Retrieve stored metadata for a URL.

**Cache Hit — `200 OK`:**
```json
{
  "url": "https://example.com/",
  "headers": {
    "content-type": "text/html; charset=UTF-8",
    "server": "cloudflare"
  },
  "cookies": [
    {
      "name": "session_id",
      "value": "abc123",
      "domain": "example.com",
      "path": "/"
    }
  ],
  "page_source": "<!doctype html>...",
  "status_code": 200,
  "collected_at": "2026-05-14T10:30:00.000Z"
}
```

**Cache Miss — `202 Accepted`:**
```json
{
  "message": "Metadata not found in inventory. A background collection has been initiated. Please retry shortly.",
  "url": "https://example.com"
}
```

> On a cache miss, a background task is automatically triggered. Subsequent `GET` requests for the same URL will return the full metadata once collection completes (typically within seconds).

---

### `GET /health`

Deep health check verifying API and database connectivity.

```json
{
  "status": "healthy",
  "service": "http-metadata-inventory",
  "database": "connected",
  "pending_background_tasks": 0
}
```

---

## Background Worker Design

The background collection system satisfies the architectural constraints specified in the challenge:

| Constraint | Implementation |
|-----------|----------------|
| **No self-HTTP calls** | Uses `asyncio.create_task()` — runs on the same event loop |
| **No external workers** | No Celery, Redis, or message queues needed |
| **Non-blocking** | API returns `202 Accepted` immediately; collection runs independently |
| **Deduplication** | In-memory `set` tracks in-flight URLs to prevent concurrent duplicate fetches |
| **Result persistence** | Data is upserted into MongoDB; available for all subsequent `GET` requests |
| **Error isolation** | Failures are logged but never crash the application |

---

## Configuration

All settings use sensible defaults and can be overridden via environment variables:

| Variable | Default | Description |
|----------|---------|-------------|
| `MONGO_URI` | `mongodb://mongodb:27017` | MongoDB connection string |
| `MONGO_DB` | `metadata_inventory` | Database name |
| `REQUEST_TIMEOUT` | `15` | HTTP request timeout (seconds) |
| `MAX_CONNECTIONS` | `20` | HTTP client connection pool limit |
| `APP_ENV` | `production` | Application environment |
| `LOG_LEVEL` | `info` | Logging level (`debug`, `info`, `warning`, `error`) |

---

## Testing

### Run All Tests

```bash
# Inside Docker (recommended — includes MongoDB)
make test

# Or directly:
docker compose run --rm api python -m pytest tests/ -v
```

### Test Structure

```
tests/
├── conftest.py           # Fixtures: isolated test DB, patched app client
├── test_api.py           # 10 integration tests — full request lifecycle
├── test_collector.py     #  5 unit tests — HTTP fetching & error handling
├── test_repository.py    #  7 unit tests — MongoDB CRUD & index behaviour
└── test_background.py    #  6 unit tests — task scheduling & deduplication
                          # ─────────────────────────────────────────────
                          # 28 tests total
```

| Category | Tests | What It Covers |
|----------|-------|---------------|
| **API Integration** | 10 | POST success/failure, GET cache hit/miss, POST→GET lifecycle, validation errors |
| **Collector** | 5 | Successful fetch, no cookies, timeout, connection error, redirect loops |
| **Repository** | 7 | Insert, find, upsert (create & update), delete, index idempotency |
| **Background Worker** | 6 | Scheduling, deduplication, success persistence, failure cleanup |

---

## Project Structure

```
http-metadata-service/
├── docker-compose.yml          # API + MongoDB orchestration
├── Dockerfile                  # Multi-stage build (builder → runtime)
├── Makefile                    # Developer convenience commands
├── .dockerignore               # Optimised Docker build context
├── requirements.txt            # Pinned Python dependencies
├── pyproject.toml              # Pytest configuration
├── .env.example                # Environment variable documentation
├── .gitignore
├── README.md
├── app/
│   ├── __init__.py
│   ├── main.py                 # FastAPI app, middleware, lifespan hooks
│   ├── config.py               # Pydantic Settings (env-based)
│   ├── database.py             # Motor client with connection retry/backoff
│   ├── models/
│   │   └── metadata.py         # 7 Pydantic models (request/response/internal)
│   ├── services/
│   │   ├── collector.py        # HTTP metadata collection via httpx
│   │   └── background.py       # Async background task orchestration
│   ├── repositories/
│   │   └── metadata_repo.py    # MongoDB CRUD with unique URL indexing
│   └── api/
│       └── routes.py           # POST & GET endpoint handlers
└── tests/
    ├── conftest.py              # Test fixtures & database isolation
    ├── test_api.py              # Integration tests
    ├── test_collector.py        # Collector unit tests
    ├── test_repository.py       # Repository unit tests
    └── test_background.py       # Background worker unit tests
```

---

## Design Decisions

| Decision | Rationale |
|----------|-----------|
| **Motor (async MongoDB driver)** | Matches FastAPI's async-first architecture for non-blocking I/O |
| **httpx over requests** | Native `async/await` support, connection pooling, and redirect handling |
| **`asyncio.create_task()` for background work** | Lightweight, no external dependencies — task runs on the same event loop |
| **In-flight deduplication via `set`** | Prevents redundant network requests on concurrent cache misses |
| **Repository pattern** | Isolates MongoDB logic behind a clean interface; easy to swap or extend |
| **API versioning (`/api/v1/`)** | Forward-compatible; new versions don't break existing consumers |
| **Multi-stage Docker build** | Final image excludes build tools (~60% smaller) |
| **Non-root container user** | Security best practice for production deployments |
| **Connection retry with backoff** | Handles Docker Compose startup race conditions gracefully |
| **Request ID middleware** | Enables end-to-end request tracing across services |
| **Deep health check** | Verifies actual MongoDB connectivity, not just API liveness |
| **Unique index on URL** | Guarantees fast O(log n) lookups as dataset grows |
| **Upsert for writes** | Idempotent operations — safe for retries and concurrent access |

---

## License

This project was created as part of a hiring challenge.
