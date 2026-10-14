"""Integration tests for AutoML Training, Model Registry, Versioning, and Real-Time Inference."""

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


CLASSIFICATION_CSV = """age,income,credit_score,tenure,plan_type,churn
25,45000,680,1,basic,0
32,62000,720,3,premium,0
48,85000,790,5,premium,0
22,30000,590,1,basic,1
58,95000,810,8,enterprise,0
41,54000,640,2,basic,1
36,71000,740,4,premium,0
29,38000,610,1,basic,1
45,88000,780,6,enterprise,0
52,92000,800,7,enterprise,0
27,42000,630,2,basic,1
39,67000,710,3,premium,0
"""

REGRESSION_CSV = """years_exp,education_level,projects_completed,certifications,salary
1,bachelor,2,1,55000
3,bachelor,5,2,68000
5,master,8,3,85000
2,bachelor,3,1,60000
8,master,14,4,115000
10,phd,18,5,140000
4,bachelor,6,2,75000
6,master,10,3,92000
12,phd,22,6,160000
7,master,11,3,98000
"""


def test_automl_classification_training_and_registry():
    """Verify classification benchmark training, champion selection, and model registration."""
    headers, _ = setup_auth("ml_classifier@corp.com", "Classifier Lead")
    ds_id = upload_csv(headers, "churn_records.csv", CLASSIFICATION_CSV)

    # 1. Train AutoML Model
    train_res = client.post(
        "/api/v1/ml/train",
        headers=headers,
        json={
            "dataset_id": ds_id,
            "model_name": "Customer Churn Predictor",
            "target_column": "churn",
            "task_type": "classification",
            "test_size": 0.25,
            "description": "AutoML classifier benchmark for customer attrition",
        },
    )
    assert train_res.status_code == 201
    data = train_res.json()

    assert data["model_name"] == "Customer Churn Predictor"
    assert data["task_type"] == "classification"
    assert data["target_column"] == "churn"
    assert len(data["model_id"]) == 36
    assert len(data["version_id"]) == 36
    assert "accuracy" in data["metrics"]
    assert "f1_score" in data["metrics"]
    assert len(data["feature_names"]) > 0
    assert len(data["feature_importances"]) > 0
    assert len(data["leaderboard"]) >= 2
    assert any(item["is_best"] for item in data["leaderboard"])

    model_id = data["model_id"]

    # 2. List Models
    models_res = client.post if False else client.get("/api/v1/ml/models", headers=headers)
    assert models_res.status_code == 200
    models_list = models_res.json()
    assert len(models_list) == 1
    assert models_list[0]["id"] == model_id
    assert models_list[0]["versions_count"] == 1
    assert models_list[0]["active_version"]["algorithm"] == data["best_algorithm"]

    # 3. Model Detail
    detail_res = client.get(f"/api/v1/ml/models/{model_id}", headers=headers)
    assert detail_res.status_code == 200
    detail = detail_res.json()
    assert len(detail["versions"]) == 1
    assert detail["versions"][0]["status"] == "champion"


def test_automl_regression_training_and_leaderboard():
    """Verify regression benchmark training, R2/RMSE scorecard, and experiment tracking."""
    headers, _ = setup_auth("ml_regressor@corp.com", "Regression Scientist")
    ds_id = upload_csv(headers, "salary_data.csv", REGRESSION_CSV)

    train_res = client.post(
        "/api/v1/ml/train",
        headers=headers,
        json={
            "dataset_id": ds_id,
            "model_name": "Salary Estimator",
            "target_column": "salary",
            "task_type": "regression",
            "test_size": 0.2,
            "description": "Compensation prediction based on experience and education",
        },
    )
    assert train_res.status_code == 201
    data = train_res.json()

    assert data["task_type"] == "regression"
    assert "r2_score" in data["metrics"]
    assert "rmse" in data["metrics"]
    assert "mae" in data["metrics"]
    assert len(data["leaderboard"]) >= 2

    # Verify Experiments query
    exp_res = client.get("/api/v1/ml/experiments", headers=headers)
    assert exp_res.status_code == 200
    exp_list = exp_res.json()
    assert len(exp_list) == 1
    assert exp_list[0]["status"] == "completed"
    assert exp_list[0]["best_algorithm"] == data["best_algorithm"]


