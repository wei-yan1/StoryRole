"""Full ten-case regression against the v2 database.

This is deliberately separate from ``e2e_ten_questions.py`` because that report
describes the old database and profile 22. Here the database, profile version,
period stage and cutoff are fixed to the v2 T6 setup.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("POSTGRES_DATABASE", "three_body_agent_v2")

from fastapi.testclient import TestClient

from app.core.security import create_access_token
from app.main import app
from scripts.e2e_ten_questions import CASES, RUN_ID, answer_shape, now_iso, request_case

DOCS = ROOT.parent / "docs"
TITLE = "罗辑十项验收 · v2 T6 独立库"
EXPECTED_PROFILE_VERSION = 24


def _result_row(record: dict) -> dict:
    meta = record.get("meta") or {}
    return {
        "id": record.get("id"),
        "group": record.get("group"),
        "mode": record.get("mode"),
        "status": record.get("status"),
        "answer_chars": (record.get("shape") or {}).get("answer_chars"),
        "evidence_count": meta.get("evidence_count"),
        "persona_score": meta.get("persona_score"),
        "stop_reason": meta.get("harness_stop_reason"),
        "period_name": meta.get("period_name"),
        "profile_version": meta.get("profile_version"),
        "cutoff": meta.get("cutoff"),
        "boundary_source": meta.get("boundary_source"),
        "degradations": meta.get("degradations") or [],
        "thread_id": record.get("thread_id"),
        "answer": record.get("answer"),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cases", help="只跑指定 id，逗号分隔")
    args = parser.parse_args()
    selected = CASES
    if args.cases:
        wanted = {item.strip() for item in args.cases.split(",") if item.strip()}
        selected = [case for case in CASES if case["id"] in wanted]

    token = create_access_token(2, "这很好1")
    started_at = now_iso()
    records: list[dict] = []
    with TestClient(app) as client:
        for case in selected:
            print(f"== {case['id']} {case['group']}/{case['category']} ==", flush=True)
            record = request_case(client, token, case, f"v2-{RUN_ID}")
            records.append(record)
            meta = record.get("meta") or {}
            print(
                f"   status={record.get('status')} chars={(record.get('shape') or {}).get('answer_chars')} "
                f"evidence={meta.get('evidence_count')} persona={meta.get('persona_score')} "
                f"profile={meta.get('profile_version')} cutoff={meta.get('cutoff')} "
                f"stop={meta.get('harness_stop_reason')} wall={record.get('wall_ms', 0)/1000:.1f}s",
                flush=True,
            )

    finished_at = now_iso()
    rows = [_result_row(record) for record in records]
    success = sum(1 for row in rows if row["status"] == 200)
    meta = {
        "run_id": RUN_ID,
        "started_at": started_at,
        "finished_at": finished_at,
        "database": os.getenv("POSTGRES_DATABASE"),
        "period_id": 7,
        "period_name": "新时期晚年时期",
        "period_stage": "T6",
        "expected_profile_version": EXPECTED_PROFILE_VERSION,
        "suite": "六问 + 三行为 + 一 smoke（v2 库）",
        "case_ids": [case["id"] for case in selected],
        "success": success,
        "total": len(rows),
        "all_status_200": success == len(rows),
    }
    DOCS.mkdir(parents=True, exist_ok=True)
    json_path = DOCS / "rolerag-ten-questions-v2.json"
    md_path = DOCS / "rolerag-ten-questions-v2.md"
    json_path.write_text(json.dumps({"meta": meta, "results": rows}, ensure_ascii=False, indent=2), encoding="utf-8")

    lines = [
        f"# {TITLE}",
        "",
        f"- 数据库：`{meta['database']}`",
        f"- period：`7 / {meta['period_name']} / {meta['period_stage']}`",
        f"- 期望 profile：`{EXPECTED_PROFILE_VERSION}`",
        f"- 结果：`{success}/{len(rows)}` HTTP 200",
        "",
        "| id | 组 | 状态 | 字数 | 证据 | persona | profile | cutoff | stop |",
        "|---|---|---:|---:|---:|---:|---:|---:|---|",
    ]
    for row in rows:
        lines.append(
            f"| {row['id']} | {row['group']} | {row['status']} | {row['answer_chars']} | "
            f"{row['evidence_count']} | {row['persona_score']} | {row['profile_version']} | "
            f"{row['cutoff']} | {row['stop_reason']} |"
        )
    lines += ["", "## 逐项回答", ""]
    for row in rows:
        lines += [
            f"### {row['id']} · {row['group']}",
            "",
            f"- 线程：`{row['thread_id']}`；profile `{row['profile_version']}`；"
            f"cutoff `{row['cutoff']}` / `{row['boundary_source']}`；"
            f"降级 `{row['degradations']}`",
            "",
            str(row["answer"] or ""),
            "",
        ]
    lines += [
        "## 判定",
        "",
        "- 这份报告只回答“v2 库、T6 profile 24 下，十项链路是否跑通”。",
        "- 它不回答“每道题是否适合 T6”；q1/q3/q4 等仍可能是早期题，时期适配要另做矩阵。",
        "- 若 `profile_version` 不是 24，或 `cutoff` 不是 53，说明 v2 数据库被旧 profile/旧 cutoff 污染。",
    ]
    md_path.write_text("\n".join(lines), encoding="utf-8")
    print(json.dumps(meta, ensure_ascii=False, indent=2))
    print("wrote", json_path)
    print("wrote", md_path)
    return 0 if meta["all_status_200"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
