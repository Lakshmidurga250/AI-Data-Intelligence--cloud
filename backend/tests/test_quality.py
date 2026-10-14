"""Integration tests for Data Quality Rules Engine, Evaluations, and Alerts."""

import io
import pandas as pd
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.services.quality.evaluator import (
    compute_health_grade,
    evaluate_single_rule,
    evaluate_suite_on_dataframe,
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


def test_evaluator_unit_rules():
    """Unit test individual rule evaluation functions."""
    data = {
        "id": [1, 2, 3, 4, 5],
        "email": ["alice@corp.com", "bob@corp.com", "carol@corp.com", "invalid-email", "dave@corp.com"],
        "age": [25, 30, 45, 120, 29],
        "status": ["active", "pending", "active", "suspended", "active"],
        "notes": ["ok", "", "done", None, "reviewed"],
    }
    df = pd.DataFrame(data)

    # 1. Null threshold check
    res_null = evaluate_single_rule(
        df=df,
        rule_id="r1",
        rule_name="Notes null check",
        rule_type="null_threshold",
        target_column="notes",
        parameters={"max_null_pct": 10.0},
    )
    assert res_null.passed is False  # 2 out of 5 are null/empty (40% > 10%)
    assert res_null.failed_rows == 2

    # 2. Uniqueness check
    res_unique = evaluate_single_rule(
        df=df,
        rule_id="r2",
        rule_name="ID uniqueness",
        rule_type="uniqueness",
        target_column="id",
        parameters={"min_unique_pct": 100.0},
    )
    assert res_unique.passed is True
    assert res_unique.failed_rows == 0

    # 3. Value range check
    res_range = evaluate_single_rule(
        df=df,
        rule_id="r3",
        rule_name="Age range check",
        rule_type="value_range",
        target_column="age",
        parameters={"min": 18, "max": 100},
    )
    assert res_range.passed is False  # 120 > 100
    assert res_range.failed_rows == 1

    # 4. Regex match check
    res_regex = evaluate_single_rule(
        df=df,
        rule_id="r4",
        rule_name="Email format check",
        rule_type="regex_match",
        target_column="email",
        parameters={"pattern": r"^[\w\.-]+@[\w\.-]+\.\w+$"},
    )
    assert res_regex.passed is False  # 'invalid-email' fails
    assert res_regex.failed_rows == 1

    # 5. Set membership check
    res_set = evaluate_single_rule(
        df=df,
        rule_id="r5",
        rule_name="Status membership",
        rule_type="set_membership",
        target_column="status",
        parameters={"allowed_values": ["active", "pending"]},
    )
    assert res_set.passed is False  # 'suspended' is not allowed
    assert res_set.failed_rows == 1

    # 6. Expression check
    res_expr = evaluate_single_rule(
        df=df,
        rule_id="r6",
        rule_name="Age positive check",
        rule_type="expression",
        target_column="age",
        parameters={"expression": "age > 0"},
    )
    assert res_expr.passed is True

    # Health grade calculations
    assert compute_health_grade(95.0) == "A"
    assert compute_health_grade(85.0) == "B"
    assert compute_health_grade(75.0) == "C"
    assert compute_health_grade(65.0) == "D"
    assert compute_health_grade(50.0) == "F"


def test_suite_crud_and_rule_management():
    """Verify QualityRuleSuite creation, updating, listing, and rule add/delete."""
    token, ws_id = setup_user_and_workspace("quality_lead@company.com", "Quality Lead")
    headers = {"Authorization": f"Bearer {token}", "X-Workspace-ID": ws_id}

    # 1. Create suite
    create_payload = {
        "name": "Customer Data Hygiene Suite",
        "description": "Validates customer master record completeness and integrity",
        "rules": [
            {
                "name": "Customer ID must be unique",
                "rule_type": "uniqueness",
                "target_column": "customer_id",
                "parameters": {"min_unique_pct": 100.0},
                "severity": "critical",
            },
            {
                "name": "Email format validity",
                "rule_type": "regex_match",
                "target_column": "email",
                "parameters": {"pattern": r"^[\w\.-]+@[\w\.-]+\.\w+$"},
                "severity": "warning",
            },
        ],
    }
    create_res = client.post("/api/v1/quality/suites", json=create_payload, headers=headers)
    assert create_res.status_code == 201
    suite_data = create_res.json()
    suite_id = suite_data["id"]
    assert suite_data["name"] == "Customer Data Hygiene Suite"
    assert len(suite_data["rules"]) == 2

    # 2. List suites
    list_res = client.get("/api/v1/quality/suites", headers=headers)
    assert list_res.status_code == 200
    assert any(s["id"] == suite_id for s in list_res.json())

    # 3. Get single suite
    get_res = client.get(f"/api/v1/quality/suites/{suite_id}", headers=headers)
    assert get_res.status_code == 200
    assert get_res.json()["id"] == suite_id

    # 4. Add rule to suite
    rule_payload = {
        "name": "Age must be >= 18",
        "rule_type": "value_range",
        "target_column": "age",
        "parameters": {"min": 18, "max": 120},
        "severity": "critical",
    }
    add_rule_res = client.post(f"/api/v1/quality/suites/{suite_id}/rules", json=rule_payload, headers=headers)
    assert add_rule_res.status_code == 201
    new_rule_id = add_rule_res.json()["id"]

    # Verify suite now has 3 rules
    updated_suite = client.get(f"/api/v1/quality/suites/{suite_id}", headers=headers).json()
    assert len(updated_suite["rules"]) == 3

    # 5. Delete rule
    del_rule_res = client.delete(f"/api/v1/quality/rules/{new_rule_id}", headers=headers)
    assert del_rule_res.status_code == 204

    # Verify suite back to 2 rules
    re_suite = client.get(f"/api/v1/quality/suites/{suite_id}", headers=headers).json()
    assert len(re_suite["rules"]) == 2

    # 6. Update suite
    upd_res = client.put(
        f"/api/v1/quality/suites/{suite_id}",
        json={"name": "Updated Customer Hygiene Suite"},
        headers=headers,
    )
    assert upd_res.status_code == 200
    assert upd_res.json()["name"] == "Updated Customer Hygiene Suite"

    # 7. Delete suite
    del_suite_res = client.delete(f"/api/v1/quality/suites/{suite_id}", headers=headers)
    assert del_suite_res.status_code == 204


def test_quality_evaluation_clean_dataset():
    """Verify evaluation on a high-quality dataset produces Grade A, 100% score, and 0 alerts."""
    token, ws_id = setup_user_and_workspace("clean_eval@company.com", "Clean Evaluator")
    headers = {"Authorization": f"Bearer {token}", "X-Workspace-ID": ws_id}

    # Upload clean CSV
    clean_csv = """customer_id,email,age,status
101,alice@example.com,28,active
102,bob@example.com,34,active
103,charlie@example.com,45,pending
104,dana@example.com,22,active
"""
    ds_id = upload_test_csv(headers, "clean_customers.csv", clean_csv)

    # Create suite
    suite_payload = {
        "name": "Clean Customers Suite",
        "dataset_id": ds_id,
        "rules": [
            {
                "name": "Customer ID Uniqueness",
                "rule_type": "uniqueness",
                "target_column": "customer_id",
                "parameters": {"min_unique_pct": 100.0},
                "severity": "critical",
            },
            {
                "name": "Valid Email Syntax",
                "rule_type": "regex_match",
                "target_column": "email",
                "parameters": {"pattern": r"^[\w\.-]+@[\w\.-]+\.\w+$"},
                "severity": "critical",
            },
            {
                "name": "Adult Age Bounds",
                "rule_type": "value_range",
                "target_column": "age",
                "parameters": {"min": 18, "max": 100},
                "severity": "warning",
            },
            {
                "name": "Allowed Status",
                "rule_type": "set_membership",
                "target_column": "status",
                "parameters": {"allowed_values": ["active", "pending"]},
                "severity": "critical",
            },
        ],
    }
    s_res = client.post("/api/v1/quality/suites", json=suite_payload, headers=headers)
    assert s_res.status_code == 201
    suite_id = s_res.json()["id"]

    # Execute evaluation
    eval_res = client.post(f"/api/v1/quality/suites/{suite_id}/evaluate", headers=headers)
    assert eval_res.status_code == 200
    eval_data = eval_res.json()
    assert eval_data["score"] == 100.0
    assert eval_data["grade"] == "A"
    assert eval_data["total_rules"] == 4
    assert eval_data["passed_rules"] == 4
    assert eval_data["failed_rules"] == 0

    # Verify no alerts created
    alerts_res = client.get("/api/v1/quality/alerts", headers=headers)
    assert alerts_res.status_code == 200
    assert len(alerts_res.json()) == 0


def test_quality_evaluation_dirty_dataset_and_alerts():
    """Verify evaluation on a dirty dataset captures violations, computes lower grade, and raises alerts."""
    token, ws_id = setup_user_and_workspace("dirty_eval@company.com", "Dirty Evaluator")
    headers = {"Authorization": f"Bearer {token}", "X-Workspace-ID": ws_id}

    # Upload dirty CSV (duplicate ID, invalid email, out of bounds age, disallowed status)
    dirty_csv = """customer_id,email,age,status
101,alice@example.com,28,active
101,not-an-email,150,banned
102,carol@example.com,33,unknown
"""
    ds_id = upload_test_csv(headers, "dirty_customers.csv", dirty_csv)

    suite_payload = {
        "name": "Strict Verification Suite",
        "dataset_id": ds_id,
        "rules": [
            {
                "name": "Strict ID Uniqueness",
                "rule_type": "uniqueness",
                "target_column": "customer_id",
                "parameters": {"min_unique_pct": 100.0},
                "severity": "critical",
            },
            {
                "name": "Valid Email Pattern",
                "rule_type": "regex_match",
                "target_column": "email",
                "parameters": {"pattern": r"^[\w\.-]+@[\w\.-]+\.\w+$"},
                "severity": "critical",
            },
            {
                "name": "Age under 100",
                "rule_type": "value_range",
                "target_column": "age",
                "parameters": {"min": 18, "max": 100},
                "severity": "warning",
            },
            {
                "name": "Standard Status",
                "rule_type": "set_membership",
                "target_column": "status",
                "parameters": {"allowed_values": ["active", "pending"]},
                "severity": "critical",
            },
        ],
    }
    s_res = client.post("/api/v1/quality/suites", json=suite_payload, headers=headers)
    suite_id = s_res.json()["id"]

    eval_res = client.post(f"/api/v1/quality/suites/{suite_id}/evaluate", headers=headers)
    assert eval_res.status_code == 200
    run_data = eval_res.json()
    assert run_data["score"] == 0.0  # all 4 rules failed
    assert run_data["grade"] == "F"
    assert run_data["failed_rules"] == 4
    assert len(run_data["rule_results"]) == 4

    # Verify violations samples
    for r in run_data["rule_results"]:
        assert r["passed"] is False
        assert len(r["sample_violations"]) > 0

    # Verify Alert was generated
    alerts_res = client.get("/api/v1/quality/alerts", headers=headers)
    assert alerts_res.status_code == 200
    alerts = alerts_res.json()
    assert len(alerts) >= 1
    alert = alerts[0]
    assert alert["severity"] == "critical"
    assert alert["is_acknowledged"] is False

    # Acknowledge Alert
    ack_res = client.post(f"/api/v1/quality/alerts/{alert['id']}/ack", headers=headers)
    assert ack_res.status_code == 200
    assert ack_res.json()["is_acknowledged"] is True

    # Check run details endpoint
    run_detail_res = client.get(f"/api/v1/quality/runs/{run_data['id']}", headers=headers)
    assert run_detail_res.status_code == 200
    assert run_detail_res.json()["id"] == run_data["id"]


def test_quality_tenancy_isolation():
    """Verify cross-workspace quality suite access is blocked."""
    token_a, ws_a = setup_user_and_workspace("tenant_a@company.com", "Tenant A")
    headers_a = {"Authorization": f"Bearer {token_a}", "X-Workspace-ID": ws_a}

    token_b, ws_b = setup_user_and_workspace("tenant_b@company.com", "Tenant B")
    headers_b = {"Authorization": f"Bearer {token_b}", "X-Workspace-ID": ws_b}

    # User A creates suite
    s_res = client.post(
        "/api/v1/quality/suites",
        json={"name": "Tenant A Secret Suite", "rules": []},
        headers=headers_a,
    )
    suite_a_id = s_res.json()["id"]

    # User B tries to view suite A -> 404
    cross_get = client.get(f"/api/v1/quality/suites/{suite_a_id}", headers=headers_b)
    assert cross_get.status_code == 404

    # User B tries to delete suite A -> 404
    cross_del = client.delete(f"/api/v1/quality/suites/{suite_a_id}", headers=headers_b)
    assert cross_del.status_code == 404
