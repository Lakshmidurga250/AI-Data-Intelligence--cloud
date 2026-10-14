"""Automated tests for workspace multi-tenancy, RBAC roles, and isolation."""

import pytest
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def get_auth_token(email: str, name: str) -> str:
    """Helper to register and/or authenticate a user and retrieve bearer token."""
    client.post(
        "/api/v1/auth/register",
        json={"email": email, "full_name": name, "password": "SecurePassword123!"},
    )
    login_res = client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": "SecurePassword123!"},
    )
    return login_res.json()["access_token"]


def test_workspace_creation_and_listing():
    """Verify that a user can create a workspace and see it in their workspace list."""
    token = get_auth_token("bob@example.com", "Bob Engineer")
    headers = {"Authorization": f"Bearer {token}"}

    create_payload = {
        "name": "Finance Analytics Cluster",
        "description": "Production datasets for finance",
    }
    create_res = client.post("/api/v1/workspaces", json=create_payload, headers=headers)
    assert create_res.status_code == 201
    ws_data = create_res.json()
    assert ws_data["name"] == "Finance Analytics Cluster"
    assert ws_data["role"] == "owner"

    list_res = client.get("/api/v1/workspaces", headers=headers)
    assert list_res.status_code == 200
    workspaces = list_res.json()
    assert any(w["name"] == "Finance Analytics Cluster" for w in workspaces)


def test_workspace_isolation_cross_tenant_access_denied():
    """
    CRITICAL SECURITY CHECK:
    Verify that User A cannot access User B's workspace without explicit membership.
    """
    token_a = get_auth_token("tenant_a@example.com", "Tenant A")
    token_b = get_auth_token("tenant_b@example.com", "Tenant B")

    # Tenant A creates a private workspace
    create_res = client.post(
        "/api/v1/workspaces",
        json={"name": "Tenant A Secret Vault"},
        headers={"Authorization": f"Bearer {token_a}"},
    )
    ws_id = create_res.json()["id"]

    # Tenant B attempts to read Tenant A's workspace
    access_attempt = client.get(
        f"/api/v1/workspaces/{ws_id}",
        headers={"Authorization": f"Bearer {token_b}"},
    )
    assert access_attempt.status_code == 403
    assert "Access denied" in access_attempt.json()["detail"]


def test_workspace_member_invitation_and_rbac():
    """Verify that Owner can add a member, and member can then access the workspace."""
    token_owner = get_auth_token("owner@example.com", "Workspace Owner")
    token_member = get_auth_token("colleague@example.com", "Colleague")

    # Create workspace
    create_res = client.post(
        "/api/v1/workspaces",
        json={"name": "Collaborative ML Project"},
        headers={"Authorization": f"Bearer {token_owner}"},
    )
    ws_id = create_res.json()["id"]

    # Owner adds colleague as member
    add_member_res = client.post(
        f"/api/v1/workspaces/{ws_id}/members",
        json={"email": "colleague@example.com", "role": "member"},
        headers={"Authorization": f"Bearer {token_owner}"},
    )
    assert add_member_res.status_code == 201
    assert add_member_res.json()["role"] == "member"

    # Colleague can now access workspace
    member_access = client.get(
        f"/api/v1/workspaces/{ws_id}",
        headers={"Authorization": f"Bearer {token_member}"},
    )
    assert member_access.status_code == 200
    assert member_access.json()["id"] == ws_id


def test_rbac_member_cannot_add_other_members():
    """Verify that a standard member without admin/owner rights cannot invite others."""
    token_owner = get_auth_token("boss@example.com", "Boss")
    token_member = get_auth_token("viewer_user@example.com", "Viewer User")
    token_third = get_auth_token("third_party@example.com", "Third Party")

    # Create workspace
    create_res = client.post(
        "/api/v1/workspaces",
        json={"name": "Strict Compliance Workspace"},
        headers={"Authorization": f"Bearer {token_owner}"},
    )
    ws_id = create_res.json()["id"]

    # Add user as viewer
    client.post(
        f"/api/v1/workspaces/{ws_id}/members",
        json={"email": "viewer_user@example.com", "role": "viewer"},
        headers={"Authorization": f"Bearer {token_owner}"},
    )

    # Viewer attempts to add a third party
    illegal_invite = client.post(
        f"/api/v1/workspaces/{ws_id}/members",
        json={"email": "third_party@example.com", "role": "member"},
        headers={"Authorization": f"Bearer {token_member}"},
    )
    assert illegal_invite.status_code == 403
    assert "Only workspace Owners and Admins" in illegal_invite.json()["detail"]


def test_workspace_audit_logging():
    """Verify that workspace actions generate audit log entries."""
    token_owner = get_auth_token("auditor_owner@example.com", "Audit Owner")
    headers = {"Authorization": f"Bearer {token_owner}"}

    create_res = client.post(
        "/api/v1/workspaces",
        json={"name": "Audited Enterprise Workspace"},
        headers=headers,
    )
    ws_id = create_res.json()["id"]

    audit_res = client.get(f"/api/v1/workspaces/{ws_id}/audit-logs", headers=headers)
    assert audit_res.status_code == 200
    logs = audit_res.json()
    assert len(logs) >= 1
    assert any(log["action"] == "workspace.create" for log in logs)
