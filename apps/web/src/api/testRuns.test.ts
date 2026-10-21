import { afterEach, describe, expect, it, vi } from 'vitest';

import { DEFAULT_SCENARIO_NAME, createTestRun } from './testRuns';

/** A minimal `fetch` stand-in that records the request and returns a canned envelope. */
function stubFetch(body: unknown, init: { ok?: boolean; status?: number } = {}) {
  const calls: { url: string; init: RequestInit | undefined }[] = [];
  const mock = vi.fn(async (url: string | URL, requestInit?: RequestInit) => {
    calls.push({ url: String(url), init: requestInit });
    return {
      ok: init.ok ?? true,
      status: init.status ?? 201,
      json: async () => body
    } as unknown as Response;
  });
  vi.stubGlobal('fetch', mock);
  return calls;
}

const CREATED_RUN = {
  success: true,
  data: {
    run_id: 'run-abc123',
    suite_name: 'Live dashboard run',
    environment: 'local',
    state: 'queued',
    target_agents: []
  },
  error: null
};

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe('createTestRun', () => {
  it('binds the deterministic CRM scenario so the backend schedules execution', async () => {
    const calls = stubFetch(CREATED_RUN);

    await createTestRun({ suite_name: 'Live dashboard run' });

    expect(calls).toHaveLength(1);
    expect(calls[0].url).toContain('/api/v1/test-runs');
    expect(calls[0].init?.method).toBe('POST');

    const payload = JSON.parse(String(calls[0].init?.body));
    // Without a registered scenario the run would stay `queued` with a silent
    // trace stream, so the dashboard must always send one.
    expect(payload.scenario).toEqual({ name: DEFAULT_SCENARIO_NAME, variables: {} });
  });

  it('lets a caller override the default scenario', async () => {
    const calls = stubFetch(CREATED_RUN);

    await createTestRun({ suite_name: 'Live dashboard run', scenario: { name: 'custom-scenario' } });

    const payload = JSON.parse(String(calls[0].init?.body));
    expect(payload.scenario).toEqual({ name: 'custom-scenario' });
  });

  it('unwraps the API envelope into the run detail', async () => {
    stubFetch(CREATED_RUN);

    const run = await createTestRun({ suite_name: 'Live dashboard run' });

    expect(run.run_id).toBe('run-abc123');
    expect(run.state).toBe('queued');
  });

  it('throws the API error message when the response signals failure', async () => {
    stubFetch(
      { success: false, data: null, error: { message: 'Validation failed.' } },
      { ok: false, status: 422 }
    );

    await expect(createTestRun({ suite_name: 'Live dashboard run' })).rejects.toThrow('Validation failed.');
  });
});
