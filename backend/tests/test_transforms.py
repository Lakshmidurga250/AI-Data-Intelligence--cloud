"""Automated integration tests for data cleaning, transformation operators, preview, and recipes."""

import io
import pandas as pd
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
        json={"name": f"{name}'s Data Lab"},
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


def test_transformation_preview_pipeline():
    """Verify non-destructive simulation of multiple transformation steps on sample rows."""
    token, ws_id = setup_user_and_workspace("preview_analyst@example.com", "Preview Analyst")
    headers = {"Authorization": f"Bearer {token}", "X-Workspace-ID": ws_id}

    csv_data = (
        "name,age,salary,city\n"
        "  Alice  ,25,50000,New York\n"
        "Bob,30,,San Francisco\n"
        "Charlie,,70000,Chicago\n"
        "David,40,80000,New York\n"
        "David,40,80000,New York\n"  # Duplicate row
    )
    dataset_id = upload_test_csv(headers, "employees_raw.csv", csv_data)

    preview_payload = {
        "sample_size": 10,
        "steps": [
            {"step_type": "text_transform", "params": {"columns": ["name"], "operation": "trim"}},
            {"step_type": "drop_duplicates", "params": {"keep": "first"}},
            {"step_type": "impute", "params": {"columns": ["age"], "strategy": "mean"}},
            {"step_type": "impute", "params": {"columns": ["salary"], "strategy": "median"}},
        ],
    }

    res = client.post(
        f"/api/v1/datasets/{dataset_id}/transforms/preview",
        headers=headers,
        json=preview_payload,
    )
    assert res.status_code == 200
    preview = res.json()

    assert preview["original_row_count"] == 5
    assert preview["transformed_row_count"] == 4  # Duplicate was dropped
    assert preview["rows_affected"] == 1
    assert len(preview["step_summaries"]) == 4

    # Check after-records: Name trimmed, duplicates gone, age and salary imputed
    records_after = preview["preview_after"]
    assert len(records_after) == 4
    for r in records_after:
        assert r["age"] is not None
        assert r["salary"] is not None
        assert not r["name"].startswith(" ")


def test_transformation_apply_as_new_dataset():
    """Verify executing recipe creates a new dataset with updated schema, file on disk, and profile."""
    token, ws_id = setup_user_and_workspace("apply_user@example.com", "Apply Analyst")
    headers = {"Authorization": f"Bearer {token}", "X-Workspace-ID": ws_id}

    csv_data = (
        "item,quantity,unit_price,department\n"
        "Widget A,10,5.50,Hardware\n"
        "Widget B,20,10.00,Hardware\n"
        "Gadget C,5,50.00,Electronics\n"
    )
    source_id = upload_test_csv(headers, "sales.csv", csv_data)

    recipe = {
        "name": "Enriched Inventory",
        "description": "Calculated total revenue and normalized department text",
        "save_as_new_dataset": True,
        "steps": [
            {
                "step_type": "derive_column",
                "params": {
                    "new_column": "total_revenue",
                    "operation": "multiply",
                    "operand_a": "quantity",
                    "operand_b": "unit_price",
                },
            },
            {
                "step_type": "text_transform",
                "params": {"columns": ["department"], "operation": "uppercase"},
            },
        ],
    }

    apply_res = client.post(
        f"/api/v1/datasets/{source_id}/transforms/apply",
        headers=headers,
        json=recipe,
    )
    assert apply_res.status_code == 201
    output = apply_res.json()

    assert output["name"] == "Enriched Inventory"
    assert output["dataset_id"] != source_id
    assert output["column_count"] == 5  # added 'total_revenue'
    assert output["row_count"] == 3
    assert output["steps_applied"] == 2

    # Verify the new dataset is retrievable with correct preview and schemas
    new_detail_res = client.get(f"/api/v1/datasets/{output['dataset_id']}", headers=headers)
    assert new_detail_res.status_code == 200
    detail = new_detail_res.json()
    cols = [c["name"] for c in detail["columns"]]
    assert "total_revenue" in cols

    # Verify revenue values in preview rows
    preview = detail["preview_rows"]
    assert preview[0]["total_revenue"] == 55.0  # 10 * 5.5
    assert preview[1]["total_revenue"] == 200.0  # 20 * 10
    assert preview[0]["department"] == "HARDWARE"


