"""The parts that make it an agent loop rather than a retrieval demo."""

from __future__ import annotations

from pathlib import Path

from app.rag.rolerag.build import build_all
from app.rag.rolerag.chat import LLMRenderer, chat_turn, settle
from app.rag.rolerag.demo import build_demo
from app.rag.rolerag.eval import REFUSE, evaluate, generate_cases
from app.rag.rolerag.llm import FakeLLM
from app.rag.rolerag.persona.style import StyleProfile
from app.rag.rolerag.project import project
from app.rag.rolerag.service import RoleRAGService, engine_enabled
from app.rag.rolerag.snapshot import dump, load, save


def test_llm_renderer_uses_prompt_and_rewrite_instruction() -> None:
    outcome = build_demo()
    store = outcome.store
    lu = store.find_entity("陆知微")
    llm = FakeLLM(
        responses=[
            "总而言之，那段往事非常复杂，我们需要从多个角度来理解它。",
            "那天我记得。玄真逐沈砚。",
        ]
    )
    renderer = LLMRenderer(llm)
    reply = chat_turn(
        store, lu.id, 6, "你还记得沈砚被逐出山门那天吗",
        renderer=renderer,
        style_profile=StyleProfile(median_chars=5.0, question_rate=0.0, exclamation_rate=0.0),
    )
    assert reply.attempts == 2
    assert len(llm.calls) == 2
    assert "必须修改" in llm.calls[1]
    assert reply.style.ok
    assert "总而言之" not in reply.text
    assert reply.messages[0]["role"] == "system"


def test_settle_turns_a_spoken_claim_into_a_belief_not_a_fact() -> None:
    outcome = build_demo()
    store = outcome.store
    lu = store.find_entity("陆知微")
    shen = store.find_entity("沈砚")
    zhao = store.find_entity("赵七")
    facts_before = len(store.facts())
    settle(store, lu.id, 6, "沈砚杀了赵七", "……")
    assert len(store.facts()) == facts_before
    beliefs = [b for b in store.beliefs(lu.id) if b.target_id == zhao.id and b.subject_id == shen.id]
    assert beliefs and beliefs[-1].channel == "told"
    state = project(store, lu.id, 6)
    assert any(b.target == "赵七" and b.channel == "told" for b in state.beliefs)


def test_unseen_trigger_is_refused_even_when_both_people_are_known() -> None:
    outcome = build_demo()
    store = outcome.store
    xuan = store.find_entity("玄真")
    reply = chat_turn(store, xuan.id, 6, "你还记得沈砚隐瞒陆知微那件事吗")
    assert reply.route == "reject"
    assert "隐瞒" not in reply.text


def test_snapshot_roundtrip_preserves_projection(tmp_path: Path) -> None:
    outcome = build_demo()
    store = outcome.store
    lu = store.find_entity("陆知微")
    path = save(store, tmp_path / "graph.json")
    loaded = load(path)
    assert dump(loaded)["novel_id"] == store.novel_id
    before = project(store, lu.id, 6)
    after = project(loaded, lu.id, 6)
    assert before.beliefs == after.beliefs
    assert len(loaded.visibility(lu.id)) == len(store.visibility(lu.id))
    assert len(loaded.chapters()) == len(store.chapters())
    assert loaded.chapters()[0].title == store.chapters()[0].title
    assert loaded.scenes()[0].roster == store.scenes()[0].roster


def test_service_facade_and_engine_flag(monkeypatch) -> None:
    outcome = build_demo()
    service = RoleRAGService(outcome.store, outcome.cutoff)
    reply = service.chat("陆知微", "沈砚为什么斩了赵七")
    assert reply.route == "probe"
    bundle = service.context("陆知微", "沈砚为什么斩了赵七")
    assert bundle.as_dict()["route"] == "probe"
    assert bundle.evidence
    monkeypatch.setenv("STORYROLE_RETRIEVAL_ENGINE", "rolerag")
    assert engine_enabled()
    monkeypatch.setenv("STORYROLE_RETRIEVAL_ENGINE", "legacy")
    assert not engine_enabled()


def test_auto_generated_kbf_cases_are_consistent() -> None:
    outcome = build_demo()
    store = outcome.store
    lu = store.find_entity("陆知微")
    cases = generate_cases(store, lu.id)
    assert len(cases) == len(store.facts())
    report = evaluate(
        cases,
        lambda case: (
            REFUSE
            if chat_turn(store, lu.id, case.cutoff, case.question).route == "reject"
            else chat_turn(store, lu.id, case.cutoff, case.question).text
        ),
    )
    assert report.krf_accuracy >= 0.8


def test_private_build_still_respects_secret_marker() -> None:
    text = "第一章 密谋\n\n沈砚隐瞒苏晚。"
    hints = [
        {"name": "沈砚", "type": "character"},
        {"name": "苏晚", "type": "character"},
        {"name": "玄真", "type": "character"},
    ]
    outcome = build_all(text, novel_id="secret", hints=hints, org_members={"青霄门": ["沈砚", "苏晚", "玄真"]})
    xuan = outcome.store.find_entity("玄真")
    state = project(outcome.store, xuan.id, 1)
    assert state.beliefs == []
    assert state.unknowns


def test_prompt_does_not_list_unknown_event_titles() -> None:
    outcome = build_demo()
    store = outcome.store
    xuan = store.find_entity("玄真")
    reply = chat_turn(store, xuan.id, 6, "你还记得沈砚隐瞒陆知微那件事吗")
    system = reply.messages[0]["content"]
    assert "隐瞒" not in system
    assert "你就是他" in system
