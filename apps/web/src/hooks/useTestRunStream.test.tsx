import { act, renderHook } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { MockEventSource } from '../test/mockEventSource';
import { useTestRunStream } from './useTestRunStream';

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
  parameters: {},
  success: false,
  result: null,
  error: { code: 'tool_execution_error', message: 'SMTP timeout' },
  execution_time_ms: 1500,
  timestamp: '2026-10-13T10:00:05+00:00'
};

beforeEach(() => {
  MockEventSource.reset();
  vi.stubGlobal('EventSource', MockEventSource);
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe('useTestRunStream', () => {
  it('is idle and opens no connection without a run id', () => {
    const { result } = renderHook(() => useTestRunStream(null));

    expect(result.current.connectionStatus).toBe('idle');
    expect(result.current.traces).toEqual([]);
    expect(result.current.runStatus).toBeNull();
    expect(MockEventSource.instances).toHaveLength(0);
  });

  it('starts in connecting and subscribes to the run stream', () => {
    const { result } = renderHook(() => useTestRunStream('run-1'));

    expect(result.current.connectionStatus).toBe('connecting');
    expect(MockEventSource.instances).toHaveLength(1);
    expect(MockEventSource.last.url).toContain('/api/v1/test-runs/run-1/stream');
  });

  it('moves to connected only after the open event fires', () => {
    const { result } = renderHook(() => useTestRunStream('run-1'));
    expect(result.current.connectionStatus).toBe('connecting');

    act(() => MockEventSource.last.emitOpen());

    expect(result.current.connectionStatus).toBe('connected');
  });

  it('appends a valid tool trace', () => {
    const { result } = renderHook(() => useTestRunStream('run-1'));
    act(() => MockEventSource.last.emitOpen());

    act(() => MockEventSource.last.emit('tool_trace', SUCCESS_TRACE, 'call-1:t1'));

    expect(result.current.traces).toHaveLength(1);
    expect(result.current.traces[0]).toMatchObject({
      call_id: 'call-1',
      tool_name: 'list_crm_leads',
      success: true,
      execution_time_ms: 12.5
    });
  });

  it('records both successful and failed traces', () => {
    const { result } = renderHook(() => useTestRunStream('run-1'));
    act(() => MockEventSource.last.emitOpen());

    act(() => MockEventSource.last.emit('tool_trace', SUCCESS_TRACE, 'call-1:t1'));
    act(() => MockEventSource.last.emit('tool_trace', FAILED_TRACE, 'call-2:t2'));

    expect(result.current.traces.map((trace) => trace.success)).toEqual([true, false]);
    expect(result.current.traces[1].error?.message).toBe('SMTP timeout');
  });

  it('updates run status and closes the stream on a terminal state', () => {
    const { result } = renderHook(() => useTestRunStream('run-1'));
    act(() => MockEventSource.last.emitOpen());

    act(() =>
      MockEventSource.last.emit('run_status', {
        run_id: 'run-1',
        state: 'failed',
        message: 'Two scenarios failed.',
        completed_at: '2026-10-13T10:01:00+00:00'
      })
    );

    expect(result.current.runStatus).toBe('failed');
    expect(result.current.runStatusMessage).toBe('Two scenarios failed.');
    expect(result.current.connectionStatus).toBe('disconnected');
    expect(MockEventSource.last.closed).toBe(true);
  });

  it('keeps a non-terminal status running', () => {
    const { result } = renderHook(() => useTestRunStream('run-1'));
    act(() => MockEventSource.last.emitOpen());

    act(() =>
      MockEventSource.last.emit('run_status', {
        run_id: 'run-1',
        state: 'running',
        message: null,
        completed_at: null
      })
    );

    expect(result.current.runStatus).toBe('running');
    expect(MockEventSource.last.closed).toBe(false);
  });

  it('ignores malformed payloads without crashing', () => {
    const { result } = renderHook(() => useTestRunStream('run-1'));
    act(() => MockEventSource.last.emitOpen());

    act(() => MockEventSource.last.emitRaw('tool_trace', '{not valid json'));
    act(() => MockEventSource.last.emitRaw('run_status', 'still not json'));
    act(() => MockEventSource.last.emit('tool_trace', { tool_name: 'missing_call_id' }, 'bad'));

    expect(result.current.traces).toHaveLength(0);
    expect(result.current.runStatus).toBeNull();
    expect(result.current.connectionStatus).toBe('connected');
  });

  it('never duplicates a trace with the same identity', () => {
    const { result } = renderHook(() => useTestRunStream('run-1'));
    act(() => MockEventSource.last.emitOpen());

    act(() => MockEventSource.last.emit('tool_trace', SUCCESS_TRACE, 'call-1:t1'));
    act(() => MockEventSource.last.emit('tool_trace', SUCCESS_TRACE, 'call-1:t1'));

    expect(result.current.traces).toHaveLength(1);
  });

  it('treats a transient drop as reconnecting and recovers on reopen', () => {
    const { result } = renderHook(() => useTestRunStream('run-1'));
    act(() => MockEventSource.last.emitOpen());

    act(() => MockEventSource.last.failTransiently());
    expect(result.current.connectionStatus).toBe('reconnecting');
    expect(result.current.error).toBeNull();

    act(() => MockEventSource.last.emitOpen());
    expect(result.current.connectionStatus).toBe('connected');
  });

  it('reports a fatal connection failure as an error', () => {
    const { result } = renderHook(() => useTestRunStream('run-1'));

    act(() => MockEventSource.last.failFatally());

    expect(result.current.connectionStatus).toBe('error');
    expect(result.current.error).toMatch(/closed unexpectedly/i);
  });

  it('resets run state and reconnects when the run id changes', () => {
    const { result, rerender } = renderHook(({ id }: { id: string | null }) => useTestRunStream(id), {
      initialProps: { id: 'run-1' as string | null }
    });
    const first = MockEventSource.instances[0];
    act(() => first.emitOpen());
    act(() => first.emit('tool_trace', SUCCESS_TRACE, 'call-1:t1'));
    expect(result.current.traces).toHaveLength(1);

    rerender({ id: 'run-2' });

    expect(first.closed).toBe(true);
    expect(MockEventSource.instances).toHaveLength(2);
    expect(MockEventSource.last.url).toContain('/test-runs/run-2/stream');
    expect(result.current.traces).toEqual([]);
    expect(result.current.runStatus).toBeNull();
    expect(result.current.connectionStatus).toBe('connecting');
  });

  it('closes the stream when the run is cleared', () => {
    const { rerender } = renderHook(({ id }: { id: string | null }) => useTestRunStream(id), {
      initialProps: { id: 'run-1' as string | null }
    });
    const source = MockEventSource.last;

    rerender({ id: null });

    expect(source.closed).toBe(true);
  });

  it('closes the stream on unmount', () => {
    const { unmount } = renderHook(() => useTestRunStream('run-1'));
    const source = MockEventSource.last;

    unmount();

    expect(source.closed).toBe(true);
  });
});
