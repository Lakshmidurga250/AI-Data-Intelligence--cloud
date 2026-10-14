"""Automated test suite for dataset statistical profiling, correlation analysis, and versioning."""

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
        json={"name": f"{name}'s Profiling Workspace"},
        headers=headers,
    )
    ws_id = ws_res.json()["id"]
    return token, ws_id


def test_statistical_profiling_metrics():
    """Verify in-depth statistical summary computation for numeric and categorical columns."""
    token, ws_id = setup_user_and_workspace("profiler_test@example.com", "Profiler Analyst")
    headers = {
        "Authorization": f"Bearer {token}",
        "X-Workspace-ID": ws_id,
    }

    # CSV with numeric, categorical, zeros, and missing values
    csv_data = (
        "age,income,department\n"
        "25,50000,Engineering\n"
        "30,60000,Engineering\n"
        "35,70000,Sales\n"
        "40,0,Sales\n"
        ",80000,Marketing\n"
    ).encode("utf-8")

    upload_res = client.post(
        "/api/v1/datasets/upload",
        headers=headers,
        files={"file": ("profile_data.csv", io.BytesIO(csv_data), "text/csv")},
        data={"name": "Workforce Analytics"},
    )
    assert upload_res.status_code == 201
    dataset_id = upload_res.json()["id"]

    # Request statistical profile
    res = client.get(f"/api/v1/datasets/{dataset_id}/profile", headers=headers)
    assert res.status_code == 200
    profile = res.json()

    assert profile["dataset_id"] == dataset_id
    assert profile["row_count"] == 5
    assert profile["column_count"] == 3
    assert profile["duplicate_rows_count"] == 0
    assert profile["completeness_score"] > 90.0  # 1 null out of 15 cells = 93.33%

    # Inspect column profiles
    col_map = {col["name"]: col for col in profile["columns"]}
    assert "age" in col_map
    assert "income" in col_map
    assert "department" in col_map

    # Age column
    age_col = col_map["age"]
    assert age_col["is_numeric"] is True
    assert age_col["null_count"] == 1
    assert age_col["numeric_stats"]["min"] == 25.0
    assert age_col["numeric_stats"]["max"] == 40.0
    assert age_col["numeric_stats"]["mean"] == 32.5
    assert age_col["numeric_stats"]["median"] == 32.5

    # Income column
    income_col = col_map["income"]
    assert income_col["is_numeric"] is True
    assert income_col["null_count"] == 0
    assert income_col["numeric_stats"]["zeros_count"] == 1
    assert income_col["numeric_stats"]["min"] == 0.0
    assert income_col["numeric_stats"]["max"] == 80000.0

    # Department column
    dept_col = col_map["department"]
    assert dept_col["is_categorical"] is True
    assert dept_col["null_count"] == 0
    assert dept_col["categorical_stats"]["distinct_count"] == 3
    top_vals = {v["value"]: v["count"] for v in dept_col["categorical_stats"]["top_values"]}
    assert top_vals["Engineering"] == 2
    assert top_vals["Sales"] == 2
    assert top_vals["Marketing"] == 1


def test_pearson_correlation_analysis():
    """Verify linear correlation matrix extraction between numeric features."""
    token, ws_id = setup_user_and_workspace("corr_user@example.com", "Correlation Analyst")
    headers = {
        "Authorization": f"Bearer {token}",
        "X-Workspace-ID": ws_id,
    }

    # x and y are perfectly positively correlated (r=1.0), x and z perfectly negatively correlated (r=-1.0)
    csv_data = (
        "x,y,z\n"
        "1,10,100\n"
        "2,20,80\n"
        "3,30,60\n"
        "4,40,40\n"
        "5,50,20\n"
    ).encode("utf-8")

    upload_res = client.post(
        "/api/v1/datasets/upload",
        headers=headers,
        files={"file": ("correlations.csv", io.BytesIO(csv_data), "text/csv")},
        data={"name": "Linear Metrics"},
    )
    dataset_id = upload_res.json()["id"]

    res = client.get(f"/api/v1/datasets/{dataset_id}/profile", headers=headers)
    assert res.status_code == 200
    profile = res.json()

    correlations = profile["correlations"]
    assert len(correlations) >= 3

    # Check pair x and y
    xy_pair = next(
        (c for c in correlations if (c["column_a"] == "x" and c["column_b"] == "y") or (c["column_a"] == "y" and c["column_b"] == "x")),
        None,
    )
    assert xy_pair is not None
    assert round(xy_pair["coefficient"], 2) == 1.0

    # Check pair x and z
    xz_pair = next(
        (c for c in correlations if (c["column_a"] == "x" and c["column_b"] == "z") or (c["column_a"] == "z" and c["column_b"] == "x")),
        None,
    )
    assert xz_pair is not None
    assert round(xz_pair["coefficient"], 2) == -1.0


