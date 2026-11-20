"""Façade for callers outside the RAG package.

The old API and agent code keep working; switching engines is one env flag:

    STORYROLE_RETRIEVAL_ENGINE=rolerag

Default stays ``legacy`` until the new path is validated on a real book.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any

from .build import BuildOutcome, build_all
from .chat import Reply, chat_turn, guard_unseen_trigger, settle
from .models import CognitionState, Entity, Evidence
from .project import project
from .retrieval import analyze_scope, route
from .retrieval.subgraph import retrieve
from .store import InMemoryGraphStore


def engine_mode() -> str:
    return os.getenv("STORYROLE_RETRIEVAL_ENGINE", "legacy").strip().lower()


def engine_enabled() -> bool:
    return engine_mode() in {"rolerag", "new", "v2"}


@dataclass
class ContextBundle:
    """What an external agent needs, without knowing the package internals."""

    character: Entity
    cutoff: int
    query: str
    scope: Any
    decision: Any
    evidence: list[Evidence]
    beliefs: list[Any]
    unknowns: list[Any]
    affect: dict[str, float]

    def as_dict(self) -> dict:
        return {
            "character": self.character.name,
            "cutoff": self.cutoff,
            "route": self.decision.kind,
            "evidence": [item.text for item in self.evidence],
            "beliefs": [
                {"subject": b.subject, "target": b.target, "kind": b.kind, "certainty": b.certainty}
                for b in self.beliefs
            ],
            "unknowns": [item.title for item in self.unknowns],
            "affect": self.affect,
        }


class RoleRAGService:
    def __init__(self, store: InMemoryGraphStore, cutoff: int) -> None:
        self.store = store
        self.cutoff = cutoff

    @classmethod
    def from_text(cls, text: str, *, novel_id: str, hints: list[dict] | None = None,
                  org_members: dict[str, set[str]] | None = None,
                  arbiter=None, embed=None) -> "RoleRAGService":
        outcome: BuildOutcome = build_all(
            text, novel_id=novel_id, hints=hints, org_members=org_members,
            arbiter=arbiter, embed=embed,
        )
        return cls(outcome.store, outcome.cutoff)

    def character(self, name: str) -> Entity:
        entity = self.store.find_entity(name)
        if not entity:
            raise KeyError(f"unknown character: {name}")
        return entity

    def cognition(self, name: str, cutoff: int | None = None) -> CognitionState:
        return project(self.store, self.character(name).id, cutoff or self.cutoff)

    def chat(self, name: str, message: str, cutoff: int | None = None) -> Reply:
        return chat_turn(self.store, self.character(name).id, cutoff or self.cutoff, message)

    def settle(self, name: str, message: str, reply: str, cutoff: int | None = None):
        return settle(self.store, self.character(name).id, cutoff or self.cutoff, message, reply)

    def context(self, name: str, query: str, cutoff: int | None = None) -> ContextBundle:
        entity = self.character(name)
        cutoff = cutoff or self.cutoff
        state = project(self.store, entity.id, cutoff)
        scope = analyze_scope(query, self.store, entity.id, cutoff)
        decision = route(query, scope)
        evidence = retrieve(self.store, entity.id, cutoff, decision)
        decision, evidence = guard_unseen_trigger(query, decision, evidence, store=self.store)
        return ContextBundle(
            character=entity,
            cutoff=cutoff,
            query=query,
            scope=scope,
            decision=decision,
            evidence=evidence,
            beliefs=state.beliefs,
            unknowns=state.unknowns,
            affect=state.affect,
        )
