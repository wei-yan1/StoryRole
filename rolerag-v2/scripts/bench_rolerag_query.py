"""Reproducible RoleRAG query-layer benchmark (no LLM calls)."""

from __future__ import annotations

import json
import statistics
import sys
import time
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
load_dotenv(ROOT.parent / ".env")

from app.rag.rolerag.persistence import load_store  # noqa: E402
from app.rag.rolerag.retrieval.ego import build_ego_network, ego_summary  # noqa: E402
from app.rag.rolerag.retrieval.router import route  # noqa: E402
from app.rag.rolerag.retrieval.scope import analyze_scope  # noqa: E402
from app.rag.rolerag.retrieval.subgraph import retrieve  # noqa: E402

NOVEL_ID = "54a5fd53434a493abafc4005fb0c70a4"
CHARACTER_NAME = "罗辑"
CUTOFF = 44
QUERIES = [
    "你还记得罗辑经历过什么吗",
    "我怎么看叶文洁和史强的关系",
    "你好",
]


def _bench(fn, *, n: int = 30) -> dict[str, float]:
    samples: list[float] = []
    for _ in range(n):
        started = time.perf_counter()
        fn()
        samples.append((time.perf_counter() - started) * 1000)
    samples.sort()
    return {
        "p50_ms": round(statistics.median(samples), 3),
        "p95_ms": round(samples[max(0, int(len(samples) * 0.95) - 1)], 3),
        "max_ms": round(max(samples), 3),
    }


def main() -> int:
    cold_started = time.perf_counter()
    store = load_store(NOVEL_ID)
    cold_load_ms = round((time.perf_counter() - cold_started) * 1000, 3)
    if store is None:
        print("no persisted graph")
        return 1
    character = next((entity for entity in store.entities() if entity.name == CHARACTER_NAME), None)
    if character is None:
        print(f"character not found: {CHARACTER_NAME}")
        return 1

    results = []
    for query in QUERIES:
        scope = analyze_scope(query, store, character.id, CUTOFF)
        decision = route(query, scope)
        results.append({
            "query": query,
            "route": decision.kind,
            "scope": _bench(lambda: analyze_scope(query, store, character.id, CUTOFF)),
            "retrieve": _bench(lambda: retrieve(store, character.id, CUTOFF, decision)),
            "ego": _bench(lambda: build_ego_network(store, character.id, CUTOFF, hops=2)),
        })

    network = build_ego_network(store, character.id, CUTOFF, hops=2)
    summary = _bench(lambda: ego_summary(network))
    payload = {
        "novel_id": NOVEL_ID,
        "character": CHARACTER_NAME,
        "cutoff": CUTOFF,
        "graph": {
            "events": len(store.events()),
            "facts": len(store.facts()),
            "entities": len(store.entities()),
            "visibility": store.count_visibility(),
            "ego_nodes": len(network.nodes),
            "ego_edges": len(network.edges),
        },
        "load_store_ms": cold_load_ms,
        "ego_summary": summary,
        "queries": results,
        "verdict": {
            "retrieval_is_subsecond": all(
                item["retrieve"]["p50_ms"] < 50 and item["ego"]["p50_ms"] < 20
                for item in results
            ),
            "next_bottleneck": "model / deep pipeline, not the graph query",
        },
    }
    target = ROOT.parent / "docs" / "rolerag-query-bench.json"
    target.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    print("wrote", target)
    return 0 if payload["verdict"]["retrieval_is_subsecond"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
