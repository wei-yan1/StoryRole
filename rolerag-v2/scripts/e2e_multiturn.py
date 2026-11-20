"""8-turn real-model conversation with settlement.

Unlike the one-shot E2E, this calls settle() after every turn, so hostility,
beliefs and dialogue events accumulate exactly as they would in the API.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
load_dotenv(ROOT.parent / ".env")

from app.rag.rolerag.chat.orchestrator import LLMRenderer, chat_turn  # noqa: E402
from app.rag.rolerag.chat.settle import settle  # noqa: E402
from app.rag.rolerag.demo import build_demo  # noqa: E402
from app.rag.rolerag.llm import OpenAICompatLLM  # noqa: E402

TURNS = [
    "沈砚为什么斩了赵七",
    "你还恨玄真吗",
    "玄真骂你是废物，你恨他吗",
    "我听说玄真说过，沈砚是被冤枉的",
    "那你现在怎么看玄真",
    "沈砚后来怎么样了",
    "如果再见沈砚，你会替他报仇吗",
    "你还愿意回青霄门吗",
    "我答应你，若再见沈砚，我会替他问清楚",
]


def main() -> int:
    outcome = build_demo()
    store = outcome.store
    lu = store.find_entity("陆知微")
    renderer = LLMRenderer(
        OpenAICompatLLM(
            os.getenv("ROLERAG_LLM_MODEL", "deepseek-v4.1-flash-1017"),
            base_url=os.getenv("OPENAI_BASE_URL") or os.getenv("DASHSCOPE_BASE_URL"),
            api_key=os.getenv("OPENAI_API_KEY") or os.getenv("DASHSCOPE_API_KEY"),
            temperature=0.4,
            max_tokens=2048,
        )
    )
    before = store.state(lu.id).as_dict()
    records = []
    for index, message in enumerate(TURNS, start=1):
        reply = chat_turn(store, lu.id, 6, message, renderer=renderer)
        settlement = settle(store, lu.id, 6, message, reply.text)
        state = store.state(lu.id).as_dict()
        records.append({
            "turn": index,
            "message": message,
            "route": reply.route,
            "text": reply.text,
            "style_ok": reply.style.ok,
            "style_score": reply.style.score,
            "attempts": reply.attempts,
            "triggers": settlement.triggers,
            "deltas": settlement.deltas,
            "event_id": settlement.event_id,
            "belief_id": settlement.belief_id,
            "state": state,
        })
        print(f"[{index}] {message}\n  route={reply.route} style={reply.style.ok} {reply.text}")
        print(f"  triggers={settlement.triggers} hostility={state['hostility']:.3f}")

    after = store.state(lu.id).as_dict()
    print("state before", {k: round(v, 3) for k, v in before.items()})
    print("state after ", {k: round(v, 3) for k, v in after.items()})
    print(f"events={len(store.events())} beliefs={len(store.beliefs(lu.id))}")
    target = ROOT.parent / "docs" / "rolerag-multiturn-e2e.jsonl"
    target.write_text("\n".join(json.dumps(row, ensure_ascii=False) for row in records), encoding="utf-8")
    print("wrote", target)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
