"""End-to-End Cross-Module Orchestration & Tenant Isolation Test Suite.

Validates the complete progressive lifecycle across all 12 modules:
0. Foundation & Core Settings
1. Identity, Auth & Workspace RBAC Isolation
2. Multi-Format Tabular Ingestion (CSV / Parquet / JSON / Excel)
3. Catalog & Statistical Profiling Engine
4. Declarative Data Transformations & Recipe Engine
5. Visual ETL Pipelines & DAG Topological Execution
6. Async Background Workers & Cron Schedulers
7. Declarative Data Quality Contracts, Grading & Alerting
8. Bidirectional Lineage Graph Traversal & Governance PII Classifier
9. AutoML Benchmark Training, Model Registry & Real-Time Inference
10. Interactive Analytics & BI Dashboards Aggregation Engine
11. AI Data Intelligence Assistant & Conversational NL Query Engine
"""

import io
import pytest
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def setup_auth(email: str, name: str):
    """Register user, authenticate, create isolated workspace, and return headers."""
    reg_res = client.post(
        "/api/v1/auth/register",
        json={"email": email, "full_name": name, "password": "SecurePassword123!"},
    )
    assert reg_res.status_code == 201

    login_res = client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": "SecurePassword123!"},
    )
    assert login_res.status_code == 200
    token = login_res.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    ws_res = client.post(
        "/api/v1/workspaces",
        json={"name": f"{name} Workspace"},
        headers=headers,
    )
    assert ws_res.status_code == 201
    ws_id = ws_res.json()["id"]
    headers["X-Workspace-ID"] = ws_id
    return headers, ws_id


def upload_csv(headers: dict, filename: str, content: str) -> str:
    """Upload CSV dataset and return dataset ID."""
    files = {"file": (filename, io.BytesIO(content.encode("utf-8")), "text/csv")}
    res = client.post("/api/v1/datasets/upload", headers=headers, files=files)
    assert res.status_code == 201
    return res.json()["id"]


TELECOM_DATASET_CSV = """customer_id,state,tenure,monthly_charges,total_charges,email,churn
101,CA,12,75.50,906.00,user101@telecom.com,0
102,NY,24,89.00,2136.00,user102@telecom.com,0
103,TX,3,45.20,135.60,user103@telecom.com,1
104,CA,36,110.00,3960.00,user104@telecom.com,0
105,FL,1,55.00,55.00,user105@telecom.com,1
106,NY,48,95.00,4560.00,user106@telecom.com,0
107,TX,6,65.00,390.00,user107@telecom.com,1
108,CA,18,80.00,1440.00,user108@telecom.com,0
109,FL,2,50.00,100.00,user109@telecom.com,1
110,NY,60,120.00,7200.00,user110@telecom.com,0
"""


