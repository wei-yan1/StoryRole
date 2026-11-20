"""Evidence-window alignment between period and persona profile."""
from __future__ import annotations

from app.storage.storyrole_alignment import check_profile_period_alignment


def _profile(evidence_ids: list[str], name: str = "新时期晚年时期", period_id: int = 7) -> dict:
    return {
        "id": 25,
        "version": 24,
        "status": "ready",
        "profile": {"period_id": period_id, "period_name": name},
        "evidence": [{"chunk_id": item} for item in evidence_ids],
    }


def test_profile_inside_period_window_passes() -> None:
    period = {"id": 7, "name": "新时期晚年时期", "evidence_ids": ["c1", "c2", "c3"]}
    report = check_profile_period_alignment(_profile(["c1", "c2", "c3"]), period)
    assert report["ok"] is True
    assert report["period_evidence_coverage"] == 1.0


def test_profile_with_early_evidence_fails_named_late_period() -> None:
    period = {"id": 7, "name": "新时期晚年时期", "evidence_ids": ["late1", "late2"]}
    report = check_profile_period_alignment(_profile(["early1", "early2"]), period)
    assert report["ok"] is False
    assert "profile_evidence_outside_period_window" in report["issues"]


def test_named_period_without_evidence_window_fails() -> None:
    period = {"id": 7, "name": "新时期晚年时期", "evidence_ids": []}
    report = check_profile_period_alignment(_profile(["c1"]), period)
    assert report["ok"] is False
    assert "period_has_no_evidence_window" in report["issues"]


def test_full_period_is_the_only_empty_window_exception() -> None:
    period = {"id": 1, "name": "全时期", "evidence_ids": []}
    report = check_profile_period_alignment(_profile(["c1"], name="全时期", period_id=1), period)
    assert report["ok"] is True
