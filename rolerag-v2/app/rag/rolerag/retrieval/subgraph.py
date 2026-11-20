"""Subgraph retrieval.

Only two operations matter: find the entities the question is about, then walk
their neighbourhood inside the visibility-bounded graph. No global search, no
community reports — both would compress the whole book into the context and
hand the character a script.
"""

from __future__ import annotations

from ..models import CognitionState, Evidence
from ..store import InMemoryGraphStore
from .ego import build_ego_network, relation_evidence
from .router import RouteDecision, _RELATION


def retrieve(
    store: InMemoryGraphStore,
    character_id: str,
    cutoff: int,
    decision: RouteDecision,
    *,
    limit: int = 8,
) -> list[Evidence]:
    if decision.kind == "reject":
        return []

    if decision.kind == "stance":
        state = _state(store, character_id, cutoff)
        return [
            Evidence(
                kind="belief",
                ref_id=belief.fact_id,
                text=f"{belief.subject}与{belief.target}：{_readable(belief.sign, belief.kind)}",
                chapter=belief.since_chapter,
                score=belief.certainty,
            )
            for belief in sorted(state.beliefs, key=lambda b: (-b.certainty, -abs(b.sign)))[:4]
        ]

    targets = _resolve_targets(store, decision.entities)
    relation_query = (
        len(decision.entities) >= 2
        and (decision.multi_hop or any(marker in (decision.query or "") for marker in _RELATION))
    )
    relation_rows: list[tuple[float, Evidence]] = []
    if relation_query:
        network = build_ego_network(store, character_id, cutoff, hops=2)
        for text, chapter, weight in relation_evidence(network, decision.entities)[:6]:
            relation_rows.append((
                weight + 0.2,
                Evidence(
                    kind="relation",
                    ref_id=f"ego:{chapter}:{len(relation_rows)}",
                    text=text[:180],
                    chapter=chapter,
                    score=round(weight, 3),
                ),
            ))
        if not relation_rows:
            names = "、".join(decision.entities)
            relation_rows.append((
                0.05,
                Evidence(
                    kind="relation_gap",
                    ref_id=f"ego:gap:{cutoff}",
                    text=f"我认识{names}，但在{cutoff}章之前没有可见的路径证明他们之间发生过关系。",
                    chapter=cutoff,
                    score=0.05,
                ),
            ))

    scored: list[tuple[float, Evidence]] = []

    for event in store.events(lte=cutoff):
        if not store.is_visible(character_id, event_id=event.id, at=cutoff):
            continue
        participant_ids = {p.entity_id for p in event.participants}
        overlap = len(participant_ids & targets)
        if targets and overlap == 0:
            continue
        score = event.importance + 0.25 * overlap
        if decision.kind == "recall":
            score += 0.1
        score += 0.6 * _trigger_bonus(decision.query, f"{event.title}{event.summary}")
        score += 0.3 * _overlap(decision.query, f"{event.title}{event.summary}")
        scored.append(
            (
                score,
                Evidence(
                    kind="event",
                    ref_id=event.id,
                    text=f"{event.title}。{event.summary}"[:160],
                    chapter=event.chapter,
                    score=round(score, 3),
                ),
            )
        )

    for fact in store.facts(lte=cutoff):
        if not store.is_visible(character_id, fact_id=fact.id, at=cutoff):
            continue
        endpoints = {fact.source_id, fact.target_id}
        if targets and not (endpoints & targets):
            continue
        score = fact.weight * fact.confidence + (0.15 if endpoints & targets else 0)
        scored.append(
            (
                score,
                Evidence(
                    kind="fact",
                    ref_id=fact.id,
                    text=f"{store.entity_name(fact.source_id)}{_readable(fact.sign, fact.kind)}{store.entity_name(fact.target_id)}",
                    chapter=fact.valid_from,
                    score=round(score, 3),
                ),
            )
        )

    for scene in store.scenes(lte=cutoff):
        if not targets:
            continue
        roster = {entry.entity_id for entry in scene.roster}
        if not (roster & targets):
            continue
        if character_id not in roster:
            continue
        visible = [
            event for event in store.events_in_scene(scene.id, lte=cutoff)
            if store.is_visible(character_id, event_id=event.id, at=cutoff)
            and ({p.entity_id for p in event.participants} & targets)
        ]
        if not visible:
            # A scene is not a room. If the only events in it are invisible to
            # this character, the scene text must not become a memory backdoor.
            continue
        place = scene.location or "那里"
        text = f"我记得那天在{place}。" + "；".join(event.title for event in visible[:3])
        score = 0.55 if decision.kind == "recall" else 0.2
        scored.append(
            (
                score,
                Evidence(
                    kind="episode",
                    ref_id=scene.id,
                    text=text[:160],
                    chapter=scene.chapter,
                    score=score,
                ),
            )
        )

    scored.sort(key=lambda pair: (-pair[0], pair[1].chapter))
    if relation_rows:
        relation_rows.sort(key=lambda pair: (-pair[0], pair[1].chapter))
        # A relationship path is the primary evidence for a relation question;
        # direct event/fact rows remain as supporting context after it.
        scored = relation_rows[:4] + scored
    return [evidence for _score, evidence in scored[:limit]]


def _resolve_targets(store: InMemoryGraphStore, names: tuple[str, ...]) -> set[str]:
    targets: set[str] = set()
    for name in names:
        entity = store.find_entity(name)
        if entity:
            targets.add(entity.id)
    return targets


def _state(store: InMemoryGraphStore, character_id: str, cutoff: int) -> CognitionState:
    from ..project import project

    return project(store, character_id, cutoff)


def _trigger_bonus(query: str, text: str) -> float:
    """A verb in the question that is also a known trigger marks the right event."""
    from ..extract.events import TRIGGERS

    return float(sum(1 for verb in TRIGGERS if verb in (query or "") and verb in (text or "")))


def _overlap(query: str, text: str) -> float:
    """Character-bigram overlap. Cheap, language-agnostic, no embedding call."""
    cleaned = "".join(ch for ch in (query or "") if "\u4e00" <= ch <= "\u9fff")
    if len(cleaned) < 2:
        return 0.0
    grams = {cleaned[i : i + 2] for i in range(len(cleaned) - 1)}
    hits = sum(1 for gram in grams if gram in (text or ""))
    return hits / len(grams)


def _readable(sign: int, kind: str) -> str:
    if sign < 0:
        return {"敌对": "结下仇怨", "信任": "不再信任", "归属": "生了离心", "尊重": "心存芥蒂"}.get(
            kind, "关系恶化"
        )
    if sign > 0:
        return {"恩情": "欠了人情", "亲近": "更为亲近", "师徒": "结为师徒", "承诺": "许下承诺"}.get(
            kind, "关系缓和"
        )
    return "关系平淡"
