/**
 * Interactive Analytics and BI Dashboards API client.
 * Manages dashboards, visualization widgets, and analytical query execution.
 */

import { getAuthHeaders } from './auth';
import { getActiveWorkspaceId } from './workspaces';

export type VisualizationType = 'bar' | 'line' | 'area' | 'scatter' | 'pie' | 'kpi' | 'table';
export type AggregationType = 'sum' | 'avg' | 'min' | 'max' | 'count' | 'distinct_count';
export type TimeGrain = 'day' | 'week' | 'month' | 'year';

export interface MetricSpec {
  column: string;
  aggregation: AggregationType;
  alias?: string;
}

export interface FilterSpec {
  column: string;
  operator: string;
  value?: unknown;
}

export interface WidgetPosition {
  x: number;
  y: number;
  w: number;
  h: number;
}

export interface WidgetQueryConfig {
  metrics: MetricSpec[];
  dimensions?: string[];
  filters?: FilterSpec[];
  time_column?: string;
  time_grain?: TimeGrain;
  sort_by?: string;
  sort_order?: 'asc' | 'desc';
  limit?: number;
}

export interface DashboardWidget {
  id: string;
  dashboard_id: string;
  dataset_id?: string | null;
  name: string;
  visualization_type: VisualizationType;
  query_config: WidgetQueryConfig;
  position?: WidgetPosition | null;
  created_at: string;
  updated_at?: string | null;
}

export interface Dashboard {
  id: string;
  workspace_id: string;
  name: string;
  description?: string | null;
  layout_config?: Record<string, unknown> | null;
  is_default: boolean;
  widgets_count: number;
  created_at: string;
  updated_at?: string | null;
}

export interface DashboardDetail extends Dashboard {
  widgets: DashboardWidget[];
}

export interface DashboardCreate {
  name: string;
  description?: string;
  layout_config?: Record<string, unknown>;
  is_default?: boolean;
}

export interface DashboardUpdate {
  name?: string;
  description?: string;
  layout_config?: Record<string, unknown>;
  is_default?: boolean;
}

export interface DashboardWidgetCreate {
  name: string;
  dataset_id?: string;
  visualization_type: VisualizationType;
  query_config: WidgetQueryConfig | Record<string, unknown>;
  position?: WidgetPosition;
}

export interface DashboardWidgetUpdate {
  name?: string;
  dataset_id?: string;
  visualization_type?: VisualizationType;
  query_config?: WidgetQueryConfig | Record<string, unknown>;
  position?: WidgetPosition;
}

export interface AnalyticsQueryRequest {
  dataset_id: string;
  metrics: MetricSpec[];
  dimensions?: string[];
  filters?: FilterSpec[];
  time_column?: string;
  time_grain?: TimeGrain;
  sort_by?: string;
  sort_order?: 'asc' | 'desc';
  limit?: number;
}

export interface AnalyticsQueryResponse {
  columns: string[];
  data: Array<Record<string, unknown>>;
  row_count: number;
  execution_time_ms: number;
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

export async function listDashboards(
  skip = 0,
  limit = 100,
  workspaceIdOverride?: string
): Promise<Dashboard[]> {
  const headers = resolveWorkspaceHeaders(workspaceIdOverride);
  const params = new URLSearchParams({
    skip: skip.toString(),
    limit: limit.toString(),
  });

  const res = await fetch(`/api/v1/dashboards?${params.toString()}`, {
    method: 'GET',
    headers,
  });

  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: 'Failed to list dashboards' }));
    throw new Error(err.detail || 'Failed to list dashboards');
  }
  return res.json();
}

export async function getDashboard(
  dashboardId: string,
  workspaceIdOverride?: string
): Promise<DashboardDetail> {
  const headers = resolveWorkspaceHeaders(workspaceIdOverride);
  const res = await fetch(`/api/v1/dashboards/${dashboardId}`, {
    method: 'GET',
    headers,
  });

  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: 'Failed to fetch dashboard' }));
    throw new Error(err.detail || 'Failed to fetch dashboard');
  }
  return res.json();
}

