"""AspectLens main FastAPI application module."""

from contextlib import asynccontextmanager
from typing import AsyncGenerator
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pathlib import Path

from app.config import settings
from app.schemas import HealthResponse, ErrorResponse, ErrorDetail


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Lifespan context manager to handle startup and shutdown logic.
    Models will be loaded once here in subsequent phases and stored in app.state.
    """
    # Phase 1: Models not loaded yet
    app.state.models_loaded = False
    app.state.models = {}

    yield

    # Clean up resources on shutdown
    app.state.models.clear()
    app.state.models_loaded = False


app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description="Aspect-based review mining system (AspectLens)",
    lifespan=lifespan,
)


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Ensure all unhandled exceptions return a clean structured JSON error without stack traces."""
    error_payload = ErrorResponse(
        error=ErrorDetail(
            code="INTERNAL_SERVER_ERROR",
            message="An unexpected error occurred while processing the request."
        )
    )
    return JSONResponse(status_code=500, content=error_payload.model_dump())


@app.get("/health", response_model=HealthResponse, tags=["System"])
async def health_check() -> HealthResponse:
    """System health check endpoint reporting service status and model readiness."""
    return HealthResponse(
        status="ok",
        models_loaded=getattr(app.state, "models_loaded", False),
        version=settings.APP_VERSION,
    )


# Mount static frontend directory if present
frontend_dir = Path(__file__).resolve().parent.parent / "frontend"
if frontend_dir.exists():
    app.mount("/static", StaticFiles(directory=str(frontend_dir)), name="static")
