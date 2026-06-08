"""
In-memory NetworkX topology graph, rebuilt from Redis on startup and kept
in sync on every entity/edge write.

Kept as a module-level singleton so routes can call graph.blast_radius(id)
without re-reading Redis on every request.
"""

from __future__ import annotations

import networkx as nx


class TopologyGraph:
    def __init__(self) -> None:
        self._g: nx.DiGraph = nx.DiGraph()

    def add_entity(self, entity: dict) -> None:
        eid = entity["entity_id"]
        self._g.add_node(
            eid,
            entity_type=entity.get("entity_type"),
            fragility_score=entity.get("fragility_score", 0.0),
            security_posture=entity.get("security_posture", "clean"),
        )

    def remove_entity(self, entity_id: str) -> None:
        self._g.remove_node(entity_id)

    def add_edge(self, edge: dict) -> None:
        self._g.add_edge(
            edge["source_id"],
            edge["target_id"],
            edge_type=edge["edge_type"],
            weight=edge.get("weight", 0.5),
        )

    def blast_radius(self, entity_id: str) -> list[str]:
        """Return all entity IDs reachable downstream from entity_id."""
        if entity_id not in self._g:
            return []
        return list(nx.descendants(self._g, entity_id))

    def top_fragile(self, n: int = 10) -> list[tuple[str, float]]:
        """Return top-n (entity_id, fragility_score) pairs, highest first."""
        scored = [
            (nid, data.get("fragility_score", 0.0))
            for nid, data in self._g.nodes(data=True)
        ]
        scored.sort(key=lambda x: x[1], reverse=True)
        return scored[:n]

    def rebuild(self, entities: list[dict], edges: list[dict]) -> None:
        self._g.clear()
        for e in entities:
            self.add_entity(e)
        for edge in edges:
            self.add_edge(edge)

    @property
    def node_count(self) -> int:
        return self._g.number_of_nodes()


graph = TopologyGraph()
