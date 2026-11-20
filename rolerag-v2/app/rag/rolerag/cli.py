"""Command line entry points.

    python -m app.rag.rolerag.cli demo
    python -m app.rag.rolerag.cli eval
"""

from __future__ import annotations

import argparse
import sys

from .chat import chat_turn
from .demo import DEMO_QUESTIONS, build_demo
from .eval import REFUSE, Case, evaluate, generate_cases, kbf
from .project import project
from .persona.state import describe


def _demo() -> int:
    outcome = build_demo()
    store = outcome.store
    result = outcome.result
    print(f"[build] chapters={result.chapters} scenes={result.scenes} entities={result.entities} "
          f"events={result.events} facts={result.facts} visibility={result.visibility_rows}")
    print(f"[persona] patterns={outcome.patterns} emotions={outcome.emotions} cutoff={outcome.cutoff}")
    for group in result.alias_groups:
        if group.aliases:
            print(f"[alias] {group.canonical} <- {', '.join(group.aliases)}")

    for character_name, cutoff, question in DEMO_QUESTIONS:
        entity = store.find_entity(character_name)
        if not entity:
            print(f"[skip] no entity {character_name}")
            continue
        state = project(store, entity.id, cutoff)
        reply = chat_turn(store, entity.id, cutoff, question, external_terms=["阿波罗"])
        print()
        print(f"--- {character_name} @ ch{cutoff} | {question}")
        print(f"    beliefs={len(state.beliefs)} unknown_events={len(state.unknowns)} "
              f"open_loops={len(state.open_loops)} affect={describe(state.affect)}")
        print(f"    route={reply.route} style_ok={reply.style.ok} attempts={reply.attempts} "
              f"score={reply.style.score}")
        print(f"    A: {reply.text}")
    return 0


def _eval() -> int:
    outcome = build_demo()
    store = outcome.store
    lu = store.find_entity("陆知微")
    if not lu:
        print("missing 陆知微", file=sys.stderr)
        return 1

    cases = [
        Case("你还记得沈砚被逐出山门那天吗", "逐", True, 6),
        Case("沈砚为什么斩了赵七", "赵七", True, 6),
        Case("玄真辱沈砚那件事，你听说了吗", "辱", True, 6),
        Case("苏晚后来原谅沈砚了吗", "原谅", True, 6),
        Case("沈砚为什么斩了赵七", "", False, 2),
        Case("赵七后来怎么样了", "", False, 2),
        Case("你怎么看阿波罗登月", "", False, 6),
    ]

    def answer(case: Case) -> str:
        reply = chat_turn(
            store, lu.id, case.cutoff or outcome.cutoff, case.question, external_terms=["阿波罗"]
        )
        return REFUSE if reply.route == "reject" else reply.text

    report = evaluate(cases, answer)
    for row in report.results:
        mark = "ok " if row.correct else "FAIL"
        print(f"[{mark}] visible={row.case.visible} ch{row.case.cutoff} {row.case.question} -> {row.prediction}")
    print(f"KRF={report.krf_accuracy:.2f} (n={report.n_krf}) "
          f"KR={report.kr_accuracy:.2f} (n={report.n_kr}) KBF={report.kbf:.2f}")
    return 0


def _auto() -> int:
    outcome = build_demo()
    store = outcome.store
    totals = {"krf": (0, 0), "kr": (0, 0)}
    for entity in [row for row in store.entities() if row.type == "character"]:
        cases = generate_cases(store, entity.id)
        if not cases:
            continue

        def answer(case: Case, character=entity) -> str:
            reply = chat_turn(store, character.id, case.cutoff, case.question)
            return REFUSE if reply.route == "reject" else reply.text

        report = evaluate(cases, answer)
        totals["krf"] = (
            totals["krf"][0] + sum(1 for row in report.results if row.case.visible and row.correct),
            totals["krf"][1] + report.n_krf,
        )
        totals["kr"] = (
            totals["kr"][0] + sum(1 for row in report.results if not row.case.visible and row.correct),
            totals["kr"][1] + report.n_kr,
        )
        kr_text = f"{report.kr_accuracy:.2f}" if report.n_kr else "n/a"
        print(f"[{entity.name}] n={len(cases)} KRF={report.krf_accuracy:.2f} "
              f"KR={kr_text} KBF={report.kbf:.2f}")
        for row in report.failures():
            print(f"    FAIL {row.case.question} -> {row.prediction} ({row.detail})")

    krf_correct, krf_total = totals["krf"]
    kr_correct, kr_total = totals["kr"]
    krf_accuracy = krf_correct / krf_total if krf_total else 0.0
    kr_accuracy = kr_correct / kr_total if kr_total else 0.0
    print(f"[aggregate] KRF={krf_accuracy:.2f} (n={krf_total}) KR={kr_accuracy:.2f} (n={kr_total}) "
          f"KBF={kbf(krf_accuracy, kr_accuracy, krf_total, kr_total):.2f}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="rolerag")
    parser.add_argument("command", choices=["demo", "eval", "auto"], nargs="?", default="demo")
    args = parser.parse_args(argv)
    if args.command == "eval":
        return _eval()
    if args.command == "auto":
        return _auto()
    return _demo()


if __name__ == "__main__":
    raise SystemExit(main())
