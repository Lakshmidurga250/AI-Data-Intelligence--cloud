/**
 * Dataset Ingestion and Catalog service for AI Data Intelligence Cloud
 */

import { getAuthHeaders } from './auth';
import { getActiveWorkspaceId } from './workspaces';

export interface ColumnSchema {
  name: string;
  data_type: string;
  null_count: number;
  null_percentage: number;
  sample_values: unknown[];
}

export interface DatasetSummary {
  id: string;
  workspace_id: string;
  name: string;
  description?: string;
  filename: string;
  format: 'csv' | 'excel' | 'json' | 'parquet';
  size_bytes: number;
  row_count: number;
  column_count: number;
  sha256: string;
  version: number;
  created_at: string;
  columns: ColumnSchema[];
}

export interface DatasetDetail extends DatasetSummary {
  preview_rows: Record<string, unknown>[];
}

export interface NumericColumnStats {
  min?: number | null;
  max?: number | null;
  mean?: number | null;
  std?: number | null;
  variance?: number | null;
  median?: number | null;
  q25?: number | null;
  q75?: number | null;
  skew?: number | null;
  zeros_count: number;
  negatives_count: number;
}

export interface ValueFrequency {
  value: string;
  count: number;
  percentage: number;
}

export interface CategoricalColumnStats {
  distinct_count: number;
  distinct_percentage: number;
  top_values: ValueFrequency[];
  min_length?: number | null;
  max_length?: number | null;
  avg_length?: number | null;
}

export interface ColumnFullProfile {
  name: string;
  data_type: string;
  total_count: number;
  null_count: number;
  null_percentage: number;
  is_numeric: boolean;
  is_categorical: boolean;
  numeric_stats?: NumericColumnStats | null;
  categorical_stats?: CategoricalColumnStats | null;
}

export interface CorrelationPair {
  column_a: string;
  column_b: string;
  coefficient: number;
}

export interface DatasetProfileResponse {
  dataset_id: string;
  dataset_name: string;
  row_count: number;
  column_count: number;
  memory_bytes: number;
  duplicate_rows_count: number;
  duplicate_rows_percentage: number;
  completeness_score: number;
  columns: ColumnFullProfile[];
  correlations: CorrelationPair[];
  profiled_at: string;
}

export interface DatasetVersionRead {
  id: string;
  dataset_id: string;
  version_number: number;
  row_count: number;
  column_count: number;
  size_bytes: number;
  sha256: string;
  change_summary: string;
  created_at: string;
}

const API_BASE_URL = import.meta.env.VITE_API_URL || '';

export async function uploadDatasetFile(
  file: File,
  name?: string,
  description?: string,
  workspaceIdOverride?: string
): Promise<DatasetDetail> {
  const wsId = workspaceIdOverride || getActiveWorkspaceId();
  if (!wsId) {
    throw new Error('No active workspace selected. Please select a workspace first.');
  }

  const formData = new FormData();
  formData.append('file', file);
  if (name) formData.append('name', name);
  if (description) formData.append('description', description);

  const authHeaders = getAuthHeaders();
  // Remove Content-Type header so browser sets multipart boundary automatically
  const { 'Content-Type': _, ...headersWithoutContentType } = authHeaders;

  const res = await fetch(`${API_BASE_URL}/api/v1/datasets/upload`, {
    method: 'POST',
    headers: {
      ...headersWithoutContentType,
      'X-Workspace-ID': wsId,
    },
    body: formData,
  });

  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || `Upload failed (HTTP ${res.status})`);
  }

  return await res.json();
}

export async function listDatasets(workspaceIdOverride?: string): Promise<DatasetSummary[]> {
  const wsId = workspaceIdOverride || getActiveWorkspaceId();
  if (!wsId) return [];

  const res = await fetch(`${API_BASE_URL}/api/v1/datasets`, {
    method: 'GET',
    headers: {
      ...getAuthHeaders(),
      'X-Workspace-ID': wsId,
    },
  });

  if (!res.ok) {
    throw new Error(`Failed to list datasets (HTTP ${res.status})`);
  }

  return await res.json();
}

