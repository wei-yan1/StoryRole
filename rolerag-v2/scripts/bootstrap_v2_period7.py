"""Rebuild Luo Ji period 7 evidence and profile inside the v2 database.

The old database is intentionally left untouched. This script only operates on
the database supplied with ``--database`` (default: three_body_agent_v2).
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

from psycopg.types.json import Jsonb

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.agents.storyrole.period_agent import collect_character_records, evidence_for_period
from app.agents.storyrole.nuwa_profiler import NuwaProfilerAgent
from app.storage.postgres.client import postgres_connection
from app.storage.repositories.storyrole_repository import get_character_period

NOVEL_ID = "54a5fd53434a493abafc4005fb0c70a4"
CHARACTER_ID = 1
PERIOD_ID = 7
OWNER_ID = 2
CHUNKS_PATH = Path(r"D:\AgentCode\two\data\imports\54a5fd53434a493abafc4005fb0c70a4\chunks.jsonl")
PERIOD_NAME = "新时期晚年时期"
LATE_CHAPTER = "三体III·死神永生"
LATE_CHAPTER_END = "第五十三章 三体III·死神永生 第161节"
KEYWORDS = ["晚年", "老人", "威慑", "执剑人", "三体III"]


def _late_records(records: list[dict]) -> list[dict]:
    """Select Luo Ji's late-book records from the imported chunk stream.

    The import chunks have book-level chapter labels, not timeline-stage labels;
    *三体III·死神永生* is the late-life book for Luo Ji. All 38 records are kept,
    which is below the 40-record cap used by the old fallback and keeps the
    evidence window late.
    """
    return [item for item in records if str(item.get("chapter") or "") == LATE_CHAPTER]


async def _rebuild_profile(database: str, period: dict, evidence: list[dict]) -> dict:
    profile_payload = {
        "character_name": "罗辑",
        "novel_name": "three_body",
        "novel_id": NOVEL_ID,
        "owner_id": OWNER_ID,
        "character_id": CHARACTER_ID,
        "period_id": PERIOD_ID,
        "period_name": PERIOD_NAME,
        "period_stage": "T6",
        "evidence": evidence,
    }
    return await NuwaProfilerAgent().profile(profile_payload)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--database", default="three_body_agent_v2")
    parser.add_argument("--skip-profile", action="store_true")
    args = parser.parse_args()

    import os
    os.environ["POSTGRES_DATABASE"] = args.database

    records = collect_character_records(CHUNKS_PATH, "罗辑")
    late = _late_records(records)
    if not late:
        raise RuntimeError("no late-book Luo Ji records found")
    # Keep the explicit evidence window below the legacy 40-record cap.
    late = late[-40:]
    evidence = [
        {
            "chapter": str(item.get("chapter") or ""),
            "chunk_id": str(item.get("chunk_id") or ""),
            "claim": "三体III 晚年阶段原文证据",
            "text": str(item.get("text") or "")[:1200],
        }
        for item in late
    ]

    with postgres_connection() as connection, connection.cursor() as cursor:
        cursor.execute(
            """
            UPDATE storyrole_character_periods
            SET chapter_start=%s,
                chapter_end=%s,
                keywords=%s::jsonb,
                evidence_ids=%s::jsonb,
                rationale=%s,
                confidence=1.0,
                status='confirmed',
                updated_at=NOW()
            WHERE id=%s AND character_id=%s AND owner_id=%s
            """,
            (
                LATE_CHAPTER_END,
                LATE_CHAPTER_END,
                Jsonb(KEYWORDS),
                Jsonb([item["chunk_id"] for item in evidence]),
                "v2 晚期证据窗：三体III 死神永生中罗辑晚年出现段落；旧库未修改",
                PERIOD_ID,
                CHARACTER_ID,
                OWNER_ID,
            ),
        )
        if cursor.rowcount != 1:
            raise RuntimeError(f"period update affected {cursor.rowcount} rows")

    period = get_character_period(period_id=PERIOD_ID, owner_id=OWNER_ID)
    selected = evidence_for_period(records, period or {})
    print(json.dumps({
        "database": args.database,
        "period_id": PERIOD_ID,
        "period_name": (period or {}).get("name"),
        "evidence_ids": len((period or {}).get("evidence_ids") or []),
        "selected_evidence": len(selected),
        "selected_chapters": sorted({str(item.get("chapter")) for item in selected}),
        "chapter_start": (period or {}).get("chapter_start"),
        "chapter_end": (period or {}).get("chapter_end"),
    }, ensure_ascii=False, indent=2))

    if args.skip_profile:
        return 0

    result = asyncio.run(_rebuild_profile(args.database, period or {}, evidence))
    profile = result.get("profile") or {}
    print(json.dumps({
        "profile_id": result.get("profile_id"),
        "profile_version": result.get("profile_version"),
        "model": result.get("model"),
        "identity": profile.get("identity", "")[:300],
        "goals": (profile.get("goals") or [])[:5],
        "fears": (profile.get("fears") or [])[:5],
        "anti_patterns": (profile.get("anti_patterns") or [])[:5],
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
