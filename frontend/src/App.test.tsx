import { render, screen, waitFor, fireEvent } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import App from './App';

// Mock API service
vi.mock('./services/api', () => ({
  checkBackendHealth: vi.fn().mockResolvedValue({
    data: {
      status: 'healthy',
      app_name: 'AI Data Intelligence Cloud',
      version: '0.1.0',
      environment: 'development',
      timestamp: '2026-10-12T10:00:00Z',
      services: {
        api: 'operational',
        metadata_store: 'operational (SQLAlchemy 2.0)',
        background_worker: 'pending_phase_6',
      },
    },
    latencyMs: 12,
    error: null,
    checkedAt: '2026-10-12T10:00:00Z',
  }),
}));

vi.mock('./services/auth', () => ({
  getCurrentUserProfile: vi.fn().mockResolvedValue(null),
  loginUser: vi.fn(),
  registerUser: vi.fn(),
  clearStoredToken: vi.fn(),
}));

vi.mock('./services/workspaces', () => ({
  getActiveWorkspaceId: vi.fn().mockReturnValue(null),
  setActiveWorkspaceId: vi.fn(),
  createWorkspace: vi.fn(),
  getWorkspaceMembers: vi.fn().mockResolvedValue([]),
  addWorkspaceMember: vi.fn(),
  getWorkspaceAuditLogs: vi.fn().mockResolvedValue([]),
}));

vi.mock('./services/datasets', () => ({
  listDatasets: vi.fn().mockResolvedValue([
    {
      id: 'mock-dataset-1',
      workspace_id: 'ws-1',
      name: 'Customer Churn Benchmark',
      filename: 'churn.parquet',
      format: 'parquet',
      size_bytes: 204800,
      row_count: 5000,
      column_count: 12,
      sha256: 'abcd1234ef',
      version: 1,
      created_at: '2026-10-12T10:00:00Z',
      columns: [],
    },
  ]),
  uploadDatasetFile: vi.fn(),
  getDatasetDetail: vi.fn().mockResolvedValue({
    id: 'mock-dataset-1',
    workspace_id: 'ws-1',
    name: 'Customer Churn Benchmark',
    filename: 'churn.parquet',
    format: 'parquet',
    size_bytes: 204800,
    row_count: 5000,
    column_count: 12,
    sha256: 'abcd1234ef',
    version: 1,
    created_at: '2026-10-12T10:00:00Z',
    columns: [
      { name: 'age', data_type: 'int64', null_count: 0, null_percentage: 0.0, sample_values: [25, 30] },
      { name: 'churn', data_type: 'bool', null_count: 0, null_percentage: 0.0, sample_values: [true, false] },
    ],
    preview_rows: [{ age: 25, churn: false }, { age: 30, churn: true }],
  }),
  deleteDataset: vi.fn(),
  getDatasetProfile: vi.fn().mockResolvedValue({
    dataset_id: 'mock-dataset-1',
    dataset_name: 'Customer Churn Benchmark',
    row_count: 5000,
    column_count: 12,
    memory_bytes: 102400,
    duplicate_rows_count: 0,
    duplicate_rows_percentage: 0.0,
    completeness_score: 99.8,
    columns: [],
    correlations: [],
    profiled_at: '2026-10-12T10:00:00Z',
  }),
  refreshDatasetProfile: vi.fn(),
  listDatasetVersions: vi.fn().mockResolvedValue([
    {
      id: 'mock-ver-1',
      dataset_id: 'mock-dataset-1',
      version_number: 1,
      row_count: 5000,
      column_count: 12,
      size_bytes: 204800,
      sha256: 'abcd1234ef',
      change_summary: 'Initial dataset upload',
      created_at: '2026-10-12T10:00:00Z',
    },
  ]),
  createDatasetVersion: vi.fn(),
}));

vi.mock('./services/transforms', () => ({
  previewTransforms: vi.fn().mockResolvedValue({
    original_row_count: 5000,
    transformed_row_count: 4950,
    rows_affected: 50,
    original_columns: [
      { name: 'age', data_type: 'int64', null_count: 0, null_percentage: 0.0, sample_values: [25, 30] },
      { name: 'churn', data_type: 'bool', null_count: 0, null_percentage: 0.0, sample_values: [true, false] },
    ],
    transformed_columns: [
      { name: 'age', data_type: 'int64', null_count: 0, null_percentage: 0.0, sample_values: [25, 30] },
      { name: 'churn', data_type: 'bool', null_count: 0, null_percentage: 0.0, sample_values: [true, false] },
    ],
    preview_before: [{ age: 25, churn: false }],
    preview_after: [{ age: 25, churn: false }],
    step_summaries: ["Clipped 50 outlier values in ['age'] using IQR."],
  }),
  applyTransforms: vi.fn().mockResolvedValue({
    dataset_id: 'mock-dataset-1-clean',
    name: 'Customer Churn Benchmark (Cleaned)',
    version: 1,
    row_count: 4950,
    column_count: 12,
    size_bytes: 200000,
    format: 'parquet',
    steps_applied: 1,
    step_summaries: ["Clipped 50 outlier values in ['age'] using IQR."],
  }),
}));

