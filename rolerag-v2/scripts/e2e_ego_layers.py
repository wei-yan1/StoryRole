"""Reproducible real-graph evidence for the five RoleRAG capabilities.

This script deliberately does not call the LLM. It proves the pieces underneath
the prompt: visibility-bounded ego edges, local first-person circles, multi-hop
relation evidence, Nuwa relationship/boundary injection, and Laya plan routing.
The HTTP scripts prove the assembled chat path.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
load_dotenv(ROOT.parent / ".env")

from app.agents.storyrole.query_planner import QueryPlannerAgent  # noqa: E402
from app.rag.rolerag.persistence import load_store  # noqa: E402
from app.rag.rolerag.chat.orchestrator import TurnContext, build_messages  # noqa: E402
from app.rag.rolerag.models import CognitionState  # noqa: E402
from app.rag.rolerag.persona.seed import build_seed, overlay_from_profile  # noqa: E402
from app.rag.rolerag.retrieval.ego import (  # noqa: E402
    build_ego_network,
    ego_summary,
    relation_evidence,
)
from app.rag.rolerag.retrieval.router import RouteDecision, route  # noqa: E402
from app.rag.rolerag.retrieval.scope import ScopeReport, analyze_scope  # noqa: E402
from app.rag.rolerag.retrieval.subgraph import retrieve  # noqa: E402
from app.storage.repositories.storyrole_repository import (  # noqa: E402
    get_persona_profile_for_period,
)

NOVEL_ID = "54a5fd53434a493abafc4005fb0c70a4"
CHARACTER_NAME = "罗辑"
CHARACTER_ID = 1
OWNER_ID = 2
PERIOD_ID = 7
CUTOFF = 44
QUESTION = "我怎么看叶文洁和史强的关系"


def main() -> int:
    store = load_store(NOVEL_ID)
    if store is None:
        print("no persisted graph")
        return 1
    character = next(
        (entity for entity in store.entities() if entity.name == CHARACTER_NAME),
        None,
    )
    if character is None:
        print(f"character not found: {CHARACTER_NAME}")
        return 1

    network = build_ego_network(store, character.id, CUTOFF, hops=2)
    summary = ego_summary(network)
    relation = relation_evidence(network, ["叶文洁", "史强"])
    profile = get_persona_profile_for_period(
        character_id=CHARACTER_ID, owner_id=OWNER_ID, period_id=PERIOD_ID
    )["profile"]
    overlay = overlay_from_profile(profile)
    plan = QueryPlannerAgent().plan({"message": QUESTION})
    scope = analyze_scope(QUESTION, store, character.id, CUTOFF)
    decision = route(QUESTION, scope, plan=plan)
    evidence = retrieve(store, character.id, CUTOFF, decision)
    seed = build_seed(store, character.id, CUTOFF, overlay=overlay)
    context = TurnContext(
        character_id=character.id,
        cutoff=CUTOFF,
        message=QUESTION,
        state=CognitionState(character_id=character.id, cutoff=CUTOFF),
        evidence=evidence,
        decision=decision,
        scope=ScopeReport(),
        seed=seed,
        ego_summary=summary,
    )
    prompt = build_messages(context, draft="")[0]["content"]

    payload = {
        "novel_id": NOVEL_ID,
        "character": CHARACTER_NAME,
        "cutoff": CUTOFF,
        "ego_nodes": len(network.nodes),
        "ego_edges": len(network.edges),
        "ego_nodes_at_depth_2": sum(1 for node in network.nodes.values() if node.depth >= 2),
        "all_edges_have_visibility": all(edge.visibility for edge in network.edges),
        "summary_is_first_person": summary.startswith("我眼里的他们"),
        "ego_summary": summary,
        "relation_evidence": [
            {"text": text, "chapter": chapter, "weight": weight}
            for text, chapter, weight in relation
        ],
        "nuwa": {
            "relationships": len(overlay.relationships) if overlay else 0,
            "known": len(overlay.known) if overlay else 0,
            "unknown": len(overlay.unknown) if overlay else 0,
        },
        "nuwa_prompt": {
            "has_relationships": "我认识的人与关系" in prompt,
            "has_known": "我确实知道的背景" in prompt,
            "has_unknown": "我不确定的背景" in prompt,
            "has_ego_summary": "我眼里的他们" in prompt,
        },
        "laya_plan": plan,
        "route": decision.kind,
        "multi_hop": decision.multi_hop,
        "evidence": [{"kind": item.kind, "text": item.text} for item in evidence],
    }
    target = ROOT.parent / "docs" / "rolerag-ego-layers.json"
    target.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({key: payload[key] for key in [
        "ego_nodes", "ego_edges", "ego_nodes_at_depth_2",
        "all_edges_have_visibility", "summary_is_first_person", "nuwa",
        "nuwa_prompt", "route", "multi_hop",
    ]}, ensure_ascii=False, indent=2))
    print("wrote", target)
    ok = (
        payload["ego_nodes"] > 1
        and payload["ego_edges"] > 0
        and payload["all_edges_have_visibility"]
        and payload["summary_is_first_person"]
        and payload["nuwa"]["relationships"] > 0
        and payload["nuwa"]["known"] > 0
        and payload["nuwa"]["unknown"] > 0
        and all(payload["nuwa_prompt"].values())
        and any(item["kind"] == "relation" for item in payload["evidence"])
    )
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())