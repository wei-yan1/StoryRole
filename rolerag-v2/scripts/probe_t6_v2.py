"""One-turn T6 probe against the v2 database.

Run with:
    $env:POSTGRES_DATABASE='three_body_agent_v2'
    python scripts/probe_t6_v2.py
"""
from __future__ import annotations

import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("POSTGRES_DATABASE", "three_body_agent_v2")


def main() -> int:
    from fastapi.testclient import TestClient
    from scripts.e2e_ten_questions import create_access_token, request_case
    from app.main import app

    case = {
        "id": "t6probe",
        "group": "T6",
        "category": "晚年回望",
        "mode": "deep",
        "prompt": (
            "你已经一百多岁了，执剑人的位置也交出去很久了。"
            "现在回头看，你最想对当年那个站在开关前的自己说什么？"
            "不要总结，就按你现在记得的细节说。"
        ),
    }
    token = create_access_token(2, "这很好1")
    thread_name = "t6probe-" + time.strftime("%Y%m%d-%H%M%S")
    with TestClient(app) as client:
        record = request_case(client, token, case, thread_name)
    print("status", record.get("status"), "chars", record["shape"].get("answer_chars"))
    print("thread", record.get("thread_id"), "stop", (record.get("meta") or {}).get("harness_stop_reason"))
    print("evidence", (record.get("meta") or {}).get("evidence_count"), "persona", (record.get("meta") or {}).get("persona_score"))
    print("answer:\n" + str(record.get("answer") or ""))
    print("meta:\n" + str(record.get("meta")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
