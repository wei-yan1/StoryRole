"""Real HTTP smoke through FastAPI -> A2A -> CharacterAgent -> RoleRAG."""

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
from app.main import app  # noqa: E402

NOVEL_ID = "54a5fd53434a493abafc4005fb0c70a4"
CHARACTER_ID = 1
PERIOD_ID = int(os.getenv("STORYROLE_E2E_PERIOD_ID", "1"))
OWNER_ID = 2
RUN_ID = str(int(time.time()))


def main() -> int:
    token = create_access_token(user_id=OWNER_ID, username="这很好1")
    body = {
        "message": "你还记得罗辑经历过什么吗",
        "thread_name": f"rolerag-live-http-{RUN_ID}",
        "period_id": PERIOD_ID,
        "mode": os.getenv("STORYROLE_E2E_MODE", "quick"),
        "web_mode": "off",
        "debug": True,
    }
    with TestClient(app) as client:
        response = client.post(
            f"/api/v1/storyrole/novels/{NOVEL_ID}/characters/{CHARACTER_ID}/chat",
            json=body,
            headers={"Authorization": f"Bearer {token}"},
        )
    print("status", response.status_code)
    data = response.json()
    print(json.dumps({
        key: data.get(key)
        for key in [
            "character", "thread_id", "profile_version", "period_id", "mode",
            "engine", "evidence_count", "cutoff", "boundary_source",
            "boundary_confidence", "profile_injected", "graph_persisted",
            "persona_fidelity", "persona_score",
            "persona_rewritten", "appraisal", "interaction_state",
            "harness_enabled", "harness", "harness_stop_reason",
            "graph_write_mode", "graph_persist_error", "latency_ms",
            "degraded", "degradations", "answer",
            "planner_backend", "planner_intent", "ego_evidence_count", "route",
        ]
    }, ensure_ascii=False, indent=2))
    target = ROOT.parent / "docs" / "rolerag-api-http.json"
    target.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    print("wrote", target)
    return 0 if response.status_code == 200 else 1


if __name__ == "__main__":
    raise SystemExit(main())
