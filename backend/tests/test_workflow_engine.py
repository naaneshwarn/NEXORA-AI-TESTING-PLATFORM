"""Unit tests for the deterministic workflow graph engine.

These tests exercise routing, cancellation, failure capture, and definition
validation.  They are fully deterministic: no timers, network, or credentials.
"""

from __future__ import annotations

import asyncio

import pytest

from app.workflow.graph import (
    WorkflowDefinitionError,
    WorkflowGraph,
    WorkflowState,
    CompiledWorkflow,
)


def _invoke(compiled: CompiledWorkflow, state: WorkflowState) -> WorkflowState:
    """Run the async engine synchronously without adding test dependencies."""
    return asyncio.run(compiled.invoke(state))


def _record(name: str, log: list[str]):
    def node(state: WorkflowState) -> None:
        log.append(name)

    return node


def test_linear_graph_visits_nodes_in_declared_order() -> None:
    log: list[str] = []
    graph = (
        WorkflowGraph()
        .add_node("start", _record("start", log))
        .add_node("middle", _record("middle", log))
        .add_node("finalize", _record("finalize", log))
        .add_edge("start", "middle")
        .add_edge("middle", "finalize")
        .set_entry("start")
        .set_finalize("finalize")
    )

    state = _invoke(graph.compile(), WorkflowState(run_id="run-order"))

    assert log == ["start", "middle", "finalize"]
    assert state.visited == ["start", "middle", "finalize"]
    assert state.error is None
    assert state.cancelled is False


def test_conditional_edges_route_on_state() -> None:
    log: list[str] = []

    def router(state: WorkflowState) -> str:
        return "good" if state.data.get("ok") else "bad"

    graph = (
        WorkflowGraph()
        .add_node("decide", _record("decide", log))
        .add_node("good_path", _record("good_path", log))
        .add_node("bad_path", _record("bad_path", log))
        .add_node("finalize", _record("finalize", log))
        .add_conditional_edges("decide", router, {"good": "good_path", "bad": "bad_path"})
        .add_edge("good_path", "finalize")
        .add_edge("bad_path", "finalize")
        .set_entry("decide")
        .set_finalize("finalize")
    )
    compiled = graph.compile()

    ok_state = _invoke(compiled, WorkflowState(run_id="run-good", data={"ok": True}))
    bad_state = _invoke(compiled, WorkflowState(run_id="run-bad", data={"ok": False}))

    assert ok_state.visited == ["decide", "good_path", "finalize"]
    assert bad_state.visited == ["decide", "bad_path", "finalize"]


def test_node_exception_is_captured_and_finalize_still_runs() -> None:
    log: list[str] = []

    def boom(state: WorkflowState) -> None:
        raise RuntimeError("node exploded")

    graph = (
        WorkflowGraph()
        .add_node("start", _record("start", log))
        .add_node("boom", boom)
        .add_node("finalize", _record("finalize", log))
        .add_edge("start", "boom")
        .add_edge("boom", "finalize")
        .set_entry("start")
        .set_finalize("finalize")
    )

    state = _invoke(graph.compile(), WorkflowState(run_id="run-boom"))

    assert state.error == {"code": "workflow_node_error", "node": "boom", "message": "node exploded"}
    # The failing node is recorded and finalize still executes exactly once.
    assert state.visited == ["start", "boom", "finalize"]
    assert log == ["start", "finalize"]


def test_abort_check_cancels_before_next_node_and_runs_finalize_once() -> None:
    log: list[str] = []
    abort_flags = {"value": False}

    def should_abort() -> bool:
        return abort_flags["value"]

    graph = (
        WorkflowGraph()
        .add_node("start", _record("start", log))
        .add_node("middle", _record("middle", log))
        .add_node("finalize", _record("finalize", log))
        .add_edge("start", "middle")
        .add_edge("middle", "finalize")
        .set_entry("start")
        .set_finalize("finalize")
    )
    compiled = graph.compile()

    # Trip the abort flag while the first node executes.
    def start_and_abort(state: WorkflowState) -> None:
        log.append("start")
        abort_flags["value"] = True

    graph2 = (
        WorkflowGraph()
        .add_node("start", start_and_abort)
        .add_node("middle", _record("middle", log))
        .add_node("finalize", _record("finalize", log))
        .add_edge("start", "middle")
        .add_edge("middle", "finalize")
        .set_entry("start")
        .set_finalize("finalize")
    )

    state = _invoke(graph2.compile(), WorkflowState(run_id="run-cancel", should_abort=should_abort))

    assert state.cancelled is True
    # "middle" is skipped; finalize runs exactly once.
    assert state.visited == ["start", "finalize"]

    # When the check never fires the graph completes normally.
    abort_flags["value"] = False
    normal = _invoke(compiled, WorkflowState(run_id="run-normal", should_abort=should_abort))
    assert normal.cancelled is False
    assert normal.visited == ["start", "middle", "finalize"]


def test_unknown_router_route_becomes_routing_error_and_finalizes() -> None:
    log: list[str] = []

    graph = (
        WorkflowGraph()
        .add_node("decide", _record("decide", log))
        .add_node("finalize", _record("finalize", log))
        .add_conditional_edges("decide", lambda state: "nope", {"ok": "finalize"})
        .set_entry("decide")
        .set_finalize("finalize")
    )

    state = _invoke(graph.compile(), WorkflowState(run_id="run-route"))

    assert state.error is not None
    assert state.error["code"] == "workflow_routing_error"
    assert state.visited == ["decide", "finalize"]


def test_async_node_functions_are_awaited() -> None:
    log: list[str] = []

    async def async_node(state: WorkflowState) -> None:
        log.append("async")

    graph = (
        WorkflowGraph()
        .add_node("async_node", async_node)
        .add_node("finalize", _record("finalize", log))
        .add_edge("async_node", "finalize")
        .set_entry("async_node")
        .set_finalize("finalize")
    )

    _invoke(graph.compile(), WorkflowState(run_id="run-async"))

    assert log == ["async", "finalize"]


def test_graph_definition_errors_are_rejected_eagerly() -> None:
    with pytest.raises(WorkflowDefinitionError, match="already registered"):
        WorkflowGraph().add_node("a", lambda state: None).add_node("a", lambda state: None)

    with pytest.raises(WorkflowDefinitionError, match="not registered"):
        WorkflowGraph().add_edge("ghost", "other")

    with pytest.raises(WorkflowDefinitionError, match="no entry node"):
        WorkflowGraph().add_node("f", lambda state: None).set_finalize("f").compile()

    with pytest.raises(WorkflowDefinitionError, match="no finalize node"):
        WorkflowGraph().add_node("s", lambda state: None).set_entry("s").compile()

    with pytest.raises(WorkflowDefinitionError, match="conditional edges"):
        WorkflowGraph().add_node("a", lambda state: None).add_node("b", lambda state: None).add_node(
            "c", lambda state: None
        ).add_edge("a", "b").add_conditional_edges("a", lambda state: "x", {"x": "c"})

    with pytest.raises(WorkflowDefinitionError, match="non-empty routing map"):
        WorkflowGraph().add_node("a", lambda state: None).add_node("b", lambda state: None).add_conditional_edges(
            "a", lambda state: "x", {}
        )


def test_state_helpers() -> None:
    state = WorkflowState(run_id="run-helpers")

    assert state.last_node is None
    state.visited.append("only")
    assert state.last_node == "only"
