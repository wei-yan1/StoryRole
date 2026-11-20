"""KBF evaluation (REVERIEMEM definition).

Two accuracies, one harmonic mean:

* KRF — the question is answerable inside the character's boundary
* KR  — the question is *not* answerable, and the character must refuse

A model that refuses everything scores 1.0 on KR and 0 on KRF; a model that
never refuses scores the reverse. Only KBF punishes both, which is why it is the
metric this project optimises.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

REFUSE = "REFUSE"


def harmonic(left: float, right: float, weight_left: float = 1.0, weight_right: float = 1.0) -> float:
    if left <= 0 or right <= 0:
        return 0.0
    return (weight_left + weight_right) / (weight_left / left + weight_right / right)


def kbf(krf_accuracy: float, kr_accuracy: float, n_krf: int, n_kr: int) -> float:
    # A side with no samples imposes no constraint; returning 0 would punish a
    # character simply because his slice happened to contain only positives.
    if n_krf == 0 and n_kr == 0:
        return 0.0
    if n_krf == 0:
        return kr_accuracy
    if n_kr == 0:
        return krf_accuracy
    return harmonic(krf_accuracy, kr_accuracy, float(n_krf), float(n_kr))


@dataclass
class Case:
    question: str
    expected: str
    visible: bool
    cutoff: int = 0
    tag: str = ""


@dataclass
class CaseResult:
    case: Case
    prediction: str
    correct: bool
    detail: str = ""


@dataclass
class EvalReport:
    results: list[CaseResult] = field(default_factory=list)
    krf_accuracy: float = 0.0
    kr_accuracy: float = 0.0
    kbf: float = 0.0
    n_krf: int = 0
    n_kr: int = 0

    def failures(self) -> list[CaseResult]:
        return [row for row in self.results if not row.correct]


def evaluate(cases: list[Case], answer: Callable[[Case], str]) -> EvalReport:
    results: list[CaseResult] = []
    for case in cases:
        prediction = answer(case)
        if case.visible:
            correct = case.expected in prediction if prediction != REFUSE else False
            detail = "" if correct else f"期望包含 {case.expected}"
        else:
            correct = prediction == REFUSE
            detail = "" if correct else "应当明确拒答"
        results.append(CaseResult(case=case, prediction=prediction, correct=correct, detail=detail))

    krf_cases = [r for r in results if r.case.visible]
    kr_cases = [r for r in results if not r.case.visible]
    krf_accuracy = _ratio(krf_cases)
    kr_accuracy = _ratio(kr_cases)
    return EvalReport(
        results=results,
        krf_accuracy=krf_accuracy,
        kr_accuracy=kr_accuracy,
        kbf=kbf(krf_accuracy, kr_accuracy, len(krf_cases), len(kr_cases)),
        n_krf=len(krf_cases),
        n_kr=len(kr_cases),
    )


def _ratio(rows: list[CaseResult]) -> float:
    if not rows:
        return 0.0
    return sum(1 for row in rows if row.correct) / len(rows)
