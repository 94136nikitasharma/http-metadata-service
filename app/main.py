"""
FastAPI application entry point.
Sets up the app, middleware, lifecycle hooks, and routes.
"""

import logging
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse

from app.api.routes import router as metadata_router
from app.config import settings
from app.database import close_mongo_connection, connect_to_mongo, get_database
from app.repositories.metadata_repo import MetadataRepository
from app.services.background import get_pending_count

logging.basicConfig(
    level=getattr(logging, settings.log_level.upper(), logging.INFO),
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup: connect to MongoDB + ensure indexes. Shutdown: close connection."""
    logger.info("Starting HTTP Metadata Inventory Service...")
    await connect_to_mongo()

    repo = MetadataRepository(get_database())
    await repo.ensure_indexes()

    yield

    pending = get_pending_count()
    if pending > 0:
        logger.warning("Shutting down with %d background task(s) in-flight.", pending)
    logger.info("Shutting down...")
    await close_mongo_connection()


app = FastAPI(
    title="HTTP Metadata Inventory Service",
    description=(
        "Collects and stores HTTP metadata (headers, cookies, page source) "
        "for any given URL. Supports sync collection via POST and "
        "inventory lookups via GET with background fetching on cache misses."
    ),
    version="1.0.0",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)

# CORS — wide open for dev, tighten for prod
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def request_id_middleware(request: Request, call_next):
    """Attach a unique request ID for tracing/debugging."""
    request_id = request.headers.get("X-Request-ID", str(uuid.uuid4()))
    request.state.request_id = request_id
    response = await call_next(request)
    response.headers["X-Request-ID"] = request_id
    return response


app.include_router(metadata_router)


@app.get("/", include_in_schema=False)
async def root_redirect():
    return RedirectResponse(url="/docs")


@app.get("/health", tags=["Infrastructure"], summary="Health check")
async def health_check():
    """
    Deep health check — pings MongoDB to verify actual connectivity,
    not just that the API process is alive.
    """
    try:
        db = get_database()
        await db.command("ping")
        db_status = "connected"
    except Exception:
        db_status = "disconnected"

    return {
        "status": "healthy" if db_status == "connected" else "degraded",
        "service": "http-metadata-inventory",
        "database": db_status,
        "pending_background_tasks": get_pending_count(),
    }
