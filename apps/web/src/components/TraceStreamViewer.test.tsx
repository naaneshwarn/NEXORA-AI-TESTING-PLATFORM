import { act, render, screen, within } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { getTestRun } from '../api/testRuns';
import { MockEventSource } from '../test/mockEventSource';
import TraceStreamViewer from './TraceStreamViewer';

// Keep the REST status lookup pending by default so stream tests stay
// synchronous; individual tests opt in with `mockResolvedValueOnce`.
vi.mock('../api/testRuns', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../api/testRuns')>();
  return {
    ...actual,
    getTestRun: vi.fn(() => new Promise(() => undefined))
  };
});

const SUCCESS_TRACE = {
  run_id: 'run-1',
  call_id: 'call-1',
  tool_name: 'list_crm_leads',
  parameters: { limit: 5 },
  success: true,
  result: { leads: 3 },
  execution_time_ms: 12.5,
  timestamp: '2026-10-13T10:00:00+00:00'
};

const FAILED_TRACE = {
  ...SUCCESS_TRACE,
  call_id: 'call-2',
  tool_name: 'send_email',
  parameters: { to: 'user@example.com' },
  success: false,
  result: null,
  error: { code: 'tool_execution_error', message: 'SMTP timeout' },
  execution_time_ms: 1500,
  timestamp: '2026-10-13T10:00:05+00:00'
};