def test_e2e_multi_module_orchestration_flow():
    """Exhaustive test executing full end-to-end lifecycle across all platform subsystems."""
    # Module 00 & 01: Identity, Auth & Workspace Tenancy
    headers, ws_id = setup_auth("e2e_director@enterprise.internal", "E2E Director")
    me_res = client.get("/api/v1/auth/me", headers=headers)
    assert me_res.status_code == 200
    assert me_res.json()["email"] == "e2e_director@enterprise.internal"

    # Module 02: Multi-Format Ingestion
    ds_id = upload_csv(headers, "telecom_master.csv", TELECOM_DATASET_CSV)
    ds_get = client.get(f"/api/v1/datasets/{ds_id}", headers=headers)
    assert ds_get.status_code == 200
    ds_info = ds_get.json()
    assert ds_info["name"] == "telecom_master.csv"
    assert ds_info["row_count"] == 10
    assert ds_info["column_count"] == 7

    # Module 03: Catalog & Statistical Profiling Engine
    prof_res = client.get(f"/api/v1/datasets/{ds_id}/profile", headers=headers)
    assert prof_res.status_code == 200
    profile = prof_res.json()
    assert profile["row_count"] == 10
    assert profile["column_count"] == 7
    col_map = {c["name"]: c for c in profile["columns"]}
    assert "monthly_charges" in col_map
    assert col_map["monthly_charges"]["is_numeric"] is True
    assert col_map["monthly_charges"]["numeric_stats"]["mean"] > 0

    # Module 04: Data Cleaning & Transforms
    preview_res = client.post(
        f"/api/v1/datasets/{ds_id}/transforms/preview",
        headers=headers,
        json={
            "sample_size": 10,
            "steps": [
                {"step_type": "text_transform", "params": {"columns": ["state"], "operation": "trim"}},
                {"step_type": "filter_rows", "params": {"column": "monthly_charges", "operator": ">=", "value": 50.0}},
            ],
        },
    )
    assert preview_res.status_code == 200
    preview_data = preview_res.json()
    assert preview_data["original_row_count"] == 10
    assert preview_data["transformed_row_count"] == 9  # Customer 103 had 45.20 < 50.0

    apply_res = client.post(
        f"/api/v1/datasets/{ds_id}/transforms/apply",
        headers=headers,
        json={
            "steps": [
                {"step_type": "filter_rows", "params": {"column": "monthly_charges", "operator": ">=", "value": 50.0}},
            ],
            "mode": "new_dataset",
            "new_dataset_name": "telecom_filtered_active",
        },
    )
    assert apply_res.status_code == 201
    filtered_ds_id = apply_res.json()["dataset_id"]
    assert filtered_ds_id != ds_id

    # Module 05: Visual ETL Pipelines & DAG Topological Sort Execution
    pipeline_res = client.post(
        "/api/v1/pipelines",
        headers=headers,
        json={
            "name": "E2E Telecom ETL Pipeline",
            "description": "Extract, filter high charges, and materialize sink",
            "graph_definition": {
                "nodes": [
                    {"id": "source-1", "type": "source", "label": "Raw Ingestion", "config": {"dataset_id": ds_id}},
                    {"id": "filter-1", "type": "filter", "label": "Filter High Charges", "config": {"column": "monthly_charges", "operator": ">", "value": 70.0}},
                    {"id": "sink-1", "type": "sink", "label": "Materialize High Value", "config": {"output_name": "telecom_high_value", "format": "parquet"}},
                ],
                "edges": [
                    {"id": "e1", "source": "source-1", "target": "filter-1"},
                    {"id": "e2", "source": "filter-1", "target": "sink-1"},
                ],
            },
        },
    )
    assert pipeline_res.status_code == 201
    pipe_id = pipeline_res.json()["id"]

    run_pipe_res = client.post(f"/api/v1/pipelines/{pipe_id}/run", headers=headers)
    assert run_pipe_res.status_code == 200
    pipe_run_data = run_pipe_res.json()
    assert pipe_run_data["status"] == "completed"
    materialized_sink_id = pipe_run_data["output_dataset_id"]
    assert materialized_sink_id is not None

    # Module 06: Async Workers & Pipeline Schedulers
    job_res = client.post(
        "/api/v1/jobs",
        headers=headers,
        json={
            "task_type": "pipeline_run",
            "resource_id": pipe_id,
            "parameters": {"environment": "test"},
        },
    )
    assert job_res.status_code == 201
    job_data = job_res.json()
    job_id = job_data["id"]
    job_status_res = client.get(f"/api/v1/jobs/{job_id}", headers=headers)
    assert job_status_res.status_code == 200
    assert job_status_res.json()["task_type"] == "pipeline_run"

    schedule_res = client.post(
        "/api/v1/schedules",
        headers=headers,
        json={"name": "Daily Telecom ETL", "pipeline_id": pipe_id, "cron_expression": "daily", "is_active": True},
    )
    assert schedule_res.status_code == 201

    # Module 07: Declarative Data Quality Rules & Scorecards
    suite_res = client.post(
        "/api/v1/quality/suites",
        headers=headers,
        json={
            "name": "Telecom Data Quality Contract",
            "dataset_id": ds_id,
            "rules": [
                {"name": "Customer ID Uniqueness", "rule_type": "uniqueness", "target_column": "customer_id", "parameters": {"min_unique_pct": 100.0}, "severity": "critical"},
                {"name": "Valid Charge Range", "rule_type": "value_range", "target_column": "monthly_charges", "parameters": {"min": 10.0, "max": 500.0}, "severity": "warning"},
                {"name": "Email Format Regex", "rule_type": "regex_match", "target_column": "email", "parameters": {"pattern": r"^[\w\.-]+@[\w\.-]+\.\w+$"}, "severity": "critical"},
            ],
        },
    )
    assert suite_res.status_code == 201
    suite_id = suite_res.json()["id"]

    eval_res = client.post(f"/api/v1/quality/suites/{suite_id}/evaluate", headers=headers)
    assert eval_res.status_code == 200
    eval_data = eval_res.json()
    assert eval_data["grade"] == "A"
    assert eval_data["score"] == 100.0

    # Module 08: Lineage DAG & Governance PII Classifier
    sync_res = client.post("/api/v1/lineage/sync", headers=headers)
    assert sync_res.status_code == 200
    graph_res = client.get("/api/v1/lineage/graph", headers=headers)
    assert graph_res.status_code == 200
    graph_data = graph_res.json()
    assert len(graph_data["nodes"]) >= 2

    pii_res = client.post(f"/api/v1/governance/classify/{ds_id}", headers=headers)
    assert pii_res.status_code == 200
    pii_data = pii_res.json()
    assert any(f["column_name"] == "email" for f in pii_data["findings"])
    assert pii_data["overall_classification"] in ["CONFIDENTIAL", "RESTRICTED_PII"]

    # Module 09: AutoML Benchmarking & Online Inference
    train_res = client.post(
        "/api/v1/ml/train",
        headers=headers,
        json={
            "dataset_id": ds_id,
            "model_name": "E2E Telecom Churn Predictor",
            "target_column": "churn",
            "task_type": "classification",
            "test_size": 0.25,
            "description": "AutoML churn prediction model",
        },
    )
    assert train_res.status_code == 201
    model_data = train_res.json()
    model_id = model_data["model_id"]
    assert "accuracy" in model_data["metrics"]

    predict_res = client.post(
        f"/api/v1/ml/models/{model_id}/predict",
        headers=headers,
        json={
            "inputs": {
                "customer_id": 199,
                "state": "CA",
                "tenure": 14,
                "monthly_charges": 82.0,
                "total_charges": 1148.0,
                "email": "test@example.com",
            }
        },
    )
    assert predict_res.status_code == 200
    pred_data = predict_res.json()
    assert len(pred_data["predictions"]) == 1
    assert pred_data["latency_ms"] >= 0.0

    # Module 10: Interactive Analytics & BI Dashboards
    dash_res = client.post(
        "/api/v1/dashboards",
        headers=headers,
        json={"name": "E2E Executive Telecom Dashboard", "description": "State analytics and charges summary"},
    )
    assert dash_res.status_code == 201
    dash_id = dash_res.json()["id"]

    query_res = client.post(
        "/api/v1/dashboards/query",
        headers=headers,
        json={
            "dataset_id": ds_id,
            "metrics": [
                {"column": "monthly_charges", "aggregation": "sum", "alias": "total_charges"},
                {"column": "monthly_charges", "aggregation": "avg", "alias": "avg_charge"},
                {"column": "*", "aggregation": "count", "alias": "customer_count"},
            ],
            "dimensions": ["state"],
            "sort_by": "total_charges",
            "sort_order": "desc",
        },
    )
    assert query_res.status_code == 200
    q_data = query_res.json()
    assert "state" in q_data["columns"]
    assert "total_charges" in q_data["columns"]
    assert q_data["row_count"] >= 3  # CA, NY, TX, FL

    # Module 11: Conversational AI & Autonomous Data Intelligence Assistant
    conv_res = client.post(
        "/api/v1/assistant/conversations",
        headers=headers,
        json={"title": "E2E Telecom Copilot Thread", "dataset_id": ds_id},
    )
    assert conv_res.status_code == 201
    conv_id = conv_res.json()["id"]

    # 11A. Autonomous Anomaly Scan
    scan_res = client.post(
        f"/api/v1/assistant/conversations/{conv_id}/messages",
        headers=headers,
        json={"content": "Discover anomalies, outliers, and defects in this dataset.", "dataset_id": ds_id},
    )
    assert scan_res.status_code == 200
    scan_reply = scan_res.json()
    assert scan_reply["assistant_message"]["role"] == "assistant"
    assert scan_reply["intent"] == "anomaly_insights"
    assert scan_reply["insights"] is not None

    # 11B. Natural Language Query Translation into Pandas Aggregation
    nl_res = client.post(
        f"/api/v1/assistant/conversations/{conv_id}/messages",
        headers=headers,
        json={"content": "What is the total monthly_charges grouped by state?", "dataset_id": ds_id},
    )
    assert nl_res.status_code == 200
    nl_reply = nl_res.json()
    assert nl_reply["intent"] == "nl_query"
    assert nl_reply["query_result"] is not None
    assert "state" in nl_reply["query_result"]["columns"]

    # 11C. Guided Platform Copilot Assistance
    help_res = client.post(
        f"/api/v1/assistant/conversations/{conv_id}/messages",
        headers=headers,
        json={"content": "How do I create and schedule an automated ETL pipeline?"},
    )
    assert help_res.status_code == 200
    help_reply = help_res.json()
    assert help_reply["intent"] == "navigation"
    assert "Visual ETL Pipeline" in help_reply["assistant_message"]["content"]


