"""Automated tests for user authentication, registration, and token handling."""

import pytest
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_register_success():
    """Verify that user registration succeeds and auto-creates an isolated workspace."""
    payload = {
        "email": "alice@example.com",
        "full_name": "Alice Innovator",
        "password": "SecurePassword123!",
    }
    response = client.post("/api/v1/auth/register", json=payload)
    assert response.status_code == 201
    data = response.json()
    assert "access_token" in data
    assert data["token_type"] == "bearer"
    assert data["email"] == "alice@example.com"
    assert "user_id" in data


def test_register_duplicate_email():
    """Verify that registering with an existing email returns 400 Bad Request."""
    payload = {
        "email": "alice@example.com",
        "full_name": "Alice Duplicate",
        "password": "SecurePassword123!",
    }
    response = client.post("/api/v1/auth/register", json=payload)
    assert response.status_code == 400
    assert "already exists" in response.json()["detail"]


def test_login_success():
    """Verify that a registered user can log in and receive an access token."""
    login_payload = {
        "email": "alice@example.com",
        "password": "SecurePassword123!",
    }
    response = client.post("/api/v1/auth/login", json=login_payload)
    assert response.status_code == 200
    data = response.json()
    assert "access_token" in data
    assert data["email"] == "alice@example.com"


def test_login_invalid_password():
    """Verify that invalid password returns 401 Unauthorized."""
    login_payload = {
        "email": "alice@example.com",
        "password": "WrongPassword!",
    }
    response = client.post("/api/v1/auth/login", json=login_payload)
    assert response.status_code == 401
    assert "Incorrect email or password" in response.json()["detail"]


def test_login_nonexistent_user():
    """Verify that nonexistent email returns 401 Unauthorized."""
    login_payload = {
        "email": "nobody@example.com",
        "password": "SecurePassword123!",
    }
    response = client.post("/api/v1/auth/login", json=login_payload)
    assert response.status_code == 401


def test_get_me_unauthenticated():
    """Verify that protected /me endpoint requires authentication."""
    response = client.get("/api/v1/auth/me")
    assert response.status_code == 401


def test_get_me_authenticated():
    """Verify that /me endpoint returns user profile and list of workspaces."""
    login_payload = {
        "email": "alice@example.com",
        "password": "SecurePassword123!",
    }
    login_res = client.post("/api/v1/auth/login", json=login_payload)
    token = login_res.json()["access_token"]

    response = client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["email"] == "alice@example.com"
    assert data["full_name"] == "Alice Innovator"
    assert len(data["workspaces"]) >= 1
    assert data["workspaces"][0]["role"] == "owner"