export async function createDashboard(
  payload: DashboardCreate,
  workspaceIdOverride?: string
): Promise<DashboardDetail> {
  const headers = resolveWorkspaceHeaders(workspaceIdOverride);
  const res = await fetch('/api/v1/dashboards', {
    method: 'POST',
    headers,
    body: JSON.stringify(payload),
  });

  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: 'Failed to create dashboard' }));
    throw new Error(err.detail || 'Failed to create dashboard');
  }
  return res.json();
}

export async function updateDashboard(
  dashboardId: string,
  payload: DashboardUpdate,
  workspaceIdOverride?: string
): Promise<DashboardDetail> {
  const headers = resolveWorkspaceHeaders(workspaceIdOverride);
  const res = await fetch(`/api/v1/dashboards/${dashboardId}`, {
    method: 'PUT',
    headers,
    body: JSON.stringify(payload),
  });

  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: 'Failed to update dashboard' }));
    throw new Error(err.detail || 'Failed to update dashboard');
  }
  return res.json();
}

export async function deleteDashboard(
  dashboardId: string,
  workspaceIdOverride?: string
): Promise<void> {
  const headers = resolveWorkspaceHeaders(workspaceIdOverride);
  const res = await fetch(`/api/v1/dashboards/${dashboardId}`, {
    method: 'DELETE',
    headers,
  });

  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: 'Failed to delete dashboard' }));
    throw new Error(err.detail || 'Failed to delete dashboard');
  }
}

export async function createDashboardWidget(
  dashboardId: string,
  payload: DashboardWidgetCreate,
  workspaceIdOverride?: string
): Promise<DashboardWidget> {
  const headers = resolveWorkspaceHeaders(workspaceIdOverride);
  const res = await fetch(`/api/v1/dashboards/${dashboardId}/widgets`, {
    method: 'POST',
    headers,
    body: JSON.stringify(payload),
  });

  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: 'Failed to add widget to dashboard' }));
    throw new Error(err.detail || 'Failed to add widget to dashboard');
  }
  return res.json();
}

export async function updateDashboardWidget(
  dashboardId: string,
  widgetId: string,
  payload: DashboardWidgetUpdate,
  workspaceIdOverride?: string
): Promise<DashboardWidget> {
  const headers = resolveWorkspaceHeaders(workspaceIdOverride);
  const res = await fetch(`/api/v1/dashboards/${dashboardId}/widgets/${widgetId}`, {
    method: 'PUT',
    headers,
    body: JSON.stringify(payload),
  });

  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: 'Failed to update widget' }));
    throw new Error(err.detail || 'Failed to update widget');
  }
  return res.json();
}

export async function deleteDashboardWidget(
  dashboardId: string,
  widgetId: string,
  workspaceIdOverride?: string
): Promise<void> {
  const headers = resolveWorkspaceHeaders(workspaceIdOverride);
  const res = await fetch(`/api/v1/dashboards/${dashboardId}/widgets/${widgetId}`, {
    method: 'DELETE',
    headers,
  });

  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: 'Failed to delete widget' }));
    throw new Error(err.detail || 'Failed to delete widget');
  }
}

export async function executeWidgetQuery(
  dashboardId: string,
  widgetId: string,
  workspaceIdOverride?: string
): Promise<AnalyticsQueryResponse> {
  const headers = resolveWorkspaceHeaders(workspaceIdOverride);
  const res = await fetch(`/api/v1/dashboards/${dashboardId}/widgets/${widgetId}/query`, {
    method: 'POST',
    headers,
  });

  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: 'Failed to execute widget query' }));
    throw new Error(err.detail || 'Failed to execute widget query');
  }
  return res.json();
}

export async function executeAdHocAnalyticsQuery(
  payload: AnalyticsQueryRequest,
  workspaceIdOverride?: string
): Promise<AnalyticsQueryResponse> {
  const headers = resolveWorkspaceHeaders(workspaceIdOverride);
  const res = await fetch('/api/v1/dashboards/query', {
    method: 'POST',
    headers,
    body: JSON.stringify(payload),
  });

  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: 'Ad-hoc analytics query failed' }));
    throw new Error(err.detail || 'Ad-hoc analytics query failed');
  }
  return res.json();
}
