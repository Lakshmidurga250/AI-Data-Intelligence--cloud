/**
 * Workspace management and RBAC service for AI Data Intelligence Cloud
 */

import { getAuthHeaders, type WorkspaceSummary } from './auth';

export interface WorkspaceMember {
  id: string;
  workspace_id: string;
  user_id: string;
  role: 'owner' | 'admin' | 'member' | 'viewer';
  created_at: string;
  user_email?: string;
  user_name?: string;
}

export interface AuditLogItem {
  id: string;
  workspace_id?: string;
  user_id?: string;
  action: string;
  resource_type: string;
  resource_id: string;
  details: string;
  ip_address?: string;
  created_at: string;
}

const ACTIVE_WS_KEY = 'aidata_active_workspace_id';
const API_BASE_URL = import.meta.env.VITE_API_URL || '';

export function getActiveWorkspaceId(): string | null {
  return localStorage.getItem(ACTIVE_WS_KEY);
}

export function setActiveWorkspaceId(workspaceId: string): void {
  localStorage.setItem(ACTIVE_WS_KEY, workspaceId);
}

export async function listWorkspaces(): Promise<WorkspaceSummary[]> {
  const res = await fetch(`${API_BASE_URL}/api/v1/workspaces`, {
    method: 'GET',
    headers: getAuthHeaders(),
  });
  if (!res.ok) {
    throw new Error(`Failed to list workspaces (HTTP ${res.status})`);
  }
  return await res.json();
}

export async function createWorkspace(
  name: string,
  description?: string,
  slug?: string
): Promise<WorkspaceSummary> {
  const res = await fetch(`${API_BASE_URL}/api/v1/workspaces`, {
    method: 'POST',
    headers: getAuthHeaders(),
    body: JSON.stringify({ name, description, slug }),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || `Failed to create workspace (HTTP ${res.status})`);
  }
  return await res.json();
}

export async function getWorkspaceMembers(workspaceId: string): Promise<WorkspaceMember[]> {
  const res = await fetch(`${API_BASE_URL}/api/v1/workspaces/${workspaceId}/members`, {
    method: 'GET',
    headers: getAuthHeaders(),
  });
  if (!res.ok) {
    throw new Error(`Failed to fetch members (HTTP ${res.status})`);
  }
  return await res.json();
}

export async function addWorkspaceMember(
  workspaceId: string,
  email: string,
  role: 'admin' | 'member' | 'viewer'
): Promise<WorkspaceMember> {
  const res = await fetch(`${API_BASE_URL}/api/v1/workspaces/${workspaceId}/members`, {
    method: 'POST',
    headers: getAuthHeaders(),
    body: JSON.stringify({ email, role }),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || `Failed to add member (HTTP ${res.status})`);
  }
  return await res.json();
}

export async function getWorkspaceAuditLogs(workspaceId: string): Promise<AuditLogItem[]> {
  const res = await fetch(`${API_BASE_URL}/api/v1/workspaces/${workspaceId}/audit-logs`, {
    method: 'GET',
    headers: getAuthHeaders(),
  });
  if (!res.ok) {
    throw new Error(`Failed to fetch audit logs (HTTP ${res.status})`);
  }
  return await res.json();
}
