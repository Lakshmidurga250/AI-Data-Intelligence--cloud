"""Automated integration tests for visual ETL pipelines, DAG cycle validation, and execution runs."""

import io
import pytest
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def setup_user_and_workspace(email: str, name: str):
    """Helper to register user, log in, create workspace, return (token, workspace_id)."""
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


def test_pipeline_crud():
    """Verify creating, reading, updating, listing, and deleting ETL pipelines."""
    token, ws_id = setup_user_and_workspace("crud_pipeline@example.com", "Pipeline Engineer")
    headers = {"Authorization": f"Bearer {token}", "X-Workspace-ID": ws_id}

    # 1. Create pipeline
    create_payload = {
        "name": "Customer Segmentation Flow",
        "description": "Initial data transformation DAG",
        "graph_definition": {
            "nodes": [
                {"id": "source-1", "type": "source", "label": "Raw Ingestion", "config": {"dataset_id": "dummy-ds"}},
                {"id": "sink-1", "type": "sink", "label": "Persist Segment", "config": {"output_name": "Segment Output"}},
            ],
            "edges": [
                {"id": "edge-1", "source": "source-1", "target": "sink-1"},
            ],
        },
    }
    create_res = client.post("/api/v1/pipelines", headers=headers, json=create_payload)
    assert create_res.status_code == 201
    created_data = create_res.json()
    assert created_data["name"] == "Customer Segmentation Flow"
    assert created_data["workspace_id"] == ws_id
    pipeline_id = created_data["id"]

    # 2. List pipelines
    list_res = client.get("/api/v1/pipelines", headers=headers)
    assert list_res.status_code == 200
    summaries = list_res.json()
    assert len(summaries) >= 1
    assert any(p["id"] == pipeline_id for p in summaries)

    # 3. Get pipeline detail
    get_res = client.get(f"/api/v1/pipelines/{pipeline_id}", headers=headers)
    assert get_res.status_code == 200
    detail = get_res.json()
    assert detail["name"] == "Customer Segmentation Flow"
    assert len(detail["graph_definition"]["nodes"]) == 2

    # 4. Update pipeline
    update_res = client.put(
        f"/api/v1/pipelines/{pipeline_id}",
        headers=headers,
        json={"name": "Renamed Segmentation Flow", "description": "Updated notes"},
    )
    assert update_res.status_code == 200
    assert update_res.json()["name"] == "Renamed Segmentation Flow"

    # 5. Delete pipeline
    del_res = client.delete(f"/api/v1/pipelines/{pipeline_id}", headers=headers)
    assert del_res.status_code == 204

    # 6. Verify 404 after deletion
    get_after_del = client.get(f"/api/v1/pipelines/{pipeline_id}", headers=headers)
    assert get_after_del.status_code == 404


def test_pipeline_dag_cycle_validation():
    """Verify DAG cycle detection identifies circular dependencies and blocks execution."""
    token, ws_id = setup_user_and_workspace("cycle_analyst@example.com", "Graph Validator")
    headers = {"Authorization": f"Bearer {token}", "X-Workspace-ID": ws_id}

    # Construct circular dependency: A -> B -> C -> A
    cyclic_payload = {
        "name": "Circular Graph",
        "description": "Intentionally cyclic pipeline for validation test",
        "graph_definition": {
            "nodes": [
                {"id": "source-1", "type": "source", "label": "Source", "config": {"dataset_id": "dummy"}},
                {"id": "node-a", "type": "transform", "label": "Node A", "config": {}},
                {"id": "node-b", "type": "transform", "label": "Node B", "config": {}},
                {"id": "sink-1", "type": "sink", "label": "Sink", "config": {}},
            ],
            "edges": [
                {"id": "e-1", "source": "source-1", "target": "node-a"},
                {"id": "e-2", "source": "node-a", "target": "node-b"},
                {"id": "e-3", "source": "node-b", "target": "node-a"},  # Cycle!
                {"id": "e-4", "source": "node-b", "target": "sink-1"},
            ],
        },
    }
    create_res = client.post("/api/v1/pipelines", headers=headers, json=cyclic_payload)
    assert create_res.status_code == 201
    pipeline_id = create_res.json()["id"]

    # Validate endpoint
    val_res = client.post(f"/api/v1/pipelines/{pipeline_id}/validate", headers=headers)
    assert val_res.status_code == 200
    val_data = val_res.json()
    assert val_data["is_valid"] is False
    assert any("Cyclic dependency" in err for err in val_data["errors"])

    # Attempting to run should return HTTP 400 Bad Request
    run_res = client.post(f"/api/v1/pipelines/{pipeline_id}/run", headers=headers)
    assert run_res.status_code == 400
    assert "Cyclic dependency" in run_res.json()["detail"]


