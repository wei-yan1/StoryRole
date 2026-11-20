"""Optional LLM fact extraction for events the rule pipeline left empty.

Facts are expensive and dangerous: a hallucinated relation is worse than an
omitted one. This module therefore only looks at a small, high-importance
candidate set, requires explicit JSON, validates every name against the store,
and keeps the existing rule facts as the primary source.
"""

from __future__ import annotations

import json
import re
from typing import Any, Protocol

from ..models import Event, Fact
from ..store import InMemoryGraphStore

_ALLOWED_KINDS = {"信任", "敌对", "亲近", "恩情", "师徒", "承诺", "归属", "尊重", "知情"}


class FactLLM(Protocol):
    def complete(self, prompt: str, system: str = "") -> str: ...


def _extract_json(text: str) -> Any:
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"(\[.*\])", text, re.S)
        if not match:
            return []
        try:
            return json.loads(match.group(1))
        except json.JSONDecodeError:
            return []


def _event_payload(event: Event, store: InMemoryGraphStore) -> dict:
    return {
        "event_id": event.id,
        "chapter": event.chapter,
        "title": event.title,
        "summary": event.summary[:160],
        "participants": [
            {"name": store.entity_name(part.entity_id), "role": part.role}
            for part in event.participants
        ],
    }


def extract_llm_facts(
    events: list[Event],
    store: InMemoryGraphStore,
    llm: FactLLM | None,
    *,
    max_events: int = 24,
    batch_size: int = 6,
) -> list[Fact]:
    if llm is None or not events:
        return []
    candidates = [
        event
        for event in events
        if not event.effects and event.participants and event.importance >= 0.4
    ]
    candidates.sort(key=lambda event: event.importance, reverse=True)
    candidates = candidates[:max_events]
    facts: list[Fact] = []
    existing = {(fact.source_id, fact.target_id, fact.kind) for fact in store.facts()}
    for offset in range(0, len(candidates), batch_size):
        batch = candidates[offset : offset + batch_size]
        payload = [_event_payload(event, store) for event in batch]
        prompt = (
            "只根据下面的事件，抽取明确发生的关系变化。没有明确关系就返回空数组。\n"
            "允许的关系 kind：信任、敌对、亲近、恩情、师徒、承诺、归属、尊重、知情。\n"
            "subject/target 必须使用事件里出现的姓名；sign 为 1 表示关系增强/建立，-1 表示削弱/破裂。\n"
            "JSON 数组格式：[{\"event_id\":\"...\",\"subject\":\"...\",\"target\":\"...\","
            "\"kind\":\"...\",\"sign\":1,\"confidence\":0.7,\"reason\":\"...\"}]\n"
            f"事件：{json.dumps(payload, ensure_ascii=False)}"
        )
        raw = llm.complete(prompt, system="你是严格的事实核查器，宁可漏，不可编。")
        rows = _extract_json(raw)
        if not isinstance(rows, list):
            continue
        by_id = {event.id: event for event in batch}
        for row in rows:
            if not isinstance(row, dict):
                continue
            event = by_id.get(str(row.get("event_id") or ""))
            if event is None:
                continue
            subject_name = str(row.get("subject") or "").strip()
            target_name = str(row.get("target") or "").strip()
            subject = store.find_entity(subject_name)
            target = store.find_entity(target_name)
            if subject is None or target is None or subject.id == target.id:
                continue
            kind = str(row.get("kind") or "").strip()
            if kind not in _ALLOWED_KINDS:
                continue
            sign = 1 if int(row.get("sign") or 1) > 0 else -1
            key = (subject.id, target.id, kind)
            if key in existing:
                continue
            confidence = max(0.35, min(0.85, float(row.get("confidence") or 0.55)))
            fact = Fact(
                id=f"{store.novel_id}:lf{event.id.split(':')[-1]}.{len(facts) + 1:02d}",
                novel_id=store.novel_id,
                source_id=subject.id,
                target_id=target.id,
                kind=kind,
                sign=sign,
                weight=round(confidence * 0.45, 3),
                valid_from=event.chapter,
                cause=str(row.get("reason") or event.title)[:80],
                caused_by_event=event.id,
                confidence=confidence,
            )
            store.add_fact(fact)
            existing.add(key)
            facts.append(fact)
    return facts


__all__ = ["FactLLM", "extract_llm_facts"]