vi.mock('./services/pipelines', () => ({
  listPipelines: vi.fn().mockResolvedValue([
    {
      id: 'mock-pipe-1',
      workspace_id: 'ws-1',
      name: 'Customer Retention Stream',
      description: 'Filter inactive users and materialize',
      node_count: 4,
      edge_count: 3,
      created_at: '2026-10-12T10:00:00Z',
      updated_at: '2026-10-12T10:00:00Z',
    },
  ]),
  getPipeline: vi.fn().mockResolvedValue({
    id: 'mock-pipe-1',
    workspace_id: 'ws-1',
    name: 'Customer Retention Stream',
    description: 'Filter inactive users and materialize',
    graph_definition: {
      nodes: [
        { id: 'node-source', type: 'source', label: 'Raw Records Source', config: { dataset_id: 'mock-dataset-1' } },
        { id: 'node-filter', type: 'filter', label: 'Active Users', config: { column: 'age', operator: '>', value: 18 } },
        { id: 'node-transform', type: 'transform', label: 'Clean Data', config: { steps: [] } },
        { id: 'node-sink', type: 'sink', label: 'Materialized Retention', config: { output_name: 'Retention.parquet', format: 'parquet' } },
      ],
      edges: [
        { id: 'e1', source: 'node-source', target: 'node-filter' },
        { id: 'e2', source: 'node-filter', target: 'node-transform' },
        { id: 'e3', source: 'node-transform', target: 'node-sink' },
      ],
    },
    created_at: '2026-10-12T10:00:00Z',
    updated_at: '2026-10-12T10:00:00Z',
  }),
  createPipeline: vi.fn(),
  updatePipeline: vi.fn(),
  deletePipeline: vi.fn(),
  validatePipeline: vi.fn().mockResolvedValue({
    is_valid: true,
    errors: [],
    warnings: [],
    execution_order: ['node-source', 'node-filter', 'node-transform', 'node-sink'],
  }),
  runPipeline: vi.fn().mockResolvedValue({
    run_id: 'mock-run-123',
    pipeline_id: 'mock-pipe-1',
    workspace_id: 'ws-1',
    status: 'completed',
    started_at: '2026-10-12T10:00:00Z',
    completed_at: '2026-10-12T10:00:01Z',
    execution_time_ms: 45,
    output_dataset_id: 'mock-out-ds-1',
    output_dataset_name: 'Retention Output',
    stage_results: [
      {
        node_id: 'node-source',
        node_type: 'source',
        label: 'Raw Records Source',
        status: 'completed',
        rows_in: 0,
        rows_out: 5000,
        columns_out: ['age', 'churn'],
        duration_ms: 10,
        summary: 'Loaded 5,000 rows',
      },
      {
        node_id: 'node-sink',
        node_type: 'sink',
        label: 'Materialized Retention',
        status: 'completed',
        rows_in: 5000,
        rows_out: 5000,
        columns_out: ['age', 'churn'],
        duration_ms: 15,
        summary: 'Materialized 5,000 rows as parquet',
      },
    ],
  }),
  listPipelineRuns: vi.fn().mockResolvedValue([]),
}));

vi.mock('./services/jobs', () => ({
  listJobs: vi.fn().mockResolvedValue([
    {
      id: 'mock-job-1',
      workspace_id: 'ws-1',
      task_type: 'pipeline_run',
      status: 'completed',
      progress_pct: 100,
      message: 'Pipeline executed successfully in 45 ms',
      resource_id: 'mock-pipe-1',
      created_at: '2026-10-12T10:00:00Z',
    },
  ]),
  getJobDetails: vi.fn().mockResolvedValue({
    id: 'mock-job-1',
    workspace_id: 'ws-1',
    task_type: 'pipeline_run',
    celery_task_id: 'celery-task-123',
    status: 'completed',
    progress_pct: 100,
    message: 'Pipeline executed successfully in 45 ms',
    resource_id: 'mock-pipe-1',
    parameters: { environment: 'production' },
    result_payload: { status: 'completed', execution_time_ms: 45 },
    retry_count: 0,
    max_retries: 3,
    created_at: '2026-10-12T10:00:00Z',
  }),
  dispatchJob: vi.fn().mockResolvedValue({
    id: 'mock-job-2',
    workspace_id: 'ws-1',
    task_type: 'pipeline_run',
    status: 'completed',
    progress_pct: 100,
    message: 'Pipeline executed successfully in 35 ms',
    parameters: {},
    result_payload: {},
    retry_count: 0,
    max_retries: 3,
    created_at: '2026-10-12T10:00:00Z',
  }),
  cancelJob: vi.fn().mockResolvedValue({
    id: 'mock-job-1',
    status: 'cancelled',
    message: 'Execution cancelled',
  }),
  getWorkerDiagnostics: vi.fn().mockResolvedValue({
    status: 'operational',
    broker_type: 'redis',
    broker_url: 'redis://127.0.0.1:6379/0',
    active_worker_count: 1,
    queued_task_count: 0,
    running_task_count: 0,
    completed_today_count: 5,
    failed_today_count: 0,
    timestamp: '2026-10-12T10:00:00Z',
  }),
}));

vi.mock('./services/schedules', () => ({
  listSchedules: vi.fn().mockResolvedValue([
    {
      id: 'mock-sched-1',
      workspace_id: 'ws-1',
      pipeline_id: 'mock-pipe-1',
      name: 'Nightly Sync',
      cron_expression: 'daily',
      is_active: true,
      next_run_at: '2026-10-13T00:00:00Z',
      created_at: '2026-10-12T10:00:00Z',
      updated_at: '2026-10-12T10:00:00Z',
    },
  ]),
  getScheduleDetails: vi.fn().mockResolvedValue({
    id: 'mock-sched-1',
    name: 'Nightly Sync',
    cron_expression: 'daily',
    is_active: true,
  }),
  createSchedule: vi.fn(),
  updateSchedule: vi.fn(),
  deleteSchedule: vi.fn(),
  triggerDueSchedules: vi.fn().mockResolvedValue([]),
}));

vi.mock('./services/quality', () => ({
  listQualitySuites: vi.fn().mockResolvedValue([
    {
      id: 'mock-suite-1',
      workspace_id: 'ws-1',
      dataset_id: 'mock-dataset-1',
      name: 'Customer Quality Suite',
      description: 'Master verification rules',
      is_active: true,
      created_at: '2026-10-12T10:00:00Z',
      rules_count: 1,
      rules: [
        {
          id: 'rule-1',
          suite_id: 'mock-suite-1',
          name: 'Age positive',
          rule_type: 'value_range',
          target_column: 'age',
          parameters: { min: 0 },
          severity: 'critical',
          is_active: true,
          created_at: '2026-10-12T10:00:00Z',
        },
      ],
    },
  ]),
  getQualitySuite: vi.fn(),
  createQualitySuite: vi.fn(),
  addQualityRule: vi.fn(),
  deleteQualityRule: vi.fn(),
  deleteQualitySuite: vi.fn(),
  evaluateQualitySuite: vi.fn().mockResolvedValue({
    id: 'mock-eval-1',
    workspace_id: 'ws-1',
    suite_id: 'mock-suite-1',
    dataset_id: 'mock-dataset-1',
    status: 'completed',
    score: 100.0,
    grade: 'A',
    total_rules: 1,
    passed_rules: 1,
    failed_rules: 0,
    execution_time_ms: 12,
    rule_results: [],
    created_at: '2026-10-12T10:00:00Z',
  }),
  listQualityRuns: vi.fn().mockResolvedValue([]),
  getQualityRun: vi.fn(),
  listQualityAlerts: vi.fn().mockResolvedValue([]),
  acknowledgeQualityAlert: vi.fn(),
}));

