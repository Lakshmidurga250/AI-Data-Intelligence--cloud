"""Background job dispatching, lifecycle management, and worker telemetry service."""

from datetime import datetime, timezone
import json
from typing import Any, Dict, List, Optional
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.dataset import Dataset
from app.models.job_task import JobTask
from app.models.pipeline import Pipeline
from app.schemas.job import WorkerDiagnosticsResponse
from app.services.audit_service import log_audit
from worker.celery_app import celery_app
from worker.tasks.ingestion import execute_ingestion_task
from worker.tasks.pipeline import execute_pipeline_task
from worker.tasks.profiling import execute_profiling_task


async def create_and_dispatch_job(
    db: AsyncSession,
    workspace_id: str,
    task_type: str,
    parameters: Optional[Dict[str, Any]] = None,
    resource_id: Optional[str] = None,
    user_id: Optional[str] = None,
) -> JobTask:
    """
    Persist new background job task record and dispatch to Celery worker queue.
    """
    params = parameters or {}

    # Validate target resources
    if task_type in ("pipeline_run", "scheduled_job"):
        if not resource_id:
            raise ValueError("resource_id (pipeline_id) is required for pipeline execution jobs")
        p_res = await db.execute(
            select(Pipeline).where(
                Pipeline.id == resource_id,
                Pipeline.workspace_id == workspace_id,
            )
        )
        if not p_res.scalar_one_or_none():
            raise ValueError(f"Pipeline '{resource_id}' does not exist in this workspace.")

    elif task_type in ("dataset_profile", "dataset_ingest"):
        if not resource_id:
            raise ValueError("resource_id (dataset_id) is required for dataset tasks")
        d_res = await db.execute(
            select(Dataset).where(
                Dataset.id == resource_id,
                Dataset.workspace_id == workspace_id,
            )
        )
        if not d_res.scalar_one_or_none():
            raise ValueError(f"Dataset '{resource_id}' does not exist in this workspace.")

    import uuid
    celery_task_id = str(uuid.uuid4())

    # Create JobTask entity
    job = JobTask(
        workspace_id=workspace_id,
        task_type=task_type,
        celery_task_id=celery_task_id,
        status="pending",
        progress_pct=0,
        message="Queued for worker execution",
        resource_id=resource_id,
        parameters=json.dumps(params),
        result_payload="{}",
        triggered_by_user_id=user_id,
    )
    db.add(job)
    await db.commit()
    await db.refresh(job)

    # Dispatch to Celery worker queue
    try:
        if task_type in ("pipeline_run", "scheduled_job"):
            execute_pipeline_task.apply_async(
                kwargs={
                    "job_task_id": job.id,
                    "pipeline_id": resource_id,
                    "workspace_id": workspace_id,
                    "user_id": user_id,
                },
                task_id=celery_task_id,
            )
        elif task_type == "dataset_profile":
            execute_profiling_task.apply_async(
                kwargs={
                    "job_task_id": job.id,
                    "dataset_id": resource_id,
                    "workspace_id": workspace_id,
                    "user_id": user_id,
                },
                task_id=celery_task_id,
            )
        elif task_type == "dataset_ingest":
            execute_ingestion_task.apply_async(
                kwargs={
                    "job_task_id": job.id,
                    "dataset_id": resource_id,
                    "workspace_id": workspace_id,
                    "user_id": user_id,
                },
                task_id=celery_task_id,
            )
        else:
            raise ValueError(f"Unsupported task type: {task_type}")

        # In eager execution mode or completed runs, reload fresh DB record
        await db.refresh(job)


    except Exception as exc:
        job.status = "failed"
        job.message = f"Worker dispatch failure: {str(exc)}"
        job.error_message = str(exc)
        job.completed_at = datetime.now(timezone.utc)
        await db.commit()
        await db.refresh(job)


    await log_audit(
        db=db,
        action="job.dispatch",
        resource_type="job",
        resource_id=job.id,
        details={"task_type": task_type, "status": job.status},
        user_id=user_id,
        workspace_id=workspace_id,
    )

    return job


