"""Lazy episodic layer.

Scenes are stored raw; the first-person memory is rendered on demand, only for
scenes the character was actually in. That keeps the offline build cheap and
avoids pre-summarising 500 chapters that most conversations never touch.
"""

from __future__ import annotations

from dataclasses import dataclass

from .models import Scene
from .store import InMemoryGraphStore


@dataclass(frozen=True)
class Episode:
    scene_id: str
    chapter: int
    text: str


def episode_line(scene: Scene) -> str:
    place = scene.location or "那里"
    return f"我记得那天在{place}。{scene.title.rstrip('。')}。"


def render_episode(
    store: InMemoryGraphStore,
    character_id: str,
    scene_id: str,
    *,
    llm=None,
) -> Episode | None:
    scene = next((row for row in store.scenes() if row.id == scene_id), None)
    if scene is None:
        return None
    if character_id not in {entry.entity_id for entry in scene.roster}:
        return None
    if llm is not None:
        prompt = (
            "把下面这段场景压缩成两三句第一人称记忆。只写你看到、听到、做过的事；"
            "不要写别人的心理，不要解释，不要总结。\n" + scene.text[:600]
        )
        text = llm.complete(prompt).strip()
    else:
        text = episode_line(scene)
    return Episode(scene_id=scene.id, chapter=scene.chapter, text=text)
