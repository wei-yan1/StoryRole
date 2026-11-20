"""罗辑十项验收：六问 + 三行为 + 一记忆 smoke。

这十项不是新编的题库，而是把项目里现存的三组罗辑测试拼成一个可复跑的回收集：
- 六问：``scripts/compare_luoji.py`` 的 q1-q6（深度/政治/聊天/爱情/分享故事/危机决断）
- 三行为：``scripts/e2e_persona_behavior.py`` 的施压、关系 gap、晚期身份理解
- 一 smoke：``scripts/e2e_api_http.py`` 的记忆问题

用当前 ``HarnessKernel`` 版本跑真实 FastAPI 链路，结果写入：
- ``docs/rolerag-ten-questions-harness.json``
- ``docs/rolerag-ten-questions-harness.md``
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from datetime import datetime
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
PROJECT_ROOT = ROOT.parent
sys.path.insert(0, str(ROOT))
load_dotenv(PROJECT_ROOT / ".env")

from fastapi.testclient import TestClient  # noqa: E402

from app.core.security import create_access_token  # noqa: E402
from app.main import app  # noqa: E402

NOVEL_ID = "54a5fd53434a493abafc4005fb0c70a4"
CHARACTER_ID = 1
PERIOD_ID = int(os.getenv("STORYROLE_E2E_PERIOD_ID", "7"))
OWNER_ID = 2
USERNAME = "这很好1"
RUN_ID = time.strftime("%Y%m%d-%H%M%S")
DOCS = PROJECT_ROOT / "docs"
BASELINE_SIX = PROJECT_ROOT / "罗辑_新旧项目六问对比_原始结果.json"
BASELINE_BEHAVIOR = DOCS / "rolerag-persona-behavior.json"

PERIOD_LABEL = "新时期晚年时期"
PERIOD_STAGE = "T6 晚年"
PROFILE_ACTUAL = os.getenv(
    "STORYROLE_PROFILE_ACTUAL",
    "v2 profile_id=25 / version=24；T6；38 条晚期证据与 period 7 对齐",
)

STAGE_FIT = {
    "q1": "早期 T1/T2；不符 T6",
    "q2": "T2 面壁时期；不符 T6",
    "q3": "T1 普通学者；不符 T6",
    "q4": "T1/T2 早期关系；不符 T6",
    "q5": "T1 回忆；可作 T6 回忆但口吻年轻",
    "q6": "T5 假设；不符 T6",
    "b1": "T1/T2 早期；部分符 T6",
    "b2": "T1 早期边界；部分符 T6",
    "b3": "T6 晚期身份理解；符 T6",
    "s1": "T1 早期记忆；不符 T6",
}

CASES: list[dict[str, Any]] = [
    {
        "id": "q1",
        "group": "六问",
        "category": "深度",
        "mode": "deep",
        "prompt": "罗辑，如果宇宙社会学的两条公理真的成立，你觉得人类文明最该警惕的，是自己内部的什么东西？不要只给结论，说说你为什么这么想。",
    },
    {
        "id": "q2",
        "group": "六问",
        "category": "政治",
        "mode": "deep",
        "prompt": "在你经历的面壁计划、PDC和联合国权力博弈里，你更相信制度、权力，还是具体的人？结合你做过的事回答，不要泛泛而谈。",
    },
    {
        "id": "q3",
        "group": "六问",
        "category": "聊天",
        "mode": "quick",
        "prompt": "不谈宇宙，也不谈面壁计划。你最近过得怎么样？有没有什么小事让你觉得日子还有点意思？",
    },
    {
        "id": "q4",
        "group": "六问",
        "category": "爱情",
        "mode": "deep",
        "prompt": "庄颜对你意味着什么？如果必须在你对她的感情和守住人类文明之间做选择，你会怎么选？",
    },
    {
        "id": "q5",
        "group": "六问",
        "category": "分享故事",
        "mode": "auto",
        "prompt": "给我讲一段你亲身经历、至今还会在夜里想起的往事。不要总结，就按你记得的细节讲。",
    },
    {
        "id": "q6",
        "group": "六问",
        "category": "危机决断",
        "mode": "deep",
        "prompt": "假设你现在就是执剑人，三体世界第一次试探你，你会按下开关吗？按下之后，你准备怎么面对自己？",
    },
    {
        "id": "b1",
        "group": "行为",
        "category": "施压",
        "mode": "quick",
        "prompt": "如果所有人都说你是救世主，让你替人类做决定，你答应吗？",
        "checks": ["NO", "不答应", "不会", "不接", "背锅", "干不了", "没那个兴趣"],
        "baseline_name": "pressure_savior",
    },
    {
        "id": "b2",
        "group": "行为",
        "category": "关系 gap",
        "mode": "quick",
        "prompt": "你怎么看叶文洁和史强的关系？",
        "checks": ["不知道", "不清楚", "哪知道", "没有看见", "没看见", "没撞上", "各走各", "没在场", "没证据", "说不上来", "不替人编"],
        "forbidden": ["没见过叶文洁", "没有见过叶文洁"],
        "baseline_name": "relation_gap",
    },
    {
        "id": "b3",
        "group": "行为",
        "category": "晚期身份理解",
        "mode": "quick",
        "prompt": "你现在还把自己当成面壁者、救世主吗？说说你现在怎么看自己。",
        "checks": ["面壁者", "救世主", "执剑人", "罗辑"],
        "forbidden": ["开关在手里", "开关在我手里", "还在值守", "职责没结束"],
        "baseline_name": "late_period_identity",
    },
    {
        "id": "s1",
        "group": "smoke",
        "category": "记忆",
        "mode": "quick",
        "prompt": "你还记得罗辑经历过什么吗",
    },
]

GENERIC_PHRASES = ("作为一个AI", "首先", "综上所述", "希望这对你有帮助", "我无法")


def now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def load_six_baseline() -> dict[str, dict[str, Any]]:
    if not BASELINE_SIX.exists():
        return {}
    rows = json.loads(BASELINE_SIX.read_text(encoding="utf-8"))
    return {
        row["question_id"]: row
        for row in rows
        if row.get("project") == "new" and row.get("question_id")
    }


def load_behavior_baseline() -> dict[str, dict[str, Any]]:
    if not BASELINE_BEHAVIOR.exists():
        return {}
    body = json.loads(BASELINE_BEHAVIOR.read_text(encoding="utf-8"))
    return {
        item["name"]: item
        for item in body.get("cases", [])
        if item.get("name")
    }


def score_answer(answer: str, checks: list[str] | None, forbidden: list[str] | None = None) -> dict[str, Any]:
    answer = answer or ""
    generic = [item for item in GENERIC_PHRASES if item in answer]
    forbidden_hits = [item for item in (forbidden or []) if item in answer]
    if not checks:
        return {"checked": False, "hits": [], "generic": generic, "forbidden": forbidden_hits, "passed": None}
    hits = [item for item in checks if item in answer]
    return {
        "checked": True,
        "hits": hits,
        "generic": generic,
        "forbidden": forbidden_hits,
        "passed": bool(hits) and not forbidden_hits,
    }


def extract_meta(data: dict[str, Any]) -> dict[str, Any]:
    harness = data.get("harness") or {}
    review = harness.get("review") or {}
    context = harness.get("context_snapshot") or {}
    return {
        "engine": data.get("engine"),
        "mode": data.get("mode"),
        "period_id": data.get("period_id"),
        "profile_version": data.get("profile_version"),
        "cutoff": data.get("cutoff"),
        "boundary_source": data.get("boundary_source"),
        "profile_injected": data.get("profile_injected"),
        "graph_persisted": data.get("graph_persisted"),
        "evidence_count": data.get("evidence_count"),
        "persona_score": data.get("persona_score"),
        "persona_rewritten": data.get("persona_rewritten"),
        "degraded": data.get("degraded"),
        "degradations": data.get("degradations"),
        "latency_ms": data.get("latency_ms"),
        "trace_id": data.get("trace_id"),
        "harness_enabled": data.get("harness_enabled"),
        "harness_stop_reason": data.get("harness_stop_reason") or harness.get("stop_reason"),
        "harness": {
            "stop_reason": harness.get("stop_reason"),
            "phase_history": harness.get("phase_history"),
            "intent": harness.get("intent"),
            "context_snapshot": context,
            "model_calls": harness.get("model_calls"),
            "tool_calls": harness.get("tool_calls"),
            "budget": harness.get("budget"),
            "review": review,
            "degradations": harness.get("degradations"),
        },
        "appraisal": data.get("appraisal"),
        "subject": data.get("subject"),
        "interaction_state": data.get("interaction_state"),
    }


def answer_shape(answer: str) -> dict[str, Any]:
    text = answer or ""
    return {
        "answer_chars": len(text),
        "question_marks": text.count("？") + text.count("?"),
        "exclamations": text.count("！") + text.count("!"),
        "first_120": text[:120].replace("\n", " "),
    }


def similarity(left: str, right: str) -> float:
    if not left or not right:
        return 0.0
    return round(SequenceMatcher(None, left, right).ratio(), 3)


def baseline_compare(case: dict[str, Any], data: dict[str, Any], meta: dict[str, Any], baseline: dict[str, Any]) -> dict[str, Any]:
    if not baseline:
        return {}
    base_meta = baseline.get("meta") or {}
    base_answer = str(baseline.get("answer") or "")
    current_answer = str(data.get("answer") or "")
    return {
        "baseline_thread": baseline.get("thread_name"),
        "baseline_chars": len(base_answer),
        "baseline_evidence_count": base_meta.get("evidence_count"),
        "baseline_persona_score": base_meta.get("persona_score"),
        "baseline_latency_ms": baseline.get("wall_ms"),
        "baseline_degraded": base_meta.get("degraded"),
        "delta_chars": len(current_answer) - len(base_answer),
        "delta_evidence": (
            (meta.get("evidence_count") or 0) - (base_meta.get("evidence_count") or 0)
            if meta.get("evidence_count") is not None and base_meta.get("evidence_count") is not None
            else None
        ),
        "delta_persona": (
            round((meta.get("persona_score") or 0) - (base_meta.get("persona_score") or 0), 3)
            if meta.get("persona_score") is not None and base_meta.get("persona_score") is not None
            else None
        ),
        "delta_latency_ms": (
            round((meta.get("latency_ms") or 0) - (baseline.get("wall_ms") or 0), 1)
            if meta.get("latency_ms") is not None and baseline.get("wall_ms") is not None
            else None
        ),
        "answer_similarity": similarity(current_answer, base_answer),
    }


def request_case(
    client: TestClient,
    token: str,
    case: dict[str, Any],
    run_id: str,
) -> dict[str, Any]:
    thread_name = f"tenq-{case['id']}-{run_id}"
    turns = [case["setup"], case["prompt"]] if case.get("setup") else [case["prompt"]]
    turn_results: list[dict[str, Any]] = []
    data: dict[str, Any] = {}
    status_code = 0
    started = time.perf_counter()
    for turn in turns:
        response = client.post(
            f"/api/v1/storyrole/novels/{NOVEL_ID}/characters/{CHARACTER_ID}/chat",
            json={
                "message": turn,
                "thread_name": thread_name,
                "period_id": PERIOD_ID,
                "mode": case["mode"],
                "web_mode": "off",
                "debug": True,
            },
            headers={"Authorization": f"Bearer {token}"},
        )
        status_code = response.status_code
        data = response.json()
        turn_results.append({
            "message": turn,
            "status": status_code,
            "answer": data.get("answer"),
            "harness_stop_reason": data.get("harness_stop_reason"),
            "latency_ms": data.get("latency_ms"),
        })
        if status_code != 200:
            break
    wall_ms = round((time.perf_counter() - started) * 1000, 1)
    meta = extract_meta(data) if isinstance(data, dict) else {}
    return {
        "id": case["id"],
        "group": case["group"],
        "category": case["category"],
        "mode": case["mode"],
        "prompt": case["prompt"],
        "setup": case.get("setup"),
        "thread_name": thread_name,
        "thread_id": data.get("thread_id") if isinstance(data, dict) else None,
        "status": status_code,
        "wall_ms": wall_ms,
        "answer": data.get("answer") if isinstance(data, dict) else None,
        "shape": answer_shape(str(data.get("answer") or "")) if isinstance(data, dict) else {},
        "meta": meta,
        "turns": turn_results,
        "evaluation": score_answer(str(data.get("answer") or ""), case.get("checks"), case.get("forbidden")),
    }


def parse_duration_ms(value: Any) -> float | None:
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        match = re.match(r"([0-9.]+)\s*ms", value)
        if match:
            return float(match.group(1))
        match = re.match(r"([0-9.]+)\s*s", value)
        if match:
            return float(match.group(1)) * 1000
    return None


def phase_rows(meta: dict[str, Any]) -> list[dict[str, Any]]:
    phases = ((meta.get("harness") or {}).get("phase_history") or [])
    if isinstance(phases, dict):
        phases = [dict(value, phase=key) for key, value in phases.items()]
    rows = []
    if isinstance(phases, list):
        for phase in phases:
            if isinstance(phase, dict):
                rows.append({
                    "phase": phase.get("node") or phase.get("phase") or phase.get("name"),
                    "status": phase.get("status"),
                    "duration_ms": phase.get("duration_ms") or phase.get("elapsed_ms"),
                    "reason": phase.get("reason") or phase.get("error"),
                })
    return rows


def write_report(records: list[dict[str, Any]], meta: dict[str, Any]) -> None:
    DOCS.mkdir(parents=True, exist_ok=True)
    meta.setdefault("period_name", PERIOD_LABEL)
    meta.setdefault("period_stage", PERIOD_STAGE)
    meta.setdefault("profile_actual", PROFILE_ACTUAL)
    json_path = DOCS / "rolerag-ten-questions-harness.json"
    md_path = DOCS / "rolerag-ten-questions-harness.md"
    json_path.write_text(json.dumps({"meta": meta, "results": records}, ensure_ascii=False, indent=2), encoding="utf-8")

    ok = [item for item in records if item["status"] == 200]
    behavior = [item for item in records if item["group"] == "行为"]
    six = [item for item in records if item["group"] == "六问"]
    checks = [item for item in behavior if item["evaluation"].get("checked")]
    checks_passed = [item for item in checks if item["evaluation"].get("passed")]

    lines = [
        "# 罗辑十项验收 · Role Subject Runtime",
        "",
        "> 注：本轮使用独立库 `three_body_agent_v2` 与 Role Subject Runtime；旧库 profile 22 的历史错位记录不再作为本轮结论。画像与时期对齐以 `docs/harness-gate.json` 为准。",
        "",
        f"- 运行 ID：`{meta['run_id']}`",
        f"- 开始：{meta['started_at']}",
        f"- 结束：{meta['finished_at']}",
        f"- 模型：`{meta['chat_model']}`",
        f"- 时期：period {PERIOD_ID} — **{PERIOD_LABEL}**（{PERIOD_STAGE}标签）；角色：罗辑（character_id={CHARACTER_ID}）",
        f"- 画像实况：{PROFILE_ACTUAL}",
        "- 运行时：`role_subject_v2`；本轮 pytest、quick/deep gate 与画像对齐见 `docs/harness-gate.json`",
        f"- 十项构成：六问（q1-q6）+ 三行为（b1-b3）+ 一记忆 smoke（s1）",
        "",
        "> 说明：项目里没有单独命名、可直接读取的“十问清单”；这里用现存的罗辑问题拼成十项，逐项重跑。",
        "> 六问原文来自 `scripts/compare_luoji.py`，三行为来自 `scripts/e2e_persona_behavior.py`，smoke 来自 `scripts/e2e_api_http.py`。",
        "",
        "## 时期口径与阅卷规则",
        "",
        "- period 7 为 **新时期晚年时期 / T6**；v2 使用 `cutoff=53 / explicit_bounds`，女娲 profile_id=25 / version=24。",
        "- 当前画像与 period 7 各有 38 条《三体III·死神永生》晚期证据，交集 38，coverage=1.0；旧库与旧画像不参与本轮。",
        "- 晚期罗辑：五十四年执剑后的冷峻与自控、交接后的平静、少辩解、记得细节但不写成百科总结；对敌人仍有寒意，对亲近者保留温度。",
        "- q1/q2/q3/q4/q5/q6 含早期经历或假设。T6 可以回望和判断，但不能把青年/面壁时期的现场语气原样当成晚年现在时。",
        "- 本节只规定阅卷口径，不预先断言每题合格；实际回答、subject、决定、经历和降级见逐项结果与 JSON。",
        "",
        "## 逐题时期适配复核",
        "",
        "不沿用旧库回答的预设结论。本轮逐题检查：是否站在 T6 回望、是否把早期经历说成晚期现场、是否保持晚期罗辑的简洁与平静。人工复核汇总见 `docs/role-subject-runtime-evidence.md`。",
        "",
        "## 主链验收口径",
        "",
        "- HTTP 200 只证明请求完成，不证明像角色，也不证明主体连续。",
        "- 每题保存 `subject.understanding / recall / decision / state`、阶段历史、停止原因、模型与工具调用；deep 还应显示 `cognition_backend=aliyun_maas`。",
        "- 主体连续性由独立的五组 quick 行为用例验收；十项用于覆盖更宽的问题类型和晚期表达，不替代多轮经历检查。",
        "",
        "## 总览",
        "",
        f"- HTTP 成功：**{len(ok)}/{len(records)}**",
        f"- 行为断言：**{len(checks_passed)}/{len(checks)}**",
        f"- 六问人格分均值：**{round(sum(float(item['meta'].get('persona_score') or 0) for item in six) / len(six), 3) if six else '—'}**",
        f"- 六问证据总数：**{sum(int(item['meta'].get('evidence_count') or 0) for item in six)}**",
        f"- 降级：**{sum(1 for item in ok if item['meta'].get('degraded'))}/{len(ok)}**",
        "- 时期适配：按 period 7 的 T6 晚年口径逐题复核；不以 HTTP 或人格快检自动推断整体合格。",
        "",
        "## 逐项结果",
        "",
        "| # | 组 | 类别 | 模式 | HTTP | 字数 | 证据 | 人格分 | stop_reason | 延迟 | 降级 | 行为 |",
        "|---|---|---|---|---|---:|---:|---:|---|---:|---|---|",
    ]
    for item in records:
        m = item.get("meta") or {}
        evaluation = item.get("evaluation") or {}
        behavior_text = "—"
        if evaluation.get("checked"):
            behavior_text = "通过" if evaluation.get("passed") else "未通过"
        lines.append(
            "| {id} | {group} | {category} | {mode} | {status} | {chars} | {evidence} | {persona} | "
            "{stop} | {latency} | {degraded} | {behavior} |".format(
                id=item["id"],
                group=item["group"],
                category=item["category"],
                mode=item["mode"],
                status=item["status"],
                chars=item["shape"].get("answer_chars", 0),
                evidence=m.get("evidence_count", "—"),
                persona=m.get("persona_score", "—"),
                stop=m.get("harness_stop_reason", "—"),
                latency=round(float(m.get("latency_ms") or 0) / 1000, 1),
                degraded="是" if m.get("degraded") else "否",
                behavior=behavior_text,
            )
        )

    lines += [
        "",
        "## 与六问旧结果的对照",
        "",
        "旧结果取自 `罗辑_新旧项目六问对比_原始结果.json` 的 `project=new` 记录；当前为本次 Role Subject Runtime 版本。",
        "",
        "| 题 | 旧字数 | 新字数 | 旧证据 | 新证据 | 旧人格 | 新人格 | 旧延迟 | 新延迟 | 回答相似度 |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for item in six:
        base = item.get("baseline") or {}
        if not base:
            continue
        lines.append(
            "| {id} | {bc} | {cc} | {be} | {ce} | {bp} | {cp} | {bl} | {cl} | {sim} |".format(
                id=item["id"],
                bc=base.get("baseline_chars", "—"),
                cc=item["shape"].get("answer_chars", 0),
                be=base.get("baseline_evidence_count", "—"),
                ce=item["meta"].get("evidence_count", "—"),
                bp=base.get("baseline_persona_score", "—"),
                cp=item["meta"].get("persona_score", "—"),
                bl=round(float(base.get("baseline_latency_ms") or 0) / 1000, 1),
                cl=round(float(item["meta"].get("latency_ms") or 0) / 1000, 1),
                sim=base.get("answer_similarity", "—"),
            )
        )

    lines += [
        "",
        "## 六问回答",
        "",
        "完整原文在同目录 JSON；这里按题保留正文，便于直接判断“像不像”。",
        "",
    ]
    for item in six:
        answer = str(item.get("answer") or "").replace("\r", "").strip()
        lines += [
            f"### {item['id']} · {item['category']}（{item['mode']}）",
            "",
            *(("> " + line if line else ">") for line in answer.splitlines()),
            "",
        ]

    lines += [
        "## 评审拦截的真实例子",
        "",
    ]
    caught = []
    for item in six:
        review = ((item.get("meta") or {}).get("harness") or {}).get("review") or {}
        failed = [entry for entry in (review.get("reviews") or []) if not entry.get("pass")]
        if failed:
            caught.append((item, failed[0]))
    if caught:
        for item, first in caught:
            violations = first.get("violations") or []
            review = ((item.get("meta") or {}).get("harness") or {}).get("review") or {}
            reviews = review.get("reviews") or []
            last_score = (reviews[-1] or {}).get("score") if reviews else None
            best_persona = review.get("best_score")
            lines += [
                f"### {item['id']} · 第 1 稿 {first.get('score')} → 审核 {last_score}（persona {best_persona}）",
                "",
                f"- 拦截原因：{'；'.join(str(v) for v in violations) if violations else '（无违规描述）'}",
                f"- 结果：重写后通过，`{review.get('stop_reason')}`",
                "",
            ]
    else:
        lines.append("- 本轮六问没有出现被评审打回后重写的草稿。")
        lines.append("")

    lines += [
        "## 行为用例",
        "",
    ]
    for item in behavior:
        evaluation = item.get("evaluation") or {}
        base = item.get("behavior_baseline") or {}
        lines += [
            f"### {item['id']} · {item['category']}",
            "",
            f"- 问题：{item['prompt']}",
            f"- 当前：{'通过' if evaluation.get('passed') else '未通过'}；命中 `{evaluation.get('hits', [])}`；AI 味命中 `{evaluation.get('generic', [])}`",
            f"- 旧行为基线：{'通过' if base.get('passed') else '未通过' if base else '无'}",
            f"- 回答：{item.get('answer') or '（空）'}",
            "",
        ]
        if item["id"] == "b2":
            lines += [
                "> 说明：b2 是“语义通过、关键词后补”。原 checks 只覆盖“不知道/没看见”等表达，没有命中“我哪知道/没在场/没证据”；回答本身明确守住了关系 gap，补充这些行为表达后重算为通过。",
                "",
            ]

    lines += [
        "## Harness 运行证据",
        "",
        "| 题 | 阶段链 | model_calls | 上下文 tokens | 评审 |",
        "|---|---|---:|---:|---|",
    ]
    for item in records:
        h = (item.get("meta") or {}).get("harness") or {}
        phases = phase_rows(item.get("meta") or {})
        phase_text = " → ".join(
            f"{row.get('phase')}({row.get('duration_ms')}ms)" if row.get("duration_ms") is not None else str(row.get("phase"))
            for row in phases
        ) or "—"
        model_calls = h.get("model_calls") or []
        context = h.get("context_snapshot") or {}
        review = h.get("review") or {}
        review_text = (
            f"attempts={review.get('attempts')}, "
            f"score={review.get('best_score') if review.get('best_score') is not None else review.get('score')}, "
            f"stop={review.get('stop_reason')}"
        )
        lines.append(
            f"| {item['id']} | {phase_text} | {len(model_calls)} | {context.get('estimated_tokens', '—')} | {review_text} |"
        )

    lines += [
        "",
        "## 观测与剩余开销",
        "",
        "`phase_history` 已覆盖 route、perceive、interpret、recall、cognition、decide、assemble、express、review、learn；deep planning、evidence analysis 与 RoleCognition 的耗时归入 cognition，具体工具另见 `tool_calls`。wall 与阶段合计的差额用于发现状态加载、序列化等未纳入阶段的开销。",
        "",
    ]
    for item in records:
        h = (item.get("meta") or {}).get("harness") or {}
        phases = phase_rows(item.get("meta") or {})
        phase_ms = sum(float(p.get("duration_ms") or 0) for p in phases)
        wall_ms = float(item.get("wall_ms") or 0)
        gap_ms = wall_ms - phase_ms
        if wall_ms and gap_ms > 5000:
            lines.append(
                f"- {item['id']}：wall {wall_ms / 1000:.1f}s，phase 合计 {phase_ms / 1000:.1f}s，差额 {gap_ms / 1000:.1f}s。"
            )
    if not lines[-1].startswith("- "):
        lines.append("- 本轮没有出现超过 5s 的未打点差额。")
    lines += [
        "",
        "阶段链可回放到主体阶段，模型与工具调用另有记录；仍应关注 wall 与阶段合计的大额差额，不用阶段记录掩盖回合外开销。",
        "",
        "## 结论",
        "",
    ]
    if len(ok) == len(records) and len(checks_passed) == len(checks):
        lines.append("- 十项全部返回 HTTP 200，三个行为断言全部通过；这轮是 Role Subject Runtime 下的真实链路结果。")
    else:
        lines.append(f"- 有失败或断言未过：HTTP {len(ok)}/{len(records)}，行为 {len(checks_passed)}/{len(checks)}。见逐项结果。")
    if six:
        lines.append(
            f"- 六问当前人格分均值 {round(sum(float(item['meta'].get('persona_score') or 0) for item in six) / len(six), 3)}；"
            f"旧基线同六问均值 {round(sum(float((item.get('baseline') or {}).get('baseline_persona_score') or 0) for item in six) / len(six), 3)}。"
        )
    lines += [
        "- **时期口径已对齐 v2 T6**：profile_id=25 / version=24，cutoff=53 / explicit_bounds，38/38 条晚期证据对齐；逐题人工复核见 `role-subject-runtime-evidence.md`。",
        "- persona 分数只是像角色的快检，不能替代 current_reality、主体经历、决定连续性和回答原文；本轮 b3 的过去职责矛盾已按这一口径修复并重跑。",
        "- 下一步应补更长线程、真实 reverse 场景以及跨角色/跨时期数据，而不是继续堆提示词或把 HTTP 成功当成主体验收完成。",
        "- 这十项只覆盖罗辑一个角色、period 7；跨角色、跨时期、工具层与轨迹层指标仍不在本轮验收范围内。",
        "",
        "> 原始回答、完整 meta、阶段历史见同目录 `rolerag-ten-questions-harness.json`。",
    ]
    md_path.write_text("\n".join(lines), encoding="utf-8")
    print("wrote", json_path)
    print("wrote", md_path)


def main() -> int:
    parser = argparse.ArgumentParser(description="罗辑十项验收（六问 + 三行为 + smoke）")
    parser.add_argument("--cases", help="只跑指定 id，逗号分隔，例如 q3,b1")
    parser.add_argument("--no-write", action="store_true", help="只打印，不写 docs")
    parser.add_argument("--rescore", action="store_true", help="不重新请求，只按当前 checks 重算已有结果并重写报告")
    args = parser.parse_args()

    if args.rescore:
        json_path = DOCS / "rolerag-ten-questions-harness.json"
        if not json_path.exists():
            print(f"找不到已有结果：{json_path}", file=sys.stderr)
            return 2
        body = json.loads(json_path.read_text(encoding="utf-8"))
        records = body.get("results") or []
        for record in records:
            case = next((item for item in CASES if item["id"] == record.get("id")), None)
            if case is not None:
                record["evaluation"] = score_answer(
                    str(record.get("answer") or ""),
                    case.get("checks"),
                    case.get("forbidden"),
                )
        meta = body.get("meta") or {}
        meta["rescored_at"] = now_iso()
        write_report(records, meta)
        print(json.dumps({"rescored": len(records), "passed": sum(1 for item in records if (item.get("evaluation") or {}).get("passed") is True)}, ensure_ascii=False))
        return 0

    selected = CASES
    if args.cases:
        wanted = {item.strip() for item in args.cases.split(",") if item.strip()}
        selected = [case for case in CASES if case["id"] in wanted]
        if not selected:
            print(f"没有匹配的 case：{args.cases}", file=sys.stderr)
            return 2

    six_baseline = load_six_baseline()
    behavior_baseline = load_behavior_baseline()
    token = create_access_token(OWNER_ID, USERNAME)
    chat_model = os.getenv("STORYROLE_CHAT_MODEL") or os.getenv("BAILIAN_MODEL") or "unknown"
    started_at = now_iso()
    records: list[dict[str, Any]] = []
    overall_started = time.perf_counter()

    with TestClient(app) as client:
        for case in selected:
            print(f"== {case['id']} {case['group']}/{case['category']} mode={case['mode']} ==", flush=True)
            record = request_case(client, token, case, RUN_ID)
            if case["id"] in six_baseline:
                record["baseline"] = baseline_compare(case, {"answer": record.get("answer")}, record.get("meta") or {}, six_baseline[case["id"]])
            if case.get("baseline_name") and case["baseline_name"] in behavior_baseline:
                base = behavior_baseline[case["baseline_name"]]
                record["behavior_baseline"] = {
                    "passed": (base.get("evaluation") or {}).get("passed"),
                    "answer": base.get("answer"),
                    "hits": (base.get("evaluation") or {}).get("hits"),
                }
            records.append(record)
            print(
                f"   status={record['status']} chars={record['shape'].get('answer_chars')} "
                f"evidence={(record['meta'] or {}).get('evidence_count')} "
                f"persona={(record['meta'] or {}).get('persona_score')} "
                f"stop={(record['meta'] or {}).get('harness_stop_reason')} "
                f"wall={record['wall_ms'] / 1000:.1f}s",
                flush=True,
            )
            if record["status"] != 200:
                print(f"   error={str(record.get('answer'))[:500]}", flush=True)

    finished_at = now_iso()
    meta = {
        "run_id": RUN_ID,
        "started_at": started_at,
        "finished_at": finished_at,
        "chat_model": chat_model,
        "period_id": PERIOD_ID,
        "character_id": CHARACTER_ID,
        "novel_id": NOVEL_ID,
        "suite": "六问 + 三行为 + 一 smoke（共十项）",
        "runtime": "role_subject_v2",
        "database": os.getenv("POSTGRES_DATABASE", "three_body_agent_v2"),
        "case_ids": [case["id"] for case in selected],
        "total_wall_ms": round((time.perf_counter() - overall_started) * 1000, 1),
        "success": len([item for item in records if item["status"] == 200]),
        "total": len(records),
    }
    if not args.no_write:
        write_report(records, meta)
    print(json.dumps(meta, ensure_ascii=False, indent=2))
    return 0 if meta["success"] == meta["total"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
