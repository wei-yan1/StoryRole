"""Behavior regression loop for the role Harness.

This is deliberately not an autonomous code-change loop. It runs the hard
gate, records a disk state file and leaves the next step to a human. The v2
copy has no independent tracked diff baseline, so isolation is a fresh
thread/state namespace rather than a git worktree.

The loop itself goes through `app.harness.loop.LoopRuntime`, not a bare
`subprocess.run` for-loop: iteration count, interval, no-progress detection,
disk memory and progressive skill loading are explicit.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.harness.loop import LoopMemory, LoopRuntime, LoopSpec, LoopStep  # noqa: E402

DOCS = ROOT.parent / "docs"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def run_once() -> dict:
    loop_gate_path = DOCS / "harness-loop-gate.json"
    env = {**os.environ, "HARNESS_GATE_REPORT": str(loop_gate_path)}
    completed = subprocess.run(
        [sys.executable, "scripts/harness_gate.py"],
        cwd=ROOT, capture_output=True, text=True, timeout=240, env=env,
    )
    gate = {}
    if loop_gate_path.exists():
        try:
            gate = json.loads(loop_gate_path.read_text(encoding="utf-8"))
        except Exception:
            gate = {}
    return {
        "ran_at": _now(),
        "passed": completed.returncode == 0,
        "returncode": completed.returncode,
        "stdout": (completed.stdout or "").strip()[:500],
        "stderr": (completed.stderr or "").strip()[:500],
        "gate": gate,
        "isolation": "fresh thread/state namespace; v2 has no independent tracked diff baseline",
        "next_step": gate.get("next_step") or (
            "continue" if completed.returncode == 0 else "inspect the failing gate"
        ),
    }


def _signature(result: dict) -> str:
    gate = result.get("gate") or {}
    stable = {
        "passed": result.get("passed"),
        "checks": gate.get("checks") or {},
        "hard": gate.get("hard") or {},
        "behavior": gate.get("behavior") or {},
        "deep_subject": gate.get("deep_subject") or {},
        "agent_harness_probe": gate.get("agent_harness_probe") or {},
        "real_eval": gate.get("real_eval"),
    }
    payload = json.dumps(stable, ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha1(payload.encode("utf-8")).hexdigest()


def _body(iteration: int, memory: LoopMemory) -> LoopStep:
    result = run_once()
    previous = str(memory.data.get("last_gate_signature") or "")
    signature = _signature(result)
    # A repeated failing gate with the same evidence is no progress. A passing
    # gate is progress even when its signature repeats.
    progress = bool(result["passed"]) or signature != previous
    memory.data["last_gate_signature"] = signature
    memory.data["last_gate"] = result.get("gate") or {}
    return LoopStep(
        iteration=iteration,
        status="ok" if result["passed"] else "error",
        output=result,
        progress=progress,
        # A pass ends the loop; a failure may be retried until no_progress.
        stop=bool(result["passed"]),
        reason=str(result.get("next_step") or ""),
    )


async def _run(runs: int, interval: float) -> dict:
    memory = LoopMemory(DOCS / "harness-loop-memory.json", namespace="role-harness")
    spec = LoopSpec(
        name="role-harness-regression",
        max_iterations=max(1, int(runs)),
        interval_seconds=max(0.0, float(interval)),
        no_progress_limit=3,
        isolation="fresh thread/state namespace; no git worktree baseline",
        skill_paths=(str(ROOT.parent / "AGENTS.md"), str(DOCS / "agent-harness-v3-architecture.md")),
        metadata={"entry": "scripts/harness_gate.py"},
    )
    report = await LoopRuntime(spec, memory).run(_body)
    latest = report.steps[-1].output if report.steps else {}
    state = {
        "generated_at": _now(),
        "runs": len(report.steps),
        "passed": bool(latest.get("passed")) and report.stop_reason != "no_progress",
        "latest": latest,
        "history": [
            {"iteration": step.iteration, "status": step.status, "progress": step.progress,
             "reason": step.reason, "duration_ms": step.duration_ms}
            for step in report.steps
        ],
        "loop": report.as_dict(),
        "known_limits": [
            "This loop never edits role contracts or code.",
            "A passing gate is evidence, not a human acceptance of the character.",
            "Real HTTP behavior is skipped unless STORYROLE_EVAL_REAL=1.",
        ],
        "next_step": latest.get("next_step") or report.stop_reason,
    }
    DOCS.mkdir(parents=True, exist_ok=True)
    (DOCS / "harness-state.json").write_text(
        json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return state


def main() -> int:
    parser = argparse.ArgumentParser(description="Role Harness behavior regression loop")
    parser.add_argument("--runs", type=int, default=1, help="number of gate runs")
    parser.add_argument("--interval", type=float, default=5.0, help="seconds between runs")
    args = parser.parse_args()
    state = asyncio.run(_run(args.runs, args.interval))
    print(json.dumps({
        "passed": state["passed"],
        "runs": state["runs"],
        "stop_reason": state["loop"]["stop_reason"],
        "next_step": state["next_step"],
        "state": str(DOCS / "harness-state.json"),
    }, ensure_ascii=False))
    return 0 if state["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
