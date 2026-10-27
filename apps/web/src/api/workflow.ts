import { authHeaders } from './auth';
import { API_BASE_URL } from './testRuns';

export interface WorkflowReadiness {
  ready: boolean;
  state_store_path: string;
  pending_run_contexts: number;
  metrics: {
    started: number;
    finished: number;
    passed: number;
    failed: number;
    cancelled: number;
    rejected: number;
    recovered: number;
  };
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

export async function getWorkflowReadiness(): Promise<WorkflowReadiness> {
  const response = await fetch(`${API_BASE_URL}/api/v1/workflow/readiness`, {
    headers: authHeaders(),
  });
  return unwrap<WorkflowReadiness>(response);
}
