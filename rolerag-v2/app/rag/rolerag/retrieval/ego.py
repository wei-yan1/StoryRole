"""Character-centred ego network and local social circles.

This is deliberately not GraphRAG's global community layer. A character only
gets the part of the graph he can perceive at this chapter: facts/events that
pass visibility, his own beliefs, and co-presence inside those events. The
network is then clustered locally into first-person circles, never into an
authorial report of the whole book.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable

from ..models import Belief, Entity, Event, Fact
from ..store import InMemoryGraphStore


@dataclass(frozen=True)
class EgoEdge:
    source_id: str
    target_id: str
    kind: str
    sign: int
    weight: float
    valid_from: int
    visibility: str
    certainty: float = 1.0
    origin: str = "fact"  # fact | belief | event

    @property
    def pair(self) -> tuple[str, str]:
        return (self.source_id, self.target_id)


@dataclass(frozen=True)
class EgoNode:
    entity_id: str
    name: str
    entity_type: str
    depth: int
    direct_sign: int = 0
    direct_weight: float = 0.0
    direct_visibility: str = ""

    @property
    def is_character(self) -> bool:
        return self.entity_type == "character"


@dataclass(frozen=True)
class EgoCluster:
    label: str
    members: tuple[EgoNode, ...]
    summary: str


@dataclass
class EgoNetwork:
    character_id: str
    cutoff: int
    nodes: dict[str, EgoNode] = field(default_factory=dict)
    edges: tuple[EgoEdge, ...] = ()
    _adjacency: dict[str, list[EgoEdge]] = field(default_factory=dict)

    def name(self, entity_id: str) -> str:
        node = self.nodes.get(entity_id)
        return node.name if node else entity_id

    def neighbours(self, entity_id: str) -> list[EgoEdge]:
        return list(self._adjacency.get(entity_id, []))

    def edge_between(self, left: str, right: str) -> list[EgoEdge]:
        return [
            edge
            for edge in self.edges
            if {edge.source_id, edge.target_id} == {left, right}
        ]

    def direct_edges(self, entity_id: str) -> list[EgoEdge]:
        return [
            edge for edge in self.edges
            if edge.source_id == self.character_id and edge.target_id == entity_id
        ]

    def path_between(self, left: str, right: str, *, max_depth: int = 4) -> list[EgoEdge]:
        """BFS over perceived edges; no edge outside visibility can be used."""
        if left == right:
            return []
        if left not in self.nodes or right not in self.nodes:
            return []
        queue: list[tuple[str, list[EgoEdge]]] = [(left, [])]
        seen = {left}
        while queue:
            current, path = queue.pop(0)
            if len(path) >= max_depth:
                continue
            for edge in self.neighbours(current):
                other = edge.target_id if edge.source_id == current else edge.source_id
                if other in seen:
                    continue
                next_path = path + [edge]
                if other == right:
                    return next_path
                seen.add(other)
                queue.append((other, next_path))
        return []


def build_ego_network(
    store: InMemoryGraphStore,
    character_id: str,
    cutoff: int,
    *,
    hops: int = 2,
    max_nodes: int = 60,
) -> EgoNetwork:
    """Build a visibility-bounded 1–2 hop network around one character."""
    character = store.entity(character_id)
    if character is None:
        return EgoNetwork(character_id=character_id, cutoff=cutoff)

    facts = _visible_facts(store, character_id, cutoff)
    events = _visible_events(store, character_id, cutoff)
    beliefs = [belief for belief in store.beliefs(character_id, lte=cutoff) if not belief.retracted]

    nodes: dict[str, EgoNode] = {
        character_id: EgoNode(character_id, character.name, character.type, 0)
    }
    edges: list[EgoEdge] = []
    edge_keys: set[tuple] = set()

    def add_node(entity_id: str, depth: int) -> bool:
        if entity_id in nodes:
            return True
        entity = store.entity(entity_id)
        if entity is None or len(nodes) >= max_nodes:
            return False
        nodes[entity_id] = EgoNode(entity_id, entity.name, entity.type, depth)
        return True

    def add_edge(
        source_id: str,
        target_id: str,
        kind: str,
        sign: int,
        weight: float,
        valid_from: int,
        visibility: str,
        certainty: float,
        origin: str,
    ) -> None:
        if source_id == target_id:
            return
        key = (source_id, target_id, kind, sign, valid_from, origin)
        if key in edge_keys:
            return
        edge_keys.add(key)
        edges.append(EgoEdge(
            source_id=source_id, target_id=target_id, kind=kind, sign=sign,
            weight=round(float(weight), 3), valid_from=int(valid_from or 0),
            visibility=visibility, certainty=round(float(certainty), 3), origin=origin,
        ))

    # Facts are objective edges, but only the ones this character can know.
    # First-hop facts must touch the character; facts between two other people
    # are reached in the second expansion below, not promoted to direct edges.
    for fact, route in facts:
        if character_id not in {fact.source_id, fact.target_id}:
            continue
        add_node(fact.source_id, 1)
        add_node(fact.target_id, 1)
        if fact.source_id not in nodes or fact.target_id not in nodes:
            continue
        add_edge(
            fact.source_id, fact.target_id, fact.kind, fact.sign,
            fact.weight, fact.valid_from, route.route, route.certainty, "fact",
        )

    # Beliefs are subjective edges owned by this character. They still carry
    # their own certainty and never become objective facts.
    for belief in beliefs:
        add_node(belief.subject_id, 1)
        add_node(belief.target_id, 1)
        if belief.subject_id not in nodes or belief.target_id not in nodes:
            continue
        add_edge(
            belief.subject_id, belief.target_id, f"认为:{belief.kind}", belief.sign,
            belief.certainty, belief.since_chapter, "self", belief.certainty, "belief",
        )

    # Co-presence inside a visible event is a weak social edge. Only events
    # that contain the character are first-hop; an event involving his friend
    # but not him is how the second hop is discovered.
    for event, route in events:
        participants = [participant.entity_id for participant in event.participants]
        if character_id not in participants:
            continue
        for participant in participants:
            add_node(participant, 1)
        for participant in participants:
            if participant not in nodes or participant == character_id:
                continue
            add_edge(
                character_id, participant, "同场", 0,
                event.importance * 0.6, event.chapter, route.route,
                route.certainty, "event",
            )
        # Within one witnessed event, two other participants are also
        # connected in his memory. Only add this when both are already in the
        # ego graph, so a huge event cannot pull in the whole cast.
        for left in participants:
            for right in participants:
                if left == right or left not in nodes or right not in nodes:
                    continue
                add_edge(
                    left, right, "同场", 0, event.importance * 0.35,
                    event.chapter, route.route, route.certainty, "event",
                )

    # A second hop: facts/events/beliefs touching the first hop. This is what
    # makes the graph a 1–2 hop network instead of only direct co-presence.
    if hops >= 2:
        first_hop = [entity_id for entity_id in nodes if entity_id != character_id]
        for entity_id in list(first_hop):
            for fact, route in facts:
                if entity_id not in {fact.source_id, fact.target_id}:
                    continue
                other = fact.target_id if fact.source_id == entity_id else fact.source_id
                if other == character_id:
                    continue
                if other not in nodes and not add_node(other, 2):
                    continue
                add_edge(
                    fact.source_id, fact.target_id, fact.kind, fact.sign,
                    fact.weight, fact.valid_from, route.route, route.certainty, "fact",
                )
            for event, route in events:
                participants = [participant.entity_id for participant in event.participants]
                if entity_id not in participants or character_id in participants:
                    continue
                for participant in participants:
                    if participant != entity_id and participant not in nodes:
                        add_node(participant, 2)
                    if participant in nodes and participant != entity_id:
                        add_edge(
                            entity_id, participant, "同场", 0,
                            event.importance * 0.35, event.chapter, route.route,
                            route.certainty, "event",
                        )

    # Fill direct-edge summaries for every node.
    for entity_id, node in list(nodes.items()):
        direct = [
            edge for edge in edges
            if edge.source_id == character_id and edge.target_id == entity_id
        ]
        if not direct:
            direct = [
                edge for edge in edges
                if edge.target_id == character_id and edge.source_id == entity_id
            ]
        if direct:
            strongest = max(direct, key=lambda edge: edge.weight)
            nodes[entity_id] = EgoNode(
                entity_id=node.entity_id, name=node.name, entity_type=node.entity_type,
                depth=node.depth, direct_sign=strongest.sign,
                direct_weight=strongest.weight, direct_visibility=strongest.visibility,
            )

    network = EgoNetwork(
        character_id=character_id,
        cutoff=cutoff,
        nodes=nodes,
        edges=tuple(edges),
    )
    adjacency: dict[str, list[EgoEdge]] = {}
    for edge in edges:
        adjacency.setdefault(edge.source_id, []).append(edge)
        adjacency.setdefault(edge.target_id, []).append(edge)
    network._adjacency = adjacency
    return network


def local_clusters(network: EgoNetwork) -> tuple[EgoCluster, ...]:
    """Group the ego's neighbours into first-person circles.

    This is a local classification, not global community detection. The labels
    are relational stances, because a person remembers "those I trust" and
    "those I guard against", not a Leiden cluster id.
    """
    groups: dict[str, list[EgoNode]] = {
        "我信得过的": [], "我防着的": [], "我拿不准的": [], "我见过的": [], "只在远处见过的": [],
    }
    for entity_id, node in network.nodes.items():
        if entity_id == network.character_id:
            continue
        direct = network.direct_edges(entity_id)
        if direct:
            edge = max(direct, key=lambda item: item.weight)
            if edge.sign < 0 or edge.kind.startswith("认为:敌对"):
                groups["我防着的"].append(node)
            elif edge.sign > 0 or edge.kind.startswith("认为:信任"):
                groups["我信得过的"].append(node)
            elif edge.certainty < 0.6:
                groups["我拿不准的"].append(node)
            elif edge.origin == "event":
                groups["我见过的"].append(node)
            else:
                groups["我见过的"].append(node)
        elif node.depth >= 2:
            groups["只在远处见过的"].append(node)
        else:
            groups["我拿不准的"].append(node)

    clusters: list[EgoCluster] = []
    for label, members in groups.items():
        if not members:
            continue
        members = sorted(members, key=lambda node: (-node.direct_weight, node.name))
        lines = [label + "："]
        for member in members[:8]:
            direct = network.direct_edges(member.entity_id)
            if direct:
                edge = max(direct, key=lambda item: item.weight)
                lines.append(_edge_line(network, edge))
            else:
                lines.append(f"{member.name}（我只在远处见过）")
        clusters.append(EgoCluster(label=label, members=tuple(members), summary=" ".join(lines)))
    return tuple(clusters)


def ego_summary(network: EgoNetwork) -> str:
    if not network.nodes or len(network.nodes) <= 1:
        return "我眼里没有能说清的人。"
    clusters = local_clusters(network)
    text = "我眼里的他们（只按我在这个时期能感知到的关系）："
    if not clusters:
        return text + "说不清。"
    return text + " " + "；".join(cluster.summary for cluster in clusters)


def relation_evidence(
    network: EgoNetwork,
    names: Iterable[str],
    *,
    max_depth: int = 4,
) -> list[tuple[str, int, float]]:
    """Return readable paths/edges between named entities; visibility already applied."""
    ids: list[str] = []
    for name in names:
        node = next((node for node in network.nodes.values() if node.name == name), None)
        if node is not None and node.entity_id not in ids:
            ids.append(node.entity_id)
    if len(ids) < 2:
        return []

    results: list[tuple[str, int, float]] = []
    for index, left in enumerate(ids):
        for right in ids[index + 1:]:
            direct = network.edge_between(left, right)
            strong_direct = [edge for edge in direct if edge.origin in {"fact", "belief"}]
            weak_direct = [edge for edge in direct if edge.origin not in {"fact", "belief"}]
            for edge in sorted(strong_direct, key=lambda item: (-item.weight, item.valid_from)):
                results.append((
                    f"我看到的直接关系：{_edge_line(network, edge)}",
                    edge.valid_from, edge.weight,
                ))
            if not strong_direct and weak_direct:
                for edge in sorted(weak_direct, key=lambda item: (-item.weight, item.valid_from)):
                    results.append((
                        f"我只见过{network.name(left)}和{network.name(right)}同场，"
                        f"没看见他们之间有直接的亲近或敌意（第{edge.valid_from}章）",
                        edge.valid_from, edge.weight,
                    ))
                continue
            path = network.path_between(left, right, max_depth=max_depth)
            if path:
                strong = any(edge.origin in {"fact", "belief"} for edge in path)
                if strong:
                    text = "我看到的路径：" + "；".join(_edge_line(network, edge) for edge in path)
                    chapter = min(edge.valid_from for edge in path)
                    weight = min(edge.weight for edge in path)
                    results.append((text, chapter, weight))
                else:
                    chapter = min(edge.valid_from for edge in path)
                    weight = min(edge.weight for edge in path)
                    results.append((
                        f"我只见过{network.name(left)}和{network.name(right)}分别与我同场"
                        f"（第{chapter}章起），但没有看见他们之间发生过直接关系",
                        chapter, weight,
                    ))
    # A co-presence row can repeat for each direction; keep the strongest one.
    deduped: dict[str, tuple[str, int, float]] = {}
    for text, chapter, weight in results:
        existing = deduped.get(text)
        if existing is None or weight > existing[2]:
            deduped[text] = (text, chapter, weight)
    results = list(deduped.values())
    results.sort(key=lambda item: (-item[2], item[1]))
    return results


def _edge_line(network: EgoNetwork, edge: EgoEdge) -> str:
    source = network.name(edge.source_id)
    target = network.name(edge.target_id)
    if edge.origin == "belief":
        verb = _belief_verb(edge.kind, edge.sign)
        return f"{source}对{target}：{verb}（第{edge.valid_from}章，确信{edge.certainty:.2f}）"
    if edge.origin == "event":
        return f"{source}和{target}同场（第{edge.valid_from}章）"
    return f"{source}{_relation_verb(edge.kind, edge.sign)}{target}（第{edge.valid_from}章，权重{edge.weight:.2f}）"


def _relation_verb(kind: str, sign: int) -> str:
    if kind == "敌对":
        return "敌视" if sign < 0 else "不再敌视"
    if kind == "信任":
        return "不再信任" if sign < 0 else "信任"
    if kind == "归属":
        return "背离" if sign < 0 else "归属"
    if kind == "尊重":
        return "轻慢" if sign < 0 else "尊重"
    return {
        "恩情": "欠着", "亲情": "亲近", "友情": "亲近",
    }.get(kind, kind)


def _belief_verb(kind: str, sign: int) -> str:
    raw = kind.removeprefix("认为:")
    if raw == "敌对":
        return "认为他敌视自己" if sign < 0 else "认为他不再敌视自己"
    if raw == "信任":
        return "已经不再信任" if sign < 0 else "信任"
    if sign < 0:
        return f"已经不再{raw}"
    return raw


def _visible_facts(
    store: InMemoryGraphStore, character_id: str, cutoff: int
) -> list[tuple[Fact, object]]:
    rows: list[tuple[Fact, object]] = []
    for fact in store.facts(lte=cutoff):
        route = store.best_route(character_id, fact_id=fact.id, at=cutoff)
        if route is not None:
            rows.append((fact, route))
    return rows


def _visible_events(
    store: InMemoryGraphStore, character_id: str, cutoff: int
) -> list[tuple[Event, object]]:
    rows: list[tuple[Event, object]] = []
    for event in store.events(lte=cutoff):
        route = store.best_route(character_id, event_id=event.id, at=cutoff)
        if route is not None:
            rows.append((event, route))
    return rows
