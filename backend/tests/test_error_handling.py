import concurrent.futures
import pytest
from fastapi.testclient import TestClient

from app.core.config import settings
from app.core.errors import BadStateError, ConflictError, NotFoundError, ValidationError
from app.core.store import InMemoryStore, reset_store, store
from app.main import app
from app.schemas.agent import AgentConfig

client = TestClient(app)


@pytest.fixture(autouse=True)
def clean_store():
    reset_store()
    yield
    reset_store()


def test_standard_error_envelope_structure() -> None:
    # 404
    res_404 = client.get("/api/v1/agents/does-not-exist")
    assert res_404.status_code == 404
    data_404 = res_404.json()
    assert data_404["success"] is False
    assert data_404["data"] is None
    assert data_404["error"]["code"] == "not_found"
    assert isinstance(data_404["error"]["message"], str)
    assert isinstance(data_404["error"]["details"], dict)

    # 422
    res_422 = client.post("/api/v1/agents", json={"role": "planner"})  # missing 'name'
    assert res_422.status_code == 422
    data_422 = res_422.json()
    assert data_422["success"] is False
    assert data_422["data"] is None
    assert data_422["error"]["code"] == "validation_error"
    assert "errors" in data_422["error"]["details"]


def test_store_thread_safety_concurrency() -> None:
    """Verifies that concurrent operations on InMemoryStore do not corrupt state."""
    test_store = InMemoryStore()

    def register_worker(index: int) -> None:
        agent = AgentConfig(
            agent_id=f"agent-thread-{index}",
            name=f"worker-{index}",
            role="executor",
        )
        test_store.register_agent(agent)

    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as executor:
        futures = [executor.submit(register_worker, i) for i in range(50)]
        for future in concurrent.futures.as_completed(futures):
            future.result()

    assert len(test_store.list_agents()) == 50
    for i in range(50):
        assert test_store.has_agent(f"agent-thread-{i}")
