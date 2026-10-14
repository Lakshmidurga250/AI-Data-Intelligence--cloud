/**
 * Data Lineage Graph, Provenance Traversal, and Governance Policies API client.
 */

import { getAuthHeaders } from './auth';
import { getActiveWorkspaceId } from './workspaces';

export type LineageNodeType =
  | 'external_source'
  | 'dataset'
  | 'transformation'
  | 'pipeline'
  | 'quality_suite'
  | 'export';

export type LineageEdgeType =
  | 'data_flow'
  | 'derivation'
  | 'validation'
  | 'pipeline_execution';

export type ClassificationTier =
  | 'PUBLIC'
  | 'INTERNAL'
  | 'CONFIDENTIAL'
  | 'RESTRICTED_PII';

export interface LineageNode {
  id: string;
  workspace_id: string;
  name: string;
  node_type: LineageNodeType;
  resource_id?: string | null;
  metadata_json?: Record<string, unknown> | null;
  created_at: string;
  updated_at: string;
}

export interface LineageEdge {
  id: string;
  workspace_id: string;
  source_node_id: string;
  target_node_id: string;
  edge_type: LineageEdgeType;
  column_mappings_json?: Array<{ source_col: string; target_col: string }> | null;
  transformation_summary?: string | null;
  created_at: string;
}

export interface LineageGraph {
  nodes: LineageNode[];
  edges: LineageEdge[];
  root_node_count: number;
  leaf_node_count: number;
}

export interface ImpactAnalysis {
  target_node: LineageNode;
  upstream_ancestors: LineageNode[];
  downstream_dependents: LineageNode[];
  total_impacted_pipelines: number;
  total_impacted_datasets: number;
  total_impacted_quality_suites: number;
}

export interface GovernancePolicy {
  id: string;
  workspace_id: string;
  name: string;
  description?: string | null;
  classification_tier: ClassificationTier;
  retention_days: number;
  compliance_framework: string;
  data_steward?: string | null;
  auto_purge_enabled: boolean;
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

export interface GovernancePolicyCreate {
  name: string;
  description?: string;
  classification_tier?: ClassificationTier;
  retention_days?: number;
  compliance_framework?: string;
  data_steward?: string;
  auto_purge_enabled?: boolean;
  is_active?: boolean;
}

export interface DatasetGovernanceTag {
  id: string;
  workspace_id: string;
  dataset_id: string;
  column_name?: string | null;
  sensitivity_label: string;
  confidence_score: number;
  is_quarantined: boolean;
  created_at: string;
  updated_at: string;
}

export interface PIIScanResult {
  column_name: string;
  sensitivity_label: string;
  confidence_score: number;
  sample_matches_count: number;
  sample_masked_values: string[];
}

export interface DatasetPIIScanResponse {
  dataset_id: string;
  dataset_name: string;
  scanned_columns_count: number;
  flagged_columns_count: number;
  findings: PIIScanResult[];
  overall_classification: ClassificationTier;
  is_quarantined: boolean;
}

export interface ComplianceAuditLog {
  id: string;
  workspace_id: string;
  dataset_id?: string | null;
  policy_id?: string | null;
  event_type: string;
  severity: string;
  findings_json?: Record<string, unknown> | null;
  actor: string;
  created_at: string;
}

const getHeaders = (): Record<string, string> => {
  const headers = getAuthHeaders();
  const wsId = getActiveWorkspaceId();
  if (wsId) {
    headers['X-Workspace-ID'] = wsId;
  }
  return headers;
};

export async function getLineageGraph(): Promise<LineageGraph> {
  const res = await fetch('/api/v1/lineage/graph', {
    headers: getHeaders(),
  });
  if (!res.ok) {
    throw new Error('Failed to retrieve lineage graph');
  }
  return res.json();
}

export async function syncLineageGraph(): Promise<Record<string, number>> {
  const res = await fetch('/api/v1/lineage/sync', {
    method: 'POST',
    headers: getHeaders(),
  });
  if (!res.ok) {
    throw new Error('Failed to synchronize lineage graph');
  }
  return res.json();
}

export async function getImpactAnalysis(nodeId: string): Promise<ImpactAnalysis> {
  const res = await fetch(`/api/v1/lineage/impact/${nodeId}`, {
    headers: getHeaders(),
  });
  if (!res.ok) {
    throw new Error('Failed to analyze impact for node');
  }
  return res.json();
}

export async function listGovernancePolicies(): Promise<GovernancePolicy[]> {
  const res = await fetch('/api/v1/governance/policies', {
    headers: getHeaders(),
  });
  if (!res.ok) {
    throw new Error('Failed to list governance policies');
  }
  return res.json();
}

export async function createGovernancePolicy(payload: GovernancePolicyCreate): Promise<GovernancePolicy> {
  const res = await fetch('/api/v1/governance/policies', {
    method: 'POST',
    headers: {
      ...getHeaders(),
      'Content-Type': 'application/json',
    },
    body: JSON.stringify(payload),
  });
  if (!res.ok) {
    throw new Error('Failed to create governance policy');
  }
  return res.json();
}

export async function deleteGovernancePolicy(policyId: string): Promise<void> {
  const res = await fetch(`/api/v1/governance/policies/${policyId}`, {
    method: 'DELETE',
    headers: getHeaders(),
  });
  if (!res.ok) {
    throw new Error('Failed to delete governance policy');
  }
}

export async function classifyDataset(datasetId: string): Promise<DatasetPIIScanResponse> {
  const res = await fetch(`/api/v1/governance/classify/${datasetId}`, {
    method: 'POST',
    headers: getHeaders(),
  });
  if (!res.ok) {
    throw new Error('Failed to classify dataset');
  }
  return res.json();
}

export async function getDatasetTags(datasetId: string): Promise<DatasetGovernanceTag[]> {
  const res = await fetch(`/api/v1/governance/tags/${datasetId}`, {
    headers: getHeaders(),
  });
  if (!res.ok) {
    throw new Error('Failed to retrieve governance tags');
  }
  return res.json();
}

export async function listComplianceAuditLogs(limit: number = 50): Promise<ComplianceAuditLog[]> {
  const res = await fetch(`/api/v1/governance/audit-logs?limit=${limit}`, {
    headers: getHeaders(),
  });
  if (!res.ok) {
    throw new Error('Failed to list compliance audit logs');
  }
  return res.json();
}

export async function evaluateRetention(): Promise<Record<string, unknown>> {
  const res = await fetch('/api/v1/governance/retention/evaluate', {
    method: 'POST',
    headers: getHeaders(),
  });
  if (!res.ok) {
    throw new Error('Failed to evaluate retention compliance');
  }
  return res.json();
}