def test_pipeline_execution_source_filter_transform_sink():
    """Verify end-to-end multi-stage pipeline: Source -> Filter -> Transform -> Sink."""
    token, ws_id = setup_user_and_workspace("exec_analyst@example.com", "Pipeline Runner")
    headers = {"Authorization": f"Bearer {token}", "X-Workspace-ID": ws_id}

    # Upload test CSV
    csv_content = (
        "emp_id,name,department,salary\n"
        "101,  Alice  ,Engineering,120000\n"
        "102,Bob,Engineering,45000\n"
        "103,Charlie,Marketing,65000\n"
        "104,David,Sales,85000\n"
        "105,Eve,Engineering,140000\n"
    )
    dataset_id = upload_test_csv(headers, "company_roster.csv", csv_content)

    # Construct pipeline DAG
    pipeline_payload = {
        "name": "Engineering High Earners Flow",
        "description": "Filter by engineering and clean strings",
        "graph_definition": {
            "nodes": [
                {
                    "id": "node-source",
                    "type": "source",
                    "label": "Company Roster",
                    "config": {"dataset_id": dataset_id},
                },
                {
                    "id": "node-filter",
                    "type": "filter",
                    "label": "Engineering Only",
                    "config": {"column": "department", "operator": "==", "value": "Engineering"},
                },
                {
                    "id": "node-transform",
                    "type": "transform",
                    "label": "Clean Names & Salaries",
                    "config": {
                        "steps": [
                            {"step_type": "text_transform", "params": {"columns": ["name"], "operation": "trim"}},
                            {"step_type": "filter_rows", "params": {"column": "salary", "operator": ">", "value": 50000}},
                        ]
                    },
                },
                {
                    "id": "node-sink",
                    "type": "sink",
                    "label": "Engineering Top Earners",
                    "config": {"output_name": "High Earning Engineers", "format": "parquet"},
                },
            ],
            "edges": [
                {"id": "e1", "source": "node-source", "target": "node-filter"},
                {"id": "e2", "source": "node-filter", "target": "node-transform"},
                {"id": "e3", "source": "node-transform", "target": "node-sink"},
            ],
        },
    }
    create_res = client.post("/api/v1/pipelines", headers=headers, json=pipeline_payload)
    assert create_res.status_code == 201
    pipeline_id = create_res.json()["id"]

    # Execute pipeline
    run_res = client.post(f"/api/v1/pipelines/{pipeline_id}/run", headers=headers)
    assert run_res.status_code == 200
    run_data = run_res.json()
    assert run_data["status"] == "completed"

    assert len(run_data["stage_results"]) == 4

    # Check stage results:
    # 5 source rows -> filter engineering (3 rows) -> filter salary > 50000 (2 rows: Alice, Eve) -> sink (2 rows)
    sink_stage = next(s for s in run_data["stage_results"] if s["node_type"] == "sink")
    assert sink_stage["rows_out"] == 2
    assert run_data["output_dataset_id"] is not None

    # Verify output dataset in workspace catalog
    output_ds_res = client.get(
        f"/api/v1/datasets/{run_data['output_dataset_id']}",
        headers=headers,
    )
    assert output_ds_res.status_code == 200
    out_ds = output_ds_res.json()
    assert out_ds["name"] == "High Earning Engineers"
    assert out_ds["row_count"] == 2
    assert out_ds["format"] == "parquet"

    # Verify run history
    runs_res = client.get(f"/api/v1/pipelines/{pipeline_id}/runs", headers=headers)
    assert runs_res.status_code == 200
    history = runs_res.json()
    assert len(history) == 1
    assert history[0]["status"] == "completed"


