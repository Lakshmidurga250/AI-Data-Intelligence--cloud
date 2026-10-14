"""Automated integration tests for multi-format tabular ingestion (CSV, JSON, Excel, Parquet)."""

import io
import json
import pandas as pd
import pytest
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def setup_user_and_workspace(email: str, name: str):
    """Register user, log in, create workspace, return (token, workspace_id)."""
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
        json={"name": f"{name}'s Ingestion Lab"},
        headers=headers,
    )
    ws_id = ws_res.json()["id"]
    return token, ws_id


def test_csv_ingestion_and_schema_inference():
    """Verify streaming upload and schema detection for CSV data."""
    token, ws_id = setup_user_and_workspace("csv_user@example.com", "CSV Analyst")
    headers = {
        "Authorization": f"Bearer {token}",
        "X-Workspace-ID": ws_id,
    }

    csv_content = (
        "employee_id,department,salary,active\n"
        "101,Engineering,95000.50,True\n"
        "102,Product,88000.00,True\n"
        "103,Marketing,72000.00,False\n"
    ).encode("utf-8")

    files = {"file": ("employees.csv", io.BytesIO(csv_content), "text/csv")}
    data = {"name": "Corporate Roster", "description": "Active employee headcount"}

    res = client.post("/api/v1/datasets/upload", headers=headers, files=files, data=data)
    assert res.status_code == 201
    payload = res.json()
    assert payload["format"] == "csv"
    assert payload["row_count"] == 3
    assert payload["column_count"] == 4
    assert len(payload["columns"]) == 4
    assert len(payload["preview_rows"]) == 3

    # Verify column schemas
    col_names = [c["name"] for c in payload["columns"]]
    assert "employee_id" in col_names
    assert "department" in col_names
    assert "salary" in col_names
    assert "active" in col_names


def test_json_ingestion():
    """Verify ingestion of JSON records."""
    token, ws_id = setup_user_and_workspace("json_user@example.com", "JSON Developer")
    headers = {
        "Authorization": f"Bearer {token}",
        "X-Workspace-ID": ws_id,
    }

    json_records = [
        {"customer_id": "C-01", "score": 98.5, "churned": False},
        {"customer_id": "C-02", "score": 45.0, "churned": True},
        {"customer_id": "C-03", "score": 88.0, "churned": False},
    ]
    json_bytes = json.dumps(json_records).encode("utf-8")
    files = {"file": ("customers.json", io.BytesIO(json_bytes), "application/json")}

    res = client.post("/api/v1/datasets/upload", headers=headers, files=files)
    assert res.status_code == 201
    payload = res.json()
    assert payload["format"] == "json"
    assert payload["row_count"] == 3
    assert payload["column_count"] == 3
    assert payload["preview_rows"][0]["customer_id"] == "C-01"


