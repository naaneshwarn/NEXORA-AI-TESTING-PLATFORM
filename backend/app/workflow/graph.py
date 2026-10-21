"""Deterministic workflow graph engine (Rahul / Work Package D).

A minimal, dependency-free state-machine engine whose public surface mirrors
LangGraph's ``StateGraph`` API (``add_node`` / ``add_conditional_edges`` /
``compile`` / ``invoke``) so a LangGraph backend can be slotted in later
without changing the workflow service built on top of it.

Design guarantees:
- Deterministic: nodes execute in a fixed, inspectable order; routers are
  pure functions of state; no wall-clock or randomness affects routing.
- Cancellable: before each node the engine consults ``state.should_abort``;
  when it fires the engine routes directly to the finalize node exactly once.
- Failure-safe: an exception inside a node is captured on the state as a
  normalized error and the graph still routes to finalize, so a broken node
  can never leave a run half-executed.
- Explicit cleanup: when the graph declares a cleanup node via
  ``set_cleanup``, every exit path (success, node failure, routing error,
  cancellation) passes through it exactly once before finalize.
"""

from __future__ import annotations

import inspect
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable

NodeFn = Callable[["WorkflowState"], "Awaitable[None] | None"]
RouterFn = Callable[["WorkflowState"], str]
AbortCheck = Callable[[], bool]


@dataclass
class WorkflowState:
    """Mutable state shared across workflow nodes.

    ``context`` carries run-specific inputs (scenario, variables, thresholds)
    supplied by the workflow service; ``data`` is a scratchpad nodes use to
    pass structured results to later nodes.
    """

    run_id: str
    context: dict[str, Any] = field(default_factory=dict)
    visited: list[str] = field(default_factory=list)
    data: dict[str, Any] = field(default_factory=dict)
    error: dict[str, Any] | None = None
    cancelled: bool = False
    should_abort: AbortCheck | None = None

    @property
    def last_node(self) -> str | None:
        return self.visited[-1] if self.visited else None


class WorkflowDefinitionError(RuntimeError):
    """Raised when a graph is mis-configured (unknown node, bad wiring)."""


class WorkflowGraph:
    """Builder for a deterministic workflow graph."""

    def __init__(self) -> None:
        self._nodes: dict[str, NodeFn] = {}
        self._edges: dict[str, str] = {}
        self._conditional: dict[str, tuple[RouterFn, dict[str, str]]] = {}
        self._entry: str | None = None
        self._cleanup: str | None = None
        self._finalize: str | None = None

    def add_node(self, name: str, fn: NodeFn) -> "WorkflowGraph":
        if not name:
            raise WorkflowDefinitionError("Node name must be a non-empty string.")
        if name in self._nodes:
            raise WorkflowDefinitionError(f"Node '{name}' is already registered.")
        self._nodes[name] = fn
        return self

    def add_edge(self, source: str, target: str) -> "WorkflowGraph":
        self._require_node(source)
        self._require_node(target)
        if source in self._conditional:
            raise WorkflowDefinitionError(f"Node '{source}' already has conditional edges.")
        self._edges[source] = target
        return self

    def add_conditional_edges(self, source: str, router: RouterFn, mapping: dict[str, str]) -> "WorkflowGraph":
        self._require_node(source)
        if source in self._edges:
            raise WorkflowDefinitionError(
                f"Node '{source}' already has a fixed edge; remove it before adding conditional edges."
            )
        if not mapping:
            raise WorkflowDefinitionError("Conditional edges require a non-empty routing map.")
        for target in mapping.values():
            self._require_node(target)
        self._conditional[source] = (router, dict(mapping))
        return self

    def set_entry(self, name: str) -> "WorkflowGraph":
        self._require_node(name)
        self._entry = name
        return self

    def set_cleanup(self, name: str) -> "WorkflowGraph":
        """Declare the cleanup node that runs exactly once before finalize.

        Every exit path — normal completion, node failure, routing error, and
        cancellation — is routed through this node before the finalize node
        executes, so resource release is an explicit, testable step.
        """
        self._require_node(name)
        if self._finalize is not None and name == self._finalize:
            raise WorkflowDefinitionError("Cleanup node must be distinct from the finalize node.")
        self._cleanup = name
        return self

    def set_finalize(self, name: str) -> "WorkflowGraph":
        self._require_node(name)
        if self._cleanup is not None and name == self._cleanup:
            raise WorkflowDefinitionError("Finalize node must be distinct from the cleanup node.")
        self._finalize = name
        return self

    def compile(self) -> "CompiledWorkflow":
        if self._entry is None:
            raise WorkflowDefinitionError("Graph has no entry node; call set_entry().")
        if self._finalize is None:
            raise WorkflowDefinitionError("Graph has no finalize node; call set_finalize().")
        if self._cleanup is not None and self._cleanup == self._entry:
            raise WorkflowDefinitionError("Cleanup node must not be the entry node.")
        return CompiledWorkflow(
            nodes=dict(self._nodes),
            edges=dict(self._edges),
            conditional={key: (router, dict(mapping)) for key, (router, mapping) in self._conditional.items()},
            entry=self._entry,
            cleanup=self._cleanup,
            finalize=self._finalize,
        )

    def _require_node(self, name: str) -> None:
        if name not in self._nodes:
            raise WorkflowDefinitionError(f"Node '{name}' is not registered.")