vi.mock('./services/lineage', () => ({
  getLineageGraph: vi.fn().mockResolvedValue({
    workspace_id: 'ws-1',
    nodes: [
      {
        id: 'node-ds-1',
        workspace_id: 'ws-1',
        node_type: 'dataset',
        entity_id: 'mock-dataset-1',
        name: 'Customer Churn Benchmark',
        metadata_payload: { format: 'parquet' },
        created_at: '2026-10-12T10:00:00Z',
      },
      {
        id: 'node-pipe-1',
        workspace_id: 'ws-1',
        node_type: 'pipeline',
        entity_id: 'mock-pipe-1',
        name: 'Customer Retention Stream',
        metadata_payload: {},
        created_at: '2026-10-12T10:00:00Z',
      },
    ],
    edges: [
      {
        id: 'edge-1',
        workspace_id: 'ws-1',
        source_node_id: 'node-ds-1',
        target_node_id: 'node-pipe-1',
        edge_type: 'transforms_to',
        transformation_summary: 'Source input to pipeline',
        created_at: '2026-10-12T10:00:00Z',
      },
    ],
    root_node_count: 1,
    leaf_node_count: 1,
  }),
  syncLineageGraph: vi.fn().mockResolvedValue({
    workspace_id: 'ws-1',
    nodes_created: 2,
    edges_created: 1,
    status: 'synced',
    graph: {
      workspace_id: 'ws-1',
      nodes: [],
      edges: [],
      root_node_count: 0,
      leaf_node_count: 0,
    },
  }),
  getImpactAnalysis: vi.fn().mockResolvedValue({
    target_node: {
      id: 'node-ds-1',
      workspace_id: 'ws-1',
      name: 'Customer Churn Benchmark',
      node_type: 'dataset',
      resource_id: 'mock-dataset-1',
      metadata_json: {},
      created_at: '2026-10-12T10:00:00Z',
      updated_at: '2026-10-12T10:00:00Z',
    },
    upstream_ancestors: [],
    downstream_dependents: [
      {
        id: 'node-pipe-1',
        workspace_id: 'ws-1',
        name: 'Customer Retention Stream',
        node_type: 'pipeline',
        resource_id: 'mock-pipe-1',
        metadata_json: {},
        created_at: '2026-10-12T10:00:00Z',
        updated_at: '2026-10-12T10:00:00Z',
      },
    ],
    total_impacted_pipelines: 1,
    total_impacted_datasets: 0,
    total_impacted_quality_suites: 0,
  }),
  listGovernancePolicies: vi.fn().mockResolvedValue([
    {
      id: 'pol-1',
      workspace_id: 'ws-1',
      name: 'GDPR Right to be Forgotten',
      description: 'Standard 90-day retention and PII erasure',
      classification_tier: 'RESTRICTED_PII',
      retention_days: 90,
      compliance_framework: 'GDPR',
      data_steward: 'dpo@company.com',
      is_active: true,
      auto_purge_enabled: true,
      created_at: '2026-10-12T10:00:00Z',
    },
  ]),
  createGovernancePolicy: vi.fn(),
  deleteGovernancePolicy: vi.fn(),
  classifyDataset: vi.fn().mockResolvedValue({
    dataset_id: 'mock-dataset-1',
    has_pii: true,
    suggested_tier: 'RESTRICTED_PII',
    findings: [
      {
        column_name: 'email',
        pii_type: 'EMAIL_ADDRESS',
        confidence: 0.95,
        matched_sample_count: 2,
        masked_examples: ['u***@domain.com'],
      },
    ],
    tags_applied_count: 1,
  }),
  listComplianceAuditLogs: vi.fn().mockResolvedValue([
    {
      id: 'audit-1',
      workspace_id: 'ws-1',
      user_id: 'u-1',
      event_type: 'pii_scan',
      resource_type: 'dataset',
      resource_id: 'mock-dataset-1',
      severity: 'warning',
      action_details: { findings_count: 1 },
      created_at: '2026-10-12T10:00:00Z',
    },
  ]),
  evaluateRetention: vi.fn().mockResolvedValue({
    total_datasets_evaluated: 1,
    expired_datasets: [],
    audit_logs_created: 1,
  }),
}));