def test_profile_refresh():
    """Verify on-demand profile refreshing recalculates stats successfully."""
    token, ws_id = setup_user_and_workspace("refresh_user@example.com", "Refresh Analyst")
    headers = {
        "Authorization": f"Bearer {token}",
        "X-Workspace-ID": ws_id,
    }

    csv_data = "metric_a,metric_b\n10,20\n30,40\n".encode("utf-8")
    upload_res = client.post(
        "/api/v1/datasets/upload",
        headers=headers,
        files={"file": ("refresh.csv", io.BytesIO(csv_data), "text/csv")},
    )
    dataset_id = upload_res.json()["id"]

    refresh_res = client.post(f"/api/v1/datasets/{dataset_id}/profile/refresh", headers=headers)
    assert refresh_res.status_code == 200
    refreshed_profile = refresh_res.json()
    assert refreshed_profile["dataset_id"] == dataset_id
    assert refreshed_profile["row_count"] == 2


def test_dataset_versioning_lifecycle():
    """Verify immutable version snapshots, incremental version numbering, and timeline queries."""
    token, ws_id = setup_user_and_workspace("version_user@example.com", "Version Manager")
    headers = {
        "Authorization": f"Bearer {token}",
        "X-Workspace-ID": ws_id,
    }

    csv_data = "id,value\n1,100\n2,200\n".encode("utf-8")
    upload_res = client.post(
        "/api/v1/datasets/upload",
        headers=headers,
        files={"file": ("snapshot_test.csv", io.BytesIO(csv_data), "text/csv")},
        data={"name": "Financial Ledger"},
    )
    dataset_id = upload_res.json()["id"]

    # Initial upload should automatically generate version 1
    versions_res = client.get(f"/api/v1/datasets/{dataset_id}/versions", headers=headers)
    assert versions_res.status_code == 200
    versions = versions_res.json()
    assert len(versions) == 1
    assert versions[0]["version_number"] == 1
    assert versions[0]["change_summary"] == "Initial dataset upload"
    assert versions[0]["row_count"] == 2

    # Create explicit version 2 snapshot
    create_res = client.post(
        f"/api/v1/datasets/{dataset_id}/versions",
        headers=headers,
        json={"change_summary": "Quarterly audit reconciliation"},
    )
    assert create_res.status_code == 201
    v2 = create_res.json()
    assert v2["version_number"] == 2
    assert v2["change_summary"] == "Quarterly audit reconciliation"

    # Query versions list again (should have 2 items, latest first)
    list_res = client.get(f"/api/v1/datasets/{dataset_id}/versions", headers=headers)
    assert list_res.status_code == 200
    updated_versions = list_res.json()
    assert len(updated_versions) == 2
    assert updated_versions[0]["version_number"] == 2
    assert updated_versions[1]["version_number"] == 1


def test_cross_workspace_profiling_isolation():
    """Ensure profiles and version snapshots cannot be accessed across tenant boundaries."""
    token_a, ws_a = setup_user_and_workspace("tenant_a@example.com", "Tenant A")
    token_b, ws_b = setup_user_and_workspace("tenant_b@example.com", "Tenant B")

    headers_a = {"Authorization": f"Bearer {token_a}", "X-Workspace-ID": ws_a}
    headers_b = {"Authorization": f"Bearer {token_b}", "X-Workspace-ID": ws_b}

    csv_data = "col1,col2\n1,2\n3,4\n".encode("utf-8")
    upload_res = client.post(
        "/api/v1/datasets/upload",
        headers=headers_a,
        files={"file": ("tenant_a_data.csv", io.BytesIO(csv_data), "text/csv")},
    )
    dataset_id = upload_res.json()["id"]

    # Tenant B tries to get profile for Tenant A's dataset
    res_profile = client.get(f"/api/v1/datasets/{dataset_id}/profile", headers=headers_b)
    assert res_profile.status_code == 404

    # Tenant B tries to get versions for Tenant A's dataset
    res_versions = client.get(f"/api/v1/datasets/{dataset_id}/versions", headers=headers_b)
    assert res_versions.status_code == 404

    # Tenant B tries to create version on Tenant A's dataset
    res_create = client.post(
        f"/api/v1/datasets/{dataset_id}/versions",
        headers=headers_b,
        json={"change_summary": "Unauthorized snapshot attempt"},
    )
    assert res_create.status_code == 404
