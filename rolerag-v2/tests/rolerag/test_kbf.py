"""KBF metric tests. Both failure directions must be punished."""

from __future__ import annotations

from app.rag.rolerag.eval import REFUSE, Case, evaluate, kbf


def test_perfect_scores_give_one() -> None:
    assert kbf(1.0, 1.0, 4, 3) == 1.0


def test_zero_accuracy_collapses_the_metric() -> None:
    assert kbf(0.0, 1.0, 2, 2) == 0.0
    assert kbf(1.0, 0.0, 2, 2) == 0.0


def test_weighted_harmonic_mean() -> None:
    value = kbf(0.5, 1.0, 2, 2)
    assert abs(value - 2 / 3) < 1e-9


def test_side_without_samples_imposes_no_constraint() -> None:
    assert kbf(0.8, 0.0, 4, 0) == 0.8
    assert kbf(0.0, 0.9, 0, 3) == 0.9
    assert kbf(0.0, 0.0, 0, 0) == 0.0


def test_evaluate_separates_refusal_from_recall() -> None:
    cases = [
        Case("q1", "甲", True, 6),
        Case("q2", "乙", True, 6),
        Case("q3", "", False, 2),
        Case("q4", "", False, 2),
    ]

    def answer(case: Case) -> str:
        if case.question == "q1":
            return "甲在这里"
        if case.question == "q2":
            return "不对"
        return REFUSE

    report = evaluate(cases, answer)
    assert report.krf_accuracy == 0.5
    assert report.kr_accuracy == 1.0
    assert report.n_krf == 2 and report.n_kr == 2
    assert report.kbf < 1.0
    assert len(report.failures()) == 1


def test_refusing_a_visible_question_is_a_krf_failure() -> None:
    report = evaluate([Case("q", "甲", True, 6)], lambda case: REFUSE)
    assert report.krf_accuracy == 0.0
    assert report.kr_accuracy == 0.0
