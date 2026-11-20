"""Small blind comparison: RoleRAG vs a flat whole-text RAG baseline.

The baseline intentionally behaves like the old retrieval: keyword-overlap over
scene text, no chapter cutoff, no visibility projection, full scene handed to
the model. Pair order is shuffled; labels live only in the key file.
"""

from __future__ import annotations

import json
import os
import random
import sys
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
load_dotenv(ROOT.parent / ".env")

from app.rag.rolerag.chat.orchestrator import LLMRenderer, chat_turn  # noqa: E402
from app.rag.rolerag.demo import build_demo  # noqa: E402
from app.rag.rolerag.llm import OpenAICompatLLM  # noqa: E402

PAIRS = [
    ("陆知微", 2, "沈砚为什么斩了赵七"),
    ("玄真", 6, "你还记得沈砚隐瞒陆知微那件事吗"),
    ("陆知微", 6, "你还记得沈砚被逐出山门那天吗"),
    ("陆知微", 2, "赵七后来怎么样了"),
    ("陆知微", 6, "你怎么看阿波罗登月"),
]


def _flat_context(store, query: str, limit: int = 3) -> str:
    cleaned = "".join(ch for ch in query if "\u4e00" <= ch <= "\u9fff")
    grams = {cleaned[i : i + 2] for i in range(len(cleaned) - 1)}
    scored = []
    for scene in store.scenes():
        hits = sum(1 for gram in grams if gram in scene.text)
        scored.append((hits, scene))
    scored.sort(key=lambda pair: -pair[0])
    return "\n".join(scene.text[:700] for _, scene in scored[:limit])


def main() -> int:
    outcome = build_demo()
    store = outcome.store
    llm = OpenAICompatLLM(
        os.getenv("ROLERAG_LLM_MODEL", "deepseek-v4.1-flash-1017"),
        base_url=os.getenv("OPENAI_BASE_URL"),
        api_key=os.getenv("OPENAI_API_KEY"),
        temperature=0.4,
        max_tokens=250,
    )
    renderer = LLMRenderer(llm)
    rng = random.Random(20261114)
    records = []
    key = []
    for index, (name, cutoff, question) in enumerate(PAIRS, start=1):
        entity = store.find_entity(name)
        new = chat_turn(store, entity.id, cutoff, question, renderer=renderer)
        context = _flat_context(store, question)
        prompt = (
            f"你是{name}。下面是小说的检索片段。请只用第一人称、简短地回答。\n"
            f"【片段】\n{context}\n【问题】{question}"
        )
        baseline = llm.complete(prompt).strip()
        sides = [("rolerag", new.text), ("flat", baseline)]
        rng.shuffle(sides)
        records.append({
            "pair": index,
            "question": question,
            "cutoff": cutoff,
            "A": sides[0][1],
            "B": sides[1][1],
        })
        key.append({
            "pair": index,
            "A": sides[0][0],
            "B": sides[1][0],
            "route": new.route,
        })
        print(f"[{index}] {question}\n  A: {sides[0][1]}\n  B: {sides[1][1]}")

    target = ROOT.parent / "docs" / "rolerag-blind-eval.jsonl"
    key_target = ROOT.parent / "docs" / "rolerag-blind-eval-key.json"
    target.write_text("\n".join(json.dumps(row, ensure_ascii=False) for row in records), encoding="utf-8")
    key_target.write_text(json.dumps(key, ensure_ascii=False, indent=2), encoding="utf-8")
    print("wrote", target, key_target)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
