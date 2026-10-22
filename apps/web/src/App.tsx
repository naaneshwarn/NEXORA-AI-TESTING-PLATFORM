import { appName, TestRunStatus } from '@nexora/shared';
import { useState, type FormEvent } from 'react';

import { createTestRun } from './api/testRuns';
import TraceStreamViewer from './components/TraceStreamViewer';

const metrics = [
  { label: 'Active suites', value: '18' },
  { label: 'Success rate', value: '96.4%' },
  { label: 'Agents online', value: '7' }
];

const runs: { id: string; status: TestRunStatus; suite: string; duration: string }[] = [
  { id: 'TR-1042', status: 'passed', suite: 'Checkout flow', duration: '02m 15s' },
  { id: 'TR-1043', status: 'running', suite: 'Regression pack', duration: '00m 48s' },
  { id: 'TR-1045', status: 'failed', suite: 'API contract tests', duration: '01m 03s' }
];

const statusTone: Record<TestRunStatus, string> = {
  queued: '#d0d7de',
  running: '#00bcd4',
  passed: '#22c55e',
  failed: '#ef4444'
};

export default function App() {
  const [runIdInput, setRunIdInput] = useState('');
  const [streamRunId, setStreamRunId] = useState<string | null>(null);
  const [creating, setCreating] = useState(false);
  const [createError, setCreateError] = useState<string | null>(null);

  const handleWatch = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const trimmed = runIdInput.trim();
    setStreamRunId(trimmed.length > 0 ? trimmed : null);
  };

  const handleCreate = async () => {
    setCreating(true);
    setCreateError(null);
    try {
      const run = await createTestRun({ suite_name: 'Live dashboard run' });
      setRunIdInput(run.run_id);
      setStreamRunId(run.run_id);
    } catch (caught) {
      setCreateError(caught instanceof Error ? caught.message : 'Unable to create a test run.');
    } finally {
      setCreating(false);
    }
  };

  return (
    <main className="shell">
      <header className="topbar">
        <div>
          <p className="eyebrow">Testing orchestration</p>
          <h1>{appName}</h1>
        </div>
        <button className="primary-button">Launch suite</button>
      </header>

      <section className="metrics-grid">
        {metrics.map((metric) => (
          <article className="metric-card" key={metric.label}>
            <span>{metric.label}</span>
            <strong>{metric.value}</strong>
          </article>
        ))}
      </section>

      <section className="panel">
        <div className="panel-header">
          <h2>Recent test runs</h2>
          <button className="secondary-button">View all</button>
        </div>

        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Run ID</th>
                <th>Status</th>
                <th>Suite</th>
                <th>Duration</th>
              </tr>
            </thead>
            <tbody>
              {runs.map((run) => (
                <tr key={run.id}>
                  <td>{run.id}</td>
                  <td>
                    <span
                      className="status-pill"
                      style={{ backgroundColor: `${statusTone[run.status]}22`, color: statusTone[run.status] }}
                    >
                      {run.status}
                    </span>
                  </td>
                  <td>{run.suite}</td>
                  <td>{run.duration}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      <section className="panel live-panel">
        <div className="panel-header">
          <h2>Live run monitoring</h2>
        </div>

        <form className="run-picker" onSubmit={handleWatch}>
          <label className="run-picker-label" htmlFor="run-id-input">
            Test run ID
          </label>
          <div className="run-picker-controls">
            <input
              id="run-id-input"
              className="run-input"
              type="text"
              value={runIdInput}
              placeholder="e.g. run_ab12cd34"
              autoComplete="off"
              onChange={(event) => setRunIdInput(event.target.value)}
            />
            <button className="secondary-button" type="submit">
              Watch run
            </button>
            <button className="secondary-button" type="button" onClick={handleCreate} disabled={creating}>
              {creating ? 'Creating…' : 'Create test run'}
            </button>
          </div>
        </form>

        {createError ? (
          <p className="run-error" role="alert">
            {createError}
          </p>
        ) : null}

        <TraceStreamViewer runId={streamRunId} />
      </section>
    </main>
  );
}
