/**
 * Conversational AI and Autonomous Data Intelligence Assistant API client.
 * Manages conversation threads, multi-turn chat interactions, automated anomaly discoveries,
 * and natural language tabular query execution.
 */

import { getAuthHeaders } from './auth';
import { getActiveWorkspaceId } from './workspaces';

export type InsightSeverity = 'info' | 'low' | 'medium' | 'high' | 'critical';
export type InsightType =
  | 'distribution_anomaly'
  | 'missing_values'
  | 'high_correlation'
  | 'target_imbalance'
  | 'outlier_risk'
  | 'cardinality_alert'
  | 'trend_indicator';

export interface InsightItem {
  insight_type: InsightType;
  severity: InsightSeverity;
  column?: string | null;
  title: string;
  description: string;
  metric_value?: number | string | null;
  recommendation: string;
}

export interface InsightReportResponse {
  dataset_id: string;
  dataset_name: string;
  total_rows: number;
  total_columns: number;
  total_insights: number;
  critical_count: number;
  insights: InsightItem[];
  generated_at: string;
}

export interface NLQueryTranslation {
  dataset_id: string;
  operation: string;
  explanation: string;
  query_spec: Record<string, unknown>;
  columns: string[];
  data: Array<Record<string, unknown>>;
  suggested_chart?: string;
}

export interface ChatMessageRead {
  id: string;
  conversation_id: string;
  role: 'user' | 'assistant';
  content: string;
  intent: string;
  metadata: Record<string, unknown>;
  execution_time_ms?: number | null;
  created_at: string;
}

export interface ConversationRead {
  id: string;
  workspace_id: string;
  user_id?: string | null;
  title: string;
  active_dataset_id?: string | null;
  message_count: number;
  created_at: string;
  updated_at: string;
}

export interface ConversationDetailRead extends ConversationRead {
  messages: ChatMessageRead[];
}

export interface ConversationCreate {
  title?: string;
  active_dataset_id?: string;
}

export interface ChatMessageCreate {
  content: string;
  active_dataset_id?: string;
}

export interface AssistantChatResponse {
  conversation_id: string;
  user_message: ChatMessageRead;
  assistant_message: ChatMessageRead;
  intent: string;
  insights?: InsightItem[] | null;
  query_result?: NLQueryTranslation | null;
  suggested_prompts: string[];
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

export async function listConversations(
  workspaceIdOverride?: string
): Promise<ConversationRead[]> {
  const headers = resolveWorkspaceHeaders(workspaceIdOverride);
  const res = await fetch('/api/v1/assistant/conversations', {
    method: 'GET',
    headers,
  });

  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: 'Failed to list assistant conversations' }));
    throw new Error(err.detail || 'Failed to list assistant conversations');
  }
  return res.json();
}

export async function createConversation(
  payload: ConversationCreate,
  workspaceIdOverride?: string
): Promise<ConversationRead> {
  const headers = resolveWorkspaceHeaders(workspaceIdOverride);
  const res = await fetch('/api/v1/assistant/conversations', {
    method: 'POST',
    headers,
    body: JSON.stringify(payload),
  });

  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: 'Failed to create assistant conversation' }));
    throw new Error(err.detail || 'Failed to create assistant conversation');
  }
  return res.json();
}

export async function getConversation(
  conversationId: string,
  workspaceIdOverride?: string
): Promise<ConversationDetailRead> {
  const headers = resolveWorkspaceHeaders(workspaceIdOverride);
  const res = await fetch(`/api/v1/assistant/conversations/${conversationId}`, {
    method: 'GET',
    headers,
  });

  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: 'Failed to retrieve assistant conversation' }));
    throw new Error(err.detail || 'Failed to retrieve assistant conversation');
  }
  return res.json();
}

export async function deleteConversation(
  conversationId: string,
  workspaceIdOverride?: string
): Promise<void> {
  const headers = resolveWorkspaceHeaders(workspaceIdOverride);
  const res = await fetch(`/api/v1/assistant/conversations/${conversationId}`, {
    method: 'DELETE',
    headers,
  });

  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: 'Failed to delete assistant conversation' }));
    throw new Error(err.detail || 'Failed to delete assistant conversation');
  }
}

export async function postChatMessage(
  conversationId: string,
  payload: ChatMessageCreate,
  workspaceIdOverride?: string
): Promise<AssistantChatResponse> {
  const headers = resolveWorkspaceHeaders(workspaceIdOverride);
  const res = await fetch(`/api/v1/assistant/conversations/${conversationId}/messages`, {
    method: 'POST',
    headers,
    body: JSON.stringify(payload),
  });

  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: 'Failed to process chat message' }));
    throw new Error(err.detail || 'Failed to process chat message');
  }
  return res.json();
}

export async function getDatasetInsights(
  datasetId: string,
  workspaceIdOverride?: string
): Promise<InsightReportResponse> {
  const headers = resolveWorkspaceHeaders(workspaceIdOverride);
  const res = await fetch(`/api/v1/assistant/insights/${datasetId}`, {
    method: 'POST',
    headers,
  });

  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: 'Failed to discover dataset insights' }));
    throw new Error(err.detail || 'Failed to discover dataset insights');
  }
  return res.json();
}
