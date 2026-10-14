/**
 * Data Quality rules, evaluation scorecards, and violation alerts API client.
 */

import { getAuthHeaders } from './auth';
import { getActiveWorkspaceId } from './workspaces';

export type QualityRuleType =
  | 'null_threshold'
  | 'uniqueness'
  | 'value_range'
  | 'regex_match'
  | 'set_membership'
  | 'expression';

export type QualitySeverity = 'critical' | 'warning' | 'info';
export type EvaluationGrade = 'A' | 'B' | 'C' | 'D' | 'F';

export interface QualityRule {
  id: string;
  suite_id: string;
  name: string;
  rule_type: QualityRuleType;
  target_column: string;
  parameters: Record<string, unknown>;
  severity: QualitySeverity;
  is_active: boolean;
  created_at: string;
  updated_at?: string | null;
}

export interface QualityRuleCreate {
  name: string;
  rule_type: QualityRuleType;
  target_column: string;
  parameters?: Record<string, unknown>;
  severity?: QualitySeverity;
  is_active?: boolean;
}

export interface QualityRuleSuite {
  id: string;
  workspace_id: string;
  dataset_id?: string | null;
  name: string;
  description?: string | null;
  is_active: boolean;
  created_at: string;
  updated_at?: string | null;
  rules: QualityRule[];
  rules_count: number;
}

export interface QualityRuleSuiteCreate {
  name: string;
  description?: string;
  dataset_id?: string;
  rules?: QualityRuleCreate[];
}

export interface RuleEvaluationResult {
  rule_id: string;
  rule_name: string;
  rule_type: string;
  target_column: string;
  severity: string;
  passed: boolean;
  total_rows: number;
  failed_rows: number;
  failure_rate_pct: number;
  message: string;
  sample_violations: Record<string, unknown>[];
}

export interface QualityEvaluationRun {
  id: string;
  workspace_id: string;
  suite_id: string;
  dataset_id: string;
  status: string;
  score: number;
  grade: EvaluationGrade;
  total_rules: number;
  passed_rules: number;
  failed_rules: number;
  execution_time_ms: number;
  rule_results: RuleEvaluationResult[];
  created_at: string;
}

export interface QualityAlert {
  id: string;
  workspace_id: string;
  suite_id: string;
  run_id: string;
  severity: string;
  title: string;
  message: string;
  is_acknowledged: boolean;
  created_at: string;
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

export async function listQualitySuites(
  datasetId?: string,
  workspaceIdOverride?: string
): Promise<QualityRuleSuite[]> {
  const headers = resolveWorkspaceHeaders(workspaceIdOverride);
  const params = new URLSearchParams();
  if (datasetId) params.append('dataset_id', datasetId);

  const res = await fetch(`/api/v1/quality/suites?${params.toString()}`, {
    method: 'GET',
    headers,
  });

  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: 'Failed to list quality suites' }));
    throw new Error(err.detail || 'Failed to list quality suites');
  }
  return res.json();
}

export async function getQualitySuite(
  suiteId: string,
  workspaceIdOverride?: string
): Promise<QualityRuleSuite> {
  const headers = resolveWorkspaceHeaders(workspaceIdOverride);
  const res = await fetch(`/api/v1/quality/suites/${suiteId}`, {
    method: 'GET',
    headers,
  });

  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: 'Failed to get quality suite' }));
    throw new Error(err.detail || 'Failed to get quality suite');
  }
  return res.json();
}

export async function createQualitySuite(
  payload: QualityRuleSuiteCreate,
  workspaceIdOverride?: string
): Promise<QualityRuleSuite> {
  const headers = resolveWorkspaceHeaders(workspaceIdOverride);
  const res = await fetch('/api/v1/quality/suites', {
    method: 'POST',
    headers,
    body: JSON.stringify(payload),
  });

  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: 'Failed to create quality suite' }));
    throw new Error(err.detail || 'Failed to create quality suite');
  }
  return res.json();
}

