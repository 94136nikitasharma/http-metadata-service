"""
HTTP Metadata Inventory Service — Application Entry Point.

This module creates the FastAPI application, configures logging,
and registers lifecycle hooks (database connection) and API routes.
"""

import logging
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, RedirectResponse

from app.api.routes import router as metadata_router
from app.config import settings
from app.database import close_mongo_connection, connect_to_mongo, get_database
from app.repositories.metadata_repo import MetadataRepository
from app.services.background import get_pending_count

# ──────────────────────────── Logging ───────────────────────────────────

logging.basicConfig(
    level=getattr(logging, settings.log_level.upper(), logging.INFO),
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)

logger = logging.getLogger(__name__)


# ──────────────────────────── Lifespan ──────────────────────────────────


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Manage application startup and shutdown.

    On startup:
      - Connect to MongoDB (with retry/backoff)
      - Ensure required indexes exist

    On shutdown:
      - Close MongoDB connection pool
    """
    # Startup
    logger.info("Starting HTTP Metadata Inventory Service …")
    await connect_to_mongo()

    # Ensure indexes after connection is established
    repo = MetadataRepository(get_database())
    await repo.ensure_indexes()

    yield

    # Shutdown — log any pending background tasks
    pending = get_pending_count()
    if pending > 0:
        logger.warning(
            "Shutting down with %d background task(s) still in-flight.",
            pending,
        )
    logger.info("Shutting down …")
    await close_mongo_connection()


# ──────────────────────────── App Factory ───────────────────────────────

app = FastAPI(
    title="HTTP Metadata Inventory Service",
    description=(
        "A service that collects and stores HTTP metadata "
        "(headers, cookies, page source) for any given URL.  "
        "Supports synchronous collection via POST and inventory "
        "lookups via GET with automatic background fetching on "
        "cache misses."
    ),
    version="1.0.0",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)


# ──────────────────────── Middleware ────────────────────────────────────

# CORS — permissive for development; tighten in production
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def request_id_middleware(request: Request, call_next):
    """
    Attach a unique request ID to every incoming request.

    This ID is included in the response headers (X-Request-ID) for
    traceability and debugging in distributed environments.
    """
    request_id = request.headers.get("X-Request-ID", str(uuid.uuid4()))
    request.state.request_id = request_id

    response = await call_next(request)
    response.headers["X-Request-ID"] = request_id
    return response


# Register routes
app.include_router(metadata_router)


# ──────────────────────── Root Redirect ─────────────────────────────────


@app.get(
    "/",
    include_in_schema=False,
)
async def root_redirect():
    """Redirect the root URL to the interactive API documentation."""
    return RedirectResponse(url="/docs")


# ──────────────────────────── Health Check ──────────────────────────────


@app.get(
    "/health",
    tags=["Infrastructure"],
    summary="Service health check",
    description=(
        "Performs a deep health check by pinging the MongoDB server. "
        "Returns the service status and database connectivity state."
    ),
)
async def health_check():
    """
    Deep health check that verifies both the API and database
    are operational.  Used by Docker HEALTHCHECK and load balancers.
    """
    try:
        db = get_database()
        # Actually ping MongoDB to verify connectivity
        await db.command("ping")
        db_status = "connected"
    except Exception:
        db_status = "disconnected"

    status = "healthy" if db_status == "connected" else "degraded"
    pending_tasks = get_pending_count()

    return {
        "status": status,
        "service": "http-metadata-inventory",
        "database": db_status,
        "pending_background_tasks": pending_tasks,
    }
