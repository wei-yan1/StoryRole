"""Query scope analysis (RoleRAG §3.4).

Before retrieving, each entity mentioned in the query is judged twice:

* ``familiar`` — can this character plausibly know this entity?
* ``level``    — is the mention specific (a person/place) or general (a theme)?

Everything out of scope is rejected *with a reason*, instead of being retrieved
and then talked around.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from ..models import Fact
from ..store import InMemoryGraphStore

_GENERAL_MARKERS = ("为什么", "怎么", "如何", "态度", "看法", "意义", "在意", "在乎", "感受", "想法")
_EXTERNAL_HINTS = ("阿波罗", "火箭", "手机", "电脑", "互联网", "股票", "总统", "联合国")


@dataclass(frozen=True)
class ScopedEntity:
    name: str
    entity_id: str | None
    familiar: bool
    level: str
    reason: str


@dataclass
class ScopeReport:
    entities: list[ScopedEntity] = field(default_factory=list)
    external_terms: list[str] = field(default_factory=list)
    has_in_scope: bool = True
    is_general: bool = False

    @property
    def all_out_of_scope(self) -> bool:
        return not self.has_in_scope


def known_entity_ids(store: InMemoryGraphStore, character_id: str, cutoff: int) -> set[str]:
    known = {character_id}
    for fact in store.facts(lte=cutoff):
        if store.is_visible(character_id, fact_id=fact.id, at=cutoff):
            known.update((fact.source_id, fact.target_id))
    for event in store.events(lte=cutoff):
        if store.is_visible(character_id, event_id=event.id, at=cutoff):
            known.update(participant.entity_id for participant in event.participants)
    for belief in store.beliefs(character_id, lte=cutoff):
        known.update((belief.subject_id, belief.target_id))
    return known


def analyze_scope(
    query: str,
    store: InMemoryGraphStore,
    character_id: str,
    cutoff: int,
    *,
    external_terms: list[str] | None = None,
) -> ScopeReport:
    known = known_entity_ids(store, character_id, cutoff)
    mentions = store.scan(query or "")

    seen: dict[str, ScopedEntity] = {}
    for entity_id, _position, surface in mentions:
        if entity_id in seen:
            continue
        entity = store.entity(entity_id)
        name = entity.name if entity else surface
        familiar = entity_id in known
        seen[entity_id] = ScopedEntity(
            name=name,
            entity_id=entity_id,
            familiar=familiar,
            level="specific",
            reason="角色可见的事实或事件中出现过" if familiar else "角色从未获得关于此人的任何可见路径",
        )

    external = [term for term in (external_terms or []) if term and term in (query or "")]
    if not external:
        external = [term for term in _EXTERNAL_HINTS if term in (query or "")]

    is_general = not seen and any(marker in (query or "") for marker in _GENERAL_MARKERS)
    has_in_scope = any(item.familiar for item in seen.values()) or (is_general and not external)

    return ScopeReport(
        entities=list(seen.values()),
        external_terms=external,
        has_in_scope=has_in_scope,
        is_general=is_general,
    )


def unknown_titles(state, limit: int = 3) -> list[str]:
    return [event.title for event in state.unknowns[:limit]]
