"""Real SSE smoke through FastAPI /chat/stream -> A2A -> RoleRAG."""

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
        "message": "你还记得罗辑经历过什么吗",
        "thread_name": "rolerag-live-stream",
        "period_id": PERIOD_ID,
        "mode": "quick",
        "web_mode": "off",
        "debug": True,
    }
    complete = None
    event_types: list[str] = []
    current_event = ""
    with TestClient(app) as client:
        with client.stream(
            "POST",
            f"/api/v1/storyrole/novels/{NOVEL_ID}/characters/{CHARACTER_ID}/chat/stream",
            json=body,
            headers={"Authorization": f"Bearer {token}"},
        ) as response:
            print("status", response.status_code)
            for line in response.iter_lines():
                if line.startswith("event:"):
                    current_event = line[6:].strip()
                    event_types.append(current_event)
                    continue
                if not line.startswith("data:"):
                    continue
                data = json.loads(line[5:].strip())
                if current_event == "complete":
                    complete = data
                if current_event == "error":
                    print("error", data)
                    return 1
    if not complete:
        print("no complete event; events", event_types)
        return 1
    print("events", event_types)
    print(json.dumps({
        key: complete.get(key)
        for key in [
            "engine", "evidence_count", "cutoff", "boundary_source",
            "boundary_confidence", "profile_injected", "graph_persisted",
            "graph_write_mode", "latency_ms", "degraded", "answer",
            "planner_backend", "planner_intent", "ego_evidence_count", "route",
        ]
    }, ensure_ascii=False, indent=2))
    target = ROOT.parent / "docs" / "rolerag-api-stream.json"
    target.write_text(json.dumps(complete, ensure_ascii=False, indent=2), encoding="utf-8")
    print("wrote", target)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