def test_model_realtime_inference_prediction():
    """Verify real-time online inference with single and batch record payloads."""
    headers, _ = setup_auth("ml_infer@corp.com", "Inference Engineer")
    ds_id = upload_csv(headers, "churn_data.csv", CLASSIFICATION_CSV)

    train_res = client.post(
        "/api/v1/ml/train",
        headers=headers,
        json={
            "dataset_id": ds_id,
            "model_name": "Churn Realtime Model",
            "target_column": "churn",
            "task_type": "classification",
        },
    )
    model_id = train_res.json()["model_id"]

    # 1. Single sample prediction
    single_req = {
        "inputs": {
            "age": 28,
            "income": 40000,
            "credit_score": 620,
            "tenure": 2,
            "plan_type": "basic",
        }
    }
    pred_res = client.post(f"/api/v1/ml/models/{model_id}/predict", headers=headers, json=single_req)
    assert pred_res.status_code == 200
    res_data = pred_res.json()

    assert len(res_data["predictions"]) == 1
    assert res_data["predictions"][0] in ["0", "1", 0, 1]
    assert res_data["latency_ms"] >= 0.0
    if res_data["probabilities"]:
        assert len(res_data["probabilities"]) == 1
        assert sum(res_data["probabilities"][0].values()) == pytest.approx(1.0, rel=1e-2)

    # 2. Batch sample prediction
    batch_req = {
        "inputs": [
            {"age": 25, "income": 35000, "credit_score": 600, "tenure": 1, "plan_type": "basic"},
            {"age": 55, "income": 95000, "credit_score": 800, "tenure": 7, "plan_type": "enterprise"},
        ]
    }
    batch_res = client.post(f"/api/v1/ml/models/{model_id}/predict", headers=headers, json=batch_req)
    assert batch_res.status_code == 200
    batch_data = batch_res.json()
    assert len(batch_data["predictions"]) == 2


def test_model_versioning_and_promotion_lifecycle():
    """Verify model version increments and promotion of candidate to champion."""
    headers, _ = setup_auth("ml_versioner@corp.com", "Model MLOps")
    ds_id = upload_csv(headers, "churn_v1.csv", CLASSIFICATION_CSV)

    # Train version 1
    res_v1 = client.post(
        "/api/v1/ml/train",
        headers=headers,
        json={
            "dataset_id": ds_id,
            "model_name": "Multi Version Model",
            "target_column": "churn",
            "task_type": "classification",
        },
    ).json()
    model_id = res_v1["model_id"]
    v1_id = res_v1["version_id"]

    # Train version 2 with same model name
    res_v2 = client.post(
        "/api/v1/ml/train",
        headers=headers,
        json={
            "dataset_id": ds_id,
            "model_name": "Multi Version Model",
            "target_column": "churn",
            "task_type": "classification",
        },
    ).json()
    v2_id = res_v2["version_id"]

    detail = client.get(f"/api/v1/ml/models/{model_id}", headers=headers).json()
    assert len(detail["versions"]) == 2
    assert detail["active_version_id"] == v2_id

    # Promote version 1 back to champion
    promote_res = client.post(
        f"/api/v1/ml/models/{model_id}/versions/{v1_id}/promote",
        headers=headers,
    )
    assert promote_res.status_code == 200
    assert promote_res.json()["status"] == "champion"

    # Verify active_version_id updated
    updated_detail = client.get(f"/api/v1/ml/models/{model_id}", headers=headers).json()
    assert updated_detail["active_version_id"] == v1_id


def test_model_deletion_and_isolation_guards():
    """Verify model deletion and cross-tenant workspace authorization boundaries."""
    headers_a, ws_a = setup_auth("ml_tenant_a@corp.com", "Tenant A Lead")
    headers_b, ws_b = setup_auth("ml_tenant_b@corp.com", "Tenant B Lead")

    ds_id = upload_csv(headers_a, "tenant_a.csv", CLASSIFICATION_CSV)
    train_res = client.post(
        "/api/v1/ml/train",
        headers=headers_a,
        json={
            "dataset_id": ds_id,
            "model_name": "Tenant A Secret Model",
            "target_column": "churn",
            "task_type": "classification",
        },
    ).json()
    model_id = train_res["model_id"]

    # Tenant B tries to inspect Tenant A model -> 404
    cross_res = client.get(f"/api/v1/ml/models/{model_id}", headers=headers_b)
    assert cross_res.status_code == 404

    # Delete model in Tenant A
    del_res = client.delete(f"/api/v1/ml/models/{model_id}", headers=headers_a)
    assert del_res.status_code == 200

    # Model no longer exists
    get_res = client.get(f"/api/v1/ml/models/{model_id}", headers=headers_a)
    assert get_res.status_code == 404
