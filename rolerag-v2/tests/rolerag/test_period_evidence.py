"""Fail-closed period evidence selection."""
from __future__ import annotations

import pytest

from app.agents.storyrole.period_agent import (
    PeriodEvidenceUnavailable,
    evidence_for_period,
)


def _records() -> list[dict]:
    return [
        {"chunk_id": f"c{i}", "chapter": "序 章" if i < 25 else "三体III·死神永生",
         "text": f"record {i}"}
        for i in range(50)
    ]


def test_explicit_evidence_ids_are_used_without_fallback() -> None:
    records = _records()
    period = {"name": "新时期晚年时期", "evidence_ids": ["c40", "c41"]}
    selected = evidence_for_period(records, period)
    assert [item["chunk_id"] for item in selected] == ["c40", "c41"]


def test_empty_named_period_fails_closed_instead_of_first_40() -> None:
    records = _records()
    period = {"name": "新时期晚年时期", "evidence_ids": [], "keywords": [],
              "chapter_start": None, "chapter_end": None}
    with pytest.raises(PeriodEvidenceUnavailable):
        evidence_for_period(records, period)


def test_stale_evidence_ids_fail_closed() -> None:
    records = _records()
    period = {"name": "新时期晚年时期", "evidence_ids": ["missing"]}
    with pytest.raises(PeriodEvidenceUnavailable):
        evidence_for_period(records, period)


def test_full_period_may_still_bound_records() -> None:
    records = _records()
    period = {"name": "全时期", "evidence_ids": [], "keywords": [],
              "chapter_start": None, "chapter_end": None}
    selected = evidence_for_period(records, period)
    assert len(selected) == 40
    assert selected[0]["chunk_id"] == "c0"
