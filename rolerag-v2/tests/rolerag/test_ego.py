from app.rag.rolerag.chat.orchestrator import chat_turn
from app.rag.rolerag.demo import build_demo
from app.rag.rolerag.retrieval.ego import (
    build_ego_network,
    ego_summary,
    local_clusters,
    relation_evidence,
)
from app.rag.rolerag.retrieval.router import route
from app.rag.rolerag.retrieval.scope import analyze_scope
from app.rag.rolerag.retrieval.subgraph import retrieve


def _entity(store, name: str):
    return next(entity for entity in store.entities() if entity.name == name)


def test_ego_network_respects_cutoff_and_edge_contract() -> None:
    outcome = build_demo()
    character = _entity(outcome.store, "陆知微")
    network = build_ego_network(outcome.store, character.id, 2)

    assert character.id in network.nodes
    assert "赵七" not in {node.name for node in network.nodes.values()}
    assert network.edges
    for edge in network.edges:
        assert edge.visibility
        assert -1 <= edge.sign <= 1
        assert edge.valid_from <= 2
        assert edge.kind


def test_ego_network_has_a_second_hop_beyond_direct_witnesses() -> None:
    outcome = build_demo()
    character = _entity(outcome.store, "沈砚")
    network = build_ego_network(outcome.store, character.id, 4)

    assert any(node.depth == 2 for node in network.nodes.values())
    assert network.edges
    assert all(edge.valid_from <= 4 for edge in network.edges)


def test_ego_clusters_are_first_person_not_global_communities() -> None:
    outcome = build_demo()
    character = _entity(outcome.store, "陆知微")
    network = build_ego_network(outcome.store, character.id, 6)
    summary = ego_summary(network)

    assert summary.startswith("我眼里的他们")
    assert "全书" not in summary
    assert "社区" not in summary
    clusters = local_clusters(network)
    assert clusters
    assert all(cluster.members for cluster in clusters)
    assert any("我见过的" == cluster.label for cluster in clusters)


def test_relation_evidence_uses_paths_and_never_leaks_future() -> None:
    outcome = build_demo()
    character = _entity(outcome.store, "沈砚")
    network = build_ego_network(outcome.store, character.id, 4)

    paths = relation_evidence(network, ["陆知微", "赵七"])
    assert paths
    assert any("陆知微" in text and "赵七" in text for text, _chapter, _weight in paths)
    assert all(chapter <= 4 for _text, chapter, _weight in paths)


def test_visibility_and_scene_indexes_match_bruteforce_filters() -> None:
    outcome = build_demo()
    store = outcome.store
    character = _entity(store, "陆知微")
    cutoff = 6

    assert not store.is_visible(character.id, at=cutoff)
    assert store.best_route(character.id, at=cutoff) is None

    for event in store.events(lte=cutoff):
        expected = any(
            row.covers(event_id=event.id, at=cutoff)
            for row in store.visibility(character.id)
        )
        assert store.is_visible(character.id, event_id=event.id, at=cutoff) is expected

    for scene in store.scenes(lte=cutoff):
        expected = [
            event for event in store.events(lte=cutoff)
            if event.scene_id == scene.id
        ]
        assert store.events_in_scene(scene.id, lte=cutoff) == expected


def test_relation_question_returns_multi_hop_evidence_before_direct_rows() -> None:
    outcome = build_demo()
    character = _entity(outcome.store, "沈砚")
    question = "我怎么看陆知微和赵七的关系"
    scope = analyze_scope(question, outcome.store, character.id, 4)
    decision = route(question, scope)
    evidence = retrieve(outcome.store, character.id, 4, decision)

    assert decision.kind == "probe"
    assert evidence
    assert evidence[0].kind == "relation"
    assert "陆知微" in evidence[0].text
    assert "赵七" in evidence[0].text
    assert "第2章" in evidence[0].text


def test_unknown_relation_target_is_rejected_not_guessed() -> None:
    outcome = build_demo()
    character = _entity(outcome.store, "陆知微")
    question = "我怎么看沈砚和赵七的关系"
    scope = analyze_scope(question, outcome.store, character.id, 2)
    decision = route(question, scope)
    evidence = retrieve(outcome.store, character.id, 2, decision)

    assert decision.kind == "reject"
    assert "赵七" in decision.reason
    assert not evidence
    assert not any(item.kind == "relation" for item in evidence)


def test_retrieval_only_adapter_returns_memory_not_a_rendered_answer(monkeypatch) -> None:
    from app.rag.rolerag import api_adapter
    from app.rag.rolerag.runtime import RoleRAGRuntime

    outcome = build_demo()
    monkeypatch.setattr(
        api_adapter,
        "runtime_from_manifest",
        lambda *args, **kwargs: RoleRAGRuntime(outcome.store, outcome.cutoff),
    )
    result = api_adapter.retrieve_from_manifest(
        {},
        novel_id="demo",
        character_name="沈砚",
        message="我怎么看陆知微和赵七的关系",
        period={"name": "demo", "chapter_start": "第一章 拜师", "chapter_end": "第六章 尾声"},
        plan={"intent": "relationship_reflection"},
    )

    assert result["evidence"]
    assert result["ego_summary"].startswith("我眼里的他们")
    assert result["route"] == "probe"
    assert "answer" not in result
    assert result["runtime"] is not None


def test_laya_plan_drives_route_and_multi_hop_flag() -> None:
    outcome = build_demo()
    character = _entity(outcome.store, "沈砚")
    question = "我怎么看陆知微和赵七的关系"
    scope = analyze_scope(question, outcome.store, character.id, 4)

    relationship_plan = {
        "intent": "relationship_reflection",
        "needs_relationship": True,
        "future_probe": False,
        "decision_backend": "laya",
    }
    decision = route(question, scope, plan=relationship_plan)
    assert decision.kind == "probe"
    assert decision.multi_hop is True

    future_plan = {
        "intent": "future_probe",
        "future_probe": True,
        "needs_relationship": False,
        "decision_backend": "laya",
    }
    assert route(question, scope, plan=future_plan).kind == "reject"


def test_chat_turn_consumes_plan_from_laya_gateway() -> None:
    outcome = build_demo()
    character = _entity(outcome.store, "沈砚")
    reply = chat_turn(
        outcome.store,
        character.id,
        4,
        "赵七后来怎么样了",
        plan={
            "intent": "future_probe",
            "future_probe": True,
            "needs_relationship": False,
            "decision_backend": "laya",
        },
    )
    assert reply.route == "reject"