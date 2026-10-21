"""Shared test fixtures for the backend suite.

Isolates the workflow subsystem's durable run-context store into a temporary
directory so tests never write into the repository and always start from a
clean snapshot.  Also silences workflow logging noise during tests.
"""

from __future__ import annotations

import logging
import sys
import tempfile
from pathlib import Path

import pytest

# Make ``app`` importable when pytest is invoked from the repository root.
_BACKEND = Path(__file__).resolve().parents[1]
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))


@pytest.fixture(autouse=True, scope="session")
def _isolate_workflow_state():
    """Redirect the durable run-context store to a throwaway temp directory."""
    import app.workflow.service as service
    import app.workflow.runtime as runtime

    tmp = Path(tempfile.mkdtemp(prefix="nexora-wf-test-"))
    # Point the store at an isolated path and reset cached singletons.
    service._CONTEXT_STORE = runtime.RunContextStore(tmp / "run_contexts.json")
    service.RUN_CONTEXTS.clear()
    # Reduce log noise for the test run.
    logging.getLogger("nexora").setLevel(logging.CRITICAL)

    yield

    logging.getLogger("nexora").setLevel(logging.NOTSET)
