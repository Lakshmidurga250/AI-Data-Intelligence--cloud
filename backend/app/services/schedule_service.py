"""Recurring pipeline schedule configuration and evaluation service."""

from datetime import datetime, timezone
from typing import List, Optional
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.job_schedule import JobSchedule
from app.models.job_task import JobTask
from app.models.pipeline import Pipeline
from app.schemas.job import JobScheduleCreate, JobScheduleUpdate
from app.services.audit_service import log_audit
from app.services.job_service import create_and_dispatch_job
from worker.schedules.cron_parser import calculate_next_run, validate_cron_expression


async def create_schedule(
    db: AsyncSession,
    workspace_id: str,
    data: JobScheduleCreate,
    user_id: Optional[str] = None,
) -> JobSchedule:
    """Create and validate a new recurring pipeline schedule."""
    # 1. Verify target pipeline exists in workspace
    p_res = await db.execute(
        select(Pipeline).where(
            Pipeline.id == data.pipeline_id,
            Pipeline.workspace_id == workspace_id,
        )
    )
    pipeline = p_res.scalar_one_or_none()
    if not pipeline:
        raise ValueError(f"Pipeline '{data.pipeline_id}' not found in workspace.")

    # 2. Validate cron expression
    if not validate_cron_expression(data.cron_expression):
        raise ValueError(
            f"Invalid cron expression '{data.cron_expression}'. "
            "Use standard 5-part cron or presets: hourly, daily, weekly, every_15_mins, every_30_mins."
        )

    # 3. Calculate next occurrence
    next_run = calculate_next_run(data.cron_expression) if data.is_active else None

    schedule = JobSchedule(
        workspace_id=workspace_id,
        pipeline_id=data.pipeline_id,
        name=data.name.strip(),
        description=data.description,
        cron_expression=data.cron_expression.strip(),
        is_active=data.is_active,
        next_run_at=next_run,
        created_by_user_id=user_id,
    )
    db.add(schedule)
    await db.commit()
    await db.refresh(schedule)

    await log_audit(
        db=db,
        action="schedule.created",
        resource_type="schedule",
        resource_id=schedule.id,
        details={"name": schedule.name, "pipeline_id": schedule.pipeline_id},
        user_id=user_id,
        workspace_id=workspace_id,
    )


    return schedule


async def get_schedule(
    db: AsyncSession,
    schedule_id: str,
    workspace_id: str,
) -> Optional[JobSchedule]:
    """Retrieve schedule by ID within workspace boundaries."""
    q = select(JobSchedule).where(
        JobSchedule.id == schedule_id,
        JobSchedule.workspace_id == workspace_id,
    )
    res = await db.execute(q)
    return res.scalar_one_or_none()


async def list_schedules(
    db: AsyncSession,
    workspace_id: str,
    is_active: Optional[bool] = None,
) -> List[JobSchedule]:
    """List recurring schedules within a workspace."""
    q = select(JobSchedule).where(JobSchedule.workspace_id == workspace_id)
    if is_active is not None:
        q = q.where(JobSchedule.is_active == is_active)
    q = q.order_by(JobSchedule.created_at.desc())
    res = await db.execute(q)
    return list(res.scalars().all())


async def update_schedule(
    db: AsyncSession,
    schedule_id: str,
    workspace_id: str,
    data: JobScheduleUpdate,
    user_id: Optional[str] = None,
) -> JobSchedule:
    """Modify schedule active status, name, or cron frequency."""
    schedule = await get_schedule(db, schedule_id, workspace_id)
    if not schedule:
        raise ValueError(f"Schedule '{schedule_id}' not found in workspace.")

    if data.name is not None:
        schedule.name = data.name.strip()
    if data.description is not None:
        schedule.description = data.description

    if data.cron_expression is not None:
        if not validate_cron_expression(data.cron_expression):
            raise ValueError(f"Invalid cron expression: '{data.cron_expression}'")
        schedule.cron_expression = data.cron_expression.strip()
        if schedule.is_active:
            schedule.next_run_at = calculate_next_run(schedule.cron_expression)

    if data.is_active is not None:
        schedule.is_active = data.is_active
        if schedule.is_active:
            schedule.next_run_at = calculate_next_run(schedule.cron_expression)
        else:
            schedule.next_run_at = None

    await db.commit()
    await db.refresh(schedule)

    await log_audit(
        db=db,
        action="schedule.updated",
        resource_type="schedule",
        resource_id=schedule.id,
        details={"name": schedule.name, "is_active": schedule.is_active},
        user_id=user_id,
        workspace_id=workspace_id,
    )

    return schedule


async def delete_schedule(
    db: AsyncSession,
    schedule_id: str,
    workspace_id: str,
    user_id: Optional[str] = None,
) -> bool:
    """Delete recurring schedule."""
    schedule = await get_schedule(db, schedule_id, workspace_id)
    if not schedule:
        raise ValueError(f"Schedule '{schedule_id}' not found in workspace.")

    name = schedule.name
    await db.delete(schedule)
    await db.commit()

    await log_audit(
        db=db,
        action="schedule.deleted",
        resource_type="schedule",
        resource_id=schedule_id,
        details={"name": name},
        user_id=user_id,
        workspace_id=workspace_id,
    )


    return True


async def evaluate_and_trigger_schedules(
    db: AsyncSession,
    now: Optional[datetime] = None,
) -> List[JobTask]:
    """
    Periodic evaluator: Find all active schedules with next_run_at in the past or now,
    and dispatch them as background jobs.
    """
    current_time = now or datetime.now(timezone.utc)
    if current_time.tzinfo is None:
        current_time = current_time.replace(tzinfo=timezone.utc)

    q = select(JobSchedule).where(
        JobSchedule.is_active == True,
        JobSchedule.next_run_at <= current_time,
    )
    res = await db.execute(q)
    due_schedules = list(res.scalars().all())

    dispatched_jobs: List[JobTask] = []
    for schedule in due_schedules:
        try:
            job = await create_and_dispatch_job(
                db=db,
                workspace_id=schedule.workspace_id,
                task_type="scheduled_job",
                parameters={
                    "schedule_id": schedule.id,
                    "schedule_name": schedule.name,
                    "cron_expression": schedule.cron_expression,
                },
                resource_id=schedule.pipeline_id,
                user_id=schedule.created_by_user_id,
            )
            dispatched_jobs.append(job)

            # Advance next_run_at
            schedule.last_run_at = current_time
            schedule.next_run_at = calculate_next_run(schedule.cron_expression, current_time)
            await db.commit()

        except Exception:
            # Continue dispatching other due schedules even if one encounters an issue
            continue

    return dispatched_jobs
