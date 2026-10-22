# NEXORA Web Dashboard (`apps/web`)

React + TypeScript + Vite dashboard for the NEXORA AI Testing Platform. It renders the
orchestration overview and a **real-time tool-call trace viewer** backed by the backend's
Server-Sent Events (SSE) stream.

## Requirements

- Node.js 20+ (verified on Node 24) and npm 10+.
- The backend running locally (default `http://localhost:8000`).

## Configuration

The backend base URL is read from the Vite env variable `VITE_API_BASE_URL` and defaults to
`http://localhost:8000`.

```powershell
Copy-Item apps/web/.env.example apps/web/.env   # optional; defaults work out of the box
```

```
VITE_API_BASE_URL=http://localhost:8000
```

The backend's CORS allow-list already includes the Vite dev origin `http://localhost:5173`
(`backend/app/core/config.py` → `cors_origins`), so no proxy is required.

> **Auth note:** browser-native `EventSource` cannot send custom headers. The stream is
> consumed anonymously (the backend route's `verify_optional_auth` permits this), and an API
> key is **never** placed in the query string.

## Running

```powershell
# from the repository root — builds @nexora/shared, then starts Vite on :5173
npm run dev

# or target the web workspace directly
npm run dev --workspace @nexora/web
```

Start the backend separately (from `backend`):

```powershell
.venv\Scripts\python.exe -m uvicorn app.main:app --reload --port 8000
```

## Live trace stream

### Endpoint

```
GET /api/v1/test-runs/{run_id}/stream        # text/event-stream
```

- Unknown runs return a structured `404` (`{"success": false, "data": null, "error": {...}}`)
  before any stream is opened.
- The stream closes once the run reaches a terminal state (`completed`, `failed`, `cancelled`,
  `passed`).
- Frames are de-duplicated by a stable `id` of the form `"{call_id}:{timestamp}"`.

### Event: `tool_trace`

Emitted once per new tool call. `data` is the stored `ToolCallTraceResponse` JSON:

```json
{
  "run_id": "run_ab12cd34",
  "call_id": "call-1",
  "tool_name": "list_crm_leads",
  "parameters": { "limit": 5 },
  "success": true,
  "result": { "leads": 3 },
  "error": null,
  "execution_time_ms": 12.5,
  "timestamp": "2026-10-13T10:00:00.123456+00:00"
}
```

`parameters` and error detail are already redacted by the backend
(`backend/app/core/redaction.py`); the viewer redacts them again defensively.

### Event: `run_status`

Emitted when the run terminates. `data`:

```json
{ "run_id": "run_ab12cd34", "state": "failed", "message": "Two scenarios failed.", "completed_at": "2026-10-13T10:01:00+00:00" }
```

`state` is one of `queued | running | passed | failed | cancelled`. Because this frame only
arrives on termination, the viewer seeds the *current* state from
`GET /api/v1/test-runs/{run_id}` when it connects; the stream event always wins once it
arrives.

## Architecture

| File | Responsibility |
| :--- | :--- |
| `src/api/testRuns.ts` | REST client: `testRunStreamUrl`, `createTestRun`, `getTestRun`, `cancelTestRun`; unwraps the backend `ApiEnvelope`. |
| `src/hooks/useTestRunStream.ts` | `EventSource` lifecycle: connect on `runId`, parse `tool_trace`/`run_status`, de-duplicate, track connection state, reconnect vs fatal handling, close on terminal/unmount. |
| `src/components/TraceStreamViewer.tsx` | Presentation: run/connection status, newest-first trace list, safe error detail, redacted parameters, loading/empty/error states. |
| `src/utils/redaction.ts` | Client-side mirror of the backend redaction rules. |
| `src/utils/format.ts` | Duration / timestamp formatting. |
| `src/App.tsx` | Dashboard shell + "Live run monitoring" panel (watch an existing run id or create one). |

`useTestRunStream(runId)` returns:

```ts
interface ToolTrace {
  run_id: string;
  call_id: string;
  tool_name: string;
  parameters: Record<string, unknown>;
  result?: unknown;
  success: boolean;
  execution_time_ms: number;
  timestamp: string;
  error?: { code?: string; message?: string } | null;
}

interface TestRunStreamState {
  traces: ToolTrace[];
  runStatus: string | null;
  runStatusMessage: string | null;
  connectionStatus: 'idle' | 'connecting' | 'connected' | 'reconnecting' | 'disconnected' | 'error';
  error: string | null;
}
```

## Testing & checks

```powershell
npm run lint  --workspace @nexora/web   # tsc --noEmit
npm test      --workspace @nexora/web   # Vitest (26 tests)
npm run build --workspace @nexora/web   # tsc --noEmit && vite build
```

`jsdom` has no `EventSource`, so tests install the mock in
`src/test/mockEventSource.ts` via `vi.stubGlobal('EventSource', …)` and drive events
explicitly.

## Known limitations

- The viewer is verified with a mocked `EventSource`; there is no browser-level end-to-end
  test yet. The backend SSE contract is covered by `backend/tests/test_streaming.py`.
- Run status is only pushed on termination, so the displayed status is seeded from REST and
  then updated by the terminal event.
- Parameters are shown as redacted JSON; large payloads are truncated by scroll containers
  rather than paginated.
- No routing or global state library is used — the dashboard is a single page.
