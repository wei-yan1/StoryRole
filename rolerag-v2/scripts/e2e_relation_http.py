"""Real HTTP check for a multi-hop relationship question.

The first two checks use the existing single-turn smoke; this one specifically
asks RoleRAG about two other people's relationship at the current period.
"""

from __future__ import annotations

import json
import os
import sys
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
PERIOD_ID = int(os.getenv("STORYROLE_E2E_PERIOD_ID", "7"))
OWNER_ID = 2


def main() -> int:
    token = create_access_token(user_id=OWNER_ID, username="这很好1")
    body = {
        "message": "我怎么看叶文洁和史强的关系",
        "thread_name": "rolerag-relation-http",
        "period_id": PERIOD_ID,
        "mode": "quick",
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
            "answer", "engine", "route", "evidence_count", "ego_evidence_count",
            "planner_backend", "planner_intent", "cutoff", "profile_injected",
            "graph_persisted", "graph_write_mode", "latency_ms", "degraded",
        ]
    }, ensure_ascii=False, indent=2))
    target = ROOT.parent / "docs" / "rolerag-ego-relation-http.json"
    target.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    print("wrote", target)
    ok = (
        response.status_code == 200
        and data.get("route") == "probe"
        and int(data.get("ego_evidence_count", 0)) > 0
        and data.get("profile_injected") is True
    )
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())