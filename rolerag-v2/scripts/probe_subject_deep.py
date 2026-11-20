"""One real deep turn proving RoleCognition joins the shared ActionDecision."""

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

EVAL_SET = ROOT.parent / "docs" / "agent-harness-eval.jsonl"


def main() -> int:
    case = load_eval_suite(EVAL_SET, "deep_probe")[0]
    token = create_access_token(user_id=2, username="这很好1")
    with TestClient(app) as client:
        response = client.post(
            "/api/v1/storyrole/novels/54a5fd53434a493abafc4005fb0c70a4/characters/1/chat",
            json={
                "message": case["message"],
                "thread_name": f"subject-deep-{int(time.time())}",
                "period_id": 7,
                "mode": "deep",
                "web_mode": "off",
                "debug": True,
            },
            headers={"Authorization": f"Bearer {token}"},
        )
    data = response.json()
    subject = data.get("subject") or {}
    decision = subject.get("decision") or {}
    state = subject.get("state") or {}
    actions = list((data.get("harness_trace") or {}).get("summary", {}).get("actions") or [])
    required = [
        "plan_turn", "understand_event", "recall_role", "deep_plan",
        "deep_retrieval", "context_curate", "deep_evidence", "deep_cognition",
        "decide", "assemble_context", "express", "review", "memory_decision",
        "learn", "stop",
    ]
    positions = [actions.index(name) if name in actions else -1 for name in required]
    phase_order = all(item >= 0 for item in positions) and positions == sorted(positions)
    degradations = list(data.get("degradations") or [])
    checks = {
        "http_200": response.status_code == 200,
        "action_order": phase_order,
        "role_cognition_real": decision.get("cognition_backend") == "aliyun_maas",
        "role_cognition_absorbed": "角色判断已吸收" in str(decision.get("decision_reason") or ""),
        "experience_recorded": int(state.get("turn_count") or 0) == 1 and len(state.get("episodes") or []) == 1,
        "review_accepted": data.get("harness_stop_reason") == "review_accepted",
        "persona_score": float(data.get("persona_score") or 0.0) >= 0.65,
        "no_critical_fallback": not any(
            item in {"role_cognition_fallback", "answer_model_fallback"}
            or str(item).startswith("harness_state_save_failed")
            for item in degradations
        ),
        "late_period_detail": any(
            token in str(data.get("answer") or "") for token in case.get("expected_tokens") or ("开关", "五十四", "执剑")
        ),
    }
    passed = all(checks.values())
    report = {
        "runtime": "role_subject_v3",
        "mode": "deep",
        "case_id": case.get("id"),
        "case_name": case.get("name"),
        "passed": passed,
        "checks": checks,
        "status": response.status_code,
        "answer": data.get("answer"),
        "persona_score": data.get("persona_score"),
        "decision": decision,
        "understanding": subject.get("understanding"),
        "state": state,
        "actions": actions,
        "degradations": degradations,
        "latency_ms": data.get("latency_ms"),
        "harness": data.get("harness"),
    }
    target = ROOT.parent / "docs" / "role-subject-deep-probe.json"
    target.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({key: value for key, value in report.items() if key != "harness"}, ensure_ascii=False, indent=2))
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
