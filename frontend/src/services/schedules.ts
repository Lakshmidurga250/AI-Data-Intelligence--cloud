/**
 * Recurring ETL pipeline scheduling and evaluation API client.
 */

import { getAuthHeaders } from './auth';
import type { JobTaskSummary } from './jobs';
import { getActiveWorkspaceId } from './workspaces';

export interface JobScheduleCreate {
  pipeline_id: string;
  name: string;
  description?: string;
  cron_expression: string;
  is_active?: boolean;
}

export interface JobScheduleUpdate {
  name?: string;
  description?: string;
  cron_expression?: string;
  is_active?: boolean;
}

export interface JobScheduleRead {
  id: string;
  workspace_id: string;
  pipeline_id: string;
  name: string;
  description?: string | null;
  cron_expression: string;
  is_active: boolean;
  last_run_at?: string | null;
  next_run_at?: string | null;
  created_at: string;
  updated_at: string;
}

const API_BASE_URL = import.meta.env.VITE_API_URL || '';

function getWorkspaceHeader(workspaceIdOverride?: string): Record<string, string> {
  const wsId = workspaceIdOverride || getActiveWorkspaceId();
  if (!wsId) {
    throw new Error('No active workspace selected.');
  }
  return { 'X-Workspace-ID': wsId };
}

export async function listSchedules(
  isActive?: boolean,
  workspaceIdOverride?: string
): Promise<JobScheduleRead[]> {
  const params = new URLSearchParams();
  if (isActive !== undefined) {
    params.append('is_active', isActive.toString());
  }

  const queryStr = params.toString() ? `?${params.toString()}` : '';
  const res = await fetch(`${API_BASE_URL}/api/v1/schedules${queryStr}`, {
    method: 'GET',
    headers: {
      ...getAuthHeaders(),
      ...getWorkspaceHeader(workspaceIdOverride),
    },
  });

  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || `Failed to list schedules (HTTP ${res.status})`);
  }

  return await res.json();
}

export async function getScheduleDetails(
  scheduleId: string,
  workspaceIdOverride?: string
): Promise<JobScheduleRead> {
  const res = await fetch(`${API_BASE_URL}/api/v1/schedules/${scheduleId}`, {
    method: 'GET',
    headers: {
      ...getAuthHeaders(),
      ...getWorkspaceHeader(workspaceIdOverride),
    },
  });

  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || `Failed to retrieve schedule details (HTTP ${res.status})`);
  }

  return await res.json();
}

export async function createSchedule(
  payload: JobScheduleCreate,
  workspaceIdOverride?: string
): Promise<JobScheduleRead> {
  const res = await fetch(`${API_BASE_URL}/api/v1/schedules`, {
    method: 'POST',
    headers: {
      ...getAuthHeaders(),
      ...getWorkspaceHeader(workspaceIdOverride),
      'Content-Type': 'application/json',
    },
    body: JSON.stringify(payload),
  });

  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || `Failed to register schedule (HTTP ${res.status})`);
  }

  return await res.json();
}

export async function updateSchedule(
  scheduleId: string,
  payload: JobScheduleUpdate,
  workspaceIdOverride?: string
): Promise<JobScheduleRead> {
  const res = await fetch(`${API_BASE_URL}/api/v1/schedules/${scheduleId}`, {
    method: 'PUT',
    headers: {
      ...getAuthHeaders(),
      ...getWorkspaceHeader(workspaceIdOverride),
      'Content-Type': 'application/json',
    },
    body: JSON.stringify(payload),
  });

  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || `Failed to update schedule (HTTP ${res.status})`);
  }

  return await res.json();
}

export async function deleteSchedule(
  scheduleId: string,
  workspaceIdOverride?: string
): Promise<{ status: string; id: string }> {
  const res = await fetch(`${API_BASE_URL}/api/v1/schedules/${scheduleId}`, {
    method: 'DELETE',
    headers: {
      ...getAuthHeaders(),
      ...getWorkspaceHeader(workspaceIdOverride),
    },
  });

  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || `Failed to delete schedule (HTTP ${res.status})`);
  }

  return await res.json();
}

export async function triggerDueSchedules(
  workspaceIdOverride?: string
): Promise<JobTaskSummary[]> {
  const res = await fetch(`${API_BASE_URL}/api/v1/schedules/trigger-due`, {
    method: 'POST',
    headers: {
      ...getAuthHeaders(),
      ...getWorkspaceHeader(workspaceIdOverride),
    },
  });

  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || `Failed to trigger due schedules (HTTP ${res.status})`);
  }

  return await res.json();
}
