import { appName } from '@nexora/shared';
import { useCallback, useEffect, useState, type FormEvent } from 'react';

import {
  createTestRun,
  getTestRun,
  cancelTestRun,
  type TestRunDetail,
  type CreateTestRunInput
} from './api/testRuns';
import { getWorkflowReadiness, type WorkflowReadiness } from './api/workflow';
import {
  createEnvironment,
  destroyEnvironment,
  getEnvironment,
  markEnvironmentReady,
  resetEnvironment,
  stopEnvironment,
  type SyntheticEnvironment
} from './api/environments';
import { registerAgent, type AgentConfig } from './api/agents';
import TraceStreamViewer from './components/TraceStreamViewer';

type Tab = 'overview' | 'workflows' | 'environments' | 'monitoring';

const SCENARIOS = [
  { id: 'crm-read-customer-summary', label: 'CRM read customer summary (pass)', tone: '#22c55e' },
  { id: 'crm-read-customer-hallucination', label: 'CRM hallucination (expected fail)', tone: '#f59e0b' },
  { id: 'crm-read-customer-agent-failure', label: 'Agent backend failure (expected fail)', tone: '#ef4444' }
] as const;

const ENV_TYPES = ['postgres', 'mysql', 'mongodb', 'redis', 'neo4j', 'docker'] as const;

const ENV_STATUS_TONE: Record<string, string> = {
  ready: '#22c55e',
  provisioning: '#00bcd4',
  stopped: '#94a3b8',
  failed: '#ef4444',
  cancelled: '#f59e0b'
};

