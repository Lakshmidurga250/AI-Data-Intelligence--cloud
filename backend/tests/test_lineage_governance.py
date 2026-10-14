"""Integration tests for Data Lineage, DAG Traversal, Impact Analysis, and Governance Policies."""

import io
import pytest
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def setup_auth(email: str, name: str):
    """Helper to register user, log in, create workspace, and return auth headers."""
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
    """Helper to upload CSV and return dataset id."""
    files = {"file": (filename, io.BytesIO(content.encode("utf-8")), "text/csv")}
    res = client.post("/api/v1/datasets/upload", headers=headers, files=files)
    assert res.status_code == 201
    return res.json()["id"]


def test_lineage_manual_nodes_edges_and_graph():
    """Verify manual lineage node registration, edge creation, and graph queries."""
    headers, _ = setup_auth("lineage_tester@corp.com", "Lineage Tester")

    # 1. Register 3 nodes
    n1 = client.post(
        "/api/v1/lineage/nodes",
        headers=headers,
        json={"name": "Raw Ingestion Source", "node_type": "external_source"},
    ).json()
    n2 = client.post(
        "/api/v1/lineage/nodes",
        headers=headers,
        json={"name": "Cleaned Dataset", "node_type": "dataset"},
    ).json()
    n3 = client.post(
        "/api/v1/lineage/nodes",
        headers=headers,
        json={"name": "Daily Quality Suite", "node_type": "quality_suite"},
    ).json()

    # 2. Connect them: n1 -> n2 -> n3
    e1 = client.post(
        "/api/v1/lineage/edges",
        headers=headers,
        json={
            "source_node_id": n1["id"],
            "target_node_id": n2["id"],
            "edge_type": "data_flow",
            "transformation_summary": "ETL Ingestion",
        },
    )
    assert e1.status_code == 201

    e2 = client.post(
        "/api/v1/lineage/edges",
        headers=headers,
        json={
            "source_node_id": n2["id"],
            "target_node_id": n3["id"],
            "edge_type": "validation",
            "transformation_summary": "Contract check",
        },
    )
    assert e2.status_code == 201

    # 3. Retrieve graph
    graph_res = client.get("/api/v1/lineage/graph", headers=headers)
    assert graph_res.status_code == 200
    graph = graph_res.json()

    node_ids = {n["id"] for n in graph["nodes"]}
    assert n1["id"] in node_ids
    assert n2["id"] in node_ids
    assert n3["id"] in node_ids
    assert graph["root_node_count"] >= 1
    assert graph["leaf_node_count"] >= 1


def test_lineage_impact_analysis_traversal():
    """Verify upstream provenance and downstream impact analysis BFS traversal."""
    headers, _ = setup_auth("impact_tester@corp.com", "Impact Tester")

    # Construct DAG: A -> B -> C and B -> D
    a = client.post("/api/v1/lineage/nodes", headers=headers, json={"name": "Source A", "node_type": "dataset"}).json()
    b = client.post("/api/v1/lineage/nodes", headers=headers, json={"name": "Transform Pipeline B", "node_type": "pipeline"}).json()
    c = client.post("/api/v1/lineage/nodes", headers=headers, json={"name": "Sink Dataset C", "node_type": "dataset"}).json()
    d = client.post("/api/v1/lineage/nodes", headers=headers, json={"name": "Quality Suite D", "node_type": "quality_suite"}).json()

    client.post("/api/v1/lineage/edges", headers=headers, json={"source_node_id": a["id"], "target_node_id": b["id"], "edge_type": "data_flow"})
    client.post("/api/v1/lineage/edges", headers=headers, json={"source_node_id": b["id"], "target_node_id": c["id"], "edge_type": "data_flow"})
    client.post("/api/v1/lineage/edges", headers=headers, json={"source_node_id": b["id"], "target_node_id": d["id"], "edge_type": "validation"})

    # Impact analysis centered on B
    res = client.get(f"/api/v1/lineage/impact/{b['id']}", headers=headers)
    assert res.status_code == 200
    impact = res.json()

    assert impact["target_node"]["id"] == b["id"]
    upstream_ids = [n["id"] for n in impact["upstream_ancestors"]]
    downstream_ids = [n["id"] for n in impact["downstream_dependents"]]

    assert a["id"] in upstream_ids
    assert c["id"] in downstream_ids
    assert d["id"] in downstream_ids
    assert impact["total_impacted_datasets"] == 1
    assert impact["total_impacted_quality_suites"] == 1


