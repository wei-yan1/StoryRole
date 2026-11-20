"""Multi-turn settlement.

The difference between a chatbot and a character: after the conversation, the
world moved. A grudge said out loud becomes an event with an effect, a belief
and a new affect value; the next visit starts from there, not from the profile.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from ..extract.events import extract_events
from ..models import Belief, Effect, Event, Participant, RosterEntry, Scene, State
from ..persona.state import apply_deltas, decay_toward_baseline, deltas_for, detect_triggers
from ..store import InMemoryGraphStore

_PROMISE_MARKERS = ("我答应", "我会", "我一定", "等我")
_GRUDGE_KINDS = {"敌对", "信任", "归属", "尊重"}


@dataclass
class Settlement:
    triggers: list[str] = field(default_factory=list)
    deltas: dict[str, float] = field(default_factory=dict)
    event_id: str = ""
    belief_id: str = ""
    state: State | None = None


def settle(
    store: InMemoryGraphStore,
    character_id: str,
    cutoff: int,
    user_message: str,
    reply_text: str,
    *,
    thread_id: int | None = None,
) -> Settlement:
    triggers = detect_triggers(user_message) + detect_triggers(reply_text)
    deltas = deltas_for(triggers)

    old_state = store.state(character_id)
    new_state = apply_deltas(decay_toward_baseline(old_state), deltas)
    store.set_state(new_state)

    target = _first_other_entity(store, user_message, character_id)
    kind = "敌对" if any(trigger in {"骗子", "懦夫", "废物", "你算什么", "闭嘴"} for trigger in triggers) else "对话"
    effects = []
    if target and kind != "对话":
        effects.append(
            Effect(
                subject_id=character_id,
                target_id=target,
                kind=kind,
                sign=-1,
                delta=-0.05,
                reason=user_message[:40],
            )
        )

    event_id = f"{store.novel_id}:d{cutoff}.{len(store.events()) + 1:03d}"
    if thread_id is not None:
        event_id = f"{event_id}.t{int(thread_id)}"
    event = Event(
        id=event_id,
        novel_id=store.novel_id,
        scene_id="",
        chapter=cutoff,
        title=f"与来客的对话（{user_message[:12]}）",
        summary=reply_text[:80],
        importance=0.3,
        source="dialogue",
        thread_id=int(thread_id) if thread_id is not None else None,
        participants=tuple(
            [Participant(entity_id=character_id, role="actor", presence="active")]
            + (
                [Participant(entity_id=target, role="patient", presence="active")] if target else []
            )
        ),
        effects=tuple(effects),
    )
    store.add_event(event)

    belief_id = ""
    if target and any(marker in user_message for marker in _PROMISE_MARKERS):
        belief = Belief(
            character_id=character_id,
            subject_id=character_id,
            target_id=target,
            kind="承诺",
            sign=1,
            certainty=0.7,
            since_chapter=cutoff,
            source="dialogue",
            channel="told",
        )
        store.add_belief(belief)
        belief_id = f"belief:{cutoff}:{belief.kind}"

    claimed = _claim_beliefs(store, character_id, cutoff, user_message)
    if claimed and not belief_id:
        belief_id = f"belief:{cutoff}:{claimed[0].kind}"

    return Settlement(
        triggers=triggers,
        deltas=deltas,
        event_id=event_id,
        belief_id=belief_id,
        state=new_state,
    )


def _first_other_entity(store: InMemoryGraphStore, text: str, character_id: str) -> str | None:
    for entity_id, _position, _surface in store.scan(text or ""):
        if entity_id != character_id and store.entity(entity_id) and store.entity(entity_id).type == "character":
            return entity_id
    return None


def _claim_beliefs(
    store: InMemoryGraphStore,
    character_id: str,
    cutoff: int,
    message: str,
) -> list[Belief]:
    """A claim made in conversation is a belief, not a fact.

    Running the same event extractor over the user's sentence lets a lie enter
    memory without ever touching the world graph. The character can be wrong,
    and the graph stays truthful.
    """
    roster = tuple(
        RosterEntry(entity_id=entity_id, presence="active")
        for entity_id, _position, _surface in store.scan(message or "")
    )
    if len(roster) < 2:
        return []
    scene = Scene(
        id=f"{store.novel_id}:d{cutoff}.claim",
        novel_id=store.novel_id,
        chapter=cutoff,
        index=0,
        title="对话",
        text=message,
        roster=roster,
    )
    claims: list[Belief] = []
    for event in extract_events(scene, store, novel_id=store.novel_id):
        for effect in event.effects:
            belief = Belief(
                character_id=character_id,
                subject_id=effect.subject_id,
                target_id=effect.target_id,
                kind=effect.kind,
                sign=effect.sign,
                certainty=0.6,
                since_chapter=cutoff,
                source="dialogue",
                channel="told",
            )
            store.add_belief(belief)
            claims.append(belief)
    return claims
