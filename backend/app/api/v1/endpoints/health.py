"""System health and diagnostic endpoints."""

from datetime import datetime, timezone
from typing import Dict
from fastapi import APIRouter
from pydantic import BaseModel, Field

from app.core.config import settings

router = APIRouter()


class HealthResponse(BaseModel):
    """Schema for health status response."""

    status: str = Field(
        ...,
        description="Overall health status",
        json_schema_extra={"example": "healthy"},
    )
    app_name: str = Field(..., description="Application name")
    version: str = Field(..., description="Application version")
    environment: str = Field(..., description="Runtime environment")
    timestamp: str = Field(..., description="UTC ISO8601 timestamp")
    services: Dict[str, str] = Field(
        ...,
        description="Individual service operational states",
        json_schema_extra={"example": {"api": "operational"}},
    )


@router.get("/health", response_model=HealthResponse, tags=["Diagnostics"])
async def get_health() -> HealthResponse:
    """Return health and status diagnostics for the platform backend."""
    return HealthResponse(
        status="healthy",
        app_name=settings.APP_NAME,
        version=settings.APP_VERSION,
        environment=settings.ENVIRONMENT,
        timestamp=datetime.now(timezone.utc).isoformat(),
        services={
            "api": "operational",
            "metadata_store": "operational (SQLAlchemy 2.0)",
            "background_worker": "pending_phase_6",
        },
    )