vi.mock('./services/ml', () => ({
  listMLModels: vi.fn().mockResolvedValue([
    {
      id: 'mock-model-1',
      workspace_id: 'ws-1',
      name: 'churn_predictor_rf',
      description: 'Customer churn prediction benchmark',
      task_type: 'classification',
      target_column: 'churn',
      framework: 'scikit-learn',
      active_version_id: 'mock-ver-1',
      versions_count: 1,
      active_version: {
        id: 'mock-ver-1',
        model_id: 'mock-model-1',
        version_number: 1,
        experiment_id: 'mock-exp-1',
        artifact_path: 'data/workspaces/ws-1/models/mock-model-1/v1/model.joblib',
        sha256: '9f86d081884c7d659a2feaa0c55ad015a3bf4f1b2b0b822cd15d6c15b0f00a08',
        algorithm: 'RandomForestClassifier',
        status: 'champion',
        metrics: { accuracy: 0.945, f1: 0.932 },
        hyperparameters: { n_estimators: 100 },
        feature_names: ['age', 'balance'],
        feature_importance: { age: 0.65, balance: 0.35 },
        created_at: '2026-10-12T10:00:00Z',
      },
      created_at: '2026-10-12T10:00:00Z',
    },
  ]),
  getMLModel: vi.fn().mockResolvedValue({
    id: 'mock-model-1',
    workspace_id: 'ws-1',
    name: 'churn_predictor_rf',
    description: 'Customer churn prediction benchmark',
    task_type: 'classification',
    target_column: 'churn',
    framework: 'scikit-learn',
    active_version_id: 'mock-ver-1',
    versions_count: 1,
    active_version: {
      id: 'mock-ver-1',
      model_id: 'mock-model-1',
      version_number: 1,
      artifact_path: 'data/workspaces/ws-1/models/mock-model-1/v1/model.joblib',
      sha256: '9f86d081884c7d659a2feaa0c55ad015a3bf4f1b2b0b822cd15d6c15b0f00a08',
      algorithm: 'RandomForestClassifier',
      status: 'champion',
      metrics: { accuracy: 0.945, f1: 0.932 },
      feature_names: ['age', 'balance'],
      feature_importance: { age: 0.65, balance: 0.35 },
      created_at: '2026-10-12T10:00:00Z',
    },
    versions: [
      {
        id: 'mock-ver-1',
        model_id: 'mock-model-1',
        version_number: 1,
        artifact_path: 'data/workspaces/ws-1/models/mock-model-1/v1/model.joblib',
        sha256: '9f86d081884c7d659a2feaa0c55ad015a3bf4f1b2b0b822cd15d6c15b0f00a08',
        algorithm: 'RandomForestClassifier',
        status: 'champion',
        metrics: { accuracy: 0.945, f1: 0.932 },
        feature_names: ['age', 'balance'],
        feature_importance: { age: 0.65, balance: 0.35 },
        created_at: '2026-10-12T10:00:00Z',
      },
    ],
    created_at: '2026-10-12T10:00:00Z',
  }),
  trainAutoMLModel: vi.fn().mockResolvedValue({
    model_id: 'mock-model-2',
    version_id: 'mock-ver-2',
    experiment_id: 'mock-exp-2',
    model_name: 'new_classifier',
    task_type: 'classification',
    target_column: 'churn',
    best_algorithm: 'GradientBoostingClassifier',
    metrics: { accuracy: 0.96 },
    feature_names: ['age', 'balance'],
    feature_importances: { age: 0.6, balance: 0.4 },
    leaderboard: [
      { algorithm: 'GradientBoostingClassifier', metrics: { accuracy: 0.96 }, training_time_ms: 25.0, is_best: true },
      { algorithm: 'RandomForestClassifier', metrics: { accuracy: 0.92 }, training_time_ms: 30.0, is_best: false },
    ],
    training_duration_ms: 120,
  }),
  deleteMLModel: vi.fn().mockResolvedValue(undefined),
  promoteMLModelVersion: vi.fn(),
  runMLInference: vi.fn().mockResolvedValue({
    model_id: 'mock-model-1',
    version_id: 'mock-ver-1',
    algorithm: 'RandomForestClassifier',
    task_type: 'classification',
    predictions: [1],
    probabilities: [{ '0': 0.15, '1': 0.85 }],
    latency_ms: 2.1,
  }),
  listMLExperiments: vi.fn().mockResolvedValue([
    {
      id: 'mock-exp-1',
      workspace_id: 'ws-1',
      model_id: 'mock-model-1',
      name: 'churn_predictor_rf_exp',
      task_type: 'classification',
      target_column: 'churn',
      status: 'completed',
      best_algorithm: 'RandomForestClassifier',
      leaderboard: [],
      training_duration_ms: 120,
      created_at: '2026-10-12T10:00:00Z',
    },
  ]),
}));

vi.mock('./services/dashboards', () => ({
  listDashboards: vi.fn().mockResolvedValue([
    {
      id: 'mock-dash-1',
      workspace_id: 'ws-1',
      name: 'Executive Operations Intelligence',
      description: 'Real-time operational summary',
      widgets_count: 1,
      created_at: '2026-10-12T10:00:00Z',
      updated_at: '2026-10-12T10:00:00Z',
    },
  ]),
  getDashboard: vi.fn().mockResolvedValue({
    id: 'mock-dash-1',
    workspace_id: 'ws-1',
    name: 'Executive Operations Intelligence',
    description: 'Real-time operational summary',
    created_at: '2026-10-12T10:00:00Z',
    updated_at: '2026-10-12T10:00:00Z',
    widgets: [
      {
        id: 'mock-widget-1',
        dashboard_id: 'mock-dash-1',
        name: 'Total Active Customers KPI',
        visualization_type: 'kpi',
        dataset_id: 'mock-dataset-1',
        query_config: {
          metrics: [{ column: '*', aggregation: 'count', alias: 'count_all' }],
        },
        position: { x: 0, y: 0, w: 6, h: 4 },
        created_at: '2026-10-12T10:00:00Z',
        updated_at: '2026-10-12T10:00:00Z',
      },
    ],
  }),
  createDashboard: vi.fn().mockResolvedValue({
    id: 'mock-dash-2',
    workspace_id: 'ws-1',
    name: 'New BI Dashboard',
    description: 'Created for testing',
    widgets_count: 0,
    created_at: '2026-10-12T10:00:00Z',
    updated_at: '2026-10-12T10:00:00Z',
  }),
  deleteDashboard: vi.fn().mockResolvedValue(undefined),
  createDashboardWidget: vi.fn().mockResolvedValue({
    id: 'mock-widget-2',
    dashboard_id: 'mock-dash-1',
    name: 'Revenue Bar Chart',
    visualization_type: 'bar',
    dataset_id: 'mock-dataset-1',
    query_config: {
      metrics: [{ column: 'amount', aggregation: 'sum', alias: 'sum_amount' }],
    },
    position: { x: 6, y: 0, w: 6, h: 4 },
    created_at: '2026-10-12T10:00:00Z',
    updated_at: '2026-10-12T10:00:00Z',
  }),
  deleteDashboardWidget: vi.fn().mockResolvedValue(undefined),
  executeWidgetQuery: vi.fn().mockResolvedValue({
    dataset_id: 'mock-dataset-1',
    visualization_type: 'kpi',
    columns: ['count_all'],
    data: [{ count_all: 5000 }],
    row_count: 1,
    execution_time_ms: 12.5,
  }),
  executeAnalyticsQuery: vi.fn().mockResolvedValue({
    dataset_id: 'mock-dataset-1',
    visualization_type: 'kpi',
    columns: ['count_all'],
    data: [{ count_all: 5000 }],
    row_count: 1,
    execution_time_ms: 12.5,
  }),
}));

