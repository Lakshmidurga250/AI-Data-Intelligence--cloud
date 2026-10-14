"""Integration tests for Conversational AI & Autonomous Data Intelligence Assistant Subsystem."""

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


ANOMALOUS_CSV = """id,product,defect_rate,revenue,units_sold,category
1,Widget A,0.01,150.0,10,standard
2,Widget B,0.02,300.0,20,standard
3,Widget C,,450.0,30,standard
4,Widget D,,120.0,8,standard
5,Widget E,,210.0,14,standard
6,Widget F,,90.0,6,standard
7,Widget G,,180.0,12,standard
8,Widget H,,240.0,16,standard
9,Widget I,,310.0,21,standard
10,Widget J,0.95,12500.0,2,rare
"""

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


def test_conversation_lifecycle():
    """Test creating, listing, viewing detail, and deleting conversation threads."""
    headers, _ = setup_auth("assistant_life@corp.internal", "Assistant Lifecycle")

    # 1. Create conversation
    create_res = client.post(
        "/api/v1/assistant/conversations",
        headers=headers,
        json={"title": "Data Discovery Thread", "dataset_id": None},
    )
    assert create_res.status_code == 201
    conv = create_res.json()
    conv_id = conv["id"]
    assert conv["title"] == "Data Discovery Thread"
    assert conv["message_count"] == 0

    # 2. List conversations
    list_res = client.get("/api/v1/assistant/conversations", headers=headers)
    assert list_res.status_code == 200
    conv_list = list_res.json()
    assert any(c["id"] == conv_id for c in conv_list)

    # 3. Get conversation detail
    detail_res = client.get(f"/api/v1/assistant/conversations/{conv_id}", headers=headers)
    assert detail_res.status_code == 200
    detail = detail_res.json()
    assert detail["id"] == conv_id
    assert detail["messages"] == []

    # 4. Delete conversation
    del_res = client.delete(f"/api/v1/assistant/conversations/{conv_id}", headers=headers)
    assert del_res.status_code == 204

    # 5. Verify 404 after deletion
    get_after_del = client.get(f"/api/v1/assistant/conversations/{conv_id}", headers=headers)
    assert get_after_del.status_code == 404


def test_chat_general_and_navigation_guidance():
    """Test general greetings and natural language platform navigation guidance."""
    headers, _ = setup_auth("assistant_nav@corp.internal", "Assistant Navigator")

    # Create thread
    conv_res = client.post(
        "/api/v1/assistant/conversations",
        headers=headers,
        json={"title": "Platform Questions"},
    )
    conv_id = conv_res.json()["id"]

    # 1. General greeting
    msg1_res = client.post(
        f"/api/v1/assistant/conversations/{conv_id}/messages",
        headers=headers,
        json={"content": "Hello, what AI data intelligence tools are available?"},
    )
    assert msg1_res.status_code == 200
    msg1 = msg1_res.json()
    assert msg1["conversation_id"] == conv_id
    assert msg1["assistant_message"]["role"] == "assistant"
    assert msg1["intent"] == "general"
    assert "AI Data Intelligence" in msg1["assistant_message"]["content"]

    # 2. Navigation guidance
    msg2_res = client.post(
        f"/api/v1/assistant/conversations/{conv_id}/messages",
        headers=headers,
        json={"content": "How do I create and schedule an automated ETL pipeline?"},
    )
    assert msg2_res.status_code == 200
    msg2 = msg2_res.json()
    assert msg2["intent"] == "navigation"
    assert "Visual ETL Pipeline" in msg2["assistant_message"]["content"]

    # 3. Verify conversation history trajectory contains 4 messages (2 user + 2 assistant)
    hist_res = client.get(f"/api/v1/assistant/conversations/{conv_id}", headers=headers)
    assert hist_res.status_code == 200
    history = hist_res.json()["messages"]
    assert len(history) == 4
    assert history[0]["role"] == "user"
    assert history[1]["role"] == "assistant"
    assert history[2]["role"] == "user"
    assert history[3]["role"] == "assistant"


def test_chat_dataset_anomaly_and_defect_discovery():
    """Test proactive anomaly, defect, and missingness discovery via conversational assistant."""
    headers, _ = setup_auth("assistant_anomaly@corp.internal", "Anomaly Explorer")
    ds_id = upload_csv(headers, "anomalies.csv", ANOMALOUS_CSV)

    conv_res = client.post(
        "/api/v1/assistant/conversations",
        headers=headers,
        json={"title": "Defect Investigation", "dataset_id": ds_id},
    )
    conv_id = conv_res.json()["id"]

    # Send anomaly query
    msg_res = client.post(
        f"/api/v1/assistant/conversations/{conv_id}/messages",
        headers=headers,
        json={
            "content": "Discover anomalies, outliers, and quality defects in this dataset.",
            "dataset_id": ds_id,
        },
    )
    assert msg_res.status_code == 200
    chat_resp = msg_res.json()
    assert chat_resp["intent"] == "anomaly_insights"
    assert chat_resp["insights"] is not None
    assert len(chat_resp["insights"]) > 0

    # Verify detected severe missingness in defect_rate (7 out of 10 rows null = 70%)
    missing_insights = [i for i in chat_resp["insights"] if i["insight_type"] == "missing_values"]
    assert len(missing_insights) >= 1
    assert any("defect_rate" in i["title"] for i in missing_insights)