beforeEach(() => {
  MockEventSource.reset();
  vi.mocked(getTestRun).mockClear();
  vi.stubGlobal('EventSource', MockEventSource);
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe('TraceStreamViewer', () => {
  it('prompts the user when no run is selected and opens no stream', () => {
    render(<TraceStreamViewer runId={null} />);

    expect(screen.getByText('No run selected')).toBeInTheDocument();
    expect(screen.getByText(/select or create a test run/i)).toBeInTheDocument();
    expect(MockEventSource.instances).toHaveLength(0);
  });

  it('shows the connecting state before the stream opens', () => {
    render(<TraceStreamViewer runId="run-1" />);

    expect(within(screen.getByTestId('connection-status')).getByText('Connecting')).toBeInTheDocument();
    expect(screen.getByText(/connecting to the live trace stream/i)).toBeInTheDocument();
  });

  it('renders a received tool trace with call id and duration', () => {
    render(<TraceStreamViewer runId="run-1" />);
    act(() => MockEventSource.last.emitOpen());
    act(() => MockEventSource.last.emit('tool_trace', SUCCESS_TRACE, 'call-1:t1'));

    expect(within(screen.getByTestId('connection-status')).getByText('Connected')).toBeInTheDocument();
    expect(screen.getByText('list_crm_leads')).toBeInTheDocument();
    expect(screen.getByText('call-1')).toBeInTheDocument();
    expect(screen.getByText('12.5 ms')).toBeInTheDocument();
    expect(screen.getByText(/1 trace/)).toBeInTheDocument();
  });

  it('updates the run status from a status event', () => {
    render(<TraceStreamViewer runId="run-1" />);
    act(() => MockEventSource.last.emitOpen());
    act(() =>
      MockEventSource.last.emit('run_status', {
        run_id: 'run-1',
        state: 'failed',
        message: 'Two scenarios failed.',
        completed_at: '2026-10-13T10:01:00+00:00'
      })
    );

    expect(within(screen.getByTestId('run-status')).getByText('Failed')).toBeInTheDocument();
    expect(screen.getByTestId('run-status-message')).toHaveTextContent('Two scenarios failed.');
    expect(within(screen.getByTestId('connection-status')).getByText('Disconnected')).toBeInTheDocument();
  });

  it('seeds the current run status from the REST API', async () => {
    vi.mocked(getTestRun).mockResolvedValueOnce({
      run_id: 'run-1',
      suite_name: 'Checkout flow',
      environment: 'local',
      state: 'running',
      target_agents: []
    });

    render(<TraceStreamViewer runId="run-1" />);

    expect(await within(screen.getByTestId('run-status')).findByText('Running')).toBeInTheDocument();
  });

  it('distinguishes successful and failed traces with accessible labels', () => {
    render(<TraceStreamViewer runId="run-1" />);
    act(() => MockEventSource.last.emitOpen());
    act(() => MockEventSource.last.emit('tool_trace', SUCCESS_TRACE, 'call-1:t1'));
    act(() => MockEventSource.last.emit('tool_trace', FAILED_TRACE, 'call-2:t2'));

    expect(screen.getByText('Success')).toBeInTheDocument();
    expect(screen.getByText('Failed')).toBeInTheDocument();
    expect(screen.getByText(/error: smtp timeout/i)).toBeInTheDocument();
    expect(screen.getByText('1.50 s')).toBeInTheDocument();
  });

  it('does not crash on malformed event payloads', () => {
    render(<TraceStreamViewer runId="run-1" />);
    act(() => MockEventSource.last.emitOpen());

    act(() => MockEventSource.last.emitRaw('tool_trace', '{not valid json'));
    act(() => MockEventSource.last.emitRaw('run_status', 'nope'));

    expect(screen.getByText(/waiting for the first tool-call trace/i)).toBeInTheDocument();
    expect(screen.queryByTestId('stream-error')).not.toBeInTheDocument();
  });

  it('surfaces fatal connection errors', () => {
    render(<TraceStreamViewer runId="run-1" />);

    act(() => MockEventSource.last.failFatally());

    expect(within(screen.getByTestId('connection-status')).getByText('Error')).toBeInTheDocument();
    const alert = screen.getByRole('alert');
    expect(alert).toHaveTextContent(/closed unexpectedly/i);
  });

  it('shows reconnection then recovery', () => {
    render(<TraceStreamViewer runId="run-1" />);
    act(() => MockEventSource.last.emitOpen());

    act(() => MockEventSource.last.failTransiently());
    expect(within(screen.getByTestId('connection-status')).getByText('Reconnecting')).toBeInTheDocument();

    act(() => MockEventSource.last.emitOpen());
    expect(within(screen.getByTestId('connection-status')).getByText('Connected')).toBeInTheDocument();
  });

  it('reconnects to a new run when the run id changes', () => {
    const { rerender } = render(<TraceStreamViewer runId="run-1" />);
    const first = MockEventSource.instances[0];
    act(() => first.emitOpen());
    act(() => first.emit('tool_trace', SUCCESS_TRACE, 'call-1:t1'));
    expect(screen.getByText('list_crm_leads')).toBeInTheDocument();

    rerender(<TraceStreamViewer runId="run-2" />);

    expect(first.closed).toBe(true);
    expect(MockEventSource.last.url).toContain('/test-runs/run-2/stream');
    expect(screen.queryByText('list_crm_leads')).not.toBeInTheDocument();
  });

  it('never renders sensitive parameter values', () => {
    render(<TraceStreamViewer runId="run-1" />);
    act(() => MockEventSource.last.emitOpen());
    act(() =>
      MockEventSource.last.emit(
        'tool_trace',
        {
          ...SUCCESS_TRACE,
          parameters: {
            lead_id: 'lead-1',
            password: 'hunter2-super-secret',
            api_key: 'sk-1234567890abcdefghijkl',
            Authorization: 'Bearer abcdefghijklmnop.qrstuvwx.yz012345'
          }
        },
        'call-1:t1'
      )
    );

    const pre = document.querySelector('pre');
    expect(pre?.textContent).toContain('lead-1');
    expect(pre?.textContent).toContain('[REDACTED]');
    expect(document.body.textContent).not.toContain('hunter2-super-secret');
    expect(document.body.textContent).not.toContain('sk-1234567890abcdefghijkl');
    expect(document.body.textContent).not.toContain('abcdefghijklmnop.qrstuvwx.yz012345');
  });

  it('renders long tool names without losing content', () => {
    const longName = `tool_${'segment_'.repeat(40)}end`;
    render(<TraceStreamViewer runId="run-1" />);
    act(() => MockEventSource.last.emitOpen());
    act(() => MockEventSource.last.emit('tool_trace', { ...SUCCESS_TRACE, tool_name: longName }, 'call-1:t1'));

    expect(screen.getByText(longName)).toBeInTheDocument();
  });
});
