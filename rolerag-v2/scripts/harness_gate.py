"""Hard gate for the role Harness.

This is the "gate" of the loop: pytest is the mandatory gate, the existing
behavior evidence is the independent real-world check. It never edits code or
turns a failure into a success.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT.parent / "docs"
EVAL_SET = DOCS / "agent-harness-eval.jsonl"
GATE_REPORT = Path(os.getenv("HARNESS_GATE_REPORT") or (DOCS / "harness-gate.json"))
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _read_eval_set() -> dict:
    if not EVAL_SET.exists():
        return {"available": False, "passed": False, "path": str(EVAL_SET), "error": "missing eval set"}
    try:
        from app.harness.eval import validate_eval_set

        return validate_eval_set(EVAL_SET)
    except Exception as error:
        return {"available": False, "passed": False, "path": str(EVAL_SET), "error": str(error)}


def _run_pytest() -> dict:
    completed = subprocess.run(
        [sys.executable, "-m", "pytest", "tests/rolerag", "-q"],
        cwd=ROOT, capture_output=True, text=True, timeout=180,
    )
    tail = (completed.stdout or completed.stderr or "").strip().splitlines()
    return {
        "passed": completed.returncode == 0,
        "returncode": completed.returncode,
        "summary": tail[-1] if tail else "",
        "output_tail": tail[-8:],
    }


def _read_behavior() -> dict:
    path = DOCS / "rolerag-persona-behavior.json"
    if not path.exists():
        return {"available": False, "passed": None, "path": str(path)}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception as error:
        return {"available": False, "passed": None, "error": str(error), "path": str(path)}
    cases = data.get("cases") or []

    def case_passed(case: dict) -> bool:
        return bool((case.get("evaluation") or {}).get("passed"))

    accepted = sum(1 for case in cases if case_passed(case))
    scores = [
        float(case.get("persona_score") or 0.0)
        for case in cases
        if case.get("persona_score") is not None
    ]
    latencies = [
        float(case.get("latency_ms") or 0.0)
        for case in cases
        if case.get("latency_ms") is not None
    ]
    return {
        "available": True,
        "runtime": data.get("runtime"),
        "passed": bool(cases) and accepted == len(cases),
        "reviewed": len(cases),
        "accepted": accepted,
        "acceptance_rate": round(accepted / len(cases), 4) if cases else 0.0,
        "avg_persona_score": round(sum(scores) / len(scores), 4) if scores else 0.0,
        "avg_latency_ms": round(sum(latencies) / len(latencies), 1) if latencies else 0.0,
        "path": str(path),
        "failures": [case.get("name") for case in cases if not case_passed(case)],
        "harness_checks": [
            {
                "name": case.get("name"),
                "harness_stop_reason": case.get("harness_stop_reason"),
                "structure_passed": ((case.get("evaluation") or {}).get("structure") or {}).get("passed"),
                "continuity": ((case.get("evaluation") or {}).get("structure") or {}).get("continuity"),
            }
            for case in cases
        ],
    }


def _read_profile_alignment() -> dict:
    if os.getenv("STORYROLE_ALIGNMENT_CHECK", "0") != "1":
        return {"available": False, "reason": "STORYROLE_ALIGNMENT_CHECK!=1"}
    database = os.getenv("POSTGRES_DATABASE", "three_body_agent_v2")
    completed = subprocess.run(
        [sys.executable, "scripts/check_profile_alignment.py", "--database", database],
        cwd=ROOT, capture_output=True, text=True, timeout=60,
    )
    try:
        report = json.loads(completed.stdout)
    except Exception:
        report = {"ok": False, "raw": (completed.stdout or completed.stderr or "")[-1200:]}
    report.setdefault("available", True)
    report["passed"] = completed.returncode == 0 and bool(report.get("ok"))
    return report


def _read_deep_probe() -> dict:
    path = DOCS / "role-subject-deep-probe.json"
    if not path.exists():
        return {"available": False, "passed": None, "path": str(path)}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception as error:
        return {"available": False, "passed": None, "error": str(error), "path": str(path)}
    return {
        "available": True,
        "passed": bool(data.get("passed")),
        "case_id": data.get("case_id"),
        "case_name": data.get("case_name"),
        "checks": data.get("checks") or {},
        "cognition_backend": (data.get("decision") or {}).get("cognition_backend"),
        "latency_ms": data.get("latency_ms"),
        "path": str(path),
    }


def _read_agent_harness_probe() -> dict:
    path = DOCS / "agent-harness-live-probe.json"
    if not path.exists():
        return {"available": False, "passed": None, "path": str(path)}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception as error:
        return {"available": False, "passed": None, "error": str(error), "path": str(path)}
    cases = data.get("cases") or []
    return {
        "available": True,
        "passed": bool(data.get("passed")),
        "runtime": data.get("runtime"),
        "generated_at": data.get("generated_at"),
        "case_count": len(cases),
        "cases": [
            {
                "name": item.get("name"),
                "status": (item.get("harness") or {}).get("status"),
                "runtime": (item.get("harness") or {}).get("runtime"),
                "actions": (item.get("harness") or {}).get("actions") or [],
                "degradations": (item.get("harness") or {}).get("degradations") or [],
                "continuity": (item.get("harness") or {}).get("continuity"),
            }
            for item in cases
        ],
        "path": str(path),
    }


def main() -> int:
    pytest_result = _run_pytest()
    eval_set = _read_eval_set()
    behavior = _read_behavior()
    alignment = _read_profile_alignment()
    deep_probe = _read_deep_probe()
    agent_harness_probe = _read_agent_harness_probe()
    real_eval = "skipped"
    if os.getenv("STORYROLE_EVAL_REAL", "0") == "1":
        completed = subprocess.run(
            [sys.executable, "scripts/e2e_persona_behavior.py"],
            cwd=ROOT, capture_output=True, text=True, timeout=240,
        )
        deep_completed = subprocess.run(
            [sys.executable, "scripts/probe_subject_deep.py"],
            cwd=ROOT, capture_output=True, text=True, timeout=300,
        )
        harness_completed = subprocess.run(
            [sys.executable, "scripts/probe_agent_harness.py"],
            cwd=ROOT, capture_output=True, text=True, timeout=300,
        )
        real_eval = (
            "passed" if all(
                item.returncode == 0
                for item in (completed, deep_completed, harness_completed)
            ) else "failed"
        )
        behavior = _read_behavior()
        deep_probe = _read_deep_probe()
        agent_harness_probe = _read_agent_harness_probe()
    passed = (
        bool(pytest_result["passed"])
        and bool(eval_set.get("passed"))
        and bool(behavior.get("passed"))
        and bool(deep_probe.get("passed"))
        and bool(agent_harness_probe.get("passed"))
        and (alignment.get("passed") is not False)
    )
    payload = {
        "generated_at": _now(),
        "passed": passed,
        "pytest": pytest_result,
        "eval_set": eval_set,
        "behavior": behavior,
        "deep_subject_probe": deep_probe,
        "profile_alignment": alignment,
        "agent_harness_probe": agent_harness_probe,
        "real_eval": real_eval,
        "cost_note": "behavior corpus is small; acceptance_rate below 0.5 would be a loss",
        "next_step": (
            "continue" if passed else
            "fix the failing gate before touching role behavior or harness defaults"
        ),
    }
    DOCS.mkdir(parents=True, exist_ok=True)
    GATE_REPORT.parent.mkdir(parents=True, exist_ok=True)
    GATE_REPORT.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps({
        "passed": passed,
        "pytest": pytest_result["summary"],
        "eval_set_passed": eval_set.get("passed"),
        "eval_set_counts": eval_set.get("counts"),
        "behavior_passed": behavior.get("passed"),
        "deep_subject_passed": deep_probe.get("passed"),
        "agent_harness_probe_passed": agent_harness_probe.get("passed"),
        "acceptance_rate": behavior.get("acceptance_rate"),
        "real_eval": real_eval,
        "report": str(GATE_REPORT),
    }, ensure_ascii=False))
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
