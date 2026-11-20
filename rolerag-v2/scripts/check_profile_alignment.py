"""Check the latest persona profile against its period evidence window."""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.storage.repositories.storyrole_repository import (
    get_character_period,
    get_persona_profile_for_period,
)
from app.storage.storyrole_alignment import check_profile_period_alignment


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--database", default="three_body_agent_v2")
    parser.add_argument("--owner-id", type=int, default=2)
    parser.add_argument("--character-id", type=int, default=1)
    parser.add_argument("--period-id", type=int, default=7)
    args = parser.parse_args()

    os.environ["POSTGRES_DATABASE"] = args.database
    period = get_character_period(period_id=args.period_id, owner_id=args.owner_id)
    profile = get_persona_profile_for_period(
        character_id=args.character_id, owner_id=args.owner_id, period_id=args.period_id,
    )
    report = check_profile_period_alignment(profile, period)
    report["database"] = args.database
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
