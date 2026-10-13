import { useEffect, useMemo, useState } from 'react';

import { getTestRun } from '../api/testRuns';
import {
  TERMINAL_RUN_STATES,
  traceIdentity,
  useTestRunStream,
  type StreamConnectionStatus,
  type ToolTrace
} from '../hooks/useTestRunStream';
import { formatDuration, formatTimestamp } from '../utils/format';
import { redactSensitiveData } from '../utils/redaction';

const RUN_STATE_LABELS: Record<string, string> = {
  queued: 'Queued',
  running: 'Running',
  passed: 'Passed',
  completed: 'Completed',
  failed: 'Failed',
  cancelled: 'Cancelled'
};

const CONNECTION_LABELS: Record<StreamConnectionStatus, string> = {
  idle: 'Idle',
  connecting: 'Connecting',
  connected: 'Connected',
  reconnecting: 'Reconnecting',
  disconnected: 'Disconnected',
  error: 'Error'
};

const CONNECTION_TONES: Record<StreamConnectionStatus, string> = {
  idle: 'muted',
  connecting: 'pending',
  connected: 'success',
  reconnecting: 'pending',
  disconnected: 'muted',
  error: 'danger'
};

function runStateLabel(state: string | null): string {
  if (!state) {
    return 'Unknown';
  }
  return RUN_STATE_LABELS[state] ?? state;
}

function runStateTone(state: string | null): string {
  switch (state) {
    case 'passed':
    case 'completed':
      return 'success';
    case 'failed':
      return 'danger';
    case 'running':
      return 'active';
    default:
      return 'muted';
  }
}

function isTerminal(state: string | null): boolean {
  return state !== null && (TERMINAL_RUN_STATES as readonly string[]).includes(state);
}

interface StatusBadgeProps {
  label: string;
  value: string;
  tone: string;
  testId: string;
}

function StatusBadge({ label, value, tone, testId }: StatusBadgeProps) {
  return (
    <span className="trace-status" data-testid={testId}>
      <span className="trace-status-label">{label}</span>
      <span className={`status-pill trace-tone-${tone}`}>{value}</span>
    </span>
  );
}

function TraceItem({ trace }: { trace: ToolTrace }) {
  const safeParameters = useMemo(() => redactSensitiveData(trace.parameters), [trace.parameters]);
  const hasParameters = Object.keys(trace.parameters).length > 0;
  const safeErrorMessage =
    trace.error && typeof trace.error.message === 'string' && trace.error.message.length > 0
      ? String(redactSensitiveData(trace.error.message))
      : null;

  return (
    <li className="trace-item" data-success={trace.success}>
      <div className="trace-item-head">
        <span className="trace-tool-name" title={trace.tool_name}>
          {trace.tool_name}
        </span>
        <span className="status-pill trace-outcome" data-success={trace.success}>
          {trace.success ? 'Success' : 'Failed'}
        </span>
      </div>

      <dl className="trace-meta">
        <div>
          <dt>Call ID</dt>
          <dd>
            <code className="trace-call-id">{trace.call_id}</code>
          </dd>
        </div>
        <div>
          <dt>Duration</dt>
          <dd>{formatDuration(trace.execution_time_ms)}</dd>
        </div>
        <div>
          <dt>Timestamp</dt>
          <dd>{formatTimestamp(trace.timestamp)}</dd>
        </div>
      </dl>

      {safeErrorMessage ? <p className="trace-item-error">Error: {safeErrorMessage}</p> : null}

      {hasParameters ? (
        <details className="trace-params">
          <summary>Parameters (redacted)</summary>
          <pre>{JSON.stringify(safeParameters, null, 2)}</pre>
        </details>
      ) : null}
    </li>
  );
}

export interface TraceStreamViewerProps {
  runId: string | null;
  className?: string;
}

/**
 * Live view of a test run's tool-call stream.
 *
 * Consumes {@link useTestRunStream} and renders connection state, run status,
 * and each incoming trace. Sensitive parameter values are redacted before they
 * are displayed.
 */
export default function TraceStreamViewer({ runId, className }: TraceStreamViewerProps) {
  const { traces, runStatus, runStatusMessage, connectionStatus, error } = useTestRunStream(runId);
  const [seedStatus, setSeedStatus] = useState<string | null>(null);
  const newestFirst = useMemo(() => [...traces].reverse(), [traces]);

  // The stream only emits a `run_status` frame when the run terminates, so seed
  // the current state from the REST API. The stream event still wins once it
  // arrives, and a failed lookup is non-fatal.
  useEffect(() => {
    setSeedStatus(null);
    if (!runId) {
      return;
    }
    let cancelled = false;
    getTestRun(runId)
      .then((run) => {
        if (!cancelled) {
          setSeedStatus(run.state);
        }
      })
      .catch(() => undefined);
    return () => {
      cancelled = true;
    };
  }, [runId]);

  const effectiveStatus = runStatus ?? seedStatus;
  const terminal = isTerminal(effectiveStatus);

  return (
    <section className={['trace-viewer', className].filter(Boolean).join(' ')} aria-label="Live trace stream">
      <header className="trace-viewer-header">
        <div>
          <p className="eyebrow">Real-time telemetry</p>
          <h2>Live trace stream</h2>
        </div>
        <div className="trace-viewer-run">
          <span className="trace-viewer-run-label">Test run</span>
          <code className="trace-run-id">{runId ?? 'No run selected'}</code>
        </div>
      </header>

      <div className="trace-status-row">
        <StatusBadge label="Run status" value={runStateLabel(effectiveStatus)} tone={runStateTone(effectiveStatus)} testId="run-status" />
        <StatusBadge
          label="Connection"
          value={CONNECTION_LABELS[connectionStatus]}
          tone={CONNECTION_TONES[connectionStatus]}
          testId="connection-status"
        />
        <span className="trace-count">
          {traces.length} {traces.length === 1 ? 'trace' : 'traces'}
        </span>
      </div>

      {runStatusMessage ? (
        <p className="trace-run-message" data-testid="run-status-message">
          {runStatusMessage}
        </p>
      ) : null}

      {error ? (
        <p className="trace-error" role="alert" data-testid="stream-error">
          {error}
        </p>
      ) : null}

      {!runId ? (
        <p className="trace-empty" data-testid="stream-empty">
          Select or create a test run to watch its live tool-call traces.
        </p>
      ) : traces.length === 0 ? (
        <p className="trace-empty" data-testid="stream-empty">
          {connectionStatus === 'connecting'
            ? 'Connecting to the live trace stream…'
            : connectionStatus === 'error'
              ? 'Unable to connect to the live trace stream.'
              : terminal
                ? 'This run has completed with no recorded tool calls.'
                : 'Waiting for the first tool-call trace…'}
        </p>
      ) : (
        <>
          <p className="trace-order-hint">Newest first</p>
          <ol className="trace-list" aria-live="polite" aria-relevant="additions">
            {newestFirst.map((trace, index) => (
              <TraceItem key={`${traceIdentity(trace)}#${index}`} trace={trace} />
            ))}
          </ol>
        </>
      )}
    </section>
  );
}
