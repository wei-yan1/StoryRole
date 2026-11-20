#!/usr/bin/env python
"""罗辑新旧链路六问对比测试 + 历史记录。

用法（在项目根目录执行）：
    .venv\\Scripts\\python.exe scripts\\compare_luoji.py
    .venv\\Scripts\\python.exe scripts\\compare_luoji.py --categories q3,爱情
    .venv\\Scripts\\python.exe scripts\\compare_luoji.py --project both --label regression
    .venv\\Scripts\\python.exe scripts\\compare_luoji.py --dry-run

每次运行会写入：
    data/evals/luoji_compare/runs/<run_id>/results.json
    data/evals/luoji_compare/runs/<run_id>/summary.md
    data/evals/luoji_compare/history.jsonl
    data/evals/luoji_compare/history.md
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

import httpx
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env")
sys.path.insert(0, str(ROOT))

from app.core.security import create_access_token  # noqa: E402

NOVEL_ID = "54a5fd53434a493abafc4005fb0c70a4"
CHARACTER_ID = 1
PERIOD_ID = 7
DEFAULT_OLD_URL = "http://127.0.0.1:1314"
DEFAULT_NEW_URL = "http://127.0.0.1:1315"
DATA_DIR = ROOT / "data" / "evals" / "luoji_compare"
RUNS_DIR = DATA_DIR / "runs"
HISTORY_JSONL = DATA_DIR / "history.jsonl"
HISTORY_MD = DATA_DIR / "history.md"

QUESTIONS: list[dict[str, str]] = [
    {
        "id": "q1",
        "category": "深度",
        "mode": "deep",
        "prompt": "罗辑，如果宇宙社会学的两条公理真的成立，你觉得人类文明最该警惕的，是自己内部的什么东西？不要只给结论，说说你为什么这么想。",
    },
    {
        "id": "q2",
        "category": "政治",
        "mode": "deep",
        "prompt": "在你经历的面壁计划、PDC和联合国权力博弈里，你更相信制度、权力，还是具体的人？结合你做过的事回答，不要泛泛而谈。",
    },
    {
        "id": "q3",
        "category": "聊天",
        "mode": "quick",
        "prompt": "不谈宇宙，也不谈面壁计划。你最近过得怎么样？有没有什么小事让你觉得日子还有点意思？",
    },
    {
        "id": "q4",
        "category": "爱情",
        "mode": "deep",
        "prompt": "庄颜对你意味着什么？如果必须在你对她的感情和守住人类文明之间做选择，你会怎么选？",
    },
    {
        "id": "q5",
        "category": "分享故事",
        "mode": "auto",
        "prompt": "给我讲一段你亲身经历、至今还会在夜里想起的往事。不要总结，就按你记得的细节讲。",
    },
    {
        "id": "q6",
        "category": "危机决断",
        "mode": "deep",
        "prompt": "假设你现在就是执剑人，三体世界第一次试探你，你会按下开关吗？按下之后，你准备怎么面对自己？",
    },
]

META_KEYS = (
    "engine",
    "mode",
    "period_id",
    "profile_version",
    "evidence_count",
    "latency_ms",
    "degraded",
    "degradations",
    "profile_injected",
    "graph_persisted",
    "graph_write_mode",
    "boundary_source",
    "boundary_confidence",
    "persona_score",
    "persona_rewritten",
    "trace_id",
)


def slugify(value: str) -> str:
    value = re.sub(r"[^0-9A-Za-z\u4e00-\u9fff_-]+", "_", value.strip())
    return value.strip("_")[:32] or "run"


def now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def select_questions(spec: str | None) -> list[dict[str, str]]:
    if not spec:
        return list(QUESTIONS)
    tokens = [token.strip().lower() for token in spec.split(",") if token.strip()]
    selected = [
        question
        for question in QUESTIONS
        if any(
            token == question["id"].lower()
            or token == question["category"].lower()
            or token in question["category"].lower()
            for token in tokens
        )
    ]
    if not selected:
        available = "、".join(f"{q['id']}={q['category']}" for q in QUESTIONS)
        raise ValueError(f"没有匹配到问题：{spec}；可选：{available}")
    return selected


def preflight(client: httpx.Client, base_url: str) -> str | None:
    try:
        response = client.get(base_url.rstrip("/") + "/", timeout=3.0)
    except Exception as error:
        return f"{type(error).__name__}: {error}"
    if response.status_code >= 500:
        return f"HTTP {response.status_code}: {response.text[:200]}"
    return None


def extract_meta(body: dict[str, Any]) -> dict[str, Any]:
    return {key: body.get(key) for key in META_KEYS}


def fetch_trace(
    client: httpx.Client,
    base_url: str,
    token: str,
    trace_id: str | None,
) -> dict[str, Any]:
    if not trace_id:
        return {"status": "skipped", "reason": "no trace_id", "model_invocations": []}
    try:
        response = client.get(
            f"{base_url.rstrip('/')}/api/v1/models/traces/{trace_id}",
            headers={"Authorization": f"Bearer {token}"},
            timeout=30.0,
        )
    except Exception as error:
        return {"status": "error", "error": f"{type(error).__name__}: {error}", "model_invocations": []}
    if response.status_code != 200:
        return {
            "status": response.status_code,
            "error": response.text[:500],
            "model_invocations": [],
        }
    body = response.json()
    calls = body.get("model_invocations") or []
    return {
        "status": "ok",
        "model_invocations": [
            {
                "provider": call.get("provider"),
                "model": call.get("model"),
                "operation": call.get("operation"),
                "input_tokens": call.get("input_tokens"),
                "output_tokens": call.get("output_tokens"),
                "status": call.get("status"),
            }
            for call in calls
        ],
    }


def call_once(
    client: httpx.Client,
    base_url: str,
    token: str,
    project: str,
    question: dict[str, str],
    run_id: str,
    period_id: int,
    timeout: float,
    retries: int,
) -> dict[str, Any]:
    thread_name = f"cmp-{project}-{question['id']}-{run_id}"
    payload = {
        "message": question["prompt"],
        "period_id": period_id,
        "mode": question["mode"],
        "web_mode": "off",
        "thread_name": thread_name,
        "debug": True,
    }
    url = (
        f"{base_url.rstrip('/')}/api/v1/storyrole/novels/{NOVEL_ID}"
        f"/characters/{CHARACTER_ID}/chat"
    )
    attempts = retries + 1
    started = time.perf_counter()
    last_error = ""

    for attempt in range(1, attempts + 1):
        try:
            response = client.post(
                url,
                headers={"Authorization": f"Bearer {token}"},
                json=payload,
                timeout=timeout,
            )
            wall_ms = round((time.perf_counter() - started) * 1000, 1)
            if response.status_code == 200:
                body = response.json()
                answer = body.get("answer") or ""
                meta = extract_meta(body)
                return {
                    "project": project,
                    "base_url": base_url,
                    "question_id": question["id"],
                    "category": question["category"],
                    "prompt": question["prompt"],
                    "mode_requested": question["mode"],
                    "thread_name": thread_name,
                    "status": 200,
                    "http_status": response.status_code,
                    "attempts": attempt,
                    "wall_ms": wall_ms,
                    "answer": answer,
                    "answer_chars": len(answer),
                    "meta": meta,
                    "trace": fetch_trace(client, base_url, token, meta.get("trace_id")),
                }
            last_error = f"HTTP {response.status_code}: {response.text[:800]}"
            if response.status_code not in {429, 500, 502, 503, 504} or attempt >= attempts:
                break
        except Exception as error:
            last_error = f"{type(error).__name__}: {error}"
            if attempt >= attempts:
                break
            # 超时不重试，避免一次慢请求变成两次慢请求。
            if "timeout" in type(error).__name__.lower() or "timeout" in str(error).lower():
                break
        if attempt < attempts:
            print(f"    retry {attempt}/{retries}：{last_error[:160]}", flush=True)
            time.sleep(2)

    return {
        "project": project,
        "base_url": base_url,
        "question_id": question["id"],
        "category": question["category"],
        "prompt": question["prompt"],
        "mode_requested": question["mode"],
        "thread_name": thread_name,
        "status": "error",
        "http_status": None,
        "attempts": attempt,
        "wall_ms": round((time.perf_counter() - started) * 1000, 1),
        "answer": "",
        "answer_chars": 0,
        "error": last_error,
        "meta": {},
        "trace": {"status": "skipped", "model_invocations": []},
    }


def result_index(results: list[dict[str, Any]]) -> dict[tuple[str, str], dict[str, Any]]:
    return {(item["project"], item["question_id"]): item for item in results}


def project_stats(results: list[dict[str, Any]], project: str) -> dict[str, Any]:
    items = [item for item in results if item["project"] == project]
    ok = [item for item in items if item["status"] == 200]
    return {
        "total": len(items),
        "success": len(ok),
        "failed": len(items) - len(ok),
        "answer_chars": sum(item["answer_chars"] for item in ok),
        "avg_wall_ms": round(sum(item["wall_ms"] for item in ok) / len(ok), 1) if ok else None,
        "total_wall_ms": round(sum(item["wall_ms"] for item in ok), 1),
        "degraded": sum(1 for item in ok if (item.get("meta") or {}).get("degraded")),
    }


def build_stats(results: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "old": project_stats(results, "old"),
        "new": project_stats(results, "new"),
        "success": sum(1 for item in results if item["status"] == 200),
        "total": len(results),
        "degraded": sum(
            1
            for item in results
            if item["status"] == 200 and (item.get("meta") or {}).get("degraded")
        ),
    }


def short(text: str, limit: int = 220) -> str:
    text = (text or "").replace("\r", "").strip()
    if len(text) <= limit:
        return text
    return text[:limit].rstrip() + "…"


def quote(text: str) -> str:
    return "\n".join("> " + line if line else ">" for line in text.splitlines()) if text else "> （空）"


def write_summary(
    run_dir: Path,
    meta: dict[str, Any],
    results: list[dict[str, Any]],
    stats: dict[str, Any],
) -> None:
    by_key = result_index(results)
    lines = [
        f"# 罗辑新旧链路测试记录 · {meta['run_id']}",
        "",
        f"- 开始：{meta['started_at']}",
        f"- 标签：`{meta['label']}`",
        f"- 旧项目：`{meta['old_url']}`",
        f"- 新项目：`{meta['new_url']}`",
        f"- 时期：period {meta['period_id']}",
        f"- 对话模型：`{meta.get('chat_model') or 'unknown'}`",
        f"- 问题：{'、'.join(item['id'] + ' ' + item['category'] for item in meta['questions'])}",
        "",
        "## 指标",
        "",
        "| 题 | 类别 | 旧字数 | 旧证据 | 旧耗时 | 旧状态 | 新字数 | 新证据 | 新耗时 | 新人格分 | 新状态 |",
        "|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    for question in meta["questions"]:
        old = by_key.get(("old", question["id"])) or {}
        new = by_key.get(("new", question["id"])) or {}
        old_meta = old.get("meta") or {}
        new_meta = new.get("meta") or {}
        old_status = "ok" if old.get("status") == 200 else "error"
        new_status = "ok" if new.get("status") == 200 else "error"
        if old_meta.get("degraded"):
            old_status += "/degraded"
        if new_meta.get("degraded"):
            new_status += "/degraded"
        lines.append(
            "| {id} | {category} | {old_chars} | {old_evidence} | {old_wall}s | {old_status} | "
            "{new_chars} | {new_evidence} | {new_wall}s | {new_persona} | {new_status} |".format(
                id=question["id"].upper(),
                category=question["category"],
                old_chars=old.get("answer_chars", "—"),
                old_evidence=old_meta.get("evidence_count", "—"),
                old_wall=round(old.get("wall_ms", 0) / 1000, 1),
                old_status=old_status,
                new_chars=new.get("answer_chars", "—"),
                new_evidence=new_meta.get("evidence_count", "—"),
                new_wall=round(new.get("wall_ms", 0) / 1000, 1),
                new_persona=new_meta.get("persona_score", "—"),
                new_status=new_status,
            )
        )
    lines += [
        "",
        f"- 成功：{stats['success']}/{stats['total']}",
        f"- 旧项目降级：{stats['old']['degraded']}/{stats['old']['success']}；新项目降级：{stats['new']['degraded']}/{stats['new']['success']}",
        f"- 旧项目总耗时：{round((stats['old']['total_wall_ms'] or 0) / 1000, 1)}s；新项目总耗时：{round((stats['new']['total_wall_ms'] or 0) / 1000, 1)}s",
        "",
        "## 回答摘要（完整回答见同目录 `results.json`）",
        "",
    ]
    for question in meta["questions"]:
        old = by_key.get(("old", question["id"])) or {}
        new = by_key.get(("new", question["id"])) or {}
        lines += [
            f"### {question['id'].upper()} · {question['category']}",
            "",
            f"**旧项目**：{short(old.get('answer', '') if old.get('status') == 200 else old.get('error', '')) or '（无）'}",
            "",
            f"**新项目**：{short(new.get('answer', '') if new.get('status') == 200 else new.get('error', '')) or '（无）'}",
            "",
        ]
    lines.append("> 该文件由 `scripts/compare_luoji.py` 自动生成；原始回答、元数据和 trace 在 `results.json`。")
    (run_dir / "summary.md").write_text("\n".join(lines), encoding="utf-8")


def compact_history_entry(
    run_id: str,
    run_dir: Path,
    meta: dict[str, Any],
    stats: dict[str, Any],
) -> dict[str, Any]:
    return {
        "run_id": run_id,
        "started_at": meta["started_at"],
        "finished_at": meta["finished_at"],
        "label": meta["label"],
        "old_url": meta["old_url"],
        "new_url": meta["new_url"],
        "period_id": meta["period_id"],
        "questions": [item["id"] for item in meta["questions"]],
        "status": meta["status"],
        "success": stats["success"],
        "total": stats["total"],
        "old": stats["old"],
        "new": stats["new"],
        "run_dir": str(run_dir),
        "summary": str(run_dir / "summary.md"),
    }


def rebuild_history_md() -> None:
    entries = []
    if HISTORY_JSONL.exists():
        for line in HISTORY_JSONL.read_text(encoding="utf-8").splitlines():
            if line.strip():
                try:
                    entries.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
    entries.sort(key=lambda item: item.get("started_at", ""), reverse=True)
    lines = [
        "# 罗辑新旧链路 · 测试历史",
        "",
        f"更新时间：{now_iso()}",
        "",
        "| run | 时间 | 标签 | 问题 | 状态 | 成功/总数 | 旧降级 | 新降级 | 旧耗时 | 新耗时 |",
        "|---|---|---|---|---|---|---|---|---|---|",
    ]
    for entry in entries:
        old = entry.get("old") or {}
        new = entry.get("new") or {}
        lines.append(
            "| {run} | {time} | {label} | {questions} | {status} | {success}/{total} | "
            "{old_deg}/{old_ok} | {new_deg}/{new_ok} | {old_wall}s | {new_wall}s |".format(
                run=entry.get("run_id", "—"),
                time=entry.get("started_at", "—"),
                label=entry.get("label", "—"),
                questions="、".join(entry.get("questions", [])),
                status=entry.get("status", "—"),
                success=entry.get("success", 0),
                total=entry.get("total", 0),
                old_deg=old.get("degraded", 0),
                old_ok=old.get("success", 0),
                new_deg=new.get("degraded", 0),
                new_ok=new.get("success", 0),
                old_wall=round((old.get("total_wall_ms") or 0) / 1000, 1),
                new_wall=round((new.get("total_wall_ms") or 0) / 1000, 1),
            )
        )
    lines += [
        "",
        "> 每个 run 的完整回答在 `runs/<run_id>/results.json`，指标摘要在同目录 `summary.md`。",
    ]
    HISTORY_MD.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="罗辑新旧链路对比测试 + 历史记录")
    parser.add_argument("--old-url", default=DEFAULT_OLD_URL)
    parser.add_argument("--new-url", default=DEFAULT_NEW_URL)
    parser.add_argument("--project", choices=["both", "old", "new"], default="both")
    parser.add_argument("--categories", help="例如 q1,q2 或 聊天,爱情；不填跑六题")
    parser.add_argument("--period-id", type=int, default=PERIOD_ID)
    parser.add_argument("--user-id", type=int, default=2)
    parser.add_argument("--username", default="这很好1")
    parser.add_argument("--label", default="manual")
    parser.add_argument("--timeout", type=float, default=420.0)
    parser.add_argument("--retries", type=int, default=0, help="失败重试次数；超时不重试")
    parser.add_argument("--no-trace", action="store_true", help="不查询 trace 模型明细")
    parser.add_argument("--fail-on-degraded", action="store_true", help="有降级时返回非零退出码")
    parser.add_argument("--dry-run", action="store_true", help="只打印计划，不调用接口")
    args = parser.parse_args()

    try:
        questions = select_questions(args.categories)
    except ValueError as error:
        print(f"参数错误：{error}", file=sys.stderr)
        return 2

    projects: list[tuple[str, str]] = []
    if args.project in {"both", "old"}:
        projects.append(("old", args.old_url))
    if args.project in {"both", "new"}:
        projects.append(("new", args.new_url))

    if args.dry_run:
        print("计划运行：")
        for project, url in projects:
            print(f"  {project}: {url}")
        for question in questions:
            print(f"  {question['id']} {question['category']} mode={question['mode']}")
        print(f"输出目录：{RUNS_DIR}")
        return 0

    token = create_access_token(args.user_id, args.username)
    chat_model = os.getenv("STORYROLE_CHAT_MODEL") or os.getenv("BAILIAN_MODEL") or "unknown"
    base_url = (
        os.getenv("OPENAI_BASE_URL")
        or os.getenv("BAILIAN_BASE_URL")
        or os.getenv("DASHSCOPE_BASE_URL")
        or ""
    )
    git_commit = ""
    try:
        proc = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=ROOT,
            capture_output=True,
            text=True,
            timeout=5,
        )
        if proc.returncode == 0:
            git_commit = proc.stdout.strip()
    except Exception:
        git_commit = ""

    run_id = f"{time.strftime('%Y%m%d-%H%M%S')}-{slugify(args.label)}-{uuid.uuid4().hex[:4]}"
    run_dir = RUNS_DIR / run_id
    started_at = now_iso()
    print(f"run_id = {run_id}")
    print(f"旧项目 = {args.old_url}")
    print(f"新项目 = {args.new_url}")
    print(f"模型 = {chat_model}")

    client = httpx.Client(timeout=args.timeout, follow_redirects=True)
    preflight_errors = []
    for project, url in projects:
        error = preflight(client, url)
        if error:
            preflight_errors.append(f"{project} {url}: {error}")
            print(f"预热检查失败：{project} {url} -> {error}", flush=True)
        else:
            print(f"预热检查通过：{project} {url}", flush=True)
    if preflight_errors:
        client.close()
        print("服务未就绪，未开始测试；请先启动对应项目。", file=sys.stderr)
        return 2

    results: list[dict[str, Any]] = []
    overall_started = time.perf_counter()
    try:
        for project, url in projects:
            print(f"== {project} ==", flush=True)
            for question in questions:
                print(f"  {question['id']} {question['category']} ({question['mode']}) ...", flush=True)
                result = call_once(
                    client,
                    url,
                    token,
                    project,
                    question,
                    run_id,
                    args.period_id,
                    args.timeout,
                    args.retries,
                )
                results.append(result)
                if result["status"] == 200:
                    meta = result.get("meta") or {}
                    print(
                        f"    ok {result['wall_ms'] / 1000:.1f}s "
                        f"chars={result['answer_chars']} "
                        f"evidence={meta.get('evidence_count')} "
                        f"degraded={meta.get('degraded')}",
                        flush=True,
                    )
                else:
                    print(f"    ERROR {result.get('error', '')[:300]}", flush=True)
    finally:
        client.close()

    stats = build_stats(results)
    finished_at = now_iso()
    status = "completed" if stats["success"] == stats["total"] else "partial"
    if stats["success"] == 0:
        status = "failed"
    meta: dict[str, Any] = {
        "run_id": run_id,
        "started_at": started_at,
        "finished_at": finished_at,
        "label": args.label,
        "old_url": args.old_url,
        "new_url": args.new_url,
        "period_id": args.period_id,
        "questions": [
            {"id": item["id"], "category": item["category"], "mode": item["mode"]}
            for item in questions
        ],
        "chat_model": chat_model,
        "base_url": base_url,
        "git_commit": git_commit,
        "status": status,
        "stats": stats,
    }

    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "results.json").write_text(
        json.dumps({"meta": meta, "results": results}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    write_summary(run_dir, meta, results, stats)
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    with HISTORY_JSONL.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(compact_history_entry(run_id, run_dir, meta, stats), ensure_ascii=False) + "\n")
    rebuild_history_md()

    print(f"完成：{status}，成功 {stats['success']}/{stats['total']}，用时 {time.perf_counter() - overall_started:.1f}s")
    print(f"记录：{run_dir}")
    print(f"历史：{HISTORY_MD}")

    if stats["success"] < stats["total"]:
        return 1
    if args.fail_on_degraded and stats["degraded"] > 0:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
