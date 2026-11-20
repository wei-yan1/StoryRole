"""A small graph runtime for one character turn.

Node / edge / state is the whole model. The production turn uses a minimal
self-loop for review-repair, while `run_dag` is available for fan-out/fan-in
phases. It is intentionally smaller than LangGraph and has no external
checkpoint database.
"""

from __future__ import annotations

import asyncio
import inspect
import time
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable

NodeFn = Callable[[dict[str, Any]], dict[str, Any] | Awaitable[dict[str, Any]] | None]
ConditionFn = Callable[[dict[str, Any]], bool]
CheckpointFn = Callable[[dict[str, Any]], None]


@dataclass
class Edge:
    source: str
    target: str
    condition: ConditionFn | None = None
    label: str = ""


@dataclass
class NodeSpec:
    name: str
    fn: NodeFn
    description: str = ""


@dataclass
class GraphRun:
    state: dict[str, Any]
    visited: list[str] = field(default_factory=list)
    steps: list[dict[str, Any]] = field(default_factory=list)
    stop_reason: str = "completed"

    def as_dict(self) -> dict[str, Any]:
        return {
            "visited": list(self.visited),
            "steps": list(self.steps),
            "stop_reason": self.stop_reason,
            "node_values": dict(self.state.get("nodes") or {}),
        }


class GraphRuntime:
    def __init__(self) -> None:
        self.nodes: dict[str, NodeSpec] = {}
        self.edges: dict[str, list[Edge]] = {}

    def add_node(self, name: str, fn: NodeFn, *, description: str = "") -> None:
        self.nodes[name] = NodeSpec(name=name, fn=fn, description=description)

    def add_edge(self, source: str, target: str, *, label: str = "") -> None:
        self.edges.setdefault(source, []).append(Edge(source=source, target=target, label=label))

    def add_conditional_edge(
        self, source: str, target: str, condition: ConditionFn, *, label: str = "",
    ) -> None:
        self.edges.setdefault(source, []).append(
            Edge(source=source, target=target, condition=condition, label=label)
        )

    async def _execute(self, name: str, state: dict[str, Any]) -> float:
        spec = self.nodes.get(name)
        if spec is None:
            state.setdefault("nodes", {})[name] = {}
            return 0.0
        started = time.perf_counter()
        result = spec.fn(state)
        if inspect.isawaitable(result):
            result = await result
        state.setdefault("nodes", {})[name] = result if isinstance(result, dict) else {}
        return (time.perf_counter() - started) * 1000

    @staticmethod
    def _active_edges(runtime: "GraphRuntime", name: str, state: dict[str, Any]) -> list[Edge]:
        active: list[Edge] = []
        for edge in runtime.edges.get(name, []):
            if edge.condition is None:
                active.append(edge)
                continue
            try:
                if edge.condition(state):
                    active.append(edge)
            except Exception:
                # A broken condition must not execute the wrong branch.
                continue
        return active

    async def run_linear(
        self,
        *,
        start: str,
        end: str,
        state: dict[str, Any] | None = None,
        max_steps: int = 8,
        checkpoint: CheckpointFn | None = None,
        step_recorder: Callable[[str, str, float], None] | None = None,
    ) -> GraphRun:
        """Run one node at a time; a self-edge is a valid bounded loop."""
        state = state if state is not None else {"nodes": {}}
        run = GraphRun(state=state)
        current = start
        for _ in range(max(1, max_steps)):
            if current == end:
                run.stop_reason = "completed"
                break
            if current not in self.nodes:
                run.stop_reason = "unknown_node"
                break
            duration = await self._execute(current, state)
            run.visited.append(current)
            run.steps.append({"node": current, "status": "completed", "duration_ms": round(duration, 2)})
            if step_recorder:
                step_recorder(current, "completed", duration)
            if checkpoint:
                checkpoint(state)
            if current == end:
                run.stop_reason = "completed"
                break
            active = self._active_edges(self, current, state)
            if not active:
                run.stop_reason = "deadlocked"
                break
            if len(active) > 1:
                run.stop_reason = "ambiguous_branch"
                break
            current = active[0].target
        else:
            run.stop_reason = "max_steps"
        return run

    async def run_dag(
        self,
        *,
        start: str,
        end: str,
        state: dict[str, Any] | None = None,
        max_steps: int = 32,
        checkpoint: CheckpointFn | None = None,
        step_recorder: Callable[[str, str, float], None] | None = None,
    ) -> GraphRun:
        """Execute a DAG with fan-out/fan-in and conditional edges."""
        state = state if state is not None else {"nodes": {}}
        run = GraphRun(state=state)
        dependencies: dict[str, set[str]] = {name: set() for name in self.nodes}
        for source, edges in self.edges.items():
            for edge in edges:
                dependencies.setdefault(edge.target, set()).add(source)

        completed: set[str] = set()
        activated: set[str] = set()
        for name in self.nodes:
            if not dependencies.get(name):
                activated.add(name)

        for _ in range(max(1, max_steps)):
            if end in completed:
                run.stop_reason = "completed"
                return run
            ready = [
                name for name in self.nodes
                if name not in completed
                and name in activated
                and dependencies.get(name, set()) <= completed
            ]
            if not ready:
                run.stop_reason = "completed" if end in completed else "deadlocked"
                return run
            if len(ready) > 1:
                durations = await asyncio.gather(*(self._execute(name, state) for name in ready))
            else:
                durations = [await self._execute(ready[0], state)]
            for name, duration in zip(ready, durations):
                completed.add(name)
                run.visited.append(name)
                run.steps.append({"node": name, "status": "completed", "duration_ms": round(duration, 2)})
                if step_recorder:
                    step_recorder(name, "completed", duration)
                if checkpoint:
                    checkpoint(state)
                for edge in self._active_edges(self, name, state):
                    activated.add(edge.target)
            if len(completed) >= len(self.nodes) and end not in self.nodes:
                run.stop_reason = "completed"
                return run
        run.stop_reason = "max_steps"
        return run
