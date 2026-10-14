/**
 * Visual ETL Pipelines and DAG Execution API Service
 */

import { getAuthHeaders } from './auth';
import { getActiveWorkspaceId } from './workspaces';

export type PipelineNodeType =
  | 'source'
  | 'transform'
  | 'filter'
  | 'aggregate'
  | 'join'
  | 'sink';

export interface NodePosition {
  x: number;
  y: number;
}

export interface PipelineNode {
  id: string;
  type: PipelineNodeType;
  label: string;
  position?: NodePosition;
  config: Record<string, unknown>;
}

export interface PipelineEdge {
  id: string;
  source: string;
  target: string;
  source_handle?: string | null;
  target_handle?: string | null;
}

export interface PipelineGraph {
  nodes: PipelineNode[];
  edges: PipelineEdge[];
}

export interface PipelineCreate {
  name: string;
  description?: string;
  graph_definition: PipelineGraph;
}

export interface PipelineUpdate {
  name?: string;
  description?: string;
  graph_definition?: PipelineGraph;
}

export interface PipelineSummary {
  id: string;
  workspace_id: string;
  name: string;
  description?: string;
  node_count: number;
  edge_count: number;
  created_at: string;
  updated_at: string;
}

export interface PipelineRead {
  id: string;
  workspace_id: string;
  name: string;
  description?: string;
  graph_definition: PipelineGraph;
  created_at: string;
  updated_at: string;
}

export interface PipelineValidationResult {
  is_valid: boolean;
  errors: string[];
  warnings: string[];
  execution_order: string[];
}

export interface PipelineStageResult {
  node_id: string;
  node_type: string;
  label: string;
  status: 'completed' | 'failed' | 'skipped';
  rows_in: number;
  rows_out: number;
  columns_out: string[];
  duration_ms: number;
  error?: string | null;
  summary: string;
}

export interface PipelineRunResponse {
  run_id: string;
  pipeline_id: string;
  workspace_id: string;
  status: 'completed' | 'failed';
  started_at: string;
  completed_at?: string | null;
  execution_time_ms: number;
  output_dataset_id?: string | null;
  output_dataset_name?: string | null;
  stage_results: PipelineStageResult[];
  error_message?: string | null;
}

export interface PipelineRunSummary {
  id: string;
  pipeline_id: string;
  status: string;
  started_at?: string | null;
  completed_at?: string | null;
  execution_time_ms?: number | null;
  output_dataset_id?: string | null;
  error_message?: string | null;
  created_at: string;
}

const API_BASE_URL = import.meta.env.VITE_API_URL || '';

function getWorkspaceHeader(workspaceIdOverride?: string): Record<string, string> {
  const wsId = workspaceIdOverride || getActiveWorkspaceId();
  if (!wsId) {
    throw new Error('No active workspace selected.');
  }
  return { 'X-Workspace-ID': wsId };
}

export async function listPipelines(workspaceIdOverride?: string): Promise<PipelineSummary[]> {
  const res = await fetch(`${API_BASE_URL}/api/v1/pipelines`, {
    method: 'GET',
    headers: {
      ...getAuthHeaders(),
      ...getWorkspaceHeader(workspaceIdOverride),
    },
  });

  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || `Failed to list pipelines (HTTP ${res.status})`);
  }

  return await res.json();
}

export async function createPipeline(
  payload: PipelineCreate,
  workspaceIdOverride?: string
): Promise<PipelineRead> {
  const res = await fetch(`${API_BASE_URL}/api/v1/pipelines`, {
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
    throw new Error(err.detail || `Failed to create pipeline (HTTP ${res.status})`);
  }

  return await res.json();
}

export async function getPipeline(
  pipelineId: string,
  workspaceIdOverride?: string
): Promise<PipelineRead> {
  const res = await fetch(`${API_BASE_URL}/api/v1/pipelines/${pipelineId}`, {
    method: 'GET',
    headers: {
      ...getAuthHeaders(),
      ...getWorkspaceHeader(workspaceIdOverride),
    },
  });

  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || `Failed to get pipeline (HTTP ${res.status})`);
  }

  return await res.json();
}

export async function updatePipeline(
  pipelineId: string,
  payload: PipelineUpdate,
  workspaceIdOverride?: string
): Promise<PipelineRead> {
  const res = await fetch(`${API_BASE_URL}/api/v1/pipelines/${pipelineId}`, {
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
    throw new Error(err.detail || `Failed to update pipeline (HTTP ${res.status})`);
  }

  return await res.json();
}

export async function deletePipeline(
  pipelineId: string,
  workspaceIdOverride?: string
): Promise<void> {
  const res = await fetch(`${API_BASE_URL}/api/v1/pipelines/${pipelineId}`, {
    method: 'DELETE',
    headers: {
      ...getAuthHeaders(),
      ...getWorkspaceHeader(workspaceIdOverride),
    },
  });

  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || `Failed to delete pipeline (HTTP ${res.status})`);
  }
}

export async function validatePipeline(
  pipelineId: string,
  workspaceIdOverride?: string
): Promise<PipelineValidationResult> {
  const res = await fetch(`${API_BASE_URL}/api/v1/pipelines/${pipelineId}/validate`, {
    method: 'POST',
    headers: {
      ...getAuthHeaders(),
      ...getWorkspaceHeader(workspaceIdOverride),
    },
  });

  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || `Failed to validate pipeline (HTTP ${res.status})`);
  }

  return await res.json();
}

export async function runPipeline(
  pipelineId: string,
  workspaceIdOverride?: string
): Promise<PipelineRunResponse> {
  const res = await fetch(`${API_BASE_URL}/api/v1/pipelines/${pipelineId}/run`, {
    method: 'POST',
    headers: {
      ...getAuthHeaders(),
      ...getWorkspaceHeader(workspaceIdOverride),
    },
  });

  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || `Failed to execute pipeline (HTTP ${res.status})`);
  }

  return await res.json();
}

export async function listPipelineRuns(
  pipelineId: string,
  workspaceIdOverride?: string
): Promise<PipelineRunSummary[]> {
  const res = await fetch(`${API_BASE_URL}/api/v1/pipelines/${pipelineId}/runs`, {
    method: 'GET',
    headers: {
      ...getAuthHeaders(),
      ...getWorkspaceHeader(workspaceIdOverride),
    },
  });

  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || `Failed to list pipeline runs (HTTP ${res.status})`);
  }

  return await res.json();
}
