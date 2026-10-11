export const appName = 'NEXORA';

export type TestRunStatus = 'queued' | 'running' | 'passed' | 'failed';

export interface TestMetrics {
  activeSuites: number;
  successRate: number;
  agentsOnline: number;
}
