/**
 * AutoML and ML Model Registry client.
 * Handles model training benchmark, registry catalog, version promotion,
 * experiment tracking, and real-time inference execution.
 */

import { getAuthHeaders } from './auth';
import { getActiveWorkspaceId } from './workspaces';

export type MLTaskType = 'classification' | 'regression';
export type ModelVersionStatus = 'candidate' | 'champion' | 'archived';
export type ExperimentStatus = 'pending' | 'running' | 'completed' | 'failed';

export interface AlgorithmLeaderboardItem {
  algorithm: string;
  metrics: Record<string, number>;
  training_time_ms: number;
  is_best: boolean;
}

export interface AutoMLTrainRequest {
  dataset_id: string;
  model_name: string;
  target_column: string;
  task_type: MLTaskType;
  test_size?: number;
  candidate_algorithms?: string[];
  feature_columns?: string[];
  description?: string;
}

export interface AutoMLTrainResponse {
  model_id: string;
  version_id: string;
  experiment_id: string;
  model_name: string;
  task_type: string;
  target_column: string;
  best_algorithm: string;
  metrics: Record<string, number>;
  feature_names: string[];
  feature_importances: Record<string, number>;
  leaderboard: AlgorithmLeaderboardItem[];
  training_duration_ms: number;
}

export interface MLModelVersion {
  id: string;
  model_id: string;
  version_number: number;
  experiment_id?: string | null;
  artifact_path: string;
  sha256: string;
  algorithm: string;
  status: ModelVersionStatus;
  metrics: Record<string, number>;
  hyperparameters?: Record<string, unknown> | null;
  feature_names: string[];
  feature_importance: Record<string, number>;
  created_at: string;
  updated_at?: string | null;
}

export interface MLModel {
  id: string;
  workspace_id: string;
  name: string;
  description?: string | null;
  task_type: MLTaskType;
  target_column: string;
  framework: string;
  active_version_id?: string | null;
  versions_count: number;
  active_version?: MLModelVersion | null;
  created_at: string;
  updated_at?: string | null;
}

export interface MLModelDetail extends MLModel {
  versions: MLModelVersion[];
}

export interface MLExperiment {
  id: string;
  workspace_id: string;
  model_id?: string | null;
  dataset_id?: string | null;
  name: string;
  task_type: MLTaskType;
  target_column: string;
  status: ExperimentStatus;
  best_algorithm?: string | null;
  leaderboard: AlgorithmLeaderboardItem[];
  logs?: string | null;
  training_duration_ms?: number | null;
  created_at: string;
  updated_at?: string | null;
}

export interface InferenceRequest {
  inputs: Record<string, unknown> | Array<Record<string, unknown>>;
}

export interface InferenceResponse {
  model_id: string;
  version_id: string;
  algorithm: string;
  task_type: MLTaskType;
  predictions: unknown[];
  probabilities?: Array<Record<string, number>> | null;
  latency_ms: number;
}

function resolveWorkspaceHeaders(workspaceIdOverride?: string): HeadersInit {
  const wsId = workspaceIdOverride || getActiveWorkspaceId();
  const headers: Record<string, string> = {
    ...getAuthHeaders(),
    'Content-Type': 'application/json',
  };
  if (wsId) {
    headers['X-Workspace-ID'] = wsId;
  }
  return headers;
}

export async function trainAutoMLModel(
  payload: AutoMLTrainRequest,
  workspaceIdOverride?: string
): Promise<AutoMLTrainResponse> {
  const headers = resolveWorkspaceHeaders(workspaceIdOverride);
  const res = await fetch('/api/v1/ml/train', {
    method: 'POST',
    headers,
    body: JSON.stringify(payload),
  });

  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: 'AutoML training benchmark failed' }));
    throw new Error(err.detail || 'AutoML training benchmark failed');
  }
  return res.json();
}

export async function listMLModels(
  skip = 0,
  limit = 100,
  workspaceIdOverride?: string
): Promise<MLModel[]> {
  const headers = resolveWorkspaceHeaders(workspaceIdOverride);
  const params = new URLSearchParams({
    skip: skip.toString(),
    limit: limit.toString(),
  });

  const res = await fetch(`/api/v1/ml/models?${params.toString()}`, {
    method: 'GET',
    headers,
  });

  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: 'Failed to list models' }));
    throw new Error(err.detail || 'Failed to list models');
  }
  return res.json();
}

export async function getMLModel(
  modelId: string,
  workspaceIdOverride?: string
): Promise<MLModelDetail> {
  const headers = resolveWorkspaceHeaders(workspaceIdOverride);
  const res = await fetch(`/api/v1/ml/models/${modelId}`, {
    method: 'GET',
    headers,
  });

  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: 'Failed to fetch model details' }));
    throw new Error(err.detail || 'Failed to fetch model details');
  }
  return res.json();
}

export async function deleteMLModel(
  modelId: string,
  workspaceIdOverride?: string
): Promise<void> {
  const headers = resolveWorkspaceHeaders(workspaceIdOverride);
  const res = await fetch(`/api/v1/ml/models/${modelId}`, {
    method: 'DELETE',
    headers,
  });

  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: 'Failed to delete model' }));
    throw new Error(err.detail || 'Failed to delete model');
  }
}

export async function promoteMLModelVersion(
  modelId: string,
  versionId: string,
  workspaceIdOverride?: string
): Promise<MLModelVersion> {
  const headers = resolveWorkspaceHeaders(workspaceIdOverride);
  const res = await fetch(`/api/v1/ml/models/${modelId}/versions/${versionId}/promote`, {
    method: 'POST',
    headers,
  });

  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: 'Failed to promote model version' }));
    throw new Error(err.detail || 'Failed to promote model version');
  }
  return res.json();
}

export async function runMLInference(
  modelId: string,
  inputs: Record<string, unknown> | Array<Record<string, unknown>>,
  versionId?: string,
  workspaceIdOverride?: string
): Promise<InferenceResponse> {
  const headers = resolveWorkspaceHeaders(workspaceIdOverride);
  const params = new URLSearchParams();
  if (versionId) params.append('version_id', versionId);

  const url = `/api/v1/ml/models/${modelId}/predict${params.toString() ? `?${params.toString()}` : ''}`;
  const res = await fetch(url, {
    method: 'POST',
    headers,
    body: JSON.stringify({ inputs }),
  });

  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: 'Model inference request failed' }));
    throw new Error(err.detail || 'Model inference request failed');
  }
  return res.json();
}

export async function listMLExperiments(
  modelId?: string,
  skip = 0,
  limit = 100,
  workspaceIdOverride?: string
): Promise<MLExperiment[]> {
  const headers = resolveWorkspaceHeaders(workspaceIdOverride);
  const params = new URLSearchParams({
    skip: skip.toString(),
    limit: limit.toString(),
  });
  if (modelId) params.append('model_id', modelId);

  const res = await fetch(`/api/v1/ml/experiments?${params.toString()}`, {
    method: 'GET',
    headers,
  });

  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: 'Failed to list experiments' }));
    throw new Error(err.detail || 'Failed to list experiments');
  }
  return res.json();
}
