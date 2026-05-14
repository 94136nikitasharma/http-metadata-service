"""
HTTP Metadata Inventory Service — Application Entry Point.

This module creates the FastAPI application, configures logging,
and registers lifecycle hooks (database connection) and API routes.
"""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse

from app.api.routes import router as metadata_router
from app.config import settings
from app.database import close_mongo_connection, connect_to_mongo, get_database
from app.repositories.metadata_repo import MetadataRepository

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
      - Connect to MongoDB
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

    # Shutdown
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

# CORS — permissive for development; tighten in production
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

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
)
async def health_check():
    """
    Returns a simple status indicator for load balancers and
    container orchestration tools.
    """
    return {"status": "healthy", "service": "http-metadata-inventory"}