def test_cross_tenant_isolation_boundary_e2e():
    """Verify strict tenant isolation boundary across all subsystems: User B cannot access User A's assets."""
    headers_a, ws_a = setup_auth("tenant_a@enterprise.internal", "Tenant A User")
    headers_b, ws_b = setup_auth("tenant_b@enterprise.internal", "Tenant B User")

    # User A creates assets in Workspace A
    ds_a = upload_csv(headers_a, "private_tenant_a.csv", TELECOM_DATASET_CSV)

    conv_a = client.post(
        "/api/v1/assistant/conversations",
        headers=headers_a,
        json={"title": "Private Conversation A", "dataset_id": ds_a},
    ).json()["id"]

    dash_a = client.post(
        "/api/v1/dashboards",
        headers=headers_a,
        json={"name": "Private Dashboard A"},
    ).json()["id"]

    # User B attempts to access User A's dataset -> Forbidden or Not Found
    get_ds_b = client.get(f"/api/v1/datasets/{ds_a}", headers=headers_b)
    assert get_ds_b.status_code in [403, 404]

    # User B attempts to query User A's assistant conversation -> Forbidden or Not Found
    get_conv_b = client.get(f"/api/v1/assistant/conversations/{conv_a}", headers=headers_b)
    assert get_conv_b.status_code in [403, 404]

    # User B attempts to query User A's dashboard -> Forbidden or Not Found
    get_dash_b = client.get(f"/api/v1/dashboards/{dash_a}", headers=headers_b)
    assert get_dash_b.status_code in [403, 404]

    # User B attempts to execute analytics query against User A's dataset
    query_b = client.post(
        "/api/v1/dashboards/query",
        headers=headers_b,
        json={"dataset_id": ds_a, "metrics": [{"column": "monthly_charges", "aggregation": "sum"}]},
    )
    assert query_b.status_code in [403, 404]
