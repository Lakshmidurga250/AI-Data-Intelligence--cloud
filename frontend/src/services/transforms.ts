/**
 * Data Cleaning & Transformation Pipeline API service
 */

import { getAuthHeaders } from './auth';
import { getActiveWorkspaceId } from './workspaces';
import type { ColumnSchema } from './datasets';

export type TransformStepType =
  | 'impute'
  | 'drop_columns'
  | 'rename_columns'
  | 'cast_type'
  | 'text_transform'
  | 'drop_duplicates'
  | 'handle_outliers'
  | 'filter_rows'
  | 'derive_column';

export interface TransformStep {
  step_type: TransformStepType;
  params: Record<string, unknown>;
}

export interface TransformPreviewResponse {
  original_row_count: number;
  transformed_row_count: number;
  rows_affected: number;
  original_columns: ColumnSchema[];
  transformed_columns: ColumnSchema[];
  preview_before: Record<string, unknown>[];
  preview_after: Record<string, unknown>[];
  step_summaries: string[];
}

export interface TransformRecipeRequest {
  name?: string;
  description?: string;
  steps: TransformStep[];
  save_as_new_dataset: boolean;
}

export interface TransformApplyResponse {
  dataset_id: string;
  name: string;
  version: number;
  row_count: number;
  column_count: number;
  size_bytes: number;
  format: string;
  steps_applied: number;
  step_summaries: string[];
}

const API_BASE_URL = import.meta.env.VITE_API_URL || '';

export async function previewTransforms(
  datasetId: string,
  steps: TransformStep[],
  sampleSize: number = 25,
  workspaceIdOverride?: string
): Promise<TransformPreviewResponse> {
  const wsId = workspaceIdOverride || getActiveWorkspaceId();
  if (!wsId) {
    throw new Error('No active workspace selected.');
  }

  const res = await fetch(`${API_BASE_URL}/api/v1/datasets/${datasetId}/transforms/preview`, {
    method: 'POST',
    headers: {
      ...getAuthHeaders(),
      'X-Workspace-ID': wsId,
    },
    body: JSON.stringify({ steps, sample_size: sampleSize }),
  });

  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || `Failed to preview transformation (HTTP ${res.status})`);
  }

  return await res.json();
}

export async function applyTransforms(
  datasetId: string,
  payload: TransformRecipeRequest,
  workspaceIdOverride?: string
): Promise<TransformApplyResponse> {
  const wsId = workspaceIdOverride || getActiveWorkspaceId();
  if (!wsId) {
    throw new Error('No active workspace selected.');
  }

  const res = await fetch(`${API_BASE_URL}/api/v1/datasets/${datasetId}/transforms/apply`, {
    method: 'POST',
    headers: {
      ...getAuthHeaders(),
      'X-Workspace-ID': wsId,
    },
    body: JSON.stringify(payload),
  });

  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || `Failed to apply transformation (HTTP ${res.status})`);
  }

  return await res.json();
}
