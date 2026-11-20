"""Automatic KBF case generation from the graph itself.

Each fact becomes one question at the chapter it happens:

* visible  -> the answer must mention the object
* invisible -> the answer must refuse

This is not a human-annotated benchmark. It is a consistency check: the same
visibility rows that build the projection must also predict what can be asked.
"""

from __future__ import annotations

from ..models import CognitionState, Fact
from ..project import project
from ..store import InMemoryGraphStore
from .kbf import Case


def generate_cases(
    store: InMemoryGraphStore,
    character_id: str,
    *,
    cutoff: int | None = None,
) -> list[Case]:
    cases: list[Case] = []
    states: dict[int, CognitionState] = {}

    def belief_keys(at: int) -> set[tuple[str, str, str]]:
        if at not in states:
            states[at] = project(store, character_id, at)
        return {(b.subject_id, b.target_id, b.kind) for b in states[at].beliefs}

    for fact in store.facts(lte=cutoff):
        event = store.event(fact.caused_by_event) if fact.caused_by_event else None
        subject = store.entity_name(fact.source_id)
        target = store.entity_name(fact.target_id)
        question = (
            f"你还记得{event.title}那件事吗"
            if event
            else f"你还记得{subject}和{target}之间那件事吗"
        )
        key = (fact.source_id, fact.target_id, fact.kind)
        # A later duplicate of an already-known relation is answerable: the
        # character remembers the earlier instance even if this fact row has no
        # direct visibility row of its own.
        visible = key in belief_keys(fact.valid_from) or store.is_visible(
            character_id, fact_id=fact.id, at=fact.valid_from
        )
        cases.append(
            Case(
                question=question,
                expected=target if visible else "",
                visible=visible,
                cutoff=fact.valid_from,
                tag=f"fact:{fact.kind}",
            )
        )
    return cases


def coverage(state: CognitionState) -> dict[str, int]:
    return {
        "beliefs": len(state.beliefs),
        "unknowns": len(state.unknowns),
        "open_loops": len(state.open_loops),
        "scenes": len(state.scene_ids),
    }
