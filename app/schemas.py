"""Pydantic schemas and request/response models."""

from pydantic import BaseModel, Field


class HealthResponse(BaseModel):
    """Health check response."""
    status: str = "ok"
    models_loaded: bool = False
    version: str = "0.1.0"


class ErrorDetail(BaseModel):
    """Structured error detail model."""
    code: str
    message: str


class ErrorResponse(BaseModel):
    """Standard structured error response model."""
    error: ErrorDetail