export async function addQualityRule(
  suiteId: string,
  rule: QualityRuleCreate,
  workspaceIdOverride?: string
): Promise<QualityRule> {
  const headers = resolveWorkspaceHeaders(workspaceIdOverride);
  const res = await fetch(`/api/v1/quality/suites/${suiteId}/rules`, {
    method: 'POST',
    headers,
    body: JSON.stringify(rule),
  });

  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: 'Failed to add rule to suite' }));
    throw new Error(err.detail || 'Failed to add rule to suite');
  }
  return res.json();
}

export async function deleteQualityRule(
  ruleId: string,
  workspaceIdOverride?: string
): Promise<void> {
  const headers = resolveWorkspaceHeaders(workspaceIdOverride);
  const res = await fetch(`/api/v1/quality/rules/${ruleId}`, {
    method: 'DELETE',
    headers,
  });

  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: 'Failed to delete rule' }));
    throw new Error(err.detail || 'Failed to delete rule');
  }
}

export async function deleteQualitySuite(
  suiteId: string,
  workspaceIdOverride?: string
): Promise<void> {
  const headers = resolveWorkspaceHeaders(workspaceIdOverride);
  const res = await fetch(`/api/v1/quality/suites/${suiteId}`, {
    method: 'DELETE',
    headers,
  });

  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: 'Failed to delete quality suite' }));
    throw new Error(err.detail || 'Failed to delete quality suite');
  }
}

export async function evaluateQualitySuite(
  suiteId: string,
  datasetId?: string,
  workspaceIdOverride?: string
): Promise<QualityEvaluationRun> {
  const headers = resolveWorkspaceHeaders(workspaceIdOverride);
  const res = await fetch(`/api/v1/quality/suites/${suiteId}/evaluate`, {
    method: 'POST',
    headers,
    body: JSON.stringify(datasetId ? { dataset_id: datasetId } : {}),
  });

  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: 'Quality evaluation failed' }));
    throw new Error(err.detail || 'Quality evaluation failed');
  }
  return res.json();
}

export async function listQualityRuns(
  suiteId?: string,
  datasetId?: string,
  workspaceIdOverride?: string
): Promise<QualityEvaluationRun[]> {
  const headers = resolveWorkspaceHeaders(workspaceIdOverride);
  const params = new URLSearchParams();
  if (suiteId) params.append('suite_id', suiteId);
  if (datasetId) params.append('dataset_id', datasetId);

  const res = await fetch(`/api/v1/quality/runs?${params.toString()}`, {
    method: 'GET',
    headers,
  });

  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: 'Failed to list evaluation runs' }));
    throw new Error(err.detail || 'Failed to list evaluation runs');
  }
  return res.json();
}

export async function listQualityAlerts(
  isAcknowledged?: boolean,
  workspaceIdOverride?: string
): Promise<QualityAlert[]> {
  const headers = resolveWorkspaceHeaders(workspaceIdOverride);
  const params = new URLSearchParams();
  if (isAcknowledged !== undefined) params.append('is_acknowledged', String(isAcknowledged));

  const res = await fetch(`/api/v1/quality/alerts?${params.toString()}`, {
    method: 'GET',
    headers,
  });

  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: 'Failed to list quality alerts' }));
    throw new Error(err.detail || 'Failed to list quality alerts');
  }
  return res.json();
}

export async function acknowledgeQualityAlert(
  alertId: string,
  workspaceIdOverride?: string
): Promise<QualityAlert> {
  const headers = resolveWorkspaceHeaders(workspaceIdOverride);
  const res = await fetch(`/api/v1/quality/alerts/${alertId}/ack`, {
    method: 'POST',
    headers,
  });

  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: 'Failed to acknowledge alert' }));
    throw new Error(err.detail || 'Failed to acknowledge alert');
  }
  return res.json();
}
