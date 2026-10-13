from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from sse_starlette.sse import EventSourceResponse

from app.core.auth import verify_optional_auth
from app.core.store import get_test_run, get_traces_for_run

router = APIRouter(prefix="/test-runs", tags=["streaming"])

# Terminal run states end the stream. ``passed`` is this platform's success
# state; ``completed`` is accepted as an alias for parity with the public
# streaming contract.
TERMINAL_STATES: frozenset[str] = frozenset({"completed", "failed", "cancelled", "passed"})
TRACE_EVENT = "tool_trace"
STATUS_EVENT = "run_status"
POLL_INTERVAL_SECONDS = 1.0


def _trace_key(trace: dict[str, Any]) -> str:
    """Stable identity for a trace so re-polls never re-emit the same record."""
    return f"{trace.get('call_id')}:{trace.get('timestamp')}"


def _status_payload(run: Any | None) -> dict[str, Any]:
    return {
        "run_id": getattr(run, "run_id", None),
        "state": getattr(run, "state", "unknown"),
        "message": getattr(run, "message", None),
        "completed_at": run.completed_at.isoformat() if getattr(run, "completed_at", None) else None,
    }


async def _event_stream(request: Request, run_id: str) -> AsyncIterator[dict[str, Any]]:
    """Poll a run's traces and status, emitting SSE frames until it terminates.

    Only newly observed traces (tracked by ``call_id:timestamp``) are emitted, so
    clients receive each tool call exactly once. The stream closes as soon as the
    run reaches a terminal state or the client disconnects.
    """
    sent: set[str] = set()

    while True:
        if await request.is_disconnected():
            break

        for trace in get_traces_for_run(run_id):
            key = _trace_key(trace)
            if key in sent:
                continue
            sent.add(key)
            yield {
                "event": TRACE_EVENT,
                "id": key,
                "data": json.dumps(trace, default=str),
            }

        run = get_test_run(run_id)
        if run is None or run.state in TERMINAL_STATES:
            yield {
                "event": STATUS_EVENT,
                "data": json.dumps(_status_payload(run), default=str),
            }
            break

        await asyncio.sleep(POLL_INTERVAL_SECONDS)


@router.get("/{run_id}/stream")
async def stream_test_run(
    run_id: str,
    request: Request,
    auth_info: dict = Depends(verify_optional_auth),
) -> EventSourceResponse:
    """Stream live tool-call traces and run status updates for a test run."""
    if get_test_run(run_id) is None:
        raise HTTPException(status_code=404, detail={"message": f"Test run '{run_id}' was not found."})

    return EventSourceResponse(_event_stream(request, run_id))
