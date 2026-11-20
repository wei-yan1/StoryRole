"""One entry point that builds a whole book: graph + personas."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from .extract import BuildResult, build_graph
from .extract.aliases import Arbiter, Vector
from .models import State
from .persona.patterns import build_emotions, build_patterns, collect_utterances
from .store import InMemoryGraphStore


@dataclass
class BuildOutcome:
    store: InMemoryGraphStore
    result: BuildResult
    cutoff: int
    patterns: int = 0
    emotions: int = 0


def build_all(
    text: str,
    *,
    novel_id: str = "demo",
    hints: list[dict] | None = None,
    org_members: dict[str, set[str]] | None = None,
    arbiter: Arbiter | None = None,
    embed: Callable[[str], Vector] | None = None,
    fact_llm=None,
) -> BuildOutcome:
    store = InMemoryGraphStore(novel_id)
    result = build_graph(
        text, store, novel_id=novel_id, hints=hints, org_members=org_members,
        arbiter=arbiter, embed=embed, fact_llm=fact_llm,
    )
    cutoff = max((scene.chapter for scene in store.scenes()), default=0)
    patterns, emotions = apply_personas(store, cutoff)
    return BuildOutcome(
        store=store,
        result=result,
        cutoff=cutoff,
        patterns=patterns,
        emotions=emotions,
    )


def apply_personas(store: InMemoryGraphStore, cutoff: int) -> tuple[int, int]:
    """Build behaviour patterns and emotion transitions for every character."""
    patterns = 0
    emotions = 0
    for entity in store.entities():
        if entity.type != "character":
            continue
        store.set_state(State(character_id=entity.id))
        utterances = collect_utterances(store, entity.id, cutoff)
        if not utterances:
            continue
        for pattern in build_patterns(entity.id, utterances):
            store.add_pattern(pattern)
            patterns += 1
        for turn in build_emotions(entity.id, utterances):
            store.add_emotion(turn)
            emotions += 1
    return patterns, emotions
