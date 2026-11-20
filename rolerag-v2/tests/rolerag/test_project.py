"""Projection tests: the boundary is the product."""

from __future__ import annotations

from app.rag.rolerag.build import build_all
from app.rag.rolerag.demo import DEMO_HINTS, DEMO_ORGS, build_demo
from app.rag.rolerag.project import ProjectionOptions, project

PRIVATE = """第一章 密谋

沈砚隐瞒苏晚。
"""

PRIVATE_HINTS = [
    {"name": "沈砚", "type": "character", "aliases": ["沈师兄"]},
    {"name": "苏晚", "type": "character", "aliases": ["苏师姐"]},
    {"name": "玄真", "type": "character", "aliases": ["师父"]},
]


def test_character_does_not_know_a_person_who_has_not_appeared() -> None:
    outcome = build_demo()
    store = outcome.store
    lu = store.find_entity("陆知微")
    early = project(store, lu.id, 2)
    assert all(belief.target != "赵七" for belief in early.beliefs)
    late = project(store, lu.id, 6)
    assert any(belief.target == "赵七" for belief in late.beliefs)


def test_fact_is_not_visible_before_its_chapter() -> None:
    outcome = build_demo()
    store = outcome.store
    lu = store.find_entity("陆知微")
    early = project(store, lu.id, 3)
    late = project(store, lu.id, 4)
    assert not any(item.chapter >= 4 for item in early.unknowns)
    assert any(belief.target == "赵七" for belief in late.beliefs)


def test_unseen_event_is_recorded_but_never_becomes_a_belief() -> None:
    outcome = build_all(PRIVATE, novel_id="private", hints=PRIVATE_HINTS, org_members=DEMO_ORGS)
    store = outcome.store
    xuan = store.find_entity("玄真")
    state = project(store, xuan.id, 1)
    assert state.beliefs == []
    assert len(state.unknowns) >= 1


def test_projection_is_pure_with_respect_to_cutoff() -> None:
    outcome = build_demo()
    store = outcome.store
    lu = store.find_entity("陆知微")
    first = project(store, lu.id, 4)
    second = project(store, lu.id, 4)
    assert first == second
    assert first.cutoff == 4
    assert first.stats["facts_in_window"] <= len(store.facts())


def test_options_threshold_controls_unknowns() -> None:
    outcome = build_all(PRIVATE, novel_id="private", hints=PRIVATE_HINTS)
    store = outcome.store
    xuan = store.find_entity("玄真")
    strict = project(store, xuan.id, 1, options=ProjectionOptions(unknown_importance=0.99))
    loose = project(store, xuan.id, 1, options=ProjectionOptions(unknown_importance=0.1))
    assert strict.unknowns == []
    assert loose.unknowns