def test_pipeline_join_and_aggregation_execution():
    """Verify multi-source join and aggregation in visual pipeline."""
    token, ws_id = setup_user_and_workspace("join_analyst@example.com", "Join Specialist")
    headers = {"Authorization": f"Bearer {token}", "X-Workspace-ID": ws_id}

    # Upload Dataset 1: Users
    users_csv = (
        "user_id,username,region\n"
        "1,Alice,North\n"
        "2,Bob,North\n"
        "3,Charlie,South\n"
    )
    users_ds_id = upload_test_csv(headers, "users.csv", users_csv)

    # Upload Dataset 2: Orders
    orders_csv = (
        "order_id,user_id,amount\n"
        "101,1,100\n"
        "102,1,150\n"
        "103,2,200\n"
        "104,3,300\n"
    )
    orders_ds_id = upload_test_csv(headers, "orders.csv", orders_csv)

    # Build Pipeline: Source(Users) + Source(Orders) -> Join(user_id) -> Aggregate(region, sum(amount)) -> Sink
    pipeline_payload = {
        "name": "Regional Sales Rollup",
        "description": "Multi-source join and grouping DAG",
        "graph_definition": {
            "nodes": [
                {"id": "src-users", "type": "source", "config": {"dataset_id": users_ds_id}},
                {"id": "src-orders", "type": "source", "config": {"dataset_id": orders_ds_id}},
                {
                    "id": "join-node",
                    "type": "join",
                    "label": "User Orders Join",
                    "config": {"how": "inner", "on": ["user_id"]},
                },
                {
                    "id": "agg-node",
                    "type": "aggregate",
                    "label": "Regional Sum",
                    "config": {
                        "group_by": ["region"],
                        "aggregations": {"amount": "sum"},
                    },
                },
                {
                    "id": "sink-node",
                    "type": "sink",
                    "label": "Sales By Region",
                    "config": {"output_name": "Regional Sales Summary", "format": "csv"},
                },
            ],
            "edges": [
                {"id": "e-u", "source": "src-users", "target": "join-node", "target_handle": "left"},
                {"id": "e-o", "source": "src-orders", "target": "join-node", "target_handle": "right"},
                {"id": "e-j", "source": "join-node", "target": "agg-node"},
                {"id": "e-a", "source": "agg-node", "target": "sink-node"},
            ],
        },
    }
    create_res = client.post("/api/v1/pipelines", headers=headers, json=pipeline_payload)
    assert create_res.status_code == 201
    pipeline_id = create_res.json()["id"]

    # Run Pipeline
    run_res = client.post(f"/api/v1/pipelines/{pipeline_id}/run", headers=headers)
    assert run_res.status_code == 200
    run_data = run_res.json()
    assert run_data["status"] == "completed"

    # Aggregated output should have 2 regions: North (100+150+200=450), South (300)
    sink_stage = next(s for s in run_data["stage_results"] if s["node_type"] == "sink")
    assert sink_stage["rows_out"] == 2


def test_pipeline_workspace_tenancy_isolation():
    """Verify tenant workspace boundary prevents unauthorized access to other workspaces' pipelines."""
    # User A in Workspace A
    token_a, ws_a = setup_user_and_workspace("tenant_a@example.com", "Tenant A")
    headers_a = {"Authorization": f"Bearer {token_a}", "X-Workspace-ID": ws_a}

    # User B in Workspace B
    token_b, ws_b = setup_user_and_workspace("tenant_b@example.com", "Tenant B")
    headers_b = {"Authorization": f"Bearer {token_b}", "X-Workspace-ID": ws_b}

    # Create pipeline in Workspace A
    create_res = client.post(
        "/api/v1/pipelines",
        headers=headers_a,
        json={"name": "Tenant A Confidential Pipeline", "graph_definition": {"nodes": [], "edges": []}},
    )
    assert create_res.status_code == 201
    pipeline_a_id = create_res.json()["id"]

    # User B tries to view Pipeline A -> should be 404 (Not Found in tenant workspace)
    unauth_get = client.get(f"/api/v1/pipelines/{pipeline_a_id}", headers=headers_b)
    assert unauth_get.status_code == 404

    # User B tries to run Pipeline A -> 404
    unauth_run = client.post(f"/api/v1/pipelines/{pipeline_a_id}/run", headers=headers_b)
    assert unauth_run.status_code == 404
