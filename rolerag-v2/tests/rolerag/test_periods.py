from app.rag.rolerag.demo import build_demo
from app.rag.rolerag.periods import clear_cache, resolve_period_cutoff
from app.rag.rolerag.runtime import RoleRAGRuntime


def test_explicit_bounds_win() -> None:
    outcome = build_demo()
    runtime = RoleRAGRuntime(outcome.store, outcome.cutoff)
    clear_cache()
    result = resolve_period_cutoff(runtime, {"chapter_start": "第一章", "chapter_end": "第二章"})
    assert result.cutoff == 2
    assert result.source == "explicit_bounds"


def test_period_analysis_prologue_maps_to_first_chapter() -> None:
    outcome = build_demo()
    runtime = RoleRAGRuntime(outcome.store, outcome.cutoff)
    clear_cache()
    result = resolve_period_cutoff(
        runtime,
        {"name": "普通学者时期"},
        period_analysis={"periods": [{"name": "前座面壁者时期：玩世不恭的普通学者", "chapter_start": "序 章", "chapter_end": "序 章"}]},
    )
    assert result.cutoff == 1
    assert result.source == "period_analysis"


def test_missing_bounds_never_default_to_whole_book() -> None:
    outcome = build_demo()
    runtime = RoleRAGRuntime(outcome.store, outcome.cutoff)
    clear_cache()
    result = resolve_period_cutoff(runtime, {"name": "没有依据的时期"})
    assert result.cutoff < runtime.cutoff
    assert result.cutoff >= 1
    assert result.source in {"period_terms", "conservative_min"}


def test_whole_book_is_explicit() -> None:
    outcome = build_demo()
    runtime = RoleRAGRuntime(outcome.store, outcome.cutoff)
    clear_cache()
    result = resolve_period_cutoff(runtime, {"name": "全时期"})
    assert result.cutoff == runtime.cutoff
    assert result.source == "whole_book"
