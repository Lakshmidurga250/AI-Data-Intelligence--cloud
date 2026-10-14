"""Celery task for asynchronous visual ETL pipeline execution."""

import asyncio
from datetime import datetime, timezone
import json
from typing import Optional

from sqlalchemy import select

from app.db.session import get_async_session
from app.models.job_task import JobTask
from app.models.pipeline import Pipeline
from app.services.pipelines.engine import execute_pipeline
from worker.async_runner import run_coroutine_sync
from worker.celery_app import celery_app


async def _async_run_pipeline_job(

    job_task_id: str,
    pipeline_id: str,
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
        job.progress_pct = 15
        job.message = "Loading graph topology and validating DAG"
        job.started_at = datetime.now(timezone.utc)
        await db.commit()

        # Fetch pipeline
        p_query = select(Pipeline).where(
            Pipeline.id == pipeline_id,
            Pipeline.workspace_id == workspace_id,
        )
        p_res = await db.execute(p_query)
        pipeline = p_res.scalar_one_or_none()
        if not pipeline:
            job.status = "failed"
            job.progress_pct = 100
            job.message = f"Pipeline '{pipeline_id}' not found in workspace."
            job.error_message = job.message
            job.completed_at = datetime.now(timezone.utc)
            await db.commit()
            return

        try:
            job.progress_pct = 40
            job.message = "Executing multi-stage pipeline graph"
            await db.commit()

            run_response = await execute_pipeline(
                db=db,
                pipeline=pipeline,
                workspace_id=workspace_id,
                user_id=user_id,
            )

            # Refresh job state
            job.status = "completed" if run_response.status == "completed" else "failed"
            job.progress_pct = 100
            job.execution_time_ms = run_response.execution_time_ms
            job.result_payload = json.dumps(run_response.model_dump(), default=str)
            job.completed_at = datetime.now(timezone.utc)

            if run_response.status == "completed":
                job.message = f"Pipeline executed successfully in {run_response.execution_time_ms} ms"
            else:
                job.message = f"Pipeline execution failed: {run_response.error_message}"
                job.error_message = run_response.error_message

            await db.commit()

        except Exception as exc:
            job.status = "failed"
            job.progress_pct = 100
            job.message = f"Execution error: {str(exc)}"
            job.error_message = str(exc)
            job.completed_at = datetime.now(timezone.utc)
            await db.commit()
        break


@celery_app.task(bind=True, max_retries=3)
def execute_pipeline_task(
    self,
    job_task_id: str,
    pipeline_id: str,
    workspace_id: str,
    user_id: Optional[str] = None,
) -> None:
    """Celery background worker entrypoint for pipeline DAG execution."""
    run_coroutine_sync(
        _async_run_pipeline_job(
            job_task_id=job_task_id,
            pipeline_id=pipeline_id,
            workspace_id=workspace_id,
            user_id=user_id,
        )
    )

