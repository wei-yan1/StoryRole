"""Unit tests for the offline construction path."""

from __future__ import annotations

from app.rag.rolerag.demo import DEMO_HINTS, SAMPLE_NOVEL, build_demo
from app.rag.rolerag.extract import split_chapters, split_sentences
from app.rag.rolerag.extract.aliases import normalize_candidates
from app.rag.rolerag.extract.entities import collect_candidates


def test_split_chapters_assigns_ordinals_and_preface() -> None:
    text = "前言部分。\n第一章 起\n正文一。\n第二章 承\n正文二。"
    chapters = split_chapters(text)
    assert [chapter.ordinal for chapter in chapters] == [0, 1, 2]
    assert chapters[0].title == "前言"
    assert chapters[1].title.startswith("第一章")


def test_split_sentences_keeps_closing_quote() -> None:
    rows = split_sentences("苏晚道：“他救过你。”陆知微点头。")
    assert rows[0] == "苏晚道：“他救过你。”"
    assert rows[1] == "陆知微点头。"


def test_alias_normalisation_collapses_role_names() -> None:
    candidates = collect_candidates(split_chapters(SAMPLE_NOVEL), hints=DEMO_HINTS)
    groups = normalize_candidates(candidates)
    by_name = {group.canonical: group for group in groups}
    assert "沈砚" in by_name
    assert "沈师兄" in by_name["沈砚"].aliases
    assert "师父" in by_name["玄真"].aliases
    assert len(groups) == 7


def test_alias_normalisation_limits_arbiter_calls() -> None:
    candidates = collect_candidates(split_chapters(SAMPLE_NOVEL), hints=DEMO_HINTS)
    calls = {"count": 0}

    def arbiter(left, right) -> bool:
        calls["count"] += 1
        return False

    groups = normalize_candidates(candidates, arbiter=arbiter, top_k=5)
    assert groups
    # Rule pre-merge handles the obvious pairs; the vector stage costs at most
    # one arbiter call per candidate per neighbour.
    assert calls["count"] <= len(candidates) * 5


def test_speech_attribution_prefers_longest_verb_and_trims_leftovers() -> None:
    from app.rag.rolerag.extract.entities import _clean_name, _SPEECH

    text = "汪淼说道：“好。”叶文洁回答：“不。”他接着说：“走。”"
    names = [_clean_name(match.group("name")) for match in _SPEECH.finditer(text)]
    assert "汪淼" in names
    assert "叶文洁" in names
    assert _clean_name("叶文洁回") == "叶文洁"
    assert _clean_name("汪淼耳边") == "汪淼"
    assert _clean_name("宽容地笑") is None
    assert _clean_name("的计算机") is None
    assert _clean_name("指着史强") == "史强"


def test_llm_arbiter_merges_names_rules_keep_apart() -> None:
    from app.rag.rolerag.extract.aliases import llm_arbiter, normalize_candidates
    from app.rag.rolerag.extract.entities import EntityCandidate
    from app.rag.rolerag.llm import FakeLLM

    left = EntityCandidate(name="沈砚", type="character", mention_count=3)
    right = EntityCandidate(name="沈公子", type="character", mention_count=2)
    groups = normalize_candidates(
        [left, right], top_k=1, arbiter=llm_arbiter(FakeLLM(['{"same": true}']))
    )
    assert len(groups) == 1
    assert groups[0].canonical == "沈砚"
    assert "沈公子" in groups[0].aliases


def test_event_has_actor_patient_and_effect() -> None:
    outcome = build_demo()
    store = outcome.store
    shen = store.find_entity("沈砚")
    xuan = store.find_entity("玄真")
    target = next(event for event in store.events() if event.title == "玄真逐沈砚")
    effect = target.effects[0]
    assert effect.subject_id == xuan.id
    assert effect.target_id == shen.id
    assert effect.sign == -1


def test_trigger_inside_quotes_is_not_an_event() -> None:
    outcome = build_demo()
    store = outcome.store
    quoted_events = [
        event
        for event in store.events()
        if "救过你" in event.summary and event.effects
    ]
    assert quoted_events == []


def test_visibility_routes_cover_all_five_paths() -> None:
    outcome = build_demo()
    store = outcome.store
    lu = store.find_entity("陆知微")
    zhao_event = next(event for event in store.events() if event.title == "沈砚斩赵七")
    assert any(
        row.route == "common" and row.character_id == lu.id
        for row in store.visibility(lu.id)
        if row.event_id == zhao_event.id
    )
    shame_event = next(event for event in store.events() if event.title == "玄真辱沈砚")
    assert any(
        row.route == "org" and row.character_id == lu.id
        for row in store.visibility(lu.id)
        if row.event_id == shame_event.id
    )
    routes = {row.route for row in store.visibility(lu.id)}
    assert {"direct", "witness", "org", "common", "told"} <= routes