async def get_job(db: AsyncSession, job_id: str, workspace_id: str) -> Optional[JobTask]:
    """Retrieve background job by ID within workspace boundary."""
    q = select(JobTask).where(JobTask.id == job_id, JobTask.workspace_id == workspace_id)
    res = await db.execute(q)
    return res.scalar_one_or_none()


async def list_jobs(
    db: AsyncSession,
    workspace_id: str,
    task_type: Optional[str] = None,
    status: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
) -> List[JobTask]:
    """List jobs within a workspace filtered by status or type."""
    q = select(JobTask).where(JobTask.workspace_id == workspace_id)
    if task_type:
        q = q.where(JobTask.task_type == task_type)
    if status:
        q = q.where(JobTask.status == status)

    q = q.order_by(JobTask.created_at.desc()).limit(limit).offset(offset)
    res = await db.execute(q)
    return list(res.scalars().all())


async def cancel_job(
    db: AsyncSession,
    job_id: str,
    workspace_id: str,
    user_id: Optional[str] = None,
) -> JobTask:
    """Request graceful cancellation of a pending or running background job."""
    job = await get_job(db=db, job_id=job_id, workspace_id=workspace_id)
    if not job:
        raise ValueError(f"Job '{job_id}' not found in workspace.")

    if job.status in ("completed", "failed", "cancelled"):
        return job

    # Attempt Celery task revocation if Celery task ID exists
    if job.celery_task_id:
        try:
            celery_app.control.revoke(job.celery_task_id, terminate=True)
        except Exception:
            pass

    job.status = "cancelled"
    job.message = "Execution cancelled by user request"
    job.completed_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(job)

    await log_audit(
        db=db,
        action="job.cancelled",
        resource_type="job",
        resource_id=job.id,
        details={"status": job.status},
        user_id=user_id,
        workspace_id=workspace_id,
    )

    return job



async def get_worker_diagnostics(
    db: AsyncSession,
    workspace_id: str,
) -> WorkerDiagnosticsResponse:
    """Inspect real-time Celery worker status, queue sizes, and daily execution metrics."""
    now = datetime.now(timezone.utc)
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)

    # 1. Count active & queued tasks in this workspace
    q_pending = select(func.count(JobTask.id)).where(
        JobTask.workspace_id == workspace_id,
        JobTask.status == "pending",
    )
    res_pending = await db.execute(q_pending)
    queued_count = res_pending.scalar_one() or 0

    q_running = select(func.count(JobTask.id)).where(
        JobTask.workspace_id == workspace_id,
        JobTask.status == "running",
    )
    res_running = await db.execute(q_running)
    running_count = res_running.scalar_one() or 0

    q_completed = select(func.count(JobTask.id)).where(
        JobTask.workspace_id == workspace_id,
        JobTask.status == "completed",
        JobTask.completed_at >= today_start,
    )
    res_completed = await db.execute(q_completed)
    completed_today = res_completed.scalar_one() or 0

    q_failed = select(func.count(JobTask.id)).where(
        JobTask.workspace_id == workspace_id,
        JobTask.status == "failed",
        JobTask.completed_at >= today_start,
    )
    res_failed = await db.execute(q_failed)
    failed_today = res_failed.scalar_one() or 0

    # 2. Worker health ping
    is_eager = getattr(celery_app.conf, "task_always_eager", False)
    active_workers = 1 if is_eager else 0

    if not is_eager:
        try:
            inspect = celery_app.control.inspect(timeout=1.0)
            ping_res = inspect.ping() if inspect else None
            if ping_res:
                active_workers = len(ping_res)
        except Exception:
            active_workers = 0

    status_str: str = "operational" if (is_eager or active_workers > 0) else "degraded"

    return WorkerDiagnosticsResponse(
        status=status_str,  # type: ignore
        broker_type="redis",
        broker_url=settings.REDIS_URL,
        active_worker_count=max(active_workers, 1 if is_eager else 0),
        queued_task_count=queued_count,
        running_task_count=running_count,
        completed_today_count=completed_today,
        failed_today_count=failed_today,
        timestamp=now,
    )
