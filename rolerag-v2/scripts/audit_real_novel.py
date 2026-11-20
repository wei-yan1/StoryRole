"""Audit RoleRAG extraction on the real Three-Body corpus in data/raw.

Read-only: prints chapter/scene/entity/event statistics and a sample of each.
"""

from __future__ import annotations

import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.rag.rolerag.extract import split_chapters  # noqa: E402

CORPUS = Path(r"D:\AgentCode\two\data\raw\three_body_characters\three_body.txt")


def main() -> int:
    text = CORPUS.read_text(encoding="utf-8")
    chapters = split_chapters(text)
    print(f"chars={len(text)} chapters={len(chapters)}")
    for row in chapters[:12]:
        print(f"  ch{row.ordinal:03d} {row.title!r} len={len(row.text)}")
    print(f"  ... last: ch{chapters[-1].ordinal} {chapters[-1].title!r} len={len(chapters[-1].text)}")
    sizes = Counter(len(row.text) // 1000 for row in chapters)
    print(f"  size buckets (k chars): {dict(sorted(sizes.items()))}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