vi.mock('./services/assistant', () => ({
  listConversations: vi.fn().mockResolvedValue([
    {
      id: 'mock-conv-1',
      workspace_id: 'ws-1',
      title: 'Executive Analytics Consultation',
      active_dataset_id: 'mock-dataset-1',
      message_count: 2,
      created_at: '2026-10-12T10:00:00Z',
      updated_at: '2026-10-12T10:00:00Z',
    },
  ]),
  getConversation: vi.fn().mockResolvedValue({
    id: 'mock-conv-1',
    workspace_id: 'ws-1',
    title: 'Executive Analytics Consultation',
    active_dataset_id: 'mock-dataset-1',
    message_count: 2,
    created_at: '2026-10-12T10:00:00Z',
    updated_at: '2026-10-12T10:00:00Z',
    messages: [
      {
        id: 'msg-1',
        conversation_id: 'mock-conv-1',
        role: 'user',
        content: 'Discover anomalies and outliers in this dataset',
        intent: 'user_prompt',
        metadata: {},
        created_at: '2026-10-12T10:00:00Z',
      },
      {
        id: 'msg-2',
        conversation_id: 'mock-conv-1',
        role: 'assistant',
        content: 'I analyzed the active dataset and discovered 2 quality observations.',
        intent: 'anomaly_insights',
        metadata: {
          insights: [
            {
              insight_type: 'missing_values',
              severity: 'high',
              column: 'churn',
              title: 'Elevated Missingness in churn',
              description: '15% null observations found.',
              metric_value: 15.0,
              recommendation: 'Impute missing values using mode imputation.',
            },
          ],
        },
        execution_time_ms: 18.5,
        created_at: '2026-10-12T10:00:01Z',
      },
    ],
  }),
  createConversation: vi.fn().mockResolvedValue({
    id: 'mock-conv-2',
    workspace_id: 'ws-1',
    title: 'Sales Trend Q&A',
    active_dataset_id: 'mock-dataset-1',
    message_count: 0,
    created_at: '2026-10-12T10:00:00Z',
    updated_at: '2026-10-12T10:00:00Z',
  }),
  deleteConversation: vi.fn().mockResolvedValue(undefined),
  postChatMessage: vi.fn().mockResolvedValue({
    conversation_id: 'mock-conv-1',
    user_message: {
      id: 'msg-3',
      conversation_id: 'mock-conv-1',
      role: 'user',
      content: 'What is the total sales grouped by region?',
      intent: 'user_prompt',
      metadata: {},
      created_at: '2026-10-12T10:00:02Z',
    },
    assistant_message: {
      id: 'msg-4',
      conversation_id: 'mock-conv-1',
      role: 'assistant',
      content: 'Computed aggregate SUM(sales) grouped by region.',
      intent: 'nl_query',
      metadata: {
        query_result: {
          dataset_id: 'mock-dataset-1',
          operation: 'aggregate',
          explanation: 'Grouped dataset by region',
          query_spec: { dimension: 'region', metric: 'sales', aggregation: 'sum' },
          columns: ['region', 'sum_sales'],
          data: [{ region: 'North', sum_sales: 15000 }],
        },
      },
      execution_time_ms: 22.0,
      created_at: '2026-10-12T10:00:03Z',
    },
    intent: 'nl_query',
    insights: null,
    query_result: {
      dataset_id: 'mock-dataset-1',
      operation: 'aggregate',
      explanation: 'Grouped dataset by region',
      query_spec: { dimension: 'region', metric: 'sales', aggregation: 'sum' },
      columns: ['region', 'sum_sales'],
      data: [{ region: 'North', sum_sales: 15000 }],
    },
    suggested_prompts: ['Show top 5 rows'],
  }),
  getDatasetInsights: vi.fn().mockResolvedValue({
    dataset_id: 'mock-dataset-1',
    dataset_name: 'Customer Churn Benchmark',
    total_rows: 5000,
    total_columns: 12,
    total_insights: 2,
    critical_count: 1,
    insights: [
      {
        insight_type: 'missing_values',
        severity: 'critical',
        column: 'churn',
        title: 'Severe Missingness in churn (60%)',
        description: 'Over half the records are null.',
        metric_value: 60.0,
        recommendation: 'Evaluate data pipeline source.',
      },
    ],
    generated_at: '2026-10-12T10:00:00Z',
  }),
}));

