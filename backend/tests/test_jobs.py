"""Automated integration tests for Celery background workers, job state streaming, and periodic schedules."""

from datetime import datetime, timezone
import io
import pytest
from fastapi.testclient import TestClient

from app.main import app
from worker.schedules.cron_parser import (
    calculate_next_run,
    normalize_expression,
    validate_cron_expression,
)

client = TestClient(app)


def setup_user_and_workspace(email: str, name: str):
    """Helper to register user, log in, create workspace, and return auth context."""
    client.post(
        "/api/v1/auth/register",
        json={"email": email, "full_name": name, "password": "SecurePassword123!"},
    )
    login_res = client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": "SecurePassword123!"},
    )
    token = login_res.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    ws_res = client.post(
        "/api/v1/workspaces",
        json={"name": f"{name}'s Lab"},
        headers=headers,
    )
    ws_id = ws_res.json()["id"]
    return token, ws_id


def upload_test_csv(headers: dict, filename: str, content: str) -> str:
    """Helper to upload CSV content and return dataset ID."""
    files = {"file": (filename, io.BytesIO(content.encode("utf-8")), "text/csv")}
    res = client.post("/api/v1/datasets/upload", headers=headers, files=files)
    assert res.status_code == 201
    return res.json()["id"]


def test_cron_parser_and_intervals():
    """Verify parsing, preset expansions, validation, and next run calculation."""
    # Presets
    assert normalize_expression("hourly") == "0 * * * *"
    assert normalize_expression("daily") == "0 0 * * *"
    assert normalize_expression("weekly") == "0 0 * * 0"
    assert normalize_expression("every_15_mins") == "*/15 * * * *"

    # Validation
    assert validate_cron_expression("hourly") is True
    assert validate_cron_expression("0 0 * * *") is True
    assert validate_cron_expression("*/5 * * * *") is True
    assert validate_cron_expression("invalid_cron_expr") is False
    assert validate_cron_expression("99 * * * *") is False

    # Next run calculation
    now = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
    next_hourly = calculate_next_run("hourly", base_time=now)
    assert next_hourly == datetime(2026, 1, 1, 13, 0, 0, tzinfo=timezone.utc)

    next_15 = calculate_next_run("every_15_mins", base_time=now)
    assert next_15 == datetime(2026, 1, 1, 12, 15, 0, tzinfo=timezone.utc)


def test_job_dispatch_and_execution_pipeline():
    """Verify asynchronous pipeline execution dispatched to Celery background worker."""
    token, ws_id = setup_user_and_workspace("worker_pipe@example.com", "Worker Dev")
    headers = {"Authorization": f"Bearer {token}", "X-Workspace-ID": ws_id}

    # 1. Ingest dataset
    csv_data = "id,score\n1,10\n2,20\n3,30\n"
    ds_id = upload_test_csv(headers, "worker_input.csv", csv_data)

    # 2. Create pipeline DAG
    p_res = client.post(
        "/api/v1/pipelines",
        headers=headers,
        json={
            "name": "Async Worker Pipeline",
            "description": "Background test pipeline",
            "graph_definition": {
                "nodes": [
                    {"id": "n1", "type": "source", "label": "Input Data", "config": {"dataset_id": ds_id}},
                    {"id": "n2", "type": "sink", "label": "Result Sink", "config": {"output_name": "worker_out"}},
                ],
                "edges": [{"id": "e1", "source": "n1", "target": "n2"}],
            },
        },
    )
    assert p_res.status_code == 201
    pipeline_id = p_res.json()["id"]

    # 3. Dispatch background job
    job_res = client.post(
        "/api/v1/jobs",
        headers=headers,
        json={
            "task_type": "pipeline_run",
            "resource_id": pipeline_id,
            "parameters": {"environment": "test"},
        },
    )
    assert job_res.status_code == 201
    job_data = job_res.json()
    assert job_data["workspace_id"] == ws_id
    assert job_data["task_type"] == "pipeline_run"
    assert job_data["status"] == "completed"
    assert job_data["progress_pct"] == 100
    assert "worker_out" in str(job_data["result_payload"])

    # 4. Fetch job details
    get_res = client.get(f"/api/v1/jobs/{job_data['id']}", headers=headers)
    assert get_res.status_code == 200
    assert get_res.json()["id"] == job_data["id"]
    assert get_res.json()["status"] == "completed"


def test_job_dispatch_and_execution_profiling():
    """Verify background statistical profiling task execution."""
    token, ws_id = setup_user_and_workspace("prof_worker@example.com", "Profiler Dev")
    headers = {"Authorization": f"Bearer {token}", "X-Workspace-ID": ws_id}

    # 1. Ingest dataset
    csv_data = "col_a,col_b\n10,foo\n20,bar\n30,baz\n"
    ds_id = upload_test_csv(headers, "profile_sample.csv", csv_data)

    # 2. Dispatch dataset profiling job
    job_res = client.post(
        "/api/v1/jobs",
        headers=headers,
        json={
            "task_type": "dataset_profile",
            "resource_id": ds_id,
        },
    )
    assert job_res.status_code == 201
    job_data = job_res.json()
    assert job_data["status"] == "completed"


    assert job_data["progress_pct"] == 100
    assert "col_a" in str(job_data["result_payload"])


def test_job_list_and_diagnostics():
    """Verify listing workspace jobs and querying worker telemetry diagnostics."""
    token, ws_id = setup_user_and_workspace("diag_worker@example.com", "Telemetry Dev")
    headers = {"Authorization": f"Bearer {token}", "X-Workspace-ID": ws_id}

    # List jobs
    list_res = client.get("/api/v1/jobs", headers=headers)
    assert list_res.status_code == 200
    assert isinstance(list_res.json(), list)

    # Diagnostics
    diag_res = client.get("/api/v1/jobs/diagnostics", headers=headers)
    assert diag_res.status_code == 200
    diag = diag_res.json()
    assert diag["broker_type"] == "redis"
    assert diag["status"] in ("operational", "degraded")
    assert "active_worker_count" in diag
    assert "queued_task_count" in diag


