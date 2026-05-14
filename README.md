# HTTP Metadata Inventory Service

A high-performance RESTful service that collects, stores, and retrieves HTTP metadata (headers, cookies, page source) for any given URL. Built with **FastAPI**, **MongoDB**, and **Docker Compose**.

## Features

- **Synchronous Collection** — `POST` a URL to immediately fetch and store its metadata
- **Inventory Lookup** — `GET` stored metadata with automatic background fetching on cache misses
- **Asynchronous Background Worker** — Non-blocking metadata collection using `asyncio` tasks
- **Request Deduplication** — In-flight tracking prevents duplicate background fetches
- **Auto-generated API Documentation** — Interactive Swagger UI at `/docs`
- **Comprehensive Test Suite** — Unit and integration tests with `pytest`
- **One-command Setup** — `docker-compose up` starts everything

---

## Architecture

```
┌──────────────────────────────────────────────────────┐
│                   FastAPI Application                │
│                                                      │
│  ┌──────────┐    ┌──────────────┐    ┌────────────┐  │
│  │  Routes   │───▸│   Services   │───▸│ Repository │  │
│  │ (API)     │    │  (Business)  │    │  (Data)    │  │
│  └──────────┘    └──────────────┘    └─────┬──────┘  │
│       │               │                    │         │
│       │          ┌────┴─────┐              │         │
│       │          │Background│              │         │
│       │          │ Worker   │──────────────┘         │
│       │          └──────────┘                        │
└───────┼──────────────────────────────────────────────┘
        │                                    │
    HTTP Clients                         MongoDB
```

**Layers:**

| Layer | Responsibility | Key Files |
|-------|---------------|-----------|
| **API** | Request parsing, validation, HTTP response mapping | `app/api/routes.py` |
| **Services** | HTTP metadata collection, background task orchestration | `app/services/collector.py`, `app/services/background.py` |
| **Repository** | MongoDB CRUD, index management | `app/repositories/metadata_repo.py` |
| **Models** | Pydantic schemas for validation and serialisation | `app/models/metadata.py` |
| **Config** | Environment-based settings | `app/config.py` |

---

## Quick Start

### Prerequisites

