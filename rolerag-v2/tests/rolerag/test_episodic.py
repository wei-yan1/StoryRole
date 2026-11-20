"""Lazy episodic memory: only scenes the character was actually in."""

from __future__ import annotations

from app.rag.rolerag.demo import build_demo
from app.rag.rolerag.episodic import episode_line, render_episode


def test_episode_is_first_person_and_scene_bound() -> None:
    outcome = build_demo()
    store = outcome.store
    scene = next(row for row in store.scenes() if row.chapter == 1)
    line = episode_line(scene)
    assert line.startswith("我记得那天在")
    lu = store.find_entity("陆知微")
    zhao = store.find_entity("赵七")
    assert render_episode(store, lu.id, scene.id) is not None
    assert render_episode(store, zhao.id, scene.id) is None


def test_episode_can_be_summarised_by_a_model() -> None:
    from app.rag.rolerag.llm import FakeLLM

    outcome = build_demo()
    store = outcome.store
    lu = store.find_entity("陆知微")
    scene = next(row for row in store.scenes() if row.chapter == 1)
    llm = FakeLLM(responses=["那天在下雨，我跪在青石上。"])
    episode = render_episode(store, lu.id, scene.id, llm=llm)
    assert episode is not None
    assert episode.text == "那天在下雨，我跪在青石上。"
