"""Build RoleRAG from the processed real corpus (chunks grouped by chapter index).

The raw three_body.txt is a table of contents plus prose without in-body chapter
headings, so it cannot be split by the normal chapter parser. The processed
chunks carry `book` and `section_index`, which is the chapter axis we need.

Usage:
    python scripts/audit_real_corpus.py --book 三体I
    python scripts/audit_real_corpus.py --book all
"""

from __future__ import annotations

import argparse
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.rag.rolerag.build import build_all  # noqa: E402

CHUNKS = Path(r"D:\AgentCode\two\data\processed\rag_chunks\novel_chunks.jsonl")
ORDER = ["三体I", "三体II·黑暗森林", "三体III·死神永生"]

CAST = [
    {"name": "汪淼", "aliases": ["汪教授"], "type": "character"},
    {"name": "史强", "aliases": ["大史", "史队长"], "type": "character"},
    {"name": "叶文洁", "type": "character"},
    {"name": "常伟思", "aliases": ["常将军"], "type": "character"},
    {"name": "申玉菲", "type": "character"},
    {"name": "潘寒", "type": "character"},
    {"name": "杨卫宁", "type": "character"},
    {"name": "雷志成", "type": "character"},
    {"name": "伊文斯", "type": "character"},
    {"name": "三体文明", "type": "org"},
    {"name": "ETO", "type": "org"},
    {"name": "红岸基地", "type": "place"},
]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--book", default="三体I", choices=ORDER + ["all"])
    parser.add_argument("--hints", default="cast", choices=["cast", "none"])
    args = parser.parse_args()

    rows = [__import__("json").loads(line) for line in CHUNKS.read_text(encoding="utf-8").splitlines()]
    if args.book != "all":
        rows = [row for row in rows if row["metadata"]["book"] == args.book]
    rows.sort(key=lambda row: (ORDER.index(row["metadata"]["book"]), row["metadata"]["section_index"], row["metadata"]["chunk_index"]))

    groups: dict[tuple[str, int], list[str]] = defaultdict(list)
    for row in rows:
        groups[(row["metadata"]["book"], row["metadata"]["section_index"])].append(row["text"])

    blocks = []
    for ordinal, key in enumerate(sorted(groups, key=lambda k: (ORDER.index(k[0]), k[1])), start=1):
        book, section = key
        body = "\n".join(groups[key])
        blocks.append(f"第{_cn(ordinal)}章 {book} 第{section}节\n{body}")
    text = "\n\n".join(blocks)

    print(f"book={args.book} chars={len(text)} sections={len(groups)}")
    hints = CAST if args.hints == "cast" else None
    outcome = build_all(text, novel_id="three_body", hints=hints)
    store = outcome.store
    print(f"chapters={len(store.chapters())} scenes={len(store.scenes())} entities={len(store.entities())} "
          f"events={len(store.events())} facts={len(store.facts())} visibility={store.count_visibility()}")

    kinds = Counter(row.type for row in store.entities())
    print(f"entity kinds: {dict(kinds)}")
    print("top entities:")
    for row in store.entities()[:20]:
        print(f"  {row.name:<8} {row.type:<10} mentions={row.mention_count} aliases={list(row.aliases)[:5]}")

    print("fact samples:")
    for row in store.facts()[:10]:
        print(f"  ch{row.valid_from} {store.entity_name(row.source_id)} -{row.kind}-> "
              f"{store.entity_name(row.target_id)} sign={row.sign}")

    print("event samples:")
    for row in store.events()[:12]:
        print(f"  ch{row.chapter} {row.title}: {row.summary[:50]}")
    wang = store.find_entity("汪淼")
    if wang:
        from app.rag.rolerag.project import project

        state = project(store, wang.id, outcome.cutoff)
        print(f"汪淼@ch{outcome.cutoff}: beliefs={len(state.beliefs)} unknowns={len(state.unknowns)} "
              f"open_loops={len(state.open_loops)}")
        for belief in state.beliefs[:8]:
            print(f"  belief: {belief.subject} -{belief.kind}-> {belief.target} "
                  f"sign={belief.sign} certainty={belief.certainty}")
    return 0


def _cn(value: int) -> str:
    digits = "零一二三四五六七八九"
    if value < 10:
        return digits[value]
    if value < 20:
        return "十" + (digits[value - 10] if value > 10 else "")
    if value < 100:
        return digits[value // 10] + "十" + (digits[value % 10] if value % 10 else "")
    return str(value)


if __name__ == "__main__":
    raise SystemExit(main())
