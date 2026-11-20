"""End-to-end: build the synthetic book, ask every question, score KBF."""

from __future__ import annotations

from app.rag.rolerag.chat import chat_turn
from app.rag.rolerag.demo import DEMO_QUESTIONS, build_demo
from app.rag.rolerag.eval import REFUSE, Case, evaluate


def test_demo_build_has_a_complete_graph() -> None:
    outcome = build_demo()
    result = outcome.result
    assert result.chapters == 6
    assert len(outcome.store.chapters()) == 6
    assert result.scenes >= 8
    assert result.entities == 7
    assert result.events >= 9
    assert result.facts >= 4
    assert result.visibility_rows >= 50
    assert outcome.patterns >= 3


def test_every_demo_question_routes_as_designed() -> None:
    outcome = build_demo()
    store = outcome.store
    expected = ["recall", "probe", "recall", "recall", "reject", "reject", "reject"]
    actual = []
    for character_name, cutoff, question in DEMO_QUESTIONS:
        entity = store.find_entity(character_name)
        reply = chat_turn(store, entity.id, cutoff, question, external_terms=["阿波罗"])
        actual.append(reply.route)
        if cutoff < 4 and "赵七" in question:
            assert "斩" not in reply.text
    assert actual == expected


def test_all_demo_answers_pass_style_acceptance() -> None:
    outcome = build_demo()
    store = outcome.store
    for character_name, cutoff, question in DEMO_QUESTIONS:
        entity = store.find_entity(character_name)
        reply = chat_turn(store, entity.id, cutoff, question, external_terms=["阿波罗"])
        assert reply.style.ok, (question, reply.style.failures, reply.text)


def test_demo_kbf_is_perfect_on_the_curated_set() -> None:
    outcome = build_demo()
    store = outcome.store
    lu = store.find_entity("陆知微")
    cases = [
        Case("你还记得沈砚被逐出山门那天吗", "逐", True, 6),
        Case("沈砚为什么斩了赵七", "赵七", True, 6),
        Case("玄真辱沈砚那件事，你听说了吗", "辱", True, 6),
        Case("苏晚后来原谅沈砚了吗", "原谅", True, 6),
        Case("沈砚为什么斩了赵七", "", False, 2),
        Case("赵七后来怎么样了", "", False, 2),
        Case("你怎么看阿波罗登月", "", False, 6),
    ]

    def answer(case: Case) -> str:
        reply = chat_turn(store, lu.id, case.cutoff, case.question, external_terms=["阿波罗"])
        return REFUSE if reply.route == "reject" else reply.text

    report = evaluate(cases, answer)
    assert report.kbf == 1.0
