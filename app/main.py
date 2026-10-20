"""AspectLens main FastAPI application module."""

from contextlib import asynccontextmanager
from typing import AsyncGenerator
import asyncio
import logging
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException
from slowapi.errors import RateLimitExceeded

from app.config import settings
from app.schemas import HealthResponse, ErrorResponse, ErrorDetail
from app.limiter import limiter
from app.api import router as api_router
from app.db import init_db
from nlp.aspects import get_spacy_model
from nlp.pipeline import get_aspect_grouper

logger = logging.getLogger(__name__)


# ----------------------------------------------------------------------
# Lifespan Context Manager (Startup / Shutdown)
# ----------------------------------------------------------------------
@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Lifespan context manager: loads models once at startup and stores on app.state."""
    logger.info("Starting up AspectLens service (version %s)...", settings.APP_VERSION)

    # 1. Concurrency guard: semaphore for heavy ML jobs (max 2 concurrent)
    app.state.heavy_job_semaphore = asyncio.Semaphore(2)

    # 2. Database initialization and demo data seeding
    try:
        init_db(seed_if_empty=True)
        logger.info("Database initialized and verified.")
    except Exception as e:
        logger.error("Failed to initialize database: %s", e)

    # 3. Pre-warm NLP models once at startup
    try:
        get_spacy_model()
        get_aspect_grouper()
        app.state.models_loaded = True
        logger.info("NLP models (spaCy, Seed Lexicon, SentenceTransformer) loaded successfully.")
    except Exception as e:
        logger.warning("Could not pre-warm all NLP models at startup: %s", e)
        app.state.models_loaded = False

    yield

    # Clean up resources on shutdown
    app.state.models_loaded = False
    logger.info("AspectLens service shutdown complete.")


# ----------------------------------------------------------------------
# Application Factory
# ----------------------------------------------------------------------
app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description="Aspect-based review mining system (AspectLens)",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url=None,
)

# Attach slowapi rate limiter to app state
app.state.limiter = limiter


# ----------------------------------------------------------------------
# Security & CORS Middleware
# ----------------------------------------------------------------------
@app.middleware("http")
async def security_headers_middleware(request: Request, call_next):
    """Enforce defense-in-depth HTTP security headers on all responses."""
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; "
        "script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; "
        "style-src 'self' 'unsafe-inline'; "
        "img-src 'self' data:; "
        "connect-src 'self';"
    )
    return response


app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)


# ----------------------------------------------------------------------
# Global Exception Handlers (Never leak stack traces)
# ----------------------------------------------------------------------
@app.exception_handler(RateLimitExceeded)
async def rate_limit_handler(request: Request, exc: RateLimitExceeded) -> JSONResponse:
    """Friendly 429 response on rate limit with Retry-After header."""
    retry_after = getattr(exc, "retry_after", 60)
    response = JSONResponse(
        status_code=429,
        content={
            "error": {
                "code": "RATE_LIMIT_EXCEEDED",
                "message": f"Rate limit exceeded: {exc.detail}. Please slow down.",
            }
        },
    )
    response.headers["Retry-After"] = str(retry_after)
    return response


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    """Format Pydantic schema validation errors into clean structured JSON."""
    messages = []
    for err in exc.errors():
        loc = " -> ".join(str(l) for l in err.get("loc", []))
        msg = err.get("msg", "Invalid value")
        messages.append(f"{loc}: {msg}")

    error_payload = ErrorResponse(
        error=ErrorDetail(
            code="VALIDATION_ERROR",
            message="; ".join(messages) if messages else "Invalid request parameters.",
        )
    )
    return JSONResponse(status_code=422, content=error_payload.model_dump())


@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request: Request, exc: StarletteHTTPException) -> JSONResponse:
    """Format HTTPException into standardized ErrorResponse shape."""
    code = "HTTP_ERROR"
    if exc.status_code == 400:
        code = "BAD_REQUEST"
    elif exc.status_code == 401:
        code = "UNAUTHORIZED"
    elif exc.status_code == 403:
        code = "FORBIDDEN"
    elif exc.status_code == 404:
        code = "NOT_FOUND"
    elif exc.status_code == 413:
        code = "PAYLOAD_TOO_LARGE"
    elif exc.status_code == 422:
        code = "UNPROCESSABLE_ENTITY"
    elif exc.status_code == 429:
        code = "RATE_LIMIT_EXCEEDED"

    # If detail is already formatted as dict with error code/message
    if isinstance(exc.detail, dict):
        if "code" in exc.detail and "message" in exc.detail:
            return JSONResponse(
                status_code=exc.status_code,
                content={"error": {"code": exc.detail["code"], "message": exc.detail["message"]}},
            )
        elif "error" in exc.detail:
            return JSONResponse(status_code=exc.status_code, content=exc.detail)

    error_payload = ErrorResponse(
        error=ErrorDetail(code=code, message=str(exc.detail))
    )
    return JSONResponse(status_code=exc.status_code, content=error_payload.model_dump())


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Ensure all unexpected errors return clean JSON without exposing stack traces."""
    logger.exception("Unhandled server exception: %s", exc)
    error_payload = ErrorResponse(
        error=ErrorDetail(
            code="INTERNAL_SERVER_ERROR",
            message="An unexpected error occurred while processing the request.",
        )
    )
    return JSONResponse(status_code=500, content=error_payload.model_dump())


# ----------------------------------------------------------------------
# Core API Routes
# ----------------------------------------------------------------------
@app.get("/health", response_model=HealthResponse, tags=["System"])
async def health_check() -> HealthResponse:
    """System health check endpoint reporting service status, version, and model readiness."""
    return HealthResponse(
        status="ok",
        models_loaded=getattr(app.state, "models_loaded", False),
        version=settings.APP_VERSION,
    )


# Include main API router
app.include_router(api_router)


# ----------------------------------------------------------------------
# Frontend Static Files Serving
# ----------------------------------------------------------------------
frontend_dir = Path(__file__).resolve().parent.parent / "frontend"
if frontend_dir.exists():
    # Dedicated root route serving index.html
    @app.get("/", include_in_schema=False)
    async def serve_root():
        index_file = frontend_dir / "index.html"
        if index_file.exists():
            return FileResponse(str(index_file))
        return JSONResponse(content={"message": "AspectLens API running"})

    # Static files mount
    app.mount("/static", StaticFiles(directory=str(frontend_dir)), name="static")
    app.mount("/", StaticFiles(directory=str(frontend_dir), html=True), name="frontend")