- [Docker](https://docs.docker.com/get-docker/) and [Docker Compose](https://docs.docker.com/compose/install/)

### Run the Service

```bash
# Clone the repository
git clone <repository-url>
cd http-metadata-service

# Start both the API and MongoDB
docker-compose up --build
```

The API will be available at **http://localhost:8000**.

### Interactive API Documentation

- **Swagger UI**: http://localhost:8000/docs
- **ReDoc**: http://localhost:8000/redoc

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

**Response (201 Created):**
```json
{
  "message": "Metadata collected and stored successfully.",
  "url": "https://example.com/",
  "collected_at": "2025-01-15T10:30:00.000Z"
}
```

**Error (400 Bad Request):**
```json
{
  "detail": "Request timed out for URL: https://unreachable-site.com"
}
```

---

### `GET /api/v1/metadata?url=<URL>`

Retrieve stored metadata for a URL.

**If found — Response (200 OK):**
```json
{
  "url": "https://example.com",
  "headers": {
    "content-type": "text/html; charset=UTF-8",
    "server": "ECAcc (sed/58EA)"
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
  "collected_at": "2025-01-15T10:30:00.000Z"
}
```

**If not found — Response (202 Accepted):**
```json
{
  "message": "Metadata not found in inventory. A background collection has been initiated. Please retry shortly.",
  "url": "https://example.com"
}
```

A background task is automatically triggered to collect and store the metadata. Subsequent `GET` requests for the same URL will return the full dataset once collection completes.

---

### `GET /health`

Health check for container orchestration.

**Response (200 OK):**
```json
{
  "status": "healthy",
  "service": "http-metadata-inventory"
}
```

---

## Configuration

All settings are managed via environment variables (see `.env.example`):

| Variable | Default | Description |
|----------|---------|-------------|
| `MONGO_URI` | `mongodb://mongodb:27017` | MongoDB connection string |
| `MONGO_DB` | `metadata_inventory` | Database name |
| `REQUEST_TIMEOUT` | `15` | HTTP request timeout (seconds) |
| `MAX_CONNECTIONS` | `20` | HTTP connection pool limit |
| `APP_ENV` | `development` | Application environment |
| `LOG_LEVEL` | `info` | Logging level |

---

## Testing

### Run Tests with Docker (Recommended)

The test suite requires a running MongoDB instance. The easiest way is to start MongoDB via Docker Compose and run tests inside the container:

```bash
# Start MongoDB
docker-compose up -d mongodb

# Run tests in a separate container
docker-compose run --rm api python -m pytest tests/ -v
```

### Run Tests Locally

If you have MongoDB running locally:

```bash
# Create a virtual environment
python3 -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Set MongoDB URI for local instance
export MONGO_URI=mongodb://localhost:27017

# Run the test suite
pytest tests/ -v
```

### Test Coverage

| Test File | What It Covers |
|-----------|---------------|
| `test_api.py` | Integration tests — full request lifecycle, endpoint behaviour, error responses |
| `test_collector.py` | Unit tests — HTTP fetching, parsing, timeout/connection error handling |
| `test_repository.py` | Unit tests — MongoDB CRUD, upsert, index behaviour |
| `test_background.py` | Unit tests — Task scheduling, deduplication, error cleanup |

---

## Project Structure

```
http-metadata-service/
├── docker-compose.yml          # API + MongoDB orchestration
├── Dockerfile                  # Multi-stage build (builder → runtime)
├── requirements.txt            # Python dependencies
├── pyproject.toml              # Pytest configuration
├── .env.example                # Environment variable template
├── .gitignore
├── README.md
├── app/
│   ├── __init__.py
│   ├── main.py                 # FastAPI app, lifespan, CORS
│   ├── config.py               # Pydantic Settings
│   ├── database.py             # Motor async MongoDB client
│   ├── models/
│   │   ├── __init__.py
│   │   └── metadata.py         # Request/response Pydantic models
│   ├── services/
│   │   ├── __init__.py
│   │   ├── collector.py        # HTTP metadata collection (httpx)
│   │   └── background.py       # Async background task orchestration
│   ├── repositories/
│   │   ├── __init__.py
│   │   └── metadata_repo.py    # MongoDB CRUD operations
│   └── api/
│       ├── __init__.py
│       └── routes.py           # POST & GET endpoint handlers
└── tests/
    ├── __init__.py
    ├── conftest.py              # Fixtures, test DB setup
    ├── test_api.py              # Integration tests
    ├── test_collector.py        # Collector unit tests
    ├── test_repository.py       # Repository unit tests
    └── test_background.py       # Background worker unit tests
```

---

## Design Decisions

1. **Motor (async MongoDB driver)** — Matches FastAPI's async-first architecture for non-blocking I/O.

2. **httpx over requests** — Native `async/await` support, connection pooling, and modern API for collecting metadata.

3. **`asyncio.create_task()` for background work** — Lightweight, no external dependencies (Celery, Redis). The task runs on the same event loop, avoiding the complexity of distributed workers for this use case.

4. **In-flight URL deduplication** — An in-memory `set` tracks URLs currently being fetched in the background. This prevents redundant network requests when multiple `GET` calls hit the same cache miss concurrently.

5. **Repository pattern** — Isolates MongoDB-specific logic behind a clean interface, making it easy to swap databases or add caching layers in the future.

6. **API versioning (`/api/v1/`)** — Demonstrates forward-thinking design; new API versions can be introduced without breaking existing consumers.

7. **Multi-stage Docker build** — Keeps the final image small by excluding build tools and caches from the runtime layer.

8. **Non-root container user** — Security best practice for production container deployments.

---

## License

This project was created as part of a hiring challenge. All rights reserved.
