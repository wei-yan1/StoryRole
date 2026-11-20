"""Real-model end-to-end check for the RoleRAG chat loop.

Loads the project .env, builds the synthetic book, and runs a few turns through
LLMRenderer (DashScope OpenAI-compatible endpoint). Writes docs/rolerag-llm-e2e.jsonl.
"""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(Path(r"D:\AgentCode\two\.env"))

from app.rag.rolerag.chat.orchestrator import LLMRenderer, chat_turn  # noqa: E402
from app.rag.rolerag.demo import build_demo  # noqa: E402
from app.rag.rolerag.llm import OpenAICompatLLM  # noqa: E402

OUT = Path(r"D:\AgentCode\two\docs\rolerag-llm-e2e.jsonl")


def main() -> int:
    model = os.getenv("ROLERAG_LLM_MODEL", "deepseek-v4.1-flash-1017")
    llm = OpenAICompatLLM(
        model,
        base_url=os.getenv("OPENAI_BASE_URL") or os.getenv("DASHSCOPE_BASE_URL"),
        api_key=os.getenv("OPENAI_API_KEY") or os.getenv("DASHSCOPE_API_KEY"),
        temperature=0.4,
        max_tokens=2048,
    )
    outcome = build_demo()
    store = outcome.store
    renderer = LLMRenderer(llm)
    turns = [
        ("陆知微", 6, "你还记得沈砚被逐出山门那天吗", None),
        ("陆知微", 6, "沈砚为什么斩了赵七", None),
        ("陆知微", 2, "沈砚为什么斩了赵七", None),
        ("玄真", 6, "你还记得沈砚隐瞒陆知微那件事吗", None),
        ("陆知微", 6, "你怎么看阿波罗登月", ["阿波罗"]),
    ]

    rows = []
    for character, cutoff, question, external in turns:
        char = store.find_entity(character)
        started = time.perf_counter()
        reply = chat_turn(
            store, char.id, cutoff, question,
            renderer=renderer, external_terms=external,
        )
        rows.append({
            "character": character,
            "cutoff": cutoff,
            "question": question,
            "route": reply.route,
            "style_ok": reply.style.ok,
            "style_score": reply.style.score,
            "attempts": reply.attempts,
            "chars": len(reply.text),
            "text": reply.text,
            "latency_ms": round((time.perf_counter() - started) * 1000),
        })
        print(f"[{character}@{cutoff}] {question}\n  route={reply.route} "
              f"style={reply.style.ok} score={reply.style.score} attempts={reply.attempts} "
              f"chars={len(reply.text)}\n  {reply.text}\n")

    OUT.write_text("\n".join(json.dumps(row, ensure_ascii=False) for row in rows) + "\n", encoding="utf-8")
    passed = sum(1 for row in rows if row["style_ok"])
    print(f"model={model} turns={len(rows)} style_pass={passed}/{len(rows)} "
          f"avg_latency={sum(row['latency_ms'] for row in rows) // len(rows)}ms")
    return 0 if passed == len(rows) else 1


if __name__ == "__main__":
    raise SystemExit(main())
