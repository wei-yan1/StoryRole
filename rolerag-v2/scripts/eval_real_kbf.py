"""Automatic KBF over the real Three-Body Book I graph.

Every character × every fact produces one positive/negative case, depending on
whether that character has a visibility path to the fact. With 30 characters
and 5 facts this is ~150 cases, enough to catch one-sided collapse.

TemplateRenderer is used on purpose: this measures boundary behaviour, not prose.
"""

from __future__ import annotations

import json
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.rag.rolerag.build import build_all  # noqa: E402
from app.rag.rolerag.chat.orchestrator import chat_turn  # noqa: E402
from app.rag.rolerag.eval.generate import generate_cases  # noqa: E402
from app.rag.rolerag.eval.kbf import REFUSE, evaluate  # noqa: E402
from scripts.audit_real_corpus import CAST, CHUNKS, ORDER  # noqa: E402


def main() -> int:
    rows = [json.loads(line) for line in CHUNKS.read_text(encoding="utf-8").splitlines()]
    rows = [row for row in rows if row["metadata"]["book"] == "三体I"]
    rows.sort(key=lambda row: (row["metadata"]["section_index"], row["metadata"]["chunk_index"]))
    groups: dict[int, list[str]] = defaultdict(list)
    for row in rows:
        groups[row["metadata"]["section_index"]].append(row["text"])
    text = "\n\n".join(
        f"第{_cn(i)}章 第{section}节\n" + "\n".join(groups[section])
        for i, section in enumerate(sorted(groups), start=1)
    )

    outcome = build_all(text, novel_id="three_body", hints=CAST)
    store = outcome.store
    characters = [row for row in store.entities() if row.type == "character"]

    total = {"ok": 0, "all": 0}
    by_char = []
    for entity in characters:
        cases = generate_cases(store, entity.id)
        if not cases:
            continue

        def answer(case, character=entity):
            reply = chat_turn(store, character.id, case.cutoff, case.question)
            return REFUSE if reply.route == "reject" else reply.text

        report = evaluate(cases, answer)
        total["ok"] += sum(1 for row in report.results if row.correct)
        total["all"] += len(report.results)
        by_char.append((entity.name, report))

    print(f"cases={total['all']} correct={total['ok']} accuracy={total['ok']/max(1, total['all']):.2f}")
    for name, report in by_char[:12]:
        kr = f"{report.kr_accuracy:.2f}" if report.n_kr else "n/a"
        print(f"  {name:<8} n={len(report.results):<3} KRF={report.krf_accuracy:.2f} KR={kr} KBF={report.kbf:.2f}")
    failures = [(name, row) for name, report in by_char for row in report.failures()]
    print(f"failed_cases={len(failures)}")
    for name, row in failures[:8]:
        print(f"  FAIL {name}: {row.case.question} expected={row.case.expected!r} got={row.prediction[:40]!r}")
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
