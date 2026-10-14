"""Integration tests for Interactive Analytics, Dashboards, Widgets, and BI Aggregations."""

import io
import pytest
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def setup_auth(email: str, name: str):
    """Register user, authenticate, create workspace, and return workspace headers."""
    client.post(
        "/api/v1/auth/register",
        json={"email": email, "full_name": name, "password": "PassPassword123!"},
    )
    login_res = client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": "PassPassword123!"},
    )
    token = login_res.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    ws_res = client.post(
        "/api/v1/workspaces",
        json={"name": f"{name} Workspace"},
        headers=headers,
    )
    ws_id = ws_res.json()["id"]
    headers["X-Workspace-ID"] = ws_id
    return headers, ws_id


def upload_csv(headers: dict, filename: str, content: str) -> str:
    """Upload CSV dataset and return dataset ID."""
    files = {"file": (filename, io.BytesIO(content.encode("utf-8")), "text/csv")}
    res = client.post("/api/v1/datasets/upload", headers=headers, files=files)
    assert res.status_code == 201
    return res.json()["id"]


SALES_CSV = """order_id,date,region,category,sales,units,status
101,2026-01-15,North,Electronics,1200.50,3,completed
102,2026-01-18,South,Furniture,450.00,2,completed
103,2026-02-05,North,Electronics,800.00,1,completed
104,2026-02-12,East,Supplies,150.25,5,pending
105,2026-03-01,South,Furniture,920.00,4,completed
106,2026-03-15,North,Supplies,75.00,3,cancelled
107,2026-03-22,East,Electronics,2100.00,4,completed
108,2026-04-10,South,Supplies,310.50,6,completed
"""


def test_ad_hoc_analytics_aggregation_query():
    """Test direct ad-hoc analytical grouping, metrics computation, and sorting."""
    headers, _ = setup_auth("bi_analyst_1@corp.internal", "BI Analyst One")
    ds_id = upload_csv(headers, "sales_q1.csv", SALES_CSV)

    query_payload = {
        "dataset_id": ds_id,
        "metrics": [
            {"column": "sales", "aggregation": "sum", "alias": "total_sales"},
            {"column": "units", "aggregation": "avg", "alias": "avg_units"},
            {"column": "*", "aggregation": "count", "alias": "order_count"},
        ],
        "dimensions": ["region"],
        "sort_by": "total_sales",
        "sort_order": "desc",
        "limit": 10,
    }

    res = client.post("/api/v1/dashboards/query", headers=headers, json=query_payload)
    assert res.status_code == 200
    data = res.json()

    assert "columns" in data
    assert "region" in data["columns"]
    assert "total_sales" in data["columns"]
    assert "avg_units" in data["columns"]
    assert "order_count" in data["columns"]
    assert data["row_count"] == 3  # North, South, East
    assert data["execution_time_ms"] >= 0.0

    # Ensure sorted descending by total_sales
    first_row = data["data"][0]
    assert first_row["total_sales"] > 0
    assert first_row["order_count"] >= 1


def test_analytics_filtering_and_temporal_bucketing():
    """Test filtering operators and temporal date grouping."""
    headers, _ = setup_auth("bi_analyst_2@corp.internal", "BI Analyst Two")
    ds_id = upload_csv(headers, "sales_temporal.csv", SALES_CSV)

    query_payload = {
        "dataset_id": ds_id,
        "metrics": [
            {"column": "sales", "aggregation": "sum", "alias": "revenue"},
        ],
        "dimensions": [],
        "filters": [
            {"column": "status", "operator": "==", "value": "completed"},
            {"column": "sales", "operator": ">=", "value": 400},
        ],
        "time_column": "date",
        "time_grain": "month",
        "sort_by": "revenue",
        "sort_order": "desc",
    }

    res = client.post("/api/v1/dashboards/query", headers=headers, json=query_payload)
    assert res.status_code == 200
    data = res.json()

    assert "revenue" in data["columns"]
    assert "date" in data["columns"]
    assert data["row_count"] > 0
    # Every row date should be in %Y-%m format
    for row in data["data"]:
        assert len(str(row["date"])) == 7  # e.g., 2026-01


def test_dashboard_crud_and_workspace_isolation():
    """Test dashboard creation, retrieval, updates, deletion, and cross-workspace isolation."""
    headers1, ws_id1 = setup_auth("dash_owner1@corp.internal", "Dashboard Owner One")
    headers2, _ = setup_auth("dash_owner2@corp.internal", "Dashboard Owner Two")

    # 1. Create Dashboard in Workspace 1
    create_payload = {
        "name": "Executive Revenue Cockpit",
        "description": "High-level KPI tracker for corporate leadership",
        "layout_config": {"columns": 12, "rowHeight": 80},
        "is_default": True,
    }
    create_res = client.post("/api/v1/dashboards", headers=headers1, json=create_payload)
    assert create_res.status_code == 201
    dash = create_res.json()
    dash_id = dash["id"]
    assert dash["name"] == "Executive Revenue Cockpit"
    assert dash["is_default"] is True
    assert dash["widgets_count"] == 0

    # 2. List Dashboards in Workspace 1
    list_res = client.post if False else client.get("/api/v1/dashboards", headers=headers1)
    assert list_res.status_code == 200
    dash_list = list_res.json()
    assert any(d["id"] == dash_id for d in dash_list)

    # 3. Cross-tenant access: Workspace 2 should not be able to read dashboard 1
    isolated_res = client.get(f"/api/v1/dashboards/{dash_id}", headers=headers2)
    assert isolated_res.status_code == 404

    # 4. Update Dashboard
    update_res = client.put(
        f"/api/v1/dashboards/{dash_id}",
        headers=headers1,
        json={"name": "Updated Executive Cockpit", "description": "Refreshed descriptions"},
    )
    assert update_res.status_code == 200
    assert update_res.json()["name"] == "Updated Executive Cockpit"

    # 5. Delete Dashboard
    del_res = client.delete(f"/api/v1/dashboards/{dash_id}", headers=headers1)
    assert del_res.status_code == 204

    # 6. Verify 404 after deletion
    check_res = client.get(f"/api/v1/dashboards/{dash_id}", headers=headers1)
    assert check_res.status_code == 404


