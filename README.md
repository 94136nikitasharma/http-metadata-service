# HTTP Metadata Inventory Service

A RESTful service that collects, stores, and retrieves HTTP metadata (headers, cookies, page source) for any given URL. Built with FastAPI, MongoDB, and Docker Compose.

## Features

- **POST** a URL → immediately fetches and stores its metadata
- **GET** a URL → returns cached metadata, or triggers a background fetch on cache miss (202 Accepted)
- Async background worker using `asyncio.create_task()` — no external workers needed
- In-flight URL deduplication to prevent redundant fetches
- MongoDB retry with backoff for container startup resilience
- Request tracing via `X-Request-ID` header
- Deep health check that actually pings MongoDB
- Interactive API docs at `/docs` (Swagger UI)

---

## Quick Start

```bash
git clone https://github.com/94136nikitasharma/http-metadata-service.git
cd http-metadata-service
docker compose up --build
```

That's it. API is at **http://localhost:8000**, docs at **http://localhost:8000/docs**.

No `.env` file needed — defaults are baked into `docker-compose.yml`.

### Makefile shortcuts

```bash
make up          # start services
make test        # run all 28 tests
make logs        # tail logs
make down        # stop & cleanup
```

---

## Architecture

```
┌──────────────────────────────────────────────────────┐
│                   FastAPI Application                 │
│                                                      │
│  Routes (API) ──▸ Services (Business) ──▸ Repository │
│       │               │                     (Data)   │
│       │          Background Worker ─────────────┘    │
│       │                                              │
│  Middleware (Request ID, CORS)                       │
└───────┼──────────────────────────────────────────────┘
        │                                    │
    HTTP Clients                         MongoDB
```

| Layer | File | What it does |
|-------|------|-------------|
| Transport | `app/api/routes.py` | Input validation, HTTP response mapping |
| Business | `app/services/collector.py` | Fetches metadata via httpx |
| Orchestration | `app/services/background.py` | Async task scheduling + dedup |
| Data | `app/repositories/metadata_repo.py` | MongoDB CRUD with unique index |
| Config | `app/config.py` | Env-based settings (pydantic-settings) |
| Infra | `app/database.py` | Connection pool with retry/backoff |

---

## API

### POST /api/v1/metadata

Collect and store metadata for a URL.

```bash
curl -X POST http://localhost:8000/api/v1/metadata \
  -H "Content-Type: application/json" \
  -d '{"url": "https://example.com"}'
```

**201 Created:**
```json
{
  "message": "Metadata collected and stored successfully.",
  "url": "https://example.com/",
  "collected_at": "2026-05-14T10:30:00.000Z"
}
```

### GET /api/v1/metadata?url=...

Look up stored metadata.

**200 OK** (cache hit) — returns headers, cookies, page source, status code.

**202 Accepted** (cache miss) — background fetch triggered, retry in a few seconds:
```json
{
  "message": "Metadata not found in inventory. A background collection has been initiated. Please retry shortly.",
  "url": "https://example.com"
}
```

### GET /health

```json
{
  "status": "healthy",
  "service": "http-metadata-inventory",
  "database": "connected",
  "pending_background_tasks": 0
}
```

---

## Background Worker

How the cache-miss flow works:

1. GET request comes in for a URL not in the database
2. API immediately returns **202 Accepted**
3. `asyncio.create_task()` kicks off a fetch in the background
4. Metadata gets fetched and stored in MongoDB
5. Next GET for the same URL returns **200** with full data

Key constraints satisfied:
- No self-HTTP calls or external workers (Celery/Redis)
- Runs on the same event loop as FastAPI
- In-flight `set` prevents duplicate fetches for the same URL
- Errors are logged, never propagated (response already sent)

---

## Testing

```bash
# all tests (requires Docker)
make test

# or directly
docker compose run --rm api python -m pytest tests/ -v
```

**28 tests total:**

| File | Count | Coverage |
|------|-------|----------|
| `test_api.py` | 10 | Full request lifecycle, validation, POST→GET flow |
| `test_collector.py` | 5 | HTTP fetching, timeouts, connection errors |
| `test_repository.py` | 7 | CRUD, upsert, index behaviour |
| `test_background.py` | 6 | Task scheduling, dedup, error cleanup |

---

## Configuration

All configurable via environment variables (with sensible defaults):

| Variable | Default | Description |
|----------|---------|-------------|
| `MONGO_URI` | `mongodb://mongodb:27017` | MongoDB connection string |
| `MONGO_DB` | `metadata_inventory` | Database name |
| `REQUEST_TIMEOUT` | `15` | HTTP timeout (seconds) |
| `LOG_LEVEL` | `info` | Log verbosity |

---

## Project Structure

```
├── docker-compose.yml      # API + MongoDB
├── Dockerfile              # Multi-stage build
├── Makefile                # Dev shortcuts
├── requirements.txt        # Pinned deps
├── app/
│   ├── main.py             # App setup, middleware, health check
│   ├── config.py           # Settings from env vars
│   ├── database.py         # MongoDB connection with retry
│   ├── models/metadata.py  # Pydantic request/response models
│   ├── services/
│   │   ├── collector.py    # HTTP metadata extraction
│   │   └── background.py   # Async background tasks
│   ├── repositories/
│   │   └── metadata_repo.py  # MongoDB operations
│   └── api/routes.py       # POST & GET endpoints
└── tests/                  # 28 pytest tests
```

## Design Notes

- **Motor** (async MongoDB driver) to match FastAPI's async model
- **httpx** over requests for native async support
- **Repository pattern** isolates DB logic — easy to swap storage later
- **Upsert** for writes — idempotent, safe for retries
- **Unique index** on URL for fast O(log n) lookups
- **Multi-stage Docker build** — smaller final image, no build tools
- **Non-root container user** — security best practice