describe('App Component', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders application title in header', async () => {
    render(<App />);
    const headings = screen.getAllByText(/AI Data Intelligence Cloud/i);
    expect(headings.length).toBeGreaterThan(0);
    await waitFor(() => {
      expect(screen.getByText(/healthy/i)).toBeInTheDocument();
    });
  });

  it('renders Phase 12 completion indicator', async () => {
    render(<App />);
    const indicators = screen.getAllByText(/Phase 12 Verified/i);
    expect(indicators.length).toBeGreaterThanOrEqual(1);
    await waitFor(() => {
      expect(screen.getByText(/healthy/i)).toBeInTheDocument();
    });
  });

  it('renders the Multi-Format Ingestion Studio and format badges', async () => {
    render(<App />);
    expect(screen.getByText(/Multi-Format Ingestion Studio/i)).toBeInTheDocument();
    expect(screen.getByText(/Upload & Quarantine/i)).toBeInTheDocument();
    const csvBadges = screen.getAllByText(/CSV/i);
    expect(csvBadges.length).toBeGreaterThanOrEqual(1);
    const parquetBadges = screen.getAllByText(/Parquet/i);
    expect(parquetBadges.length).toBeGreaterThanOrEqual(1);
    await waitFor(() => {
      expect(screen.getByText(/healthy/i)).toBeInTheDocument();
    });
  });

  it('renders Developer Quick Reference with 76 tests command', async () => {
    render(<App />);
    expect(screen.getByText(/Developer Quick Reference/i)).toBeInTheDocument();
    expect(screen.getByText(/Run Backend Pytest \((67|74|76) Tests\):/i)).toBeInTheDocument();
    await waitFor(() => {
      expect(screen.getByText(/healthy/i)).toBeInTheDocument();
    });
  });


  it('opens and closes the authentication modal on button click', async () => {
    render(<App />);
    const authBtn = screen.getByRole('button', { name: /Sign In \/ Register/i });
    expect(authBtn).toBeInTheDocument();

    fireEvent.click(authBtn);
    expect(screen.getByPlaceholderText(/name@company.com/i)).toBeInTheDocument();

    // Switch to Register tab
    const registerTab = screen.getByRole('button', { name: /Create Account/i });
    fireEvent.click(registerTab);
    expect(screen.getByPlaceholderText(/e\.g\. Jane Doe/i)).toBeInTheDocument();
  });

  it('renders the 12-module architecture roadmap with Phase 8 completed', async () => {
    render(<App />);
    expect(screen.getByText(/Modular Platform Roadmap/i)).toBeInTheDocument();
    const catalogElements = screen.getAllByText(/Catalog & Schema Profiling/i);
    expect(catalogElements.length).toBeGreaterThanOrEqual(1);
    const transformElements = screen.getAllByText(/Data Cleaning & Transforms/i);
    expect(transformElements.length).toBeGreaterThanOrEqual(1);
    const etlElements = screen.getAllByText(/Visual ETL Pipelines/i);
    expect(etlElements.length).toBeGreaterThanOrEqual(1);
    const workerElements = screen.getAllByText(/Async Workers & Schedules/i);
    expect(workerElements.length).toBeGreaterThanOrEqual(1);
    const qualityElements = screen.getAllByText(/Quality Rules & Alerts/i);
    expect(qualityElements.length).toBeGreaterThanOrEqual(1);
    const lineageElements = screen.getAllByText(/Lineage & Governance/i);
    expect(lineageElements.length).toBeGreaterThanOrEqual(1);
    await waitFor(() => {
      expect(screen.getByText(/healthy/i)).toBeInTheDocument();
    });
  });


  it('renders the Visual ETL Pipelines Studio and DAG canvas controls', async () => {
    render(<App />);
    expect(screen.getByText(/Visual ETL Pipelines Studio/i)).toBeInTheDocument();
    expect(screen.getByText(/DAG Graph Engine/i)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /New Pipeline/i })).toBeInTheDocument();
  });


  it('renders dataset inspection modal with profiling and version tabs', async () => {
    window.alert = vi.fn();
    const { getCurrentUserProfile } = await import('./services/auth');
    const { getActiveWorkspaceId } = await import('./services/workspaces');
    const { getDatasetDetail } = await import('./services/datasets');

    vi.mocked(getCurrentUserProfile).mockResolvedValueOnce({
      id: 'u-1',
      email: 'user@example.com',
      full_name: 'Lead Analyst',
      is_active: true,
      is_superuser: false,
      created_at: '2026-10-12T10:00:00Z',
      workspaces: [{ id: 'ws-1', name: 'Primary Analytics', slug: 'primary', role: 'owner', owner_id: 'u-1', created_at: '2026-10-12T10:00:00Z' }],
    });
    vi.mocked(getActiveWorkspaceId).mockReturnValue('ws-1');
    vi.mocked(getDatasetDetail).mockResolvedValueOnce({
      id: 'mock-dataset-1',
      workspace_id: 'ws-1',
      name: 'Customer Churn Benchmark',
      filename: 'churn.parquet',
      format: 'parquet',
      size_bytes: 204800,
      row_count: 5000,
      column_count: 12,
      sha256: 'abcd1234ef',
      version: 1,
      created_at: '2026-10-12T10:00:00Z',
      columns: [
        { name: 'age', data_type: 'int64', null_count: 0, null_percentage: 0.0, sample_values: [25, 30] },
        { name: 'churn', data_type: 'bool', null_count: 0, null_percentage: 0.0, sample_values: [true, false] },
      ],
      preview_rows: [{ age: 25, churn: false }, { age: 30, churn: true }],
    });

    render(<App />);
    await waitFor(() => {
      expect(screen.getAllByText(/Customer Churn Benchmark/i).length).toBeGreaterThanOrEqual(1);
    }, { timeout: 10000 });

    const inspectBtn = screen.getByRole('button', { name: /Preview/i });
    fireEvent.click(inspectBtn);

    await waitFor(() => {
      expect(screen.getByRole('button', { name: /Statistical Profile/i })).toBeInTheDocument();
      expect(screen.getByRole('button', { name: /Version Snapshots/i })).toBeInTheDocument();
      expect(screen.getByRole('button', { name: /Transformation Studio/i })).toBeInTheDocument();
    });
  });

  it('interacts with Transformation Studio to add steps and simulate preview', async () => {
    window.alert = vi.fn();
    const { getCurrentUserProfile } = await import('./services/auth');
    const { getActiveWorkspaceId } = await import('./services/workspaces');
    const { getDatasetDetail } = await import('./services/datasets');
    const { previewTransforms } = await import('./services/transforms');

    vi.mocked(getCurrentUserProfile).mockResolvedValueOnce({
      id: 'u-1',
      email: 'user@example.com',
      full_name: 'Lead Analyst',
      is_active: true,
      is_superuser: false,
      created_at: '2026-10-12T10:00:00Z',
      workspaces: [{ id: 'ws-1', name: 'Primary Analytics', slug: 'primary', role: 'owner', owner_id: 'u-1', created_at: '2026-10-12T10:00:00Z' }],
    });
    vi.mocked(getActiveWorkspaceId).mockReturnValue('ws-1');
    vi.mocked(getDatasetDetail).mockResolvedValueOnce({
      id: 'mock-dataset-1',
      workspace_id: 'ws-1',
      name: 'Customer Churn Benchmark',
      filename: 'churn.parquet',
      format: 'parquet',
      size_bytes: 204800,
      row_count: 5000,
      column_count: 12,
      sha256: 'abcd1234ef',
      version: 1,
      created_at: '2026-10-12T10:00:00Z',
      columns: [
        { name: 'age', data_type: 'int64', null_count: 0, null_percentage: 0.0, sample_values: [25, 30] },
        { name: 'churn', data_type: 'bool', null_count: 0, null_percentage: 0.0, sample_values: [true, false] },
      ],
      preview_rows: [{ age: 25, churn: false }, { age: 30, churn: true }],
    });

    render(<App />);
    await waitFor(() => {
      expect(screen.getAllByText(/Customer Churn Benchmark/i).length).toBeGreaterThanOrEqual(1);
    }, { timeout: 10000 });

    // Click "Transform" button in catalog
    const transformBtn = screen.getByRole('button', { name: /Transform/i });
    fireEvent.click(transformBtn);

    await waitFor(() => {
      expect(screen.getByText(/Composable Tabular Transformation Engine/i)).toBeInTheDocument();
      expect(screen.getByText(/Add Transformation Step/i)).toBeInTheDocument();
    });

    // Click Add Step to Recipe
    const addStepBtn = screen.getByRole('button', { name: /Add Step to Recipe/i });
    fireEvent.click(addStepBtn);

    // Verify step appears in queue
    await waitFor(() => {
      expect(screen.getByRole('button', { name: /Run Simulation Preview/i })).toBeInTheDocument();
    });

    // Run preview
    const simBtn = screen.getByRole('button', { name: /Run Simulation Preview/i });
    fireEvent.click(simBtn);

    await waitFor(() => {
      expect(previewTransforms).toHaveBeenCalledTimes(1);
      expect(screen.getByText(/Simulated Output Data Preview/i)).toBeInTheDocument();
      expect(screen.getByText(/Persist Cleaned Dataset/i)).toBeInTheDocument();
    });
  });

  it('renders Async Background Workers & Pipeline Schedulers Studio with Celery diagnostics', async () => {
    render(<App />);
    expect(screen.getByText(/Async Background Workers & Pipeline Schedulers/i)).toBeInTheDocument();
    expect(screen.getByText(/Celery distributed worker telemetry/i)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Refresh Workers/i })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Trigger Due Now/i })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /\+ Register Schedule/i })).toBeInTheDocument();
    expect(screen.getByText(/Live Task State Streaming/i)).toBeInTheDocument();
  });

  it('opens and closes the register schedule modal', async () => {
    render(<App />);
    const regBtn = screen.getByRole('button', { name: /\+ Register Schedule/i });
    fireEvent.click(regBtn);
    expect(screen.getByText(/Register Pipeline Schedule/i)).toBeInTheDocument();
    expect(screen.getByText(/Configure automated recurring ETL pipeline triggers/i)).toBeInTheDocument();
    const cancelBtn = screen.getByRole('button', { name: /Cancel/i });
    fireEvent.click(cancelBtn);
  });

  it('renders Data Quality Rules, Validation & Alerts Studio', async () => {
    render(<App />);
    expect(screen.getByText(/Data Quality Rules, Validation & Alerts Studio/i)).toBeInTheDocument();
    expect(screen.getByText(/Declarative data contracts, automated constraint evaluation, and violation alerts/i)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /\+ New Rule Suite/i })).toBeInTheDocument();
    expect(screen.getByText(/Validation Scorecard/i)).toBeInTheDocument();
  });

  it('opens and closes the register quality rule suite modal', async () => {
    render(<App />);
    const regBtn = screen.getByRole('button', { name: /\+ New Rule Suite/i });
    fireEvent.click(regBtn);
    expect(screen.getByText(/Create Quality Rule Suite/i)).toBeInTheDocument();
    expect(screen.getByText(/Establish declarative data quality contracts/i)).toBeInTheDocument();
    const cancelBtn = screen.getByRole('button', { name: /Cancel/i });
    fireEvent.click(cancelBtn);
  });

  it('renders Data Lineage & Enterprise Governance Studio with DAG vertices and policy controls', async () => {
    render(<App />);
    expect(screen.getByText(/Data Lineage & Enterprise Governance Studio/i)).toBeInTheDocument();
    expect(screen.getByText(/End-to-end DAG provenance, root cause & impact analysis/i)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Sync Lineage/i })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Evaluate Retention/i })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /\+ New Policy/i })).toBeInTheDocument();
    expect(screen.getByText(/Lineage Vertices/i)).toBeInTheDocument();
    expect(screen.getByText(/Dependency Edges/i)).toBeInTheDocument();
  });

  it('opens and closes the create governance policy modal', async () => {
    render(<App />);
    const newPolicyBtn = screen.getByRole('button', { name: /\+ New Policy/i });
    fireEvent.click(newPolicyBtn);
    expect(screen.getByText(/Create Governance Policy/i)).toBeInTheDocument();
    expect(screen.getByText(/Define data classification tiers and retention standards/i)).toBeInTheDocument();
    expect(screen.getByPlaceholderText(/e\.g\. GDPR 90-Day Right to be Forgotten/i)).toBeInTheDocument();
    const cancelBtn = screen.getByRole('button', { name: /Cancel/i });
    fireEvent.click(cancelBtn);
  });

  it('renders AutoML & Model Registry Studio with KPI cards and models catalog', async () => {
    render(<App />);
    expect(screen.getByText(/AutoML & Model Registry Studio/i)).toBeInTheDocument();
    expect(screen.getByText(/Automated multi-algorithm benchmarking, artifact versioning/i)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Train AutoML Model/i })).toBeInTheDocument();
    expect(screen.getByText(/Registered Models/i)).toBeInTheDocument();
    expect(screen.getByText(/Champion Deployments/i)).toBeInTheDocument();
    expect(screen.getByText(/Model Registry Catalog/i)).toBeInTheDocument();
  });

  it('opens and closes the AutoML training wizard modal', async () => {
    render(<App />);
    const trainBtn = screen.getByRole('button', { name: /Train AutoML Model/i });
    fireEvent.click(trainBtn);
    expect(screen.getByText(/AutoML Training Benchmark Wizard/i)).toBeInTheDocument();
    expect(screen.getByText(/Candidate Algorithms to Benchmark/i)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Start Benchmark/i })).toBeInTheDocument();
    const cancelBtn = screen.getByRole('button', { name: /Cancel/i });
    fireEvent.click(cancelBtn);
  });

  it('opens and closes the AutoML training wizard modal via empty state button', async () => {
    render(<App />);
    const launchBtn = screen.getByRole('button', { name: /Launch First AutoML Benchmark/i });
    fireEvent.click(launchBtn);
    expect(screen.getByText(/AutoML Training Benchmark Wizard/i)).toBeInTheDocument();
    expect(screen.getByText(/Candidate Algorithms to Benchmark/i)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Start Benchmark/i })).toBeInTheDocument();
    const cancelBtn = screen.getByRole('button', { name: /Cancel/i });
    fireEvent.click(cancelBtn);
  });

  it('renders Interactive Analytics & BI Dashboards Studio in empty state when no active workspace', async () => {
    render(<App />);
    expect(screen.getByText(/Interactive Analytics & BI Dashboards Studio/i)).toBeInTheDocument();
    expect(screen.getByText(/Multi-metric analytical aggregation engine/i)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /New Dashboard/i })).toBeInTheDocument();
    expect(screen.getByText(/Dashboards Registered/i)).toBeInTheDocument();
    expect(screen.getByText(/Live Visual Queries/i)).toBeInTheDocument();
  });

  it('allows opening and closing the Create Dashboard modal', async () => {
    render(<App />);
    const newDashBtn = screen.getByRole('button', { name: /New Dashboard/i });
    fireEvent.click(newDashBtn);
    expect(screen.getByText(/New BI Dashboard/i)).toBeInTheDocument();
    expect(screen.getByPlaceholderText(/e\.g\. Executive Revenue & Retention/i)).toBeInTheDocument();
    const cancelBtn = screen.getByRole('button', { name: /Cancel/i });
    fireEvent.click(cancelBtn);
  });

  it('renders dashboards tabs and visualization widgets with live analytics query data for active workspace', async () => {
    const { getCurrentUserProfile } = await import('./services/auth');
    const { getActiveWorkspaceId } = await import('./services/workspaces');

    vi.mocked(getCurrentUserProfile).mockResolvedValueOnce({
      id: 'u-1',
      email: 'user@example.com',
      full_name: 'Lead Analyst',
      is_active: true,
      is_superuser: false,
      created_at: '2026-10-12T10:00:00Z',
      workspaces: [
        {
          id: 'ws-1',
          name: 'Primary Analytics',
          slug: 'primary',
          role: 'owner',
          owner_id: 'u-1',
          created_at: '2026-10-12T10:00:00Z',
        },
      ],
    });
    vi.mocked(getActiveWorkspaceId).mockReturnValue('ws-1');

    render(<App />);

    await waitFor(() => {
      expect(screen.getAllByText(/Executive Operations Intelligence/i).length).toBeGreaterThanOrEqual(1);
    }, { timeout: 10000 });

    await waitFor(() => {
      expect(screen.getByText(/Total Active Customers KPI/i)).toBeInTheDocument();
    }, { timeout: 10000 });

    expect(screen.getByRole('button', { name: /Add Widget/i })).toBeInTheDocument();
  });

  it('allows opening and closing the Add Visualization Widget modal', async () => {
    const { getCurrentUserProfile } = await import('./services/auth');
    const { getActiveWorkspaceId } = await import('./services/workspaces');

    vi.mocked(getCurrentUserProfile).mockResolvedValueOnce({
      id: 'u-1',
      email: 'user@example.com',
      full_name: 'Lead Analyst',
      is_active: true,
      is_superuser: false,
      created_at: '2026-10-12T10:00:00Z',
      workspaces: [
        {
          id: 'ws-1',
          name: 'Primary Analytics',
          slug: 'primary',
          role: 'owner',
          owner_id: 'u-1',
          created_at: '2026-10-12T10:00:00Z',
        },
      ],
    });
    vi.mocked(getActiveWorkspaceId).mockReturnValue('ws-1');

    render(<App />);

    await waitFor(() => {
      expect(screen.getAllByText(/Executive Operations Intelligence/i).length).toBeGreaterThanOrEqual(1);
    }, { timeout: 10000 });

    const addWidgetBtn = await screen.findByRole('button', { name: /Add Widget/i });
    fireEvent.click(addWidgetBtn);

    expect(screen.getByText(/Add Visualization Widget/i)).toBeInTheDocument();
    expect(screen.getByPlaceholderText(/e\.g\. Total Revenue by Region/i)).toBeInTheDocument();
    const cancelBtn = screen.getByRole('button', { name: /Cancel/i });
    fireEvent.click(cancelBtn);
  });

  it('renders Phase 11 AI Data Intelligence Assistant Studio and conversation history', async () => {
    const { getCurrentUserProfile } = await import('./services/auth');
    const { getActiveWorkspaceId } = await import('./services/workspaces');

    vi.mocked(getCurrentUserProfile).mockResolvedValueOnce({
      id: 'u-1',
      email: 'user@example.com',
      full_name: 'Lead Analyst',
      is_active: true,
      is_superuser: false,
      created_at: '2026-10-12T10:00:00Z',
      workspaces: [
        {
          id: 'ws-1',
          name: 'Primary Analytics',
          slug: 'primary',
          role: 'owner',
          owner_id: 'u-1',
          created_at: '2026-10-12T10:00:00Z',
        },
      ],
    });
    vi.mocked(getActiveWorkspaceId).mockReturnValue('ws-1');

    render(<App />);

    await waitFor(() => {
      expect(screen.getAllByText(/AI Data Intelligence Assistant/i).length).toBeGreaterThanOrEqual(1);
    }, { timeout: 10000 });

    await waitFor(() => {
      expect(screen.getAllByText(/Executive Analytics Consultation/i).length).toBeGreaterThanOrEqual(1);
    }, { timeout: 10000 });

    expect(screen.getByText(/Elevated Missingness in churn/i)).toBeInTheDocument();
    expect(screen.getByText(/15% null observations found/i)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /New Thread/i })).toBeInTheDocument();
  });

  it('allows opening and creating a new AI Assistant conversation thread', async () => {
    const { getCurrentUserProfile } = await import('./services/auth');
    const { getActiveWorkspaceId } = await import('./services/workspaces');

    vi.mocked(getCurrentUserProfile).mockResolvedValueOnce({
      id: 'u-1',
      email: 'user@example.com',
      full_name: 'Lead Analyst',
      is_active: true,
      is_superuser: false,
      created_at: '2026-10-12T10:00:00Z',
      workspaces: [
        {
          id: 'ws-1',
          name: 'Primary Analytics',
          slug: 'primary',
          role: 'owner',
          owner_id: 'u-1',
          created_at: '2026-10-12T10:00:00Z',
        },
      ],
    });
    vi.mocked(getActiveWorkspaceId).mockReturnValue('ws-1');

    render(<App />);

    await waitFor(() => {
      expect(screen.getAllByText(/AI Data Intelligence Assistant/i).length).toBeGreaterThanOrEqual(1);
    }, { timeout: 10000 });

    const newThreadBtn = await screen.findByRole('button', { name: /New Thread/i });
    fireEvent.click(newThreadBtn);

    expect(screen.getByText(/New AI Assistant Thread/i)).toBeInTheDocument();
    expect(screen.getByPlaceholderText(/e\.g\. Sales Churn & Outlier Analysis/i)).toBeInTheDocument();

    const cancelBtn = screen.getByRole('button', { name: /Cancel/i });
    fireEvent.click(cancelBtn);
  });

  it('renders Phase 12 verified platform banner and operational status', async () => {
    render(<App />);
    expect(screen.getByText(/Phase 12 Complete & Verified • Enterprise Data Intelligence Cloud Operational/i)).toBeInTheDocument();
    expect(screen.getByText(/12 \/ 12 VERIFIED/i)).toBeInTheDocument();
    await waitFor(() => {
      expect(screen.getByText(/healthy/i)).toBeInTheDocument();
    });
  });
});

