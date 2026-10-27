import { authHeaders } from './auth';
import { API_BASE_URL } from './testRuns';

export interface AgentConfig {
  agent_id: string;
  name: string;
  role: 'planner' | 'executor' | 'observer' | 'reporter';
  model?: string | null;
  provider?: string | null;
  endpoint?: string | null;
  status: 'registered' | 'active' | 'disabled';
  config?: Record<string, unknown>;
  created_at?: string | null;
}

export interface RegisterAgentInput {
  agent_id: string;
  name: string;
  role: 'planner' | 'executor' | 'observer' | 'reporter';
  model?: string;
  provider?: string;
  endpoint?: string;
  status?: 'registered' | 'active' | 'disabled';
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

export async function registerAgent(input: RegisterAgentInput): Promise<AgentConfig> {
  const response = await fetch(`${API_BASE_URL}/api/v1/agents`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', ...authHeaders() },
    body: JSON.stringify(input),
  });
  return unwrap<AgentConfig>(response);
}

export async function getAgent(agentId: string): Promise<AgentConfig> {
  const response = await fetch(`${API_BASE_URL}/api/v1/agents/${encodeURIComponent(agentId)}`, {
    headers: authHeaders(),
  });
  return unwrap<AgentConfig>(response);
}