export default function App() {
  const [activeTab, setActiveTab] = useState<Tab>('overview');

  // Overview state
  const [readiness, setReadiness] = useState<WorkflowReadiness | null>(null);
  const [readinessError, setReadinessError] = useState<string | null>(null);

  // Workflow state
  const [scenario, setScenario] = useState<string>(SCENARIOS[0].id);
  const [suiteName, setSuiteName] = useState('Dashboard verification run');
  const [runs, setRuns] = useState<TestRunDetail[]>([]);
  const [creatingRun, setCreatingRun] = useState(false);
  const [runError, setRunError] = useState<string | null>(null);
  const [selectedRunId, setSelectedRunId] = useState<string | null>(null);

  // Environment state
  const [envLabel, setEnvLabel] = useState('dashboard-env');
  const [envType, setEnvType] = useState<(typeof ENV_TYPES)[number]>('postgres');
  const [env, setEnv] = useState<SyntheticEnvironment | null>(null);
  const [envBusy, setEnvBusy] = useState(false);
  const [envError, setEnvError] = useState<string | null>(null);
  const [envLog, setEnvLog] = useState<string[]>([]);

  // Agent state
  const [agentId, setAgentId] = useState('');
  const [agentName, setAgentName] = useState('');
  const [agent, setAgent] = useState<AgentConfig | null>(null);
  const [agentBusy, setAgentBusy] = useState(false);
  const [agentError, setAgentError] = useState<string | null>(null);

  // Monitoring state
  const [watchRunId, setWatchRunId] = useState('');

  const refreshReadiness = useCallback(() => {
    getWorkflowReadiness()
      .then((data) => {
        setReadiness(data);
        setReadinessError(null);
      })
      .catch((caught: unknown) => {
        setReadinessError(caught instanceof Error ? caught.message : 'Unable to reach workflow engine.');
      });
  }, []);

  useEffect(() => {
    refreshReadiness();
    const interval = window.setInterval(refreshReadiness, 5000);
    return () => window.clearInterval(interval);
  }, [refreshReadiness]);

  // Auto-poll non-terminal runs so the list reflects backend progress without
  // requiring a manual "Refresh" click. Terminal states stop the polling.
  useEffect(() => {
    const hasPending = runs.some((run) => run.state === 'queued' || run.state === 'running');
    if (!hasPending) return undefined;

    const interval = window.setInterval(() => {
      const pendingIds = runs
        .filter((run) => run.state === 'queued' || run.state === 'running')
        .map((run) => run.run_id);
      if (pendingIds.length === 0) return;
      Promise.all(pendingIds.map((runId) => getTestRun(runId)))
        .then((fresh) => {
          setRuns((previous) =>
            previous.map((run) => fresh.find((update) => update.run_id === run.run_id) ?? run)
          );
        })
        .catch(() => {
          // Transient poll failure — the next interval retries.
        });
    }, 2000);
    return () => window.clearInterval(interval);
  }, [runs]);

  const pushEnvLog = (line: string) => {
    setEnvLog((previous) => [...previous.slice(-7), line]);
  };

  const handleCreateRun = async (event: FormEvent) => {
    event.preventDefault();
    setCreatingRun(true);
    setRunError(null);
    try {
      const input: CreateTestRunInput = {
        suite_name: suiteName.trim() || 'Dashboard verification run',
        scenario: { name: scenario, variables: {} }
      };
      const run = await createTestRun(input);
      setRuns((previous) => [run, ...previous].slice(0, 8));
      setSelectedRunId(run.run_id);
      setWatchRunId(run.run_id);
      refreshReadiness();
    } catch (caught) {
      setRunError(caught instanceof Error ? caught.message : 'Unable to create a test run.');
    } finally {
      setCreatingRun(false);
    }
  };

  const handleRefreshRun = async (runId: string) => {
    try {
      const fresh = await getTestRun(runId);
      setRuns((previous) => previous.map((run) => (run.run_id === runId ? fresh : run)));
    } catch (caught) {
      setRunError(caught instanceof Error ? caught.message : 'Unable to refresh run.');
    }
  };

  const handleCancelRun = async (runId: string) => {
    try {
      const cancelled = await cancelTestRun(runId);
      setRuns((previous) => previous.map((run) => (run.run_id === runId ? cancelled : run)));
      refreshReadiness();
    } catch (caught) {
      setRunError(caught instanceof Error ? caught.message : 'Unable to cancel run.');
    }
  };

  const handleProvisionEnv = async (event: FormEvent) => {
    event.preventDefault();
    setEnvBusy(true);
    setEnvError(null);
    pushEnvLog(`POST /environments → provisioning ${envType} "${envLabel}"`);
    try {
      const created = await createEnvironment({
        environment_type: envType,
        label: envLabel.trim() || 'dashboard-env'
      });
      setEnv(created);
      pushEnvLog(`created ${created.environment_id} (${created.status})`);
      // Poll until the background provisioning settles.
      for (let attempt = 0; attempt < 10; attempt += 1) {
        await new Promise((resolve) => window.setTimeout(resolve, 1500));
        const current = await getEnvironment(created.environment_id);
        setEnv(current);
        if (current.status !== 'provisioning') {
          pushEnvLog(`settled → ${current.status}`);
          break;
        }
      }
    } catch (caught) {
      const message = caught instanceof Error ? caught.message : 'Unable to provision environment.';
      setEnvError(message);
      pushEnvLog(`error: ${message}`);
    } finally {
      setEnvBusy(false);
    }
  };

  const handleEnvAction = async (action: 'ready' | 'reset' | 'stop' | 'destroy') => {
    if (!env) return;
    setEnvBusy(true);
    setEnvError(null);
    pushEnvLog(`POST /environments/${env.environment_id}/${action}`);
    try {
      const updated =
        action === 'ready'
          ? await markEnvironmentReady(env.environment_id)
          : action === 'reset'
            ? await resetEnvironment(env.environment_id)
            : action === 'stop'
              ? await stopEnvironment(env.environment_id)
              : await destroyEnvironment(env.environment_id);
      setEnv(updated);
      pushEnvLog(`→ ${updated.status}`);
    } catch (caught) {
      const message = caught instanceof Error ? caught.message : `Unable to ${action} environment.`;
      setEnvError(message);
      pushEnvLog(`error: ${message}`);
    } finally {
      setEnvBusy(false);
    }
  };

  const handleRegisterAgent = async (event: FormEvent) => {
    event.preventDefault();
    setAgentBusy(true);
    setAgentError(null);
    try {
      const created = await registerAgent({
        agent_id: agentId.trim(),
        name: agentName.trim() || agentId.trim(),
        role: 'executor',
        provider: 'mock',
        status: 'active'
      });
      setAgent(created);
    } catch (caught) {
      setAgentError(caught instanceof Error ? caught.message : 'Unable to register agent.');
    } finally {
      setAgentBusy(false);
    }
  };

  const handleWatch = (event: FormEvent) => {
    event.preventDefault();
    const trimmed = watchRunId.trim();
    setSelectedRunId(trimmed.length > 0 ? trimmed : null);
  };

  const metrics = [
    { label: 'Runs started', value: readiness ? String(readiness.metrics.started) : '—' },
    { label: 'Passed', value: readiness ? String(readiness.metrics.passed) : '—', tone: '#22c55e' },
    { label: 'Failed', value: readiness ? String(readiness.metrics.failed) : '—', tone: '#ef4444' },
    {
      label: 'Success rate',
      value:
        readiness && readiness.metrics.started > 0
          ? `${((readiness.metrics.passed / readiness.metrics.started) * 100).toFixed(1)}%`
          : readiness
            ? '0%'
            : '—'
    },
    { label: 'Cancelled', value: readiness ? String(readiness.metrics.cancelled) : '—' },
    { label: 'Pending contexts', value: readiness ? String(readiness.pending_run_contexts) : '—' }
  ];

  return (
    <main className="shell">
      <header className="topbar">
        <div>
          <p className="eyebrow">AI Sandbox Testing Platform • Phase 3</p>
          <h1>{appName}</h1>
        </div>
        <div style={{ display: 'flex', gap: '10px', flexWrap: 'wrap' }}>
          <button className="secondary-button" onClick={refreshReadiness}>
            Refresh status
          </button>
          <button
            className="primary-button"
            onClick={() => window.open('http://127.0.0.1:8000/docs', '_blank')}
          >
            API docs (Swagger)
          </button>
        </div>
      </header>

      <nav className="tab-bar" aria-label="Dashboard sections">
        {(['overview', 'workflows', 'environments', 'monitoring'] as Tab[]).map((tab) => (
          <button
            key={tab}
            className={activeTab === tab ? 'primary-button' : 'secondary-button'}
            onClick={() => setActiveTab(tab)}
            aria-current={activeTab === tab}
          >
            {tab === 'overview'
              ? 'Overview'
              : tab === 'workflows'
                ? 'Workflows (WP-D)'
                : tab === 'environments'
                  ? 'Environments (WP-B)'
                  : 'Monitoring'}
          </button>
        ))}
      </nav>

      {activeTab === 'overview' && (
        <>
          <section className="metrics-grid" aria-label="Workflow metrics">
            {metrics.map((metric) => (
              <article className="metric-card" key={metric.label}>
                <span>{metric.label}</span>
                <strong style={metric.tone ? { color: metric.tone } : undefined}>{metric.value}</strong>
              </article>
            ))}
          </section>

          <section className="panel">
            <div className="panel-header">
              <h2>System status</h2>
              <span className={`status-pill ${readiness?.ready ? 'trace-tone-success' : 'trace-tone-danger'}`}>
                {readiness ? (readiness.ready ? 'Ready' : 'Degraded') : 'Checking…'}
              </span>
            </div>
            <div className="status-grid">
              <div className="status-card status-ok">
                <strong>Python API (FastAPI)</strong>
                <span>http://127.0.0.1:8000</span>
                <code>/api/v1 + /v1/* + Swagger</code>
              </div>
              <div className="status-card status-ok">
                <strong>Node API (Express)</strong>
                <span>http://127.0.0.1:4000</span>
                <code>legacy placeholder</code>
              </div>
              <div className={`status-card ${readiness?.ready ? 'status-ok' : 'status-warn'}`}>
                <strong>Workflow engine</strong>
                <span>{readiness?.ready ? 'Ready' : readinessError ?? 'Not ready'}</span>
                <code>{readiness?.state_store_path ?? '—'}</code>
              </div>
            </div>
          </section>
        </>
      )}

      {activeTab === 'workflows' && (
        <>
          <section className="panel">
            <div className="panel-header">
              <h2>Execute a scenario run</h2>
              <span className="trace-viewer-run-label">auto-executes in background</span>
            </div>
            <form className="run-picker" onSubmit={handleCreateRun}>
              <div className="form-grid">
                <label className="field" htmlFor="suite-name-input">
                  <span>Suite name</span>
                  <input
                    id="suite-name-input"
                    className="run-input"
                    value={suiteName}
                    onChange={(event) => setSuiteName(event.target.value)}
                    autoComplete="off"
                  />
                </label>
                <label className="field" htmlFor="scenario-select">
                  <span>Scenario</span>
                  <select
                    id="scenario-select"
                    className="run-input"
                    value={scenario}
                    onChange={(event) => setScenario(event.target.value)}
                  >
                    {SCENARIOS.map((option) => (
                      <option key={option.id} value={option.id}>
                        {option.label}
                      </option>
                    ))}
                  </select>
                </label>
              </div>
              <button className="primary-button" type="submit" disabled={creatingRun}>
                {creatingRun ? 'Creating…' : 'Create & execute run'}
              </button>
            </form>
            {runError ? (
              <p className="run-error" role="alert">
                {runError}
              </p>
            ) : null}
          </section>

          <section className="panel">
            <div className="panel-header">
              <h2>Recent runs</h2>
              <span className="trace-viewer-run-label">{runs.length} this session</span>
            </div>
            {runs.length === 0 ? (
              <p className="empty-state">No runs yet — execute a scenario above.</p>
            ) : (
              <div className="table-wrap">
                <table>
                  <thead>
                    <tr>
                      <th>Run ID</th>
                      <th>Suite</th>
                      <th>Environment</th>
                      <th>State</th>
                      <th>Actions</th>
                    </tr>
                  </thead>
                  <tbody>
                    {runs.map((run) => (
                      <tr key={run.run_id}>
                        <td>
                          <code>{run.run_id}</code>
                        </td>
                        <td>{run.suite_name}</td>
                        <td>{run.environment}</td>
                        <td>
                          <span
                            className={`status-pill ${
                              run.state === 'passed'
                                ? 'trace-tone-success'
                                : run.state === 'failed'
                                  ? 'trace-tone-danger'
                                  : run.state === 'cancelled'
                                    ? 'trace-tone-muted'
                                    : 'trace-tone-active'
                            }`}
                          >
                            {run.state}
                          </span>
                        </td>
                        <td>
                          <div className="row-actions">
                            <button className="secondary-button" onClick={() => handleRefreshRun(run.run_id)}>
                              Refresh
                            </button>
                            <button
                              className="secondary-button"
                              onClick={() => {
                                setSelectedRunId(run.run_id);
                                setWatchRunId(run.run_id);
                                setActiveTab('monitoring');
                              }}
                            >
                              Watch
                            </button>
                            {run.state === 'queued' || run.state === 'running' ? (
                              <button className="secondary-button" onClick={() => handleCancelRun(run.run_id)}>
                                Cancel
                              </button>
                            ) : null}
                          </div>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </section>
        </>
      )}

      {activeTab === 'environments' && (
        <>
          <section className="panel">
            <div className="panel-header">
              <h2>Provision a synthetic environment</h2>
              <span className="trace-viewer-run-label">Docker lifecycle • WP-B</span>
            </div>
            <form className="run-picker" onSubmit={handleProvisionEnv}>
              <div className="form-grid">
                <label className="field" htmlFor="env-type-select">
                  <span>Environment type</span>
                  <select
                    id="env-type-select"
                    className="run-input"
                    value={envType}
                    onChange={(event) => setEnvType(event.target.value as (typeof ENV_TYPES)[number])}
                  >
                    {ENV_TYPES.map((type) => (
                      <option key={type} value={type}>
                        {type}
                      </option>
                    ))}
                  </select>
                </label>
                <label className="field" htmlFor="env-label-input">
                  <span>Label</span>
                  <input
                    id="env-label-input"
                    className="run-input"
                    value={envLabel}
                    onChange={(event) => setEnvLabel(event.target.value)}
                    autoComplete="off"
                  />
                </label>
              </div>
              <button className="primary-button" type="submit" disabled={envBusy}>
                {envBusy ? 'Working…' : 'Provision environment'}
              </button>
            </form>
            {envError ? (
              <p className="run-error" role="alert">
                {envError}
              </p>
            ) : null}
          </section>

          {env ? (
            <section className="panel">
              <div className="panel-header">
                <h2>
                  Environment <code>{env.environment_id}</code>
                </h2>
                <span className="status-pill" style={{ color: ENV_STATUS_TONE[env.status] ?? '#94a3b8' }}>
                  {env.status}
                </span>
              </div>
              <dl className="env-meta">
                <div>
                  <dt>Type</dt>
                  <dd>{env.environment_type}</dd>
                </div>
                <div>
                  <dt>Label</dt>
                  <dd>{env.label}</dd>
                </div>
                <div>
                  <dt>Endpoint</dt>
                  <dd>{env.endpoint ?? '—'}</dd>
                </div>
                <div>
                  <dt>Lifecycle</dt>
                  <dd>{String((env.metadata as Record<string, unknown> | undefined)?.lifecycle ?? '—')}</dd>
                </div>
              </dl>
              <div className="row-actions">
                <button className="secondary-button" disabled={envBusy} onClick={() => handleEnvAction('ready')}>
                  Mark ready
                </button>
                <button className="secondary-button" disabled={envBusy} onClick={() => handleEnvAction('reset')}>
                  Reset
                </button>
                <button className="secondary-button" disabled={envBusy} onClick={() => handleEnvAction('stop')}>
                  Stop
                </button>
                <button className="secondary-button" disabled={envBusy} onClick={() => handleEnvAction('destroy')}>
                  Destroy
                </button>
              </div>
            </section>
          ) : null}

          <section className="panel">
            <div className="panel-header">
              <h2>Lifecycle log</h2>
            </div>
            {envLog.length === 0 ? (
              <p className="empty-state">No environment operations yet.</p>
            ) : (
              <ol className="lifecycle-log">
                {envLog.map((line, index) => (
                  <li key={`${index}-${line}`}>{line}</li>
                ))}
              </ol>
            )}
          </section>

          <section className="panel">
            <div className="panel-header">
              <h2>Register a target agent</h2>
              <span className="trace-viewer-run-label">WP-A contract</span>
            </div>
            <form className="run-picker" onSubmit={handleRegisterAgent}>
              <div className="form-grid">
                <label className="field" htmlFor="agent-id-input">
                  <span>Agent ID</span>
                  <input
                    id="agent-id-input"
                    className="run-input"
                    value={agentId}
                    placeholder="agent-executor-1"
                    onChange={(event) => setAgentId(event.target.value)}
                    autoComplete="off"
                    required
                  />
                </label>
                <label className="field" htmlFor="agent-name-input">
                  <span>Display name</span>
                  <input
                    id="agent-name-input"
                    className="run-input"
                    value={agentName}
                    placeholder="Mock Executor"
                    onChange={(event) => setAgentName(event.target.value)}
                    autoComplete="off"
                  />
                </label>
              </div>
              <button className="primary-button" type="submit" disabled={agentBusy}>
                {agentBusy ? 'Registering…' : 'Register agent'}
              </button>
            </form>
            {agentError ? (
              <p className="run-error" role="alert">
                {agentError}
              </p>
            ) : null}
            {agent ? (
              <p className="agent-registered">
                Registered <code>{agent.agent_id}</code> — status <strong>{agent.status}</strong>
              </p>
            ) : null}
          </section>
        </>
      )}

      {activeTab === 'monitoring' && (
        <section className="panel live-panel">
          <div className="panel-header">
            <h2>Live trace stream</h2>
            <span className="trace-viewer-run-label">SSE • tool_trace + run_status</span>
          </div>
          <form className="run-picker" onSubmit={handleWatch}>
            <span className="field-label" id="watch-run-label">
              Test run ID
            </span>
            <div className="run-picker-controls">
              <input
                id="watch-run-id-input"
                className="run-input"
                aria-labelledby="watch-run-label"
                value={watchRunId}
                placeholder="run-xxxxxxxx"
                autoComplete="off"
                onChange={(event) => setWatchRunId(event.target.value)}
              />
              <button className="secondary-button" type="submit">
                Watch run
              </button>
            </div>
          </form>
          <TraceStreamViewer runId={selectedRunId} />
        </section>
      )}
    </main>
  );
}
