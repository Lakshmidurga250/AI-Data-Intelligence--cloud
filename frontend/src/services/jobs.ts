/**
 * Celery background workers and asynchronous job state streaming client.
 */

import { getAuthHeaders } from './auth';
import { getActiveWorkspaceId } from './workspaces';

export type JobStatusType = 'pending' | 'running' | 'completed' | 'failed' | 'cancelled';
export type TaskType = 'pipeline_run' | 'dataset_profile' | 'dataset_ingest' | 'scheduled_job';

export interface JobTaskCreate {
  task_type: TaskType;
  resource_id?: string;
  parameters?: Record<string, unknown>;
}

export interface JobTaskSummary {
  id: string;
  workspace_id: string;
  task_type: string;
  status: JobStatusType;
  progress_pct: number;
  message: string;
  resource_id?: string | null;
  created_at: string;
  started_at?: string | null;
  completed_at?: string | null;
  execution_time_ms?: number | null;
}

export interface JobTaskRead extends JobTaskSummary {
  celery_task_id?: string | null;
  parameters: Record<string, unknown>;
  result_payload: Record<string, unknown>;
  error_message?: string | null;
  retry_count: number;
  max_retries: number;
  triggered_by_user_id?: string | null;
}

export interface WorkerDiagnosticsResponse {
  status: 'operational' | 'degraded' | 'offline';
  broker_type: string;
  broker_url: string;
  active_worker_count: number;
  queued_task_count: number;
  running_task_count: number;
  completed_today_count: number;
  failed_today_count: number;
  timestamp: string;
}

const API_BASE_URL = import.meta.env.VITE_API_URL || '';

function getWorkspaceHeader(workspaceIdOverride?: string): Record<string, string> {
  const wsId = workspaceIdOverride || getActiveWorkspaceId();
  if (!wsId) {
    throw new Error('No active workspace selected.');
  }
  return { 'X-Workspace-ID': wsId };
}

export async function listJobs(
  taskType?: string,
  status?: string,
  limit: number = 50,
  workspaceIdOverride?: string
): Promise<JobTaskSummary[]> {
  const params = new URLSearchParams();
  if (taskType) params.append('task_type', taskType);
  if (status) params.append('status', status);
  if (limit) params.append('limit', limit.toString());

  const queryStr = params.toString() ? `?${params.toString()}` : '';
  const res = await fetch(`${API_BASE_URL}/api/v1/jobs${queryStr}`, {
    method: 'GET',
    headers: {
      ...getAuthHeaders(),
      ...getWorkspaceHeader(workspaceIdOverride),
    },
  });

  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || `Failed to list background jobs (HTTP ${res.status})`);
  }

  return await res.json();
}

export async function getJobDetails(
  jobId: string,
  workspaceIdOverride?: string
): Promise<JobTaskRead> {
  const res = await fetch(`${API_BASE_URL}/api/v1/jobs/${jobId}`, {
    method: 'GET',
    headers: {
      ...getAuthHeaders(),
      ...getWorkspaceHeader(workspaceIdOverride),
    },
  });

  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || `Failed to retrieve job details (HTTP ${res.status})`);
  }

  return await res.json();
}

export async function dispatchJob(
  payload: JobTaskCreate,
  workspaceIdOverride?: string
): Promise<JobTaskRead> {
  const res = await fetch(`${API_BASE_URL}/api/v1/jobs`, {
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
    throw new Error(err.detail || `Failed to dispatch background job (HTTP ${res.status})`);
  }

  return await res.json();
}

export async function cancelJob(
  jobId: string,
  workspaceIdOverride?: string
): Promise<JobTaskRead> {
  const res = await fetch(`${API_BASE_URL}/api/v1/jobs/${jobId}/cancel`, {
    method: 'POST',
    headers: {
      ...getAuthHeaders(),
      ...getWorkspaceHeader(workspaceIdOverride),
    },
  });

  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || `Failed to cancel background job (HTTP ${res.status})`);
  }

  return await res.json();
}

export async function getWorkerDiagnostics(
  workspaceIdOverride?: string
): Promise<WorkerDiagnosticsResponse> {
  const res = await fetch(`${API_BASE_URL}/api/v1/jobs/diagnostics`, {
    method: 'GET',
    headers: {
      ...getAuthHeaders(),
      ...getWorkspaceHeader(workspaceIdOverride),
    },
  });

  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || `Failed to fetch worker diagnostics (HTTP ${res.status})`);
  }

  return await res.json();
}
