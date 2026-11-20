"""Persona layer: style is measured, affect is a state machine."""

from __future__ import annotations

from app.rag.rolerag.demo import build_demo
from app.rag.rolerag.models import State
from app.rag.rolerag.persona.emotion import gate, select_pattern
from app.rag.rolerag.persona.state import apply_deltas, decay_toward_baseline, deltas_for
from app.rag.rolerag.persona.style import StyleProfile, check, fingerprint, measure
from app.rag.rolerag.chat.settle import settle


def test_fingerprint_and_measure_agree_on_same_corpus() -> None:
    corpus = ["他年纪小。", "我认过。", "你问这个做什么。"]
    profile = fingerprint(corpus)
    stats = measure("。".join(corpus) + "。")
    assert stats["median_chars"] == profile.median_chars
    assert stats["question_rate"] == profile.question_rate


def test_long_summary_style_is_rejected_with_instruction() -> None:
    profile = StyleProfile(median_chars=4.0, question_rate=0.0, exclamation_rate=0.0)
    report = check(profile, "总而言之，这件事我们需要从长计议，首先应当考虑各方立场。")
    assert not report.ok
    assert any("句长" in failure for failure in report.failures)
    assert "压到" in report.instruction


def test_unknown_terms_are_caught_as_leakage() -> None:
    profile = StyleProfile()
    report = check(profile, "阿波罗登月那年我见过他。", unknown_terms=("阿波罗",))
    assert not report.ok
    assert any("越界" in failure for failure in report.failures)


def test_affect_deltas_clamp_at_one() -> None:
    state = State(character_id="x", hostility=0.95)
    updated = apply_deltas(state, {"hostility": 0.3})
    assert updated.hostility == 1.0
    assert updated.version == state.version + 1


def test_decay_moves_toward_baseline() -> None:
    state = State(character_id="x", hostility=0.9)
    decayed = decay_toward_baseline(state, rate=0.5)
    assert 0.1 < decayed.hostility < 0.9


def test_emotion_gate_detects_a_jump_and_selects_a_pattern() -> None:
    from app.rag.rolerag.project import project

    outcome = build_demo()
    store = outcome.store
    lu = store.find_entity("陆知微")
    state = project(store, lu.id, 6)
    emotion, jump = gate(state, "你个骗子")
    assert emotion == "怒"
    assert jump
    pattern = select_pattern(state.patterns, emotion)
    assert pattern is not None


def test_settlement_persists_affect_and_event() -> None:
    outcome = build_demo()
    store = outcome.store
    lu = store.find_entity("陆知微")
    before = store.state(lu.id).hostility
    result = settle(store, lu.id, 6, "你个骗子", "……")
    assert result.event_id
    assert store.state(lu.id).hostility > before
    assert any(event.source == "dialogue" for event in store.events())


def test_promise_becomes_a_belief() -> None:
    outcome = build_demo()
    store = outcome.store
    lu = store.find_entity("陆知微")
    settle(store, lu.id, 6, "我会替沈砚保密", "……")
    beliefs = store.beliefs(lu.id)
    assert any(belief.kind == "承诺" for belief in beliefs)
    assert deltas_for(["欠"]) == {"indebtedness": 0.12}
