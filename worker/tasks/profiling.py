"""Celery task for asynchronous statistical profiling of datasets."""

import asyncio
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Optional

from sqlalchemy import select

from app.db.session import get_async_session
from app.models.dataset import Dataset
from app.models.job_task import JobTask
from app.services.profiling.profiler import profile_dataset_file

from worker.async_runner import run_coroutine_sync
from worker.celery_app import celery_app




async def _async_run_profiling_job(
    job_task_id: str,
    dataset_id: str,
    workspace_id: str,
    user_id: Optional[str] = None,
) -> None:
    """Async execution coroutine running inside the worker."""
    async for db in get_async_session():
        # Fetch JobTask record
        q = select(JobTask).where(JobTask.id == job_task_id)
        res = await db.execute(q)
        job = res.scalar_one_or_none()
        if not job:
            return

        # Check if cancelled before starting
        if job.status == "cancelled":
            return

        job.status = "running"
        job.progress_pct = 20
        job.message = "Locating dataset and storage files"
        job.started_at = datetime.now(timezone.utc)
        await db.commit()

        # Fetch dataset
        d_query = select(Dataset).where(
            Dataset.id == dataset_id,
            Dataset.workspace_id == workspace_id,
        )
        d_res = await db.execute(d_query)
        dataset = d_res.scalar_one_or_none()
        if not dataset:
            job.status = "failed"
            job.progress_pct = 100
            job.message = f"Dataset '{dataset_id}' not found in workspace."
            job.error_message = job.message
            job.completed_at = datetime.now(timezone.utc)
            await db.commit()
            return

        try:
            job.progress_pct = 50
            job.message = f"Computing statistical metrics and correlations for '{dataset.name}'"
            await db.commit()

            file_path = Path(dataset.storage_path)
            profile = profile_dataset_file(
                file_path=file_path,
                format_type=dataset.format,
                dataset_id=dataset.id,
                dataset_name=dataset.name,
            )

            job.progress_pct = 85
            job.message = "Persisting profile telemetry"
            await db.commit()

            # Finish job
            job.status = "completed"
            job.progress_pct = 100
            job.completed_at = datetime.now(timezone.utc)
            if job.started_at:
                delta_ms = int((job.completed_at - job.started_at).total_seconds() * 1000)
                job.execution_time_ms = max(delta_ms, 1)

            job.result_payload = profile.model_dump_json()
            job.message = (
                f"Dataset '{dataset.name}' profiled successfully "
                f"({profile.row_count} rows, {profile.column_count} columns)"
            )
            await db.commit()

        except Exception as exc:
            job.status = "failed"
            job.progress_pct = 100
            job.message = f"Profiling failed: {str(exc)}"
            job.error_message = str(exc)
            job.completed_at = datetime.now(timezone.utc)
            await db.commit()
        break


@celery_app.task(bind=True, max_retries=3)
def execute_profiling_task(
    self,
    job_task_id: str,
    dataset_id: str,
    workspace_id: str,
    user_id: Optional[str] = None,
) -> None:
    """Celery background worker entrypoint for dataset statistical profiling."""
    run_coroutine_sync(
        _async_run_profiling_job(
            job_task_id=job_task_id,
            dataset_id=dataset_id,
            workspace_id=workspace_id,
            user_id=user_id,
        )
    )