export async function getDatasetDetail(
  datasetId: string,
  workspaceIdOverride?: string
): Promise<DatasetDetail> {
  const wsId = workspaceIdOverride || getActiveWorkspaceId();
  if (!wsId) {
    throw new Error('No active workspace selected.');
  }

  const res = await fetch(`${API_BASE_URL}/api/v1/datasets/${datasetId}`, {
    method: 'GET',
    headers: {
      ...getAuthHeaders(),
      'X-Workspace-ID': wsId,
    },
  });

  if (!res.ok) {
    throw new Error(`Failed to fetch dataset (HTTP ${res.status})`);
  }

  return await res.json();
}

export async function deleteDataset(
  datasetId: string,
  workspaceIdOverride?: string
): Promise<void> {
  const wsId = workspaceIdOverride || getActiveWorkspaceId();
  if (!wsId) {
    throw new Error('No active workspace selected.');
  }

  const res = await fetch(`${API_BASE_URL}/api/v1/datasets/${datasetId}`, {
    method: 'DELETE',
    headers: {
      ...getAuthHeaders(),
      'X-Workspace-ID': wsId,
    },
  });

  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || `Failed to delete dataset (HTTP ${res.status})`);
  }
}

export async function getDatasetProfile(
  datasetId: string,
  refresh: boolean = false,
  workspaceIdOverride?: string
): Promise<DatasetProfileResponse> {
  const wsId = workspaceIdOverride || getActiveWorkspaceId();
  if (!wsId) {
    throw new Error('No active workspace selected.');
  }

  const query = refresh ? '?refresh=true' : '';
  const res = await fetch(`${API_BASE_URL}/api/v1/datasets/${datasetId}/profile${query}`, {
    method: 'GET',
    headers: {
      ...getAuthHeaders(),
      'X-Workspace-ID': wsId,
    },
  });

  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || `Failed to fetch dataset profile (HTTP ${res.status})`);
  }

  return await res.json();
}

export async function refreshDatasetProfile(
  datasetId: string,
  workspaceIdOverride?: string
): Promise<DatasetProfileResponse> {
  const wsId = workspaceIdOverride || getActiveWorkspaceId();
  if (!wsId) {
    throw new Error('No active workspace selected.');
  }

  const res = await fetch(`${API_BASE_URL}/api/v1/datasets/${datasetId}/profile/refresh`, {
    method: 'POST',
    headers: {
      ...getAuthHeaders(),
      'X-Workspace-ID': wsId,
    },
  });

  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || `Failed to refresh profile (HTTP ${res.status})`);
  }

  return await res.json();
}

export async function listDatasetVersions(
  datasetId: string,
  workspaceIdOverride?: string
): Promise<DatasetVersionRead[]> {
  const wsId = workspaceIdOverride || getActiveWorkspaceId();
  if (!wsId) {
    throw new Error('No active workspace selected.');
  }

  const res = await fetch(`${API_BASE_URL}/api/v1/datasets/${datasetId}/versions`, {
    method: 'GET',
    headers: {
      ...getAuthHeaders(),
      'X-Workspace-ID': wsId,
    },
  });

  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || `Failed to list versions (HTTP ${res.status})`);
  }

  return await res.json();
}

export async function createDatasetVersion(
  datasetId: string,
  changeSummary: string,
  workspaceIdOverride?: string
): Promise<DatasetVersionRead> {
  const wsId = workspaceIdOverride || getActiveWorkspaceId();
  if (!wsId) {
    throw new Error('No active workspace selected.');
  }

  const res = await fetch(`${API_BASE_URL}/api/v1/datasets/${datasetId}/versions`, {
    method: 'POST',
    headers: {
      ...getAuthHeaders(),
      'X-Workspace-ID': wsId,
    },
    body: JSON.stringify({ change_summary: changeSummary }),
  });

  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || `Failed to create version snapshot (HTTP ${res.status})`);
  }

  return await res.json();
}

