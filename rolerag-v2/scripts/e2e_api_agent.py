"""Live upper/lower-chain smoke for the copied project.

Calls the real CharacterConversationAgent (not the demo), so it exercises:
DB character/profile/period -> import manifest -> chunks -> RoleRAG build ->
projection/retrieval/render/settle -> reply dict.
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
load_dotenv(ROOT.parent / ".env")

from app.agents.storyrole.character_agent import CharacterConversationAgent  # noqa: E402

PAYLOAD = {
    "owner_id": 2,
    "novel_id": "54a5fd53434a493abafc4005fb0c70a4",
    "character_id": 1,
    "period_id": 1,
    "message": "你还记得罗辑经历过什么吗",
    "mode": "quick",
    "user": {},
    "thread": {},
    "recent_messages": [],
}


async def main() -> int:
    result = await CharacterConversationAgent().reply(PAYLOAD)
    keys = [
        "answer", "mode", "engine", "route", "style_ok", "style_score",
        "attempts", "evidence_count", "cutoff", "latency_ms", "profile_version",
        "degraded", "degradations", "settled",
    ]
    print(json.dumps({key: result.get(key) for key in keys}, ensure_ascii=False, indent=2))
    target = ROOT.parent / "docs" / "rolerag-api-agent.json"
    target.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print("wrote", target)
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
