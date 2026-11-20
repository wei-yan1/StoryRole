"""Projection: one world graph -> one character's cognition at a cutoff.

Pure function. No database handle, no LLM, no clock. Everything it needs is
passed in through the store, which makes it the most testable part of the
architecture and the one that decides whether the character can be wrong.
"""

from __future__ import annotations

from dataclasses import dataclass

from .models import (
    BeliefView,
    CognitionState,
    Fact,
    OpenLoop,
    UnknownEvent,
)
from .store import InMemoryGraphStore


@dataclass(frozen=True)
class ProjectionOptions:
    unknown_importance: float = 0.55
    recent_scenes: int = 8


_CHANNEL = {
    "direct": "observed",
    "witness": "observed",
    "told": "told",
    "org": "heard",
    "common": "heard",
}


def project(
    store: InMemoryGraphStore,
    character_id: str,
    cutoff: int,
    *,
    options: ProjectionOptions | None = None,
) -> CognitionState:
    options = options or ProjectionOptions()

    facts = [f for f in store.facts(lte=cutoff) if _valid_at(f, cutoff)]
    beliefs_by_key: dict[tuple[str, str, str], BeliefView] = {}

    for fact in facts:
        route = store.best_route(character_id, fact_id=fact.id, at=cutoff)
        if route is None:
            # He has no path to this fact. He does not get a low-confidence
            # version of it: inventing content for unseen events is leakage,
            # not nuance. Unseen *important events* are recorded separately as
            # unknowns for the orchestrator, never as beliefs.
            continue
        view = _view(
            store,
            fact,
            certainty=float(fact.confidence) * float(route.certainty),
            channel=_CHANNEL[route.route],
        )
        beliefs_by_key[(view.subject_id, view.target_id, view.kind)] = view

    # Things the user told him override the graph: a lie is a belief.
    for belief in store.beliefs(character_id, lte=cutoff):
        if belief.retracted:
            continue
        beliefs_by_key[(belief.subject_id, belief.target_id, belief.kind)] = BeliefView(
            fact_id=f"belief:{belief.since_chapter}:{belief.kind}",
            subject_id=belief.subject_id,
            subject=store.entity_name(belief.subject_id),
            target_id=belief.target_id,
            target=store.entity_name(belief.target_id),
            kind=belief.kind,
            sign=belief.sign,
            certainty=belief.certainty,
            channel=belief.channel,
            since_chapter=belief.since_chapter,
        )

    unknowns: list[UnknownEvent] = []
    for event in store.events(lte=cutoff):
        if store.is_visible(character_id, event_id=event.id, at=cutoff):
            continue
        if event.importance >= options.unknown_importance and event.source == "novel":
            unknowns.append(
                UnknownEvent(
                    event_id=event.id,
                    title=event.title,
                    chapter=event.chapter,
                    importance=event.importance,
                    reason="尚无任何可见路径（未在场、未被告知、非公共事件）",
                )
            )

    open_loops = _open_loops(store, beliefs_by_key.values(), facts, cutoff)

    state = store.state(character_id)
    scenes = [s for s in store.scenes(lte=cutoff) if any(
        entry.entity_id == character_id for entry in s.roster
    )][-options.recent_scenes :]

    emotions = store.emotions(character_id, lte=cutoff)

    return CognitionState(
        character_id=character_id,
        cutoff=cutoff,
        beliefs=sorted(beliefs_by_key.values(), key=lambda b: (-b.certainty, b.subject)),
        unknowns=sorted(unknowns, key=lambda u: (-u.importance, u.chapter)),
        open_loops=open_loops,
        affect=state.as_dict(),
        patterns=store.patterns(character_id),
        emotion=emotions[-1] if emotions else None,
        scene_ids=[scene.id for scene in scenes],
        stats={
            "facts_in_window": len(facts),
            "visible_facts": sum(
                1 for f in facts if store.is_visible(character_id, fact_id=f.id, at=cutoff)
            ),
            "events_in_window": len(store.events(lte=cutoff)),
            "scenes": len(scenes),
        },
    )


def _valid_at(fact: Fact, cutoff: int) -> bool:
    if fact.valid_from > cutoff:
        return False
    return fact.valid_to is None or fact.valid_to <= cutoff


def _view(store: InMemoryGraphStore, fact: Fact, *, certainty: float, channel: str) -> BeliefView:
    return BeliefView(
        fact_id=fact.id,
        subject_id=fact.source_id,
        subject=store.entity_name(fact.source_id),
        target_id=fact.target_id,
        target=store.entity_name(fact.target_id),
        kind=fact.kind,
        sign=fact.sign,
        certainty=round(certainty, 2),
        channel=channel,
        since_chapter=fact.valid_from,
    )


def _open_loops(
    store: InMemoryGraphStore,
    beliefs: object,
    facts: list[Fact],
    cutoff: int,
) -> list[OpenLoop]:
    loops: list[OpenLoop] = []
    for belief in beliefs:  # type: ignore[assignment]
        if belief.sign >= 0:
            continue
        repaired = any(
            fact.source_id == belief.subject_id
            and fact.target_id == belief.target_id
            and fact.sign > 0
            and fact.valid_from > belief.since_chapter
            and fact.valid_from <= cutoff
            for fact in facts
        )
        if not repaired:
            loops.append(
                OpenLoop(
                    kind="grudge",
                    target_name=belief.target,
                    description=f"{belief.subject}与{belief.target}的{belief.kind}裂痕尚未修复",
                    event_id=belief.fact_id,
                )
            )
    return loops
