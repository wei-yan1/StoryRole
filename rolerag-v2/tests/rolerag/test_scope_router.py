"""Scope and routing tests."""

from __future__ import annotations

from app.rag.rolerag.demo import build_demo
from app.rag.rolerag.retrieval import analyze_scope, route


def _setup():
    outcome = build_demo()
    return outcome.store, outcome.store.find_entity("陆知微")


def test_external_topic_is_out_of_scope() -> None:
    store, lu = _setup()
    scope = analyze_scope("你怎么看阿波罗登月", store, lu.id, 6, external_terms=["阿波罗"])
    decision = route("你怎么看阿波罗登月", scope)
    assert not scope.has_in_scope
    assert decision.kind == "reject"
    assert "阿波罗" in decision.reason


def test_future_character_is_out_of_scope_early() -> None:
    store, lu = _setup()
    query = "赵七后来怎么样了"
    scope = analyze_scope(query, store, lu.id, 2)
    assert any(item.name == "赵七" and not item.familiar for item in scope.entities)
    assert route(query, scope).kind == "reject"


def test_known_character_probe_routes_to_subgraph() -> None:
    store, lu = _setup()
    query = "沈砚为什么斩了赵七"
    scope = analyze_scope(query, store, lu.id, 6, external_terms=["阿波罗"])
    decision = route(query, scope)
    assert scope.has_in_scope
    assert decision.kind == "probe"
    assert "沈砚" in decision.entities


def test_recall_marker_beats_stance() -> None:
    store, lu = _setup()
    query = "你还记得沈砚被逐出山门那天吗"
    scope = analyze_scope(query, store, lu.id, 6)
    assert route(query, scope).kind == "recall"


def test_bare_action_question_is_event_lookup() -> None:
    store, lu = _setup()
    query = "玄真辱沈砚"
    scope = analyze_scope(query, store, lu.id, 6)
    assert route(query, scope).kind == "recall"


def test_general_question_is_stance() -> None:
    store, lu = _setup()
    query = "师父是个怎样的人"
    scope = analyze_scope(query, store, lu.id, 6)
    assert route(query, scope).kind == "stance"
