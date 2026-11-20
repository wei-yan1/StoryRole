"""Loop Engineering runtime for maintenance, evaluation and guarded automation.

This is intentionally not an autonomous code-writing loop. It provides the parts
that make a loop safe:

- explicit trigger and iteration budget;
- isolated state scope;
- disk-backed progress memory;
- progressive skill loading;
- a stop condition and a no-progress circuit breaker;
- a report that can be inspected before any human merges anything.

A loop body is an injected callable, so the runtime never decides on its own to
edit files, run shell commands or merge changes.
"""

from __future__ import annotations

import asyncio
import inspect
import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Awaitable, Callable, Protocol


@dataclass(frozen=True)
class LoopSpec:
    name: str
    max_iterations: int = 1
    interval_seconds: float = 0.0
    no_progress_limit: int = 3
    isolation: str = "thread/state scope"
    skill_paths: tuple[str, ...] = ()
    connector_names: tuple[str, ...] = ()
    metadata: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "max_iterations": self.max_iterations,
            "interval_seconds": self.interval_seconds,
            "no_progress_limit": self.no_progress_limit,
            "isolation": self.isolation,
            "skill_paths": list(self.skill_paths),
            "connector_names": list(self.connector_names),
            "metadata": dict(self.metadata),
        }


@dataclass
class LoopStep:
    iteration: int
    status: str = "ok"  # ok | degraded | error | stopped
    output: Any = None
    progress: bool = True
    stop: bool = False
    reason: str = ""
    duration_ms: float = 0.0

    def as_dict(self) -> dict[str, Any]:
        return {
            "iteration": self.iteration,
            "status": self.status,
            "output": self.output,
            "progress": bool(self.progress),
            "stop": bool(self.stop),
            "reason": self.reason,
            "duration_ms": round(self.duration_ms, 2),
        }


class LoopBody(Protocol):
    def __call__(self, iteration: int, memory: "LoopMemory") -> LoopStep | Awaitable[LoopStep]: ...


class LoopMemory:
    """Disk-backed loop state; deliberately not hidden in a context window."""

    def __init__(self, path: Path | str, *, namespace: str = "default") -> None:
        self.path = Path(path)
        self.namespace = namespace
        self.data: dict[str, Any] = {}
        self.load()

    def load(self) -> dict[str, Any]:
        if not self.path.exists():
            self.data = {"namespace": self.namespace, "iterations": [], "summary": {}}
            return self.data
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
            self.data = payload if isinstance(payload, dict) else {}
        except Exception:
            # Corrupt memory must not silently become a fresh run.
            self.data = {
                "namespace": self.namespace,
                "iterations": [],
                "summary": {},
                "load_error": "invalid_json",
            }
        self.data.setdefault("namespace", self.namespace)
        self.data.setdefault("iterations", [])
        self.data.setdefault("summary", {})
        return self.data

    def append(self, step: LoopStep) -> None:
        self.data.setdefault("iterations", []).append(step.as_dict())
        self.data["summary"] = {
            "runs": len(self.data.get("iterations") or []),
            "last_status": step.status,
            "last_reason": step.reason,
            "updated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        }
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(self.data, ensure_ascii=False, indent=2), encoding="utf-8")

    def last_iteration(self) -> int:
        return int(self.data.get("summary", {}).get("runs") or 0)


@dataclass
class LoopReport:
    spec: LoopSpec
    steps: list[LoopStep]
    stop_reason: str
    memory_path: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "spec": self.spec.as_dict(),
            "steps": [step.as_dict() for step in self.steps],
            "stop_reason": self.stop_reason,
            "passed": all(step.status in {"ok", "degraded"} for step in self.steps)
            and bool(self.steps),
            "memory_path": self.memory_path,
        }


class SkillCatalog:
    """Progressive disclosure for loop skills: index first, body on demand."""

    def __init__(self, paths: list[Path | str] | tuple[Path | str, ...]) -> None:
        self.paths = [Path(path) for path in paths]

    def index(self) -> list[dict[str, str]]:
        result = []
        for path in self.paths:
            if not path.exists():
                continue
            text = path.read_text(encoding="utf-8")
            title = next(
                (line.lstrip("# ").strip() for line in text.splitlines() if line.startswith("#")),
                path.stem,
            )
            result.append({"name": path.stem, "title": title, "path": str(path)})
        return result

    def load(self, name: str) -> str:
        for path in self.paths:
            if path.stem == name and path.exists():
                return path.read_text(encoding="utf-8")
        raise KeyError(f"unknown skill: {name}")


class LoopRuntime:
    """Runs a body with explicit iteration, memory and stop conditions."""

    def __init__(self, spec: LoopSpec, memory: LoopMemory) -> None:
        self.spec = spec
        self.memory = memory
        self.skills = SkillCatalog(spec.skill_paths)

    async def run(self, body: LoopBody) -> LoopReport:
        steps: list[LoopStep] = []
        no_progress = 0
        stop_reason = "max_iterations"
        start = self.memory.last_iteration()
        for iteration in range(start + 1, start + max(1, int(self.spec.max_iterations)) + 1):
            started = time.perf_counter()
            try:
                step = body(iteration, self.memory)
                if inspect.isawaitable(step):
                    step = await step
                if not isinstance(step, LoopStep):
                    step = LoopStep(iteration=iteration, output=step)
            except Exception as error:
                step = LoopStep(
                    iteration=iteration, status="error",
                    output={"error": f"{type(error).__name__}: {error}"},
                    progress=False,
                )
            step.duration_ms = (time.perf_counter() - started) * 1000
            steps.append(step)
            self.memory.append(step)
            if step.stop or step.status == "stopped":
                stop_reason = step.reason or "body_stop"
                break
            no_progress = 0 if step.progress else no_progress + 1
            if no_progress >= max(1, int(self.spec.no_progress_limit)):
                stop_reason = "no_progress"
                break
            if self.spec.interval_seconds > 0:
                await asyncio.sleep(float(self.spec.interval_seconds))
        return LoopReport(
            spec=self.spec, steps=steps, stop_reason=stop_reason,
            memory_path=str(self.memory.path),
        )
