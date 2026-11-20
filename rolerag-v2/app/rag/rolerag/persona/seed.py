"""Persona seed: structured drives instead of adjectives.

Every entry must carry a quote and a chapter. Anything the text cannot support
is dropped, because an unsupported trait is exactly what makes a character read
like a résumé.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from ..models import Pattern
from ..store import InMemoryGraphStore
from .patterns import collect_utterances


@dataclass
class Drive:
    want: str
    fear: str
    taboo: str
    evidence_chapter: int
    quote: str


@dataclass
class ProfileOverlay:
    """Upstream Nuwa profile projected into RoleRAG's structured persona.

    The overlay never becomes a story fact. It only supplies identity, drives,
    fears, speech notes and taboos; the graph still decides what this character
    has actually seen.
    """

    identity: str = ""
    traits: tuple[str, ...] = ()
    goals: tuple[str, ...] = ()
    fears: tuple[str, ...] = ()
    speech_style: tuple[str, ...] = ()
    anti_patterns: tuple[str, ...] = ()
    core_beliefs: tuple[str, ...] = ()
    decision_patterns: tuple[str, ...] = ()
    conversation_rules: tuple[str, ...] = ()
    knowledge_rules: tuple[str, ...] = ()
    relationships: tuple[str, ...] = ()
    known: tuple[str, ...] = ()
    unknown: tuple[str, ...] = ()
    evidence_count: int = 0


_PLACEHOLDER_MARKERS = ("证据未提供", "证据未披露", "不能补写", "无法确认", "证据不足")


def _clean_profile_text(text: str) -> str:
    pieces = [piece.strip() for piece in str(text or "").split("；") if piece.strip()]
    kept = [piece for piece in pieces if not any(marker in piece for marker in _PLACEHOLDER_MARKERS)]
    return "；".join(kept)


def _strings(value: object) -> tuple[str, ...]:
    if isinstance(value, str):
        return (value.strip(),) if value.strip() else ()
    if isinstance(value, (list, tuple)):
        items = tuple(str(item).strip() for item in value if str(item).strip())
        return tuple(item for item in items if not any(marker in item for marker in _PLACEHOLDER_MARKERS))
    return ()


def _relationship_strings(value: object) -> tuple[str, ...]:
    if isinstance(value, str):
        return _strings(value)
    if not isinstance(value, (list, tuple)):
        return ()
    rows: list[str] = []
    for item in value:
        if isinstance(item, dict):
            name = str(item.get("name") or item.get("target") or item.get("character") or "").strip()
            relation = str(item.get("relation") or item.get("description") or item.get("attitude") or "").strip()
            if not name and not relation:
                continue
            if name and relation:
                rows.append(f"{name}：{relation}")
            elif name:
                rows.append(name)
            elif relation:
                rows.append(relation)
        else:
            text = str(item).strip()
            if text:
                rows.append(text)
    return tuple(row for row in rows if not any(marker in row for marker in _PLACEHOLDER_MARKERS))


def overlay_from_profile(profile: dict | None) -> ProfileOverlay | None:
    if not profile:
        return None
    boundary = profile.get("knowledge_boundary") if isinstance(profile.get("knowledge_boundary"), dict) else {}
    return ProfileOverlay(
        identity=_clean_profile_text(profile.get("identity") or ""),
        traits=_strings(profile.get("personality")),
        goals=_strings(profile.get("goals")),
        fears=_strings(profile.get("fears")),
        speech_style=_strings(profile.get("speech_style")),
        anti_patterns=_strings(profile.get("anti_patterns")),
        core_beliefs=_strings(profile.get("core_beliefs")),
        decision_patterns=_strings(profile.get("decision_patterns")),
        conversation_rules=_strings(profile.get("conversation_rules")),
        knowledge_rules=_strings(boundary.get("rules")),
        relationships=_relationship_strings(profile.get("relationships")),
        known=_strings(boundary.get("known")),
        unknown=_strings(boundary.get("unknown")),
        evidence_count=int(profile.get("evidence_count") or 0),
    )


@dataclass
class PersonaSeed:
    character_id: str
    name: str
    identity: str = ""
    drives: list[Drive] = field(default_factory=list)
    judgement: list[str] = field(default_factory=list)
    patterns: list[Pattern] = field(default_factory=list)
    exemplars: list[str] = field(default_factory=list)
    address_map: dict[str, str] = field(default_factory=dict)
    overlay: ProfileOverlay | None = None

    def style_corpus(self) -> list[str]:
        return list(self.exemplars)


def build_seed(
    store: InMemoryGraphStore,
    character_id: str,
    cutoff: int,
    *,
    overlay: ProfileOverlay | None = None,
) -> PersonaSeed:
    entity = store.entity(character_id)
    if not entity:
        return PersonaSeed(
            character_id=character_id,
            name=character_id,
            overlay=overlay,
        )

    drives: list[Drive] = []
    # A belief is knowledge, not motivation. Knowing that A trusts or hates B
    # does not imply that this character wants to preserve the relationship,
    # fears losing it, or is forbidden to mention it. Motivations come only
    # from the explicit Nuwa overlay below.

    utterances = collect_utterances(store, character_id, cutoff)
    exemplars = [row.text for row in sorted(utterances, key=lambda r: -len(r.text))[:8]] or [entity.description]
    address_map = {other.name: other.name for other in store.entities() if other.type == "character"}

    overlay_drives: list[Drive] = []
    if overlay is not None:
        for index in range(max(len(overlay.goals), len(overlay.fears))):
            goal = overlay.goals[index] if index < len(overlay.goals) else "守住自己现在在意的东西"
            fear = overlay.fears[index] if index < len(overlay.fears) else "再次失去在意的东西"
            taboo = (
                overlay.anti_patterns[index]
                if index < len(overlay.anti_patterns)
                else "把没看见的事说成亲眼见过"
            )
            overlay_drives.append(
                Drive(
                    want=goal,
                    fear=fear,
                    taboo=taboo,
                    evidence_chapter=cutoff,
                    quote="（女娲画像）",
                )
            )

    return PersonaSeed(
        character_id=character_id,
        name=entity.name,
        identity=(overlay.identity if overlay and overlay.identity else entity.description),
        drives=overlay_drives + drives,
        judgement=["被追问动机时先反问", "不愿主动解释自己"] if entity.type == "character" else [],
        patterns=store.patterns(character_id),
        exemplars=[item for item in exemplars if item],
        address_map=address_map,
        overlay=overlay,
    )


def _relation_word(kind: str) -> str:
    return {
        "敌对": "仇怨",
        "信任": "信任",
        "归属": "归属",
        "尊重": "体面",
        "恩情": "情分",
        "亲近": "亲近",
        "师徒": "名分",
        "承诺": "承诺",
    }.get(kind, "关系")