class CompiledWorkflow:
    """An executable workflow graph."""

    def __init__(
        self,
        nodes: dict[str, NodeFn],
        edges: dict[str, str],
        conditional: dict[str, tuple[RouterFn, dict[str, str]]],
        entry: str,
        finalize: str,
        cleanup: str | None = None,
    ) -> None:
        self._nodes = nodes
        self._edges = edges
        self._conditional = conditional
        self._entry = entry
        self._cleanup = cleanup
        self._finalize = finalize

    def _exit_target(self, cleanup_done: bool) -> str:
        """First node of the exit sequence: cleanup (once) then finalize."""
        if self._cleanup is not None and not cleanup_done:
            return self._cleanup
        return self._finalize

    async def invoke(self, state: WorkflowState) -> WorkflowState:
        """Run the graph to completion and return the final state.

        Every exit — normal completion, node failure, routing error, or
        cancellation — passes through the cleanup node (when configured)
        exactly once before finalize runs.
        """
        current: str | None = self._entry
        finalize_pending = False
        cleanup_done = False

        while current is not None:
            is_exit_node = current in (self._finalize, self._cleanup)
            if not is_exit_node and not finalize_pending:
                if state.should_abort is not None and state.should_abort():
                    state.cancelled = True
                    current = self._exit_target(cleanup_done)
                    continue

            await self._run_node(current, state)

            if current == self._cleanup:
                cleanup_done = True
                current = self._finalize
                continue

            if current == self._finalize:
                current = None
                continue

            if state.error is not None and not finalize_pending:
                # Route to the exit sequence so failures always release
                # resources and finalize exactly once.
                finalize_pending = True
                current = self._exit_target(cleanup_done)
                continue

            nxt = self._next_node(current, state)
            # Normal completion also honours the cleanup-before-finalize rule.
            if nxt == self._finalize and self._cleanup is not None and not cleanup_done:
                nxt = self._cleanup
            current = nxt

        return state

    async def _run_node(self, name: str, state: WorkflowState) -> None:
        state.visited.append(name)
        fn = self._nodes[name]
        try:
            result = fn(state)
            if inspect.isawaitable(result):
                await result
        except Exception as exc:  # noqa: BLE001 - engine must normalize every node failure
            state.error = {"code": "workflow_node_error", "node": name, "message": str(exc)}

    def _next_node(self, name: str, state: WorkflowState) -> str | None:
        if name in self._conditional:
            router, mapping = self._conditional[name]
            route = router(state)
            if route not in mapping:
                state.error = {
                    "code": "workflow_routing_error",
                    "node": name,
                    "message": f"Router returned unknown route '{route}'.",
                }
                return self._finalize
            return mapping[route]
        if name in self._edges:
            return self._edges[name]
        # Unwired, non-final node: treat the graph as finished.
        return self._finalize if name != self._finalize else None
