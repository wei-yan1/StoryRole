"""Data alignment checks between a persona profile and its declared period."""
from __future__ import annotations

from typing import Any

_ALL_PERIOD_NAMES = {"全时期", "全书时期", "全书"}


def check_profile_period_alignment(
    profile_row: dict[str, Any] | None,
    period: dict[str, Any] | None,
) -> dict[str, Any]:
    """Return a deterministic alignment report for one profile/period pair.

    This is intentionally evidence-based, not name-based: a profile that says
    "新时期晚年时期" while all its evidence comes from "序 章" must fail even
    though the display name matches.
    """
    profile_row = profile_row or {}
    period = period or {}
    profile = profile_row.get("profile") or {}
    period_name = str(period.get("name") or "")
    profile_name = str(profile.get("period_name") or "")
    period_id = period.get("id")
    profile_period_id = profile.get("period_id")

    issues: list[str] = []
    if period_id is not None and profile_period_id is not None and int(profile_period_id) != int(period_id):
        issues.append("profile_period_id_mismatch")
    if period_name and profile_name and profile_name != period_name:
        issues.append("profile_period_name_mismatch")

    period_ids = {str(item) for item in (period.get("evidence_ids") or []) if str(item)}
    profile_ids = {
        str(item.get("chunk_id"))
        for item in (profile_row.get("evidence") or [])
        if isinstance(item, dict) and item.get("chunk_id")
    }
    overlap = len(period_ids & profile_ids)
    coverage = round(overlap / len(period_ids), 4) if period_ids else 0.0

    if period_ids:
        if not profile_ids:
            issues.append("profile_has_no_evidence")
        elif coverage < 0.5:
            issues.append("profile_evidence_outside_period_window")
    elif period_name not in _ALL_PERIOD_NAMES:
        # A named period must carry an evidence window. "全时期" is the only
        # deliberate exception where a broad record set is allowed.
        issues.append("period_has_no_evidence_window")

    return {
        "ok": not issues,
        "issues": issues,
        "period_id": period_id,
        "period_name": period_name,
        "profile_id": profile_row.get("id"),
        "profile_version": profile_row.get("version"),
        "profile_status": profile_row.get("status"),
        "profile_evidence_count": len(profile_ids),
        "period_evidence_count": len(period_ids),
        "evidence_overlap": overlap,
        "period_evidence_coverage": coverage,
    }
