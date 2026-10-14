"""Celery task for asynchronous dataset ingestion and integrity verification."""

import asyncio
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Optional

from sqlalchemy import select

from app.db.session import get_async_session
from app.models.dataset import Dataset
from app.models.job_task import JobTask
from app.services.ingestion.parser import parse_and_profile_tabular_file
from worker.async_runner import run_coroutine_sync
from worker.celery_app import celery_app



async def _async_run_ingestion_job(
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
        job.progress_pct = 25
        job.message = "Verifying dataset storage access and integrity"
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
            job.progress_pct = 60
            job.message = f"Parsing and profiling storage file for '{dataset.name}'"
            await db.commit()

            file_path = Path(dataset.storage_path)
            format_type, row_count, column_count, columns, preview_rows = (
                parse_and_profile_tabular_file(
                    file_path=file_path,
                    filename=dataset.filename,
                    max_preview_rows=25,
                )
            )

            job.progress_pct = 90
            job.message = "Updating dataset metadata"
            dataset.row_count = row_count
            dataset.column_count = column_count
            await db.commit()

            # Finish job
            job.status = "completed"
            job.progress_pct = 100
            job.completed_at = datetime.now(timezone.utc)
            if job.started_at:
                delta_ms = int((job.completed_at - job.started_at).total_seconds() * 1000)
                job.execution_time_ms = max(delta_ms, 1)

            job.result_payload = json.dumps(
                {
                    "dataset_id": dataset.id,
                    "dataset_name": dataset.name,
                    "format": format_type,
                    "row_count": row_count,
                    "column_count": column_count,
                    "preview_rows_count": len(preview_rows),
                }
            )
            job.message = (
                f"Dataset '{dataset.name}' verified ({row_count} rows, {column_count} columns)"
            )
            await db.commit()

        except Exception as exc:
            job.status = "failed"
            job.progress_pct = 100
            job.message = f"Ingestion verification failed: {str(exc)}"
            job.error_message = str(exc)
            job.completed_at = datetime.now(timezone.utc)
            await db.commit()
        break


@celery_app.task(bind=True, max_retries=3)
def execute_ingestion_task(
    self,
    job_task_id: str,
    dataset_id: str,
    workspace_id: str,
    user_id: Optional[str] = None,
) -> None:
    """Celery background worker entrypoint for dataset ingestion and parsing."""
    run_coroutine_sync(
        _async_run_ingestion_job(
            job_task_id=job_task_id,
            dataset_id=dataset_id,
            workspace_id=workspace_id,
            user_id=user_id,
        )
    )

