"""Real HTTP probes for likeness, need-driven recall and subject continuity."""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
load_dotenv(ROOT.parent / ".env")

from fastapi.testclient import TestClient  # noqa: E402

from app.core.security import create_access_token  # noqa: E402
from app.harness.eval import load_eval_suite  # noqa: E402
from app.main import app  # noqa: E402

NOVEL_ID = "54a5fd53434a493abafc4005fb0c70a4"
CHARACTER_ID = 1
PERIOD_ID = int(os.getenv("STORYROLE_E2E_PERIOD_ID", "7"))
OWNER_ID = 2
RUN_ID = str(int(time.time()))
EVAL_SET = ROOT.parent / "docs" / "agent-harness-eval.jsonl"

CASES = load_eval_suite(EVAL_SET, "behavior")


def _structure(data: dict, case: dict) -> dict:
    subject = data.get("subject") or {}
    state = subject.get("state") or {}
    decision = subject.get("decision") or {}
    understanding = subject.get("understanding") or {}
    recall = subject.get("recall") or {}
    phases = list((data.get("harness_trace") or {}).get("summary", {}).get("actions") or [])
    required = ["plan_turn", "understand_event", "decide", "assemble_context", "express", "review", "learn"]
    positions = [phases.index(name) if name in phases else -1 for name in required]
    phase_order = all(position >= 0 for position in positions) and positions == sorted(positions)
    no_legacy_state = all(key not in state for key in ("commitments", "claimed_commitments", "open_loops"))
    action_ok = not case.get("expected_action") or decision.get("action") == case["expected_action"]
    recall_ok = not case.get("expect_no_role_recall") or recall.get("role_recall_executed") is False
    current_reality_ok = not case.get("require_current_reality") or (
        bool(understanding.get("current_reality"))
        and any("当前现实" in str(item) for item in (decision.get("boundaries") or []))
    )
    state_save_ok = not any(
        str(item).startswith("harness_state_save_failed")
        for item in (data.get("degradations") or [])
    )
    continuity_ok = True
    continuity_detail = {"required": False}
    if case.get("require_continuity"):
        continuity_ok = (
            int(state.get("turn_count") or 0) >= 2
            and len(state.get("episodes") or []) >= 2
            and bool(understanding.get("prior_episode_ids"))
            and decision.get("change_from_previous") in {"continue", "adjust", "reverse"}
            and (
                not case.get("expected_continuity")
                or decision.get("change_from_previous") == case["expected_continuity"]
            )
        )
        continuity_detail = {
            "required": True,
            "turn_count": state.get("turn_count"),
            "episode_count": len(state.get("episodes") or []),
            "prior_episode_ids": understanding.get("prior_episode_ids"),
            "change_from_previous": decision.get("change_from_previous"),
            "expected_continuity": case.get("expected_continuity"),
        }
    passed = all((phase_order, no_legacy_state, action_ok, recall_ok, current_reality_ok, state_save_ok, continuity_ok))
    return {
        "passed": passed,
        "phase_order": phase_order,
        "phases": phases,
        "no_legacy_state": no_legacy_state,
        "action_ok": action_ok,
        "recall_ok": recall_ok,
        "current_reality_ok": current_reality_ok,
        "state_save_ok": state_save_ok,
        "continuity_ok": continuity_ok,
        "continuity": continuity_detail,
    }


def _score(data: dict, case: dict) -> dict:
    answer = str(data.get("answer") or "")
    hits = [item for item in case["checks"] if item in answer]
    generic = [item for item in ("作为一个AI", "首先", "综上所述", "希望这对你有帮助") if item in answer]
    forbidden = [item for item in case.get("forbidden", []) if item in answer]
    score = data.get("persona_score")
    likeness_ok = score is not None and float(score) >= 0.65
    structure = _structure(data, case)
    return {
        "hits": hits,
        "generic": generic,
        "forbidden": forbidden,
        "likeness_ok": likeness_ok,
        "structure": structure,
        "passed": bool(hits) and not forbidden and likeness_ok and structure["passed"],
    }


def main() -> int:
    token = create_access_token(user_id=OWNER_ID, username="这很好1")
    results = []
    with TestClient(app) as client:
        for case in CASES:
            turns = [case["setup"], case["message"]] if case.get("setup") else [case["message"]]
            data = {}
            response = None
            for turn in turns:
                response = client.post(
                    f"/api/v1/storyrole/novels/{NOVEL_ID}/characters/{CHARACTER_ID}/chat",
                    json={
                        "message": turn,
                        "thread_name": f"subject-behavior-{case['name']}-{RUN_ID}",
                        "period_id": PERIOD_ID,
                        "mode": "quick",
                        "web_mode": "off",
                        "debug": True,
                    },
                    headers={"Authorization": f"Bearer {token}"},
                )
                data = response.json()
            results.append({
                "name": case["name"],
                "message": case["message"],
                "setup": case.get("setup"),
                "status": response.status_code if response is not None else 0,
                "answer": data.get("answer"),
                "persona_fidelity": data.get("persona_fidelity"),
                "persona_score": data.get("persona_score"),
                "persona_rewritten": data.get("persona_rewritten"),
                "appraisal": data.get("appraisal"),
                "subject": data.get("subject"),
                "interaction_state": data.get("interaction_state"),
                "harness_stop_reason": data.get("harness_stop_reason"),
                "harness": data.get("harness"),
                "latency_ms": data.get("latency_ms"),
                "degraded": data.get("degraded"),
                "degradations": data.get("degradations"),
                "evaluation": _score(data, case),
            })
    passed = all(
        case["status"] == 200 and (case.get("evaluation") or {}).get("passed")
        for case in results
    )
    target = ROOT.parent / "docs" / "rolerag-persona-behavior.json"
    target.write_text(json.dumps({
        "period_id": PERIOD_ID,
        "runtime": "role_subject_v3",
        "passed": passed,
        "cases": results,
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({
        "period_id": PERIOD_ID,
        "passed": passed,
        "cases": [{
            "name": case["name"],
            "status": case["status"],
            "answer": case["answer"],
            "persona_score": case["persona_score"],
            "evaluation_passed": case["evaluation"]["passed"],
            "structure": case["evaluation"]["structure"],
            "latency_ms": case["latency_ms"],
            "degradations": case["degradations"],
        } for case in results],
        "report": str(target),
    }, ensure_ascii=False, indent=2))
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
