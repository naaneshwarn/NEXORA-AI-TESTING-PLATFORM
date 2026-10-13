import { useEffect, useRef, useState } from 'react';

import { testRunStreamUrl } from '../api/testRuns';

/** Run states that terminate the backend SSE stream. */
export const TERMINAL_RUN_STATES = ['completed', 'failed', 'cancelled', 'passed'] as const;

const TERMINAL_STATES = new Set<string>(TERMINAL_RUN_STATES);

export type StreamConnectionStatus =
  | 'idle'
  | 'connecting'
  | 'connected'
  | 'reconnecting'
  | 'disconnected'
  | 'error';

/** A single `tool_trace` event payload (mirrors the backend `ToolCallTraceResponse`). */
export interface ToolTrace {
  run_id: string;
  call_id: string;
  tool_name: string;
  parameters: Record<string, unknown>;
  result?: unknown;
  success: boolean;
  execution_time_ms: number;
  timestamp: string;
  error?: { code?: string; message?: string } & Record<string, unknown> | null;
}

/** A `run_status` event payload. */
export interface RunStatusEvent {
  run_id: string | null;
  state: string;
  message: string | null;
  completed_at: string | null;
}

export interface TestRunStreamState {
  traces: ToolTrace[];
  runStatus: string | null;
  runStatusMessage: string | null;
  connectionStatus: StreamConnectionStatus;
  error: string | null;
}

const CONNECTION_ERROR_MESSAGE =
  'The live trace stream closed unexpectedly. The run may not exist or access was denied.';

function isTerminalState(state: string | null | undefined): boolean {
  return typeof state === 'string' && TERMINAL_STATES.has(state);
}

/** Stable identity for a trace so re-delivered events are never duplicated. */
export function traceIdentity(trace: Pick<ToolTrace, 'call_id' | 'timestamp'>): string {
  return `${trace.call_id}:${trace.timestamp}`;
}

function parseToolTrace(raw: unknown): ToolTrace | null {
  if (typeof raw !== 'string') {
    return null;
  }
  let decoded: unknown;
  try {
    decoded = JSON.parse(raw);
  } catch {
    return null;
  }
  if (decoded === null || typeof decoded !== 'object' || Array.isArray(decoded)) {
    return null;
  }
  const record = decoded as Record<string, unknown>;
  const callId = record.call_id;
  const toolName = record.tool_name;
  if (typeof callId !== 'string' || callId.length === 0) {
    return null;
  }
  if (typeof toolName !== 'string' || toolName.length === 0) {
    return null;
  }

  const parameters =
    record.parameters !== null && typeof record.parameters === 'object' && !Array.isArray(record.parameters)
      ? (record.parameters as Record<string, unknown>)
      : {};
  const executionTime = Number(record.execution_time_ms);

  return {
    run_id: typeof record.run_id === 'string' ? record.run_id : '',
    call_id: callId,
    tool_name: toolName,
    parameters,
    result: record.result,
    success: record.success === true,
    execution_time_ms: Number.isFinite(executionTime) && executionTime >= 0 ? executionTime : 0,
    timestamp: typeof record.timestamp === 'string' ? record.timestamp : '',
    error: (record.error as ToolTrace['error']) ?? null
  };
}

function parseRunStatus(raw: unknown): RunStatusEvent | null {
  if (typeof raw !== 'string') {
    return null;
  }
  let decoded: unknown;
  try {
    decoded = JSON.parse(raw);
  } catch {
    return null;
  }
  if (decoded === null || typeof decoded !== 'object' || Array.isArray(decoded)) {
    return null;
  }
  const record = decoded as Record<string, unknown>;
  if (typeof record.state !== 'string' || record.state.length === 0) {
    return null;
  }
  return {
    run_id: typeof record.run_id === 'string' ? record.run_id : null,
    state: record.state,
    message: typeof record.message === 'string' ? record.message : null,
    completed_at: typeof record.completed_at === 'string' ? record.completed_at : null
  };
}

/**
 * Subscribe to the backend's live tool-trace stream for a test run.
 *
 * Returns the accumulated traces (in arrival order), the latest run status, and
 * an accurate connection status. The stream is closed and all run-specific state
 * is reset whenever `runId` changes or the consuming component unmounts.
 */
export function useTestRunStream(runId: string | null): TestRunStreamState {
  const [traces, setTraces] = useState<ToolTrace[]>([]);
  const [runStatus, setRunStatus] = useState<string | null>(null);
  const [runStatusMessage, setRunStatusMessage] = useState<string | null>(null);
  const [connectionStatus, setConnectionStatus] = useState<StreamConnectionStatus>('idle');
  const [error, setError] = useState<string | null>(null);

  const sourceRef = useRef<EventSource | null>(null);
  const seenRef = useRef<Set<string>>(new Set());

  useEffect(() => {
    // Reset every piece of run-specific state when the selected run changes.
    seenRef.current = new Set();
    setTraces([]);
    setRunStatus(null);
    setRunStatusMessage(null);
    setError(null);

    if (!runId) {
      setConnectionStatus('idle');
      return;
    }

    if (typeof EventSource === 'undefined') {
      setConnectionStatus('error');
      setError('Live trace streaming is not supported in this browser.');
      return;
    }

    setConnectionStatus('connecting');
    const source = new EventSource(testRunStreamUrl(runId));
    sourceRef.current = source;
    let terminal = false;

    const handleOpen = () => {
      if (terminal) {
        return;
      }
      setConnectionStatus('connected');
      setError(null);
    };

    const handleTrace = (event: Event) => {
      const message = event as MessageEvent<string>;
      const trace = parseToolTrace(message.data);
      if (!trace) {
        // Malformed payloads are ignored so a bad frame cannot crash the UI.
        return;
      }
      const identity = message.lastEventId || traceIdentity(trace);
      if (seenRef.current.has(identity)) {
        return;
      }
      seenRef.current.add(identity);
      setTraces((previous) => [...previous, trace]);
    };

    const handleStatus = (event: Event) => {
      const message = event as MessageEvent<string>;
      const status = parseRunStatus(message.data);
      if (!status) {
        return;
      }
      setRunStatus(status.state);
      setRunStatusMessage(status.message);
      if (isTerminalState(status.state)) {
        // The server ends the stream after a terminal status; close explicitly so
        // the browser's automatic reconnection does not loop forever.
        terminal = true;
        source.close();
        if (sourceRef.current === source) {
          sourceRef.current = null;
        }
        setConnectionStatus('disconnected');
      }
    };

    const handleError = () => {
      if (terminal) {
        return;
      }
      if (source.readyState === EventSource.CLOSED) {
        // The browser will not retry a fatal failure (e.g. HTTP 404/403).
        setConnectionStatus('error');
        setError(CONNECTION_ERROR_MESSAGE);
      } else {
        // The browser retries automatically; surface it as a reconnection.
        setConnectionStatus('reconnecting');
        setError(null);
      }
    };

    source.onopen = handleOpen;
    source.onerror = handleError;
    source.addEventListener('tool_trace', handleTrace);
    source.addEventListener('run_status', handleStatus);

    return () => {
      source.close();
      if (sourceRef.current === source) {
        sourceRef.current = null;
      }
    };
  }, [runId]);

  return { traces, runStatus, runStatusMessage, connectionStatus, error };
}