def test_excel_ingestion():
    """Verify ingestion of Microsoft Excel (.xlsx) files."""
    token, ws_id = setup_user_and_workspace("excel_user@example.com", "Excel Specialist")
    headers = {
        "Authorization": f"Bearer {token}",
        "X-Workspace-ID": ws_id,
    }

    # Generate synthetic Excel workbook
    df = pd.DataFrame({
        "sku": ["SKU-A", "SKU-B", "SKU-C", "SKU-D"],
        "price": [19.99, 49.99, 9.99, 120.00],
        "inventory": [100, 25, 300, 5],
    })
    excel_buffer = io.BytesIO()
    df.to_excel(excel_buffer, index=False, engine="openpyxl")
    excel_buffer.seek(0)

    files = {
        "file": (
            "inventory_q3.xlsx",
            excel_buffer,
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
    }

    res = client.post("/api/v1/datasets/upload", headers=headers, files=files)
    assert res.status_code == 201
    payload = res.json()
    assert payload["format"] == "excel"
    assert payload["row_count"] == 4
    assert payload["column_count"] == 3


def test_parquet_ingestion():
    """Verify ingestion of Apache Parquet columnar files."""
    token, ws_id = setup_user_and_workspace("parquet_user@example.com", "Big Data Engineer")
    headers = {
        "Authorization": f"Bearer {token}",
        "X-Workspace-ID": ws_id,
    }

    # Generate synthetic Parquet buffer
    df = pd.DataFrame({
        "timestamp_ms": [1700000000000, 1700000001000, 1700000002000],
        "sensor_temp": [22.4, 23.1, 22.8],
        "status": ["OK", "OK", "WARN"],
    })
    parquet_buffer = io.BytesIO()
    df.to_parquet(parquet_buffer, engine="pyarrow")
    parquet_buffer.seek(0)

    files = {"file": ("telemetry.parquet", parquet_buffer, "application/octet-stream")}

    res = client.post("/api/v1/datasets/upload", headers=headers, files=files)
    assert res.status_code == 201
    payload = res.json()
    assert payload["format"] == "parquet"
    assert payload["row_count"] == 3
    assert payload["column_count"] == 3


def test_cross_tenant_dataset_isolation():
    """
    CRITICAL SECURITY CHECK:
    Verify that Tenant B cannot access or list datasets uploaded by Tenant A.
    """
    token_a, ws_a = setup_user_and_workspace("tenant_alpha@example.com", "Alpha Corp")
    token_b, ws_b = setup_user_and_workspace("tenant_beta@example.com", "Beta Corp")

    # Alpha uploads confidential data
    csv_bytes = b"secret_id,code\n1,CONFIDENTIAL\n"
    files = {"file": ("alpha_secrets.csv", io.BytesIO(csv_bytes), "text/csv")}
    upload_res = client.post(
        "/api/v1/datasets/upload",
        headers={"Authorization": f"Bearer {token_a}", "X-Workspace-ID": ws_a},
        files=files,
    )
    dataset_id = upload_res.json()["id"]

    # Beta attempts to read Alpha's dataset using Beta's workspace header
    beta_access = client.get(
        f"/api/v1/datasets/{dataset_id}",
        headers={"Authorization": f"Bearer {token_b}", "X-Workspace-ID": ws_b},
    )
    assert beta_access.status_code == 404

    # Beta attempts to read Alpha's dataset with Alpha's workspace header (cross-tenant header spoof)
    spoof_access = client.get(
        f"/api/v1/datasets/{dataset_id}",
        headers={"Authorization": f"Bearer {token_b}", "X-Workspace-ID": ws_a},
    )
    assert spoof_access.status_code == 403


def test_viewer_role_cannot_upload_datasets():
    """Verify that a user with Viewer role is prevented from uploading files."""
    token_owner, ws_id = setup_user_and_workspace("data_boss@example.com", "Data Boss")
    token_viewer, _ = setup_user_and_workspace("view_only@example.com", "View Only User")

    # Add user as viewer
    client.post(
        f"/api/v1/workspaces/{ws_id}/members",
        json={"email": "view_only@example.com", "role": "viewer"},
        headers={"Authorization": f"Bearer {token_owner}"},
    )

    # Viewer attempts upload
    csv_bytes = b"id,val\n1,10\n"
    files = {"file": ("test.csv", io.BytesIO(csv_bytes), "text/csv")}
    res = client.post(
        "/api/v1/datasets/upload",
        headers={"Authorization": f"Bearer {token_viewer}", "X-Workspace-ID": ws_id},
        files=files,
    )
    assert res.status_code == 403
    assert "Viewers cannot upload datasets" in res.json()["detail"]


def test_unsupported_file_extension_rejected():
    """Verify that unsupported file extensions are safely rejected with 400 Bad Request."""
    token, ws_id = setup_user_and_workspace("format_checker@example.com", "Format Checker")
    headers = {
        "Authorization": f"Bearer {token}",
        "X-Workspace-ID": ws_id,
    }

    files = {"file": ("malicious.exe", io.BytesIO(b"binary"), "application/octet-stream")}
    res = client.post("/api/v1/datasets/upload", headers=headers, files=files)
    assert res.status_code == 400
    assert "Unsupported file format" in res.json()["detail"]


def test_dataset_deletion():
    """Verify dataset deletion removes database record and storage file."""
    token, ws_id = setup_user_and_workspace("delete_tester@example.com", "Delete Tester")
    headers = {
        "Authorization": f"Bearer {token}",
        "X-Workspace-ID": ws_id,
    }

    csv_bytes = b"item,qty\nbolts,100\n"
    files = {"file": ("items.csv", io.BytesIO(csv_bytes), "text/csv")}
    upload_res = client.post("/api/v1/datasets/upload", headers=headers, files=files)
    dataset_id = upload_res.json()["id"]

    # Delete dataset
    del_res = client.delete(f"/api/v1/datasets/{dataset_id}", headers=headers)
    assert del_res.status_code == 204

    # Verify subsequent lookup returns 404
    get_res = client.get(f"/api/v1/datasets/{dataset_id}", headers=headers)
    assert get_res.status_code == 404
