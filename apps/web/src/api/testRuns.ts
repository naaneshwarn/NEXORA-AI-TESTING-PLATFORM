import type { TestRunStatus } from '@nexora/shared';

import { authHeaders } from './auth';

/**
 * Base URL of the NEXORA FastAPI backend.
 *
 * Configure it with the `VITE_API_BASE_URL` environment variable (see
 * `.env.example`). Browser-native `EventSource` cannot send custom headers, so
 * the SSE route is consumed anonymously and no token is ever placed in the URL;
 * the backend's default auth mode keeps reads open while requiring the API key
 * (see `authHeaders`) on mutations.
 */
export const API_BASE_URL = String(import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000').replace(/\/+$/, '');

export type RunState = TestRunStatus | 'cancelled' | 'completed';

/**
 * Identifier of the deterministic CRM scenario the dashboard drives by default.
 *
 * The backend only schedules workflow execution when a run is bound to a
 * registered scenario (see `POST /api/v1/test-runs`); a scenario-less run stays
 * `queued` forever and its trace stream stays silent. The dashboard therefore
 * pins the platform's built-in deterministic scenario so "Create test run"
 * actually executes and streams.
 */
export const DEFAULT_SCENARIO_NAME = 'crm-read-customer-summary';

/** Scenario binding sent with a create-run request. */
export interface ScenarioConfig {
  name: string;
  variables?: Record<string, unknown>;
}

export interface TestRunDetail {
  run_id: string;
  suite_name: string;
  environment: string;
  state: RunState;
  target_agents: string[];
  created_at?: string | null;
  started_at?: string | null;
  completed_at?: string | null;
  message?: string | null;
}

export interface CreateTestRunInput {
  suite_name: string;
  environment?: string;
  target_agents?: string[];
  scenario?: ScenarioConfig;
}

interface ApiError {
  code?: string;
  message?: string;
  details?: unknown;
}

interface ApiEnvelope<T> {
  success: boolean;
  data: T | null;
  error: ApiError | null;
}

/** Absolute SSE endpoint for a test run, e.g. `.../api/v1/test-runs/{id}/stream`. */
export function testRunStreamUrl(runId: string): string {
  return `${API_BASE_URL}/api/v1/test-runs/${encodeURIComponent(runId)}/stream`;
}

async function unwrap<T>(response: Response): Promise<T> {
  const body = (await response.json().catch(() => null)) as ApiEnvelope<T> | null;
  if (!response.ok || !body || body.success === false || body.data == null) {
    const message = body?.error?.message ?? `Request failed with HTTP ${response.status}.`;
    throw new Error(message);
  }
  return body.data;
}

export async function createTestRun(input: CreateTestRunInput): Promise<TestRunDetail> {
  const response = await fetch(`${API_BASE_URL}/api/v1/test-runs`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', ...authHeaders() },
    body: JSON.stringify({
      environment: 'local',
      target_agents: [],
      // Bind the run to a registered scenario so the backend schedules workflow
      // execution; otherwise the run would remain `queued` with no trace stream.
      scenario: { name: DEFAULT_SCENARIO_NAME, variables: {} },
      ...input,
    }),
  });
  return unwrap<TestRunDetail>(response);
}

export async function getTestRun(runId: string): Promise<TestRunDetail> {
  const response = await fetch(`${API_BASE_URL}/api/v1/test-runs/${encodeURIComponent(runId)}`, {
    headers: authHeaders(),
  });
  return unwrap<TestRunDetail>(response);
}

export async function cancelTestRun(runId: string): Promise<TestRunDetail> {
  const response = await fetch(`${API_BASE_URL}/api/v1/test-runs/${encodeURIComponent(runId)}/cancel`, {
    method: 'POST',
    headers: authHeaders(),
  });
  return unwrap<TestRunDetail>(response);
}
