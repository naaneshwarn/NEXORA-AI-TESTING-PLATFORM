import { authHeaders } from './auth';
import { API_BASE_URL } from './testRuns';

export interface SyntheticEnvironment {
  environment_id: string;
  environment_type: 'postgres' | 'mysql' | 'mongodb' | 'redis' | 'neo4j' | 'docker';
  label: string;
  status: 'provisioning' | 'ready' | 'stopped' | 'failed' | 'cancelled';
  endpoint?: string | null;
  metadata?: Record<string, unknown>;
  created_at?: string | null;
  updated_at?: string | null;
}

export interface CreateEnvironmentInput {
  environment_type: 'postgres' | 'mysql' | 'mongodb' | 'redis' | 'neo4j' | 'docker';
  label: string;
  config?: Record<string, unknown>;
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

async function unwrap<T>(response: Response): Promise<T> {
  const body = (await response.json().catch(() => null)) as ApiEnvelope<T> | null;
  if (!response.ok || !body || body.success === false || body.data == null) {
    const message = body?.error?.message ?? `Request failed with HTTP ${response.status}.`;
    throw new Error(message);
  }
  return body.data;
}

/** POST-style lifecycle action (all environment transitions are POSTs). */
async function lifecycleAction(path: string): Promise<SyntheticEnvironment> {
  const response = await fetch(`${API_BASE_URL}/api/v1/environments/${encodeURIComponent(path)}`, {
    method: 'POST',
    headers: authHeaders(),
  });
  return unwrap<SyntheticEnvironment>(response);
}

export async function createEnvironment(input: CreateEnvironmentInput): Promise<SyntheticEnvironment> {
  const response = await fetch(`${API_BASE_URL}/api/v1/environments`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', ...authHeaders() },
    body: JSON.stringify(input),
  });
  return unwrap<SyntheticEnvironment>(response);
}

export async function getEnvironment(environmentId: string): Promise<SyntheticEnvironment> {
  const response = await fetch(`${API_BASE_URL}/api/v1/environments/${encodeURIComponent(environmentId)}`, {
    headers: authHeaders(),
  });
  return unwrap<SyntheticEnvironment>(response);
}

export async function stopEnvironment(environmentId: string): Promise<SyntheticEnvironment> {
  return lifecycleAction(`${environmentId}/stop`);
}

export async function resetEnvironment(environmentId: string): Promise<SyntheticEnvironment> {
  return lifecycleAction(`${environmentId}/reset`);
}

export async function destroyEnvironment(environmentId: string): Promise<SyntheticEnvironment> {
  return lifecycleAction(`${environmentId}/destroy`);
}

export async function markEnvironmentReady(environmentId: string): Promise<SyntheticEnvironment> {
  return lifecycleAction(`${environmentId}/ready`);
}