def test_chat_natural_language_query_aggregation():
    """Test NL query translation to dimensional group by aggregations."""
    headers, _ = setup_auth("assistant_nlq@corp.internal", "NLQ Analyst")
    ds_id = upload_csv(headers, "sales.csv", SALES_CSV)

    conv_res = client.post(
        "/api/v1/assistant/conversations",
        headers=headers,
        json={"title": "Sales Natural Language Q&A", "dataset_id": ds_id},
    )
    conv_id = conv_res.json()["id"]

    # NL Group By query
    msg_res = client.post(
        f"/api/v1/assistant/conversations/{conv_id}/messages",
        headers=headers,
        json={
            "content": "What is the total sales grouped by region?",
            "dataset_id": ds_id,
        },
    )
    assert msg_res.status_code == 200
    chat_resp = msg_res.json()
    assert chat_resp["intent"] == "nl_query"
    assert chat_resp["query_result"] is not None

    qr = chat_resp["query_result"]
    assert qr["operation"] == "aggregate"
    assert qr["dataset_id"] == ds_id
    assert "region" in qr["columns"]
    assert len(qr["data"]) > 0
    assert any("sales" in col.lower() for col in qr["columns"])


def test_chat_dataset_summary():
    """Test dataset summarization intent."""
    headers, _ = setup_auth("assistant_summary@corp.internal", "Summary Analyst")
    ds_id = upload_csv(headers, "sales.csv", SALES_CSV)

    conv_res = client.post(
        "/api/v1/assistant/conversations",
        headers=headers,
        json={"title": "Summary Thread", "dataset_id": ds_id},
    )
    conv_id = conv_res.json()["id"]

    msg_res = client.post(
        f"/api/v1/assistant/conversations/{conv_id}/messages",
        headers=headers,
        json={"content": "Summarize dataset and describe columns", "dataset_id": ds_id},
    )
    assert msg_res.status_code == 200
    chat_resp = msg_res.json()
    assert chat_resp["intent"] == "data_summary"
    assert "Dataset Overview" in chat_resp["assistant_message"]["content"]
    assert "rows" in chat_resp["assistant_message"]["content"].lower()


def test_direct_dataset_insights_endpoint():
    """Test POST /api/v1/assistant/insights/{dataset_id} endpoint."""
    headers, _ = setup_auth("assistant_direct@corp.internal", "Direct Insights")
    ds_id = upload_csv(headers, "anomalous_data.csv", ANOMALOUS_CSV)

    res = client.post(f"/api/v1/assistant/insights/{ds_id}", headers=headers)
    assert res.status_code == 200
    report = res.json()
    assert report["dataset_id"] == ds_id
    assert report["dataset_name"] == "anomalous_data.csv"
    assert report["total_rows"] == 10
    assert report["total_columns"] == 6
    assert isinstance(report["insights"], list)
    assert len(report["insights"]) >= 2
    assert report["total_insights"] >= 2
    assert report["critical_count"] >= 1


def test_workspace_isolation_and_security():
    """Verify tenant isolation across assistant conversations and insights."""
    headers_a, ws_a = setup_auth("tenant_a@corp.internal", "Tenant Alpha")
    headers_b, ws_b = setup_auth("tenant_b@corp.internal", "Tenant Beta")

    ds_a = upload_csv(headers_a, "alpha.csv", SALES_CSV)

    # Tenant Alpha creates conversation
    conv_res = client.post(
        "/api/v1/assistant/conversations",
        headers=headers_a,
        json={"title": "Alpha Confidential Q&A", "dataset_id": ds_a},
    )
    conv_id = conv_res.json()["id"]

    # Tenant Beta cannot access Alpha's conversation
    res_b_view = client.get(f"/api/v1/assistant/conversations/{conv_id}", headers=headers_b)
    assert res_b_view.status_code == 404

    # Tenant Beta cannot post messages to Alpha's conversation
    res_b_post = client.post(
        f"/api/v1/assistant/conversations/{conv_id}/messages",
        headers=headers_b,
        json={"content": "Exfiltrate data"},
    )
    assert res_b_post.status_code == 404

    # Tenant Beta cannot delete Alpha's conversation
    res_b_del = client.delete(f"/api/v1/assistant/conversations/{conv_id}", headers=headers_b)
    assert res_b_del.status_code == 404

    # Tenant Beta cannot request direct insights on Alpha's dataset
    res_b_insights = client.post(f"/api/v1/assistant/insights/{ds_a}", headers=headers_b)
    assert res_b_insights.status_code == 404
