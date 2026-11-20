"""Live smoke probe for the default AgentHarness quick path.

This script does not overwrite the sealed behavior report. It writes a separate
`docs/agent-harness-live-probe.json` so cached legacy evidence and the new
runtime evidence cannot be confused.
"""

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

os.environ.setdefault("POSTGRES_DATABASE", "three_body_agent_v2")

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

CASES = load_eval_suite(EVAL_SET, "quick_probe")


def _summary(data: dict) -> dict:
    harness = data.get("harness") or {}
    trace = data.get("harness_trace") or {}
    subject = harness.get("subject") or {}
    decision = harness.get("decision") or {}
    understanding = harness.get("understanding") or {}
    episodes = subject.get("episodes") or []
    return {
        "status": data.get("harness_stop_reason"),
        "runtime": data.get("agent_runtime"),
        "actions": (trace.get("summary") or {}).get("actions") or [],
        "event_count": (trace.get("summary") or {}).get("event_count"),
        "budget": data.get("harness_budget"),
        "degradations": data.get("degradations") or [],
        "harness_state_keys": sorted(harness.keys()) if isinstance(harness, dict) else [],
        "continuity": {
            "turn_count": subject.get("turn_count"),
            "episode_count": len(episodes),
            "prior_episode_ids": understanding.get("prior_episode_ids") or [],
            "change_from_previous": decision.get("change_from_previous"),
        },
    }


def main() -> int:
    token = create_access_token(user_id=OWNER_ID, username="这很好1")
    results = []
    with TestClient(app) as client:
        for case in CASES:
            started = time.perf_counter()
            data = {}
            response = None
            turns = [case["setup"], case["message"]] if case.get("setup") else [case["message"]]
            for turn in turns:
                response = client.post(
                    f"/api/v1/storyrole/novels/{NOVEL_ID}/characters/{CHARACTER_ID}/chat",
                    json={
                        "message": turn,
                        "thread_name": f"agent-harness-{case['name']}-{RUN_ID}",
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
                "status_code": response.status_code if response is not None else 0,
                "answer": data.get("answer"),
                "persona_score": data.get("persona_score"),
                "latency_ms": data.get("latency_ms") or round((time.perf_counter() - started) * 1000, 1),
                "harness": _summary(data),
                "trace": data.get("harness_trace"),
            })
    passed = all(
        item["status_code"] == 200
        and item["harness"]["runtime"] == "agent_harness"
        and item["harness"]["status"] in {"completed", "review_accepted"}
        and bool(item["answer"])
        and not any(str(value).startswith("agent_harness_stop:") for value in item["harness"]["degradations"])
        and (
            item["name"] != "decision_continuity"
            or (
                item["harness"]["continuity"]["turn_count"] >= 2
                and item["harness"]["continuity"]["episode_count"] >= 2
                and bool(item["harness"]["continuity"]["prior_episode_ids"])
                and item["harness"]["continuity"]["change_from_previous"] in {"continue", "adjust", "reverse"}
            )
        )
        for item in results
    )
    target = ROOT.parent / "docs" / "agent-harness-live-probe.json"
    target.write_text(json.dumps({
        "period_id": PERIOD_ID,
        "runtime": "agent_harness_v3_quick",
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "passed": passed,
        "cases": results,
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({
        "passed": passed,
        "cases": [
            {
                "name": item["name"],
                "status_code": item["status_code"],
                "status": item["harness"]["status"],
                "actions": item["harness"]["actions"],
                "answer": item["answer"],
                "persona_score": item["persona_score"],
                "degradations": item["harness"]["degradations"],
                "continuity": item["harness"]["continuity"],
            }
            for item in results
        ],
        "report": str(target),
    }, ensure_ascii=False, indent=2))
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