def test_job_cancellation_lifecycle():
    """Verify job cancellation semantics."""
    token, ws_id = setup_user_and_workspace("cancel_worker@example.com", "Cancel Dev")
    headers = {"Authorization": f"Bearer {token}", "X-Workspace-ID": ws_id}

    # Dispatch a job for a dataset
    csv_data = "x,y\n1,2\n"
    ds_id = upload_test_csv(headers, "cancel_data.csv", csv_data)
    job_res = client.post(
        "/api/v1/jobs",
        headers=headers,
        json={"task_type": "dataset_ingest", "resource_id": ds_id},
    )
    job_id = job_res.json()["id"]

    # Cancel job
    cancel_res = client.post(f"/api/v1/jobs/{job_id}/cancel", headers=headers)
    assert cancel_res.status_code == 200


def test_pipeline_schedule_crud_and_trigger():
    """Verify schedule creation, editing, execution trigger, and deletion."""
    token, ws_id = setup_user_and_workspace("schedule_dev@example.com", "Scheduler Dev")
    headers = {"Authorization": f"Bearer {token}", "X-Workspace-ID": ws_id}

    # 1. Ingest & create pipeline
    ds_id = upload_test_csv(headers, "sched_in.csv", "a,b\n1,2\n")
    p_res = client.post(
        "/api/v1/pipelines",
        headers=headers,
        json={
            "name": "Scheduled Pipeline",
            "graph_definition": {
                "nodes": [
                    {"id": "n1", "type": "source", "config": {"dataset_id": ds_id}},
                    {"id": "n2", "type": "sink", "config": {"output_name": "sched_out"}},
                ],
                "edges": [{"id": "e1", "source": "n1", "target": "n2"}],
            },
        },
    )
    pipeline_id = p_res.json()["id"]

    # 2. Create schedule
    s_res = client.post(
        "/api/v1/schedules",
        headers=headers,
        json={
            "pipeline_id": pipeline_id,
            "name": "Hourly ETL Batch",
            "cron_expression": "hourly",
            "is_active": True,
        },
    )
    assert s_res.status_code == 201
    sched = s_res.json()
    sched_id = sched["id"]
    assert sched["name"] == "Hourly ETL Batch"
    assert sched["is_active"] is True
    assert sched["next_run_at"] is not None

    # 3. List schedules
    list_res = client.get("/api/v1/schedules", headers=headers)
    assert list_res.status_code == 200
    assert len(list_res.json()) >= 1

    # 4. Update schedule
    update_res = client.put(
        f"/api/v1/schedules/{sched_id}",
        headers=headers,
        json={"name": "Nightly ETL Batch", "cron_expression": "daily"},
    )
    assert update_res.status_code == 200
    assert update_res.json()["name"] == "Nightly ETL Batch"
    assert update_res.json()["cron_expression"] == "daily"

    # 5. Trigger due schedules
    trigger_res = client.post("/api/v1/schedules/trigger-due", headers=headers)
    assert trigger_res.status_code == 200
    assert isinstance(trigger_res.json(), list)

    # 6. Delete schedule
    del_res = client.delete(f"/api/v1/schedules/{sched_id}", headers=headers)
    assert del_res.status_code == 200
    assert del_res.json()["status"] == "deleted"


def test_jobs_and_schedules_workspace_isolation_and_rbac():
    """Verify viewer role cannot dispatch jobs and tenant isolation prevents cross-tenant access."""
    # User 1 with admin workspace
    token1, ws1_id = setup_user_and_workspace("admin_iso@example.com", "Admin 1")
    headers1 = {"Authorization": f"Bearer {token1}", "X-Workspace-ID": ws1_id}

    # User 2 in separate workspace
    token2, ws2_id = setup_user_and_workspace("other_iso@example.com", "Admin 2")
    headers2 = {"Authorization": f"Bearer {token2}", "X-Workspace-ID": ws2_id}

    # Create dataset & job in workspace 1
    ds1_id = upload_test_csv(headers1, "iso_data.csv", "k,v\n1,10\n")
    job1_res = client.post(
        "/api/v1/jobs",
        headers=headers1,
        json={"task_type": "dataset_profile", "resource_id": ds1_id},
    )
    job1_id = job1_res.json()["id"]

    # User 2 tries to access User 1's job with workspace 2 header -> 404
    cross_res = client.get(f"/api/v1/jobs/{job1_id}", headers=headers2)
    assert cross_res.status_code == 404

    # User 3 registered and added as VIEWER to workspace 1
    client.post(
        "/api/v1/auth/register",
        json={"email": "viewer_job@example.com", "full_name": "Job Viewer", "password": "SecurePassword123!"},
    )
    v_login = client.post(
        "/api/v1/auth/login",
        json={"email": "viewer_job@example.com", "password": "SecurePassword123!"},
    )
    v_token = v_login.json()["access_token"]

    # Add as viewer
    add_res = client.post(
        f"/api/v1/workspaces/{ws1_id}/members",
        headers=headers1,
        json={"email": "viewer_job@example.com", "role": "viewer"},
    )
    assert add_res.status_code == 201

    viewer_headers = {"Authorization": f"Bearer {v_token}", "X-Workspace-ID": ws1_id}

    # Viewer cannot dispatch job -> 403 Forbidden
    v_job_res = client.post(
        "/api/v1/jobs",
        headers=viewer_headers,
        json={"task_type": "dataset_profile", "resource_id": ds1_id},
    )
    assert v_job_res.status_code == 403