def test_lineage_auto_sync():
    """Verify automated scanning of workspace datasets and pipelines."""
    headers, _ = setup_auth("sync_tester@corp.com", "Sync Tester")

    csv_data = "customer_id,name,spend\n101,Acme,450.0\n102,Beta,1200.5\n"
    ds_id = upload_csv(headers, "sync_dataset.csv", csv_data)

    # Trigger auto sync
    sync_res = client.post("/api/v1/lineage/sync", headers=headers)
    assert sync_res.status_code == 200
    stats = sync_res.json()

    assert stats["total_nodes"] >= 2  # Ingestion source + dataset
    assert stats["total_edges"] >= 1  # Ingestion -> dataset

    graph_res = client.get("/api/v1/lineage/graph", headers=headers)
    graph = graph_res.json()
    assert any(n["resource_id"] == ds_id for n in graph["nodes"])


def test_governance_policy_lifecycle():
    """Verify CRUD lifecycle for governance retention and classification policies."""
    headers, _ = setup_auth("gov_tester@corp.com", "Gov Tester")

    # 1. Create policy
    create_payload = {
        "name": "GDPR 90-Day Retention & Masking",
        "description": "European consumer protection policy",
        "classification_tier": "CONFIDENTIAL",
        "retention_days": 90,
        "compliance_framework": "GDPR",
        "data_steward": "compliance_officer@corp.com",
        "auto_purge_enabled": False,
        "is_active": True,
    }
    create_res = client.post("/api/v1/governance/policies", headers=headers, json=create_payload)
    assert create_res.status_code == 201
    policy = create_res.json()
    policy_id = policy["id"]
    assert policy["name"] == "GDPR 90-Day Retention & Masking"
    assert policy["retention_days"] == 90

    # 2. List policies
    list_res = client.get("/api/v1/governance/policies", headers=headers)
    assert list_res.status_code == 200
    assert any(p["id"] == policy_id for p in list_res.json())

    # 3. Delete policy
    del_res = client.delete(f"/api/v1/governance/policies/{policy_id}", headers=headers)
    assert del_res.status_code == 204


def test_pii_classification_and_retention_audit():
    """Verify automated PII scanning heuristics, column sensitivity tagging, and retention evaluation."""
    headers, _ = setup_auth("pii_tester@corp.com", "PII Tester")

    # Upload dataset containing sensitive attributes
    csv_content = (
        "user_id,email,social_security,phone,revenue\n"
        "1,alice@example.com,123-45-6789,+1-555-123-4567,95000\n"
        "2,bob@enterprise.org,987-65-4321,+1-555-987-6543,120000\n"
        "3,carol@cloud.io,456-78-1234,+1-555-456-7890,82000\n"
    )
    ds_id = upload_csv(headers, "customers_pii.csv", csv_content)

    # 1. Run PII Classification Scan
    scan_res = client.post(f"/api/v1/governance/classify/{ds_id}", headers=headers)
    assert scan_res.status_code == 200
    scan = scan_res.json()

    assert scan["dataset_id"] == ds_id
    assert scan["scanned_columns_count"] == 5
    assert scan["flagged_columns_count"] >= 3
    assert scan["overall_classification"] == "RESTRICTED_PII"
    assert scan["is_quarantined"] is True

    findings_map = {f["column_name"]: f for f in scan["findings"]}
    assert "email" in findings_map
    assert findings_map["email"]["sensitivity_label"] == "PII_EMAIL"
    assert "social_security" in findings_map
    assert findings_map["social_security"]["sensitivity_label"] == "PII_SSN"
    assert "phone" in findings_map
    assert findings_map["phone"]["sensitivity_label"] == "PII_PHONE"

    # Masked samples check
    assert any("***" in v for v in findings_map["email"]["sample_masked_values"])

    # 2. Check Governance Tags endpoint
    tags_res = client.get(f"/api/v1/governance/tags/{ds_id}", headers=headers)
    assert tags_res.status_code == 200
    tags = tags_res.json()
    assert len(tags) >= 3

    # 3. Check Compliance Audit Logs
    audit_res = client.get("/api/v1/governance/audit-logs", headers=headers)
    assert audit_res.status_code == 200
    logs = audit_res.json()
    assert any(l["event_type"] == "pii_scan" and l["dataset_id"] == ds_id for l in logs)

    # 4. Evaluate Retention Compliance
    ret_res = client.post("/api/v1/governance/retention/evaluate", headers=headers)
    assert ret_res.status_code == 200
    ret_data = ret_res.json()
    assert "status" in ret_data
