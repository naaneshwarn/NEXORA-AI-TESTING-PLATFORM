/** Human-readable helpers shared by the live trace viewer. */

export function formatDuration(ms: number): string {
  if (!Number.isFinite(ms) || ms < 0) {
    return '—';
  }
  if (ms < 1000) {
    return `${ms.toFixed(ms < 10 ? 2 : 1)} ms`;
  }
  return `${(ms / 1000).toFixed(2)} s`;
}

export function formatTimestamp(value: string): string {
  if (!value) {
    return '—';
  }
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return value;
  }
  return date.toLocaleString();
}