def test_transformation_apply_in_place_versioning():
    """Verify executing in-place transformation increments version and registers a snapshot."""
    token, ws_id = setup_user_and_workspace("inplace_user@example.com", "In-Place Analyst")
    headers = {"Authorization": f"Bearer {token}", "X-Workspace-ID": ws_id}

    csv_data = "col_a,col_b\n1,10\n2,20\n3,30\n"
    dataset_id = upload_test_csv(headers, "metrics.csv", csv_data)

    recipe = {
        "description": "Renamed col_a to id and doubled col_b",
        "save_as_new_dataset": False,
        "steps": [
            {
                "step_type": "rename_columns",
                "params": {"mapping": {"col_a": "metric_id"}},
            },
            {
                "step_type": "derive_column",
                "params": {
                    "new_column": "doubled_b",
                    "operation": "multiply",
                    "operand_a": "col_b",
                    "operand_b": 2,
                },
            },
        ],
    }

    apply_res = client.post(
        f"/api/v1/datasets/{dataset_id}/transforms/apply",
        headers=headers,
        json=recipe,
    )
    assert apply_res.status_code == 201
    output = apply_res.json()

    assert output["dataset_id"] == dataset_id
    assert output["version"] == 2

    # Check version history snapshots
    versions_res = client.get(f"/api/v1/datasets/{dataset_id}/versions", headers=headers)
    assert versions_res.status_code == 200
    versions = versions_res.json()
    assert len(versions) == 2
    assert versions[0]["version_number"] == 2
    assert "Renamed col_a" in versions[0]["change_summary"]


def test_outlier_treatment_and_filtering():
    """Verify Interquartile Range outlier clipping and relational row filtering."""
    token, ws_id = setup_user_and_workspace("outlier_user@example.com", "Outlier Analyst")
    headers = {"Authorization": f"Bearer {token}", "X-Workspace-ID": ws_id}

    # Value 1000 is an extreme outlier
    csv_data = (
        "id,val,category\n"
        "1,10,A\n"
        "2,12,A\n"
        "3,11,B\n"
        "4,13,B\n"
        "5,1000,A\n"
    )
    dataset_id = upload_test_csv(headers, "outliers.csv", csv_data)

    preview_payload = {
        "steps": [
            {
                "step_type": "handle_outliers",
                "params": {"columns": ["val"], "method": "iqr", "action": "clip", "factor": 1.5},
            },
            {
                "step_type": "filter_rows",
                "params": {"column": "category", "operator": "==", "value": "A"},
            },
        ],
    }

    res = client.post(
        f"/api/v1/datasets/{dataset_id}/transforms/preview",
        headers=headers,
        json=preview_payload,
    )
    assert res.status_code == 200
    preview = res.json()

    # Category A had 3 rows (ids 1, 2, 5)
    assert preview["transformed_row_count"] == 3
    # Extreme outlier (1000) should be clipped down to around <= 20
    row_5 = next(r for r in preview["preview_after"] if r["id"] == 5)
    assert row_5["val"] < 100.0


def test_cross_tenant_transforms_isolation():
    """Ensure users cannot preview or apply transformations on other tenants' datasets."""
    token_a, ws_a = setup_user_and_workspace("tenant_alpha@example.com", "Tenant Alpha")
    token_b, ws_b = setup_user_and_workspace("tenant_beta@example.com", "Tenant Beta")

    headers_a = {"Authorization": f"Bearer {token_a}", "X-Workspace-ID": ws_a}
    headers_b = {"Authorization": f"Bearer {token_b}", "X-Workspace-ID": ws_b}

    dataset_id = upload_test_csv(headers_a, "alpha.csv", "x,y\n1,2\n")

    # Tenant B attempts preview
    res_preview = client.post(
        f"/api/v1/datasets/{dataset_id}/transforms/preview",
        headers=headers_b,
        json={"steps": [{"step_type": "impute", "params": {"strategy": "mean"}}]},
    )
    assert res_preview.status_code == 404

    # Tenant B attempts apply
    res_apply = client.post(
        f"/api/v1/datasets/{dataset_id}/transforms/apply",
        headers=headers_b,
        json={"steps": [], "save_as_new_dataset": True},
    )
    assert res_apply.status_code == 404
