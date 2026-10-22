/**
 * NEXORA Frontend API Client
 *
 * Configured to connect to the FastAPI backend using VITE_API_BASE_URL.
 * Falls back to http://localhost:8000/api/v1 in local development.
 */

export const API_BASE_URL =
  (import.meta.env.VITE_API_BASE_URL as string | undefined)?.replace(/\/+$/, '') ||
  'http://localhost:8000/api/v1';

export interface ApiEnvelope<T> {
  success: boolean;
  data: T | null;
  error: {
    code: string;
    message: string;
    details?: Record<string, unknown>;
  } | null;
}

export interface HealthResponse {
  status: string;
  service: string;
  environment: string;
  version: string;
}

export interface AgentConfig {
  agent_id?: string;
  name: string;
  role: 'planner' | 'executor' | 'observer' | 'reporter';
  model?: string;
  provider?: string;
  endpoint?: string;
  status: 'registered' | 'active' | 'disabled';
  config?: Record<string, unknown>;
  created_at?: string;
}

export interface RunDetail {
  run_id: string;
  suite_name: string;
  environment: string;
  state: 'queued' | 'running' | 'passed' | 'failed' | 'cancelled';
  target_agents: string[];
  created_at?: string;
  started_at?: string;
  completed_at?: string;
  message?: string;
}

export interface RunCreateRequest {
  suite_name: string;
  scenario?: {
    name: string;
    description?: string;
    variables?: Record<string, unknown>;
  };
  environment?: string;
  tags?: string[];
  target_agents?: string[];
  config?: Record<string, unknown>;
}

export interface SyntheticEnvironment {
  environment_id: string;
  environment_type: 'postgres' | 'mysql' | 'mongodb' | 'redis' | 'neo4j' | 'docker';
  label: string;
  status: 'provisioning' | 'ready' | 'stopped' | 'failed' | 'cancelled';
  endpoint?: string | null;
  metadata?: Record<string, unknown>;
  created_at?: string;
  updated_at?: string;
}

export interface ReportSummary {
  report_id: string;
  run_id: string;
  score: number;
  status: 'generated' | 'partial' | 'failed';
  summary: string;
  metrics: Record<string, number>;
  generated_at?: string;
}

async function request<T>(endpoint: string, options?: RequestInit): Promise<ApiEnvelope<T>> {
  const url = `${API_BASE_URL}${endpoint.startsWith('/') ? endpoint : `/${endpoint}`}`;
  const response = await fetch(url, {
    ...options,
    headers: {
      'Content-Type': 'application/json',
      ...options?.headers,
    },
  });

  const body = (await response.json()) as ApiEnvelope<T>;
  if (!response.ok && body.success !== false) {
    throw new Error(`API request failed with status ${response.status}`);
  }
  return body;
}

export const api = {
  // Health
  checkHealth: async (): Promise<HealthResponse> => {
    const res = await fetch(`${API_BASE_URL}/health`);
    return res.json();
  },

  // Agents
  getAgents: () => request<AgentConfig[]>('/agents'),
  getAgent: (agentId: string) => request<AgentConfig>(`/agents/${agentId}`),
  registerAgent: (agent: AgentConfig) =>
    request<AgentConfig>('/agents', {
      method: 'POST',
      body: JSON.stringify(agent),
    }),

  // Test runs
  getTestRuns: () => request<RunDetail[]>('/test-runs'),
  getTestRun: (runId: string) => request<RunDetail>(`/test-runs/${runId}`),
  createTestRun: (run: RunCreateRequest) =>
    request<RunDetail>('/test-runs', {
      method: 'POST',
      body: JSON.stringify(run),
    }),
  cancelTestRun: (runId: string) =>
    request<{ run_id: string; state: string; message?: string }>(`/test-runs/${runId}/cancel`, {
      method: 'POST',
    }),
  getTestRunEvents: (runId: string) => request<unknown[]>(`/test-runs/${runId}/events`),

  // Environments
  getEnvironments: () => request<SyntheticEnvironment[]>('/environments'),
  getEnvironment: (envId: string) => request<SyntheticEnvironment>(`/environments/${envId}`),
  createEnvironment: (env: {
    environment_type: SyntheticEnvironment['environment_type'];
    label: string;
    config?: Record<string, unknown>;
  }) =>
    request<SyntheticEnvironment>('/environments', {
      method: 'POST',
      body: JSON.stringify(env),
    }),
  stopEnvironment: (envId: string) =>
    request<SyntheticEnvironment>(`/environments/${envId}/stop`, {
      method: 'POST',
    }),

  // Reports
  getReport: (reportId: string) => request<ReportSummary>(`/reports/${reportId}`),
  getReportByRun: (runId: string) => request<ReportSummary>(`/reports/runs/${runId}`),
};