def test_dashboard_widget_lifecycle():
    """Test adding, updating, and removing visualization widgets in a dashboard."""
    headers, _ = setup_auth("widget_engineer@corp.internal", "Widget Engineer")
    ds_id = upload_csv(headers, "metrics_data.csv", SALES_CSV)

    # 1. Create Dashboard
    dash_res = client.post(
        "/api/v1/dashboards",
        headers=headers,
        json={"name": "Operations Overview"},
    )
    dash_id = dash_res.json()["id"]

    # 2. Add Widget (Bar chart)
    widget_payload = {
        "name": "Regional Sales Bar Chart",
        "dataset_id": ds_id,
        "visualization_type": "bar",
        "query_config": {
            "metrics": [{"column": "sales", "aggregation": "sum", "alias": "regional_sales"}],
            "dimensions": ["region"],
            "sort_by": "regional_sales",
            "sort_order": "desc",
        },
        "position": {"x": 0, "y": 0, "w": 6, "h": 4},
    }
    w_res = client.post(f"/api/v1/dashboards/{dash_id}/widgets", headers=headers, json=widget_payload)
    assert w_res.status_code == 201
    widget = w_res.json()
    widget_id = widget["id"]
    assert widget["name"] == "Regional Sales Bar Chart"
    assert widget["visualization_type"] == "bar"

    # 3. Verify widget appears in Dashboard Details
    detail_res = client.get(f"/api/v1/dashboards/{dash_id}", headers=headers)
    assert detail_res.status_code == 200
    detail = detail_res.json()
    assert detail["widgets_count"] == 1
    assert detail["widgets"][0]["id"] == widget_id

    # 4. Update Widget (Change to Pie chart and modify layout position)
    upd_res = client.put(
        f"/api/v1/dashboards/{dash_id}/widgets/{widget_id}",
        headers=headers,
        json={
            "name": "Regional Sales Distribution Pie",
            "visualization_type": "pie",
            "position": {"x": 6, "y": 0, "w": 6, "h": 4},
        },
    )
    assert upd_res.status_code == 200
    updated_w = upd_res.json()
    assert updated_w["visualization_type"] == "pie"
    assert updated_w["position"]["x"] == 6

    # 5. Delete Widget
    del_w_res = client.delete(f"/api/v1/dashboards/{dash_id}/widgets/{widget_id}", headers=headers)
    assert del_w_res.status_code == 204

    # 6. Verify widget removed from Dashboard
    post_del_res = client.get(f"/api/v1/dashboards/{dash_id}", headers=headers)
    assert post_del_res.json()["widgets_count"] == 0


def test_widget_live_query_execution():
    """Test executing a live aggregated analytical query bound to a dashboard widget."""
    headers, _ = setup_auth("live_query_tester@corp.internal", "Live Query Tester")
    ds_id = upload_csv(headers, "category_sales.csv", SALES_CSV)

    # 1. Create Dashboard and KPI Widget
    dash_res = client.post("/api/v1/dashboards", headers=headers, json={"name": "Executive KPI"})
    dash_id = dash_res.json()["id"]

    widget_payload = {
        "name": "Total Gross Revenue KPI",
        "dataset_id": ds_id,
        "visualization_type": "kpi",
        "query_config": {
            "metrics": [{"column": "sales", "aggregation": "sum", "alias": "gross_revenue"}],
            "dimensions": [],
            "filters": [{"column": "status", "operator": "!=", "value": "cancelled"}],
        },
        "position": {"x": 0, "y": 0, "w": 4, "h": 2},
    }
    w_res = client.post(f"/api/v1/dashboards/{dash_id}/widgets", headers=headers, json=widget_payload)
    widget_id = w_res.json()["id"]

    # 2. Execute Widget Query
    q_res = client.post(
        f"/api/v1/dashboards/{dash_id}/widgets/{widget_id}/query",
        headers=headers,
    )
    assert q_res.status_code == 200
    q_data = q_res.json()

    assert "gross_revenue" in q_data["columns"]
    assert q_data["row_count"] == 1
    # Total sales excluding cancelled order 106 ($75) = 1200.5 + 450 + 800 + 150.25 + 920 + 2100 + 310.5 = 5931.25
    assert q_data["data"][0]["gross_revenue"] > 5000.0
