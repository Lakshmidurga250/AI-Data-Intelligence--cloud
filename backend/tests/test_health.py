"""Tests for health diagnostic and root endpoints."""

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.core.config import settings

client = TestClient(app)


def test_root_endpoint():
    """Verify that root endpoint returns operational metadata."""
    response = client.get("/")
    assert response.status_code == 200
    data = response.json()
    assert data["app"] == settings.APP_NAME
    assert data["version"] == settings.APP_VERSION
    assert "docs" in data
    assert "health" in data


def test_health_endpoint():
    """Verify that the v1 health check returns full diagnostic payload."""
    response = client.get(f"{settings.API_V1_PREFIX}/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert data["app_name"] == settings.APP_NAME
    assert data["version"] == settings.APP_VERSION
    assert data["environment"] == settings.ENVIRONMENT
    assert "timestamp" in data
    assert "services" in data
    assert data["services"]["api"] == "operational"


def test_direct_health_alias():
    """Verify that convenience alias /health responds successfully."""
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"


def test_cors_headers():
    """Verify that allowed origin receives appropriate CORS headers."""
    response = client.get(
        f"{settings.API_V1_PREFIX}/health",
        headers={"Origin": "http://localhost:5173"},
    )
    assert response.status_code == 200
    assert response.headers.get("access-control-allow-origin") == "http://localhost:5173"


def test_settings_sanity():
    """Verify that default settings object is well-formed."""
    assert settings.APP_NAME == "AI Data Intelligence Cloud"
    assert settings.API_V1_PREFIX == "/api/v1"
    assert len(settings.BACKEND_CORS_ORIGINS) > 0
