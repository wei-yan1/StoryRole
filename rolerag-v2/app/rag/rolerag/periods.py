"""Period boundary resolution.

A period is a promise: this character may only speak from what they could have
seen by the end of that period. A missing chapter bound must therefore never
silently collapse into the whole book. The resolver is ordered from strongest
evidence to weakest, and always reports which source it used.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from .runtime import RoleRAGRuntime
from .store import InMemoryGraphStore

_GENERIC = {
    "全时期", "时期", "阶段", "早期", "中期", "晚期", "建立", "普通", "学者",
    "新", "旧", "前", "后", "的", "与", "和",
}


@dataclass(frozen=True)
class PeriodCutoff:
    cutoff: int
    source: str
    confidence: float


_CACHE: dict[tuple[str, str, str], PeriodCutoff] = {}


def _norm(text: str) -> str:
    return re.sub(r"[\s\W_]+", "", text or "")


def _terms(name: str) -> tuple[str, ...]:
    chunks = re.split(r"[：:·、，,/\s]+", name or "")
    terms: list[str] = []
    for chunk in chunks:
        chunk = re.sub(r"(时期|阶段|早期|中期|晚期)$", "", chunk.strip())
        if not chunk or chunk in _GENERIC:
            continue
        if 2 <= len(chunk) <= 8:
            terms.append(chunk)
    return tuple(dict.fromkeys(terms))[:6]


def _profile_terms(profile: dict | None) -> tuple[str, ...]:
    if not profile:
        return ()
    values: list[str] = []
    boundary = profile.get("knowledge_boundary") or {}
    if isinstance(boundary, dict):
        values.extend(str(item) for item in (boundary.get("known") or [])[:3])
    values.extend(str(item) for item in (profile.get("core_beliefs") or [])[:3])
    terms: list[str] = []
    for value in values:
        for token in re.findall(r"[\u4e00-\u9fff]{2,6}", value):
            if token not in _GENERIC:
                terms.append(token)
    return tuple(dict.fromkeys(terms))[:8]


def _term_cutoff(store: InMemoryGraphStore, name: str, profile: dict | None) -> PeriodCutoff | None:
    terms = _terms(name) + _profile_terms(profile)
    if not terms:
        return None
    chapters = [(chapter.ordinal, _norm(chapter.text)) for chapter in store.chapters()]
    if not chapters:
        return None
    scored: list[tuple[int, int]] = []
    for ordinal, text in chapters:
        score = sum(text.count(term) for term in terms)
        if score:
            scored.append((score, ordinal))
    if not scored:
        return None
    best = max(score for score, _ in scored)
    # Earliest chapter that contains the strongest period vocabulary is the
    # conservative end of the period: it cannot leak later plot.
    ordinal = min(ordinal for score, ordinal in scored if score == best)
    confidence = min(0.75, 0.35 + best / max(1, len(terms)) / 10)
    return PeriodCutoff(ordinal, "period_terms", confidence)


def _name_matches(left: str, right: str) -> bool:
    def key(value: str) -> str:
        value = re.sub(r"(时期|阶段|早期|中期|晚期)", "", value or "")
        return _norm(value)
    a, b = key(left), key(right)
    return bool(a and b and (a in b or b in a))


def resolve_period_cutoff(
    runtime: RoleRAGRuntime,
    period: dict | None,
    *,
    profile: dict | None = None,
    period_analysis: dict | None = None,
) -> PeriodCutoff:
    name = str((period or {}).get("name") or (period or {}).get("period_name") or "")
    cache_key = (str(id(runtime.store)), name, _norm(str((profile or {}).get("identity", "")))[:80])
    if cache_key in _CACHE:
        return _CACHE[cache_key]

    # 1) Explicit bounds on the period row are authoritative.
    if period:
        matched = runtime.match_cutoff_for_period(
            period.get("chapter_start"), period.get("chapter_end")
        )
        if matched is not None:
            result = PeriodCutoff(matched, "explicit_bounds", 1.0)
            _CACHE[cache_key] = result
            return result

    # 2) A saved period analysis may carry chapter_start/chapter_end.
    if period_analysis:
        periods = period_analysis.get("periods") or []
        if isinstance(periods, list):
            for item in periods:
                if not isinstance(item, dict):
                    continue
                item_name = str(item.get("name") or "")
                if name and _name_matches(name, item_name):
                    matched = runtime.match_cutoff_for_period(
                        item.get("chapter_start"), item.get("chapter_end")
                    )
                    if matched is not None:
                        result = PeriodCutoff(matched, "period_analysis", 0.85)
                        _CACHE[cache_key] = result
                        return result

    # 3) "all periods" is the explicit whole-book case.
    if "全时期" in name or "全部时期" in name:
        result = PeriodCutoff(runtime.cutoff, "whole_book", 1.0)
        _CACHE[cache_key] = result
        return result

    # 4) Conservative vocab search over chapter text.
    term_result = _term_cutoff(runtime.store, name, profile)
    if term_result is not None:
        _CACHE[cache_key] = term_result
        return term_result

    # 5) No evidence at all: do not leak the whole book. The first chapter is
    #    the smallest boundary the graph can defend.
    result = PeriodCutoff(min(1, runtime.cutoff), "conservative_min", 0.1)
    _CACHE[cache_key] = result
    return result


def clear_cache() -> None:
    _CACHE.clear()


__all__ = ["PeriodCutoff", "resolve_period_cutoff", "clear_cache"]
