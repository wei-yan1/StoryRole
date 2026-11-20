"""Domain models for RoleRAG.

Ids are strings everywhere so an offline builder can write a JSON snapshot and
PostgreSQL can store the same graph without changing call sites.

The five-tuple at the centre of the semantic layer follows REVERIEMEM's SPOCV
shape: ``(subject, predicate, object, cause, visibility)``. ``cause`` is not
decoration — narrative reasoning needs *why* an event happened, not only that
it did.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

Presence = Literal["active", "silent", "referenced"]
Route = Literal["direct", "witness", "org", "common", "told"]


@dataclass(frozen=True)
class Chapter:
    ordinal: int
    title: str
    text: str


@dataclass(frozen=True)
class Entity:
    id: str
    name: str
    type: str  # character | org | place | item | concept
    aliases: tuple[str, ...] = ()
    description: str = ""
    first_chapter: int = 0
    last_chapter: int = 0
    mention_count: int = 0


@dataclass(frozen=True)
class RosterEntry:
    entity_id: str
    presence: Presence


@dataclass(frozen=True)
class Scene:
    id: str
    novel_id: str
    chapter: int
    index: int
    title: str
    text: str = ""
    location: str = ""
    atmosphere: str = ""
    roster: tuple[RosterEntry, ...] = ()


@dataclass(frozen=True)
class Participant:
    entity_id: str
    role: str  # actor | patient | witness
    presence: Presence = "active"


@dataclass(frozen=True)
class Effect:
    """A relation change caused by an event. The only legal write path."""

    subject_id: str
    target_id: str
    kind: str
    sign: int
    delta: float
    reason: str = ""


@dataclass(frozen=True)
class Event:
    id: str
    novel_id: str
    scene_id: str
    chapter: int
    title: str
    summary: str = ""
    importance: float = 0.5
    cause: str = ""
    participants: tuple[Participant, ...] = ()
    effects: tuple[Effect, ...] = ()
    source: str = "novel"  # novel | dialogue
    thread_id: int | None = None


@dataclass(frozen=True)
class Fact:
    """SPOC without the visibility set; visibility lives in its own rows."""

    id: str
    novel_id: str
    source_id: str
    target_id: str
    kind: str
    sign: int
    weight: float
    valid_from: int
    valid_to: int | None = None
    cause: str = ""
    caused_by_event: str | None = None
    confidence: float = 0.5


@dataclass(frozen=True)
class Visibility:
    character_id: str
    route: Route
    from_chapter: int
    certainty: float = 1.0
    event_id: str | None = None
    fact_id: str | None = None

    def covers(self, *, event_id: str | None = None, fact_id: str | None = None, at: int) -> bool:
        if self.from_chapter > at:
            return False
        if event_id is not None and self.event_id == event_id:
            return True
        if fact_id is not None and self.fact_id == fact_id:
            return True
        return False


@dataclass(frozen=True)
class Belief:
    character_id: str
    subject_id: str
    target_id: str
    kind: str
    sign: int
    certainty: float
    since_chapter: int
    channel: str
    source: str = "dialogue"
    retracted: bool = False


@dataclass(frozen=True)
class BeliefView:
    """A belief after projection, carrying display names for prompting."""

    fact_id: str
    subject_id: str
    subject: str
    target_id: str
    target: str
    kind: str
    sign: int
    certainty: float
    channel: str
    since_chapter: int = 0


@dataclass(frozen=True)
class UnknownEvent:
    event_id: str
    title: str
    chapter: int
    importance: float
    reason: str


@dataclass(frozen=True)
class OpenLoop:
    kind: str  # grudge | debt | promise
    target_name: str
    description: str
    event_id: str | None = None


@dataclass(frozen=True)
class Pattern:
    id: str
    character_id: str
    description: str
    excerpts: tuple[str, ...] = ()
    tags: tuple[str, ...] = ()
    centroid: tuple[float, float] = (0.0, 0.0)


@dataclass(frozen=True)
class EmotionTurn:
    character_id: str
    emotion: str
    intensity: float
    trigger: str
    intent: str
    chapter: int
    seq: int


@dataclass
class State:
    """Six scalars. Deliberately not a description of a mood."""

    character_id: str
    alertness: float = 0.5
    fatigue: float = 0.3
    indebtedness: float = 0.0
    shame: float = 0.0
    interest: float = 0.5
    hostility: float = 0.1
    version: int = 0

    _FIELDS = ("alertness", "fatigue", "indebtedness", "shame", "interest", "hostility")

    def as_dict(self) -> dict[str, float]:
        return {name: float(getattr(self, name)) for name in self._FIELDS}

    def clamped(self) -> "State":
        return State(
            character_id=self.character_id,
            **{name: min(1.0, max(0.0, float(getattr(self, name)))) for name in self._FIELDS},
            version=self.version,
        )


@dataclass
class CognitionState:
    character_id: str
    cutoff: int
    beliefs: list[BeliefView] = field(default_factory=list)
    unknowns: list[UnknownEvent] = field(default_factory=list)
    open_loops: list[OpenLoop] = field(default_factory=list)
    affect: dict[str, float] = field(default_factory=dict)
    patterns: list[Pattern] = field(default_factory=list)
    emotion: EmotionTurn | None = None
    scene_ids: list[str] = field(default_factory=list)
    stats: dict[str, int] = field(default_factory=dict)

    def summary(self) -> str:
        return (
            f"{self.character_id}@{self.cutoff}: "
            f"{len(self.beliefs)} beliefs, {len(self.unknowns)} unknowns, "
            f"{len(self.open_loops)} open loops"
        )


@dataclass(frozen=True)
class Evidence:
    kind: str  # fact | event | scene | episode | belief
    ref_id: str
    text: str
    chapter: int
    score: float = 0.0
