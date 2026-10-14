"""Aggregated API router for v1 endpoints."""

from fastapi import APIRouter
from app.api.v1.endpoints import (
    assistant,
    auth,
    datasets,
    dashboards,
    governance,
    health,
    jobs,
    lineage,
    ml,
    pipelines,
    quality,
    schedules,
    transforms,
    workspaces,
)

api_router = APIRouter()
api_router.include_router(health.router)
api_router.include_router(auth.router)
api_router.include_router(workspaces.router)
api_router.include_router(datasets.router)
api_router.include_router(transforms.router)
api_router.include_router(pipelines.router, prefix="/pipelines", tags=["pipelines"])
api_router.include_router(jobs.router, prefix="/jobs", tags=["jobs"])
api_router.include_router(schedules.router, prefix="/schedules", tags=["schedules"])
api_router.include_router(quality.router, prefix="/quality", tags=["quality"])
api_router.include_router(lineage.router, prefix="/lineage", tags=["lineage"])
api_router.include_router(governance.router, prefix="/governance", tags=["governance"])
api_router.include_router(ml.router, prefix="/ml", tags=["ml"])
api_router.include_router(dashboards.router, prefix="/dashboards", tags=["dashboards"])
api_router.include_router(assistant.router, prefix="/assistant", tags=["assistant"])




