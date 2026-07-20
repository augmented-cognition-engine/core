# engine/graph/cluster.py
"""Pure community detection logic using networkx Louvain algorithm."""

from __future__ import annotations

import networkx as nx

_LAYER_MAP = {
    "graph_file": "code",
    "graph_function": "code",
    "graph_decision": "code",
    "capability": "product",
    "decision": "product",
    "insight": "product",
    "idea": "work",
    "initiative": "work",
    "task": "work",
    "agent_session": "live",
    "active_edit": "live",
}


def _node_layer(node_id: str) -> str:
    """Return the layer for a node based on its table prefix."""
    table = node_id.split(":")[0] if ":" in node_id else ""
    return _LAYER_MAP.get(table, "unknown")


def build_graph(edges: list[dict]) -> nx.Graph:
    """Build undirected networkx graph from edge dicts with from/to/type."""
    g = nx.Graph()
    for e in edges:
        src, tgt = e.get("from", ""), e.get("to", "")
        if src and tgt:
            g.add_edge(src, tgt, type=e.get("type", ""))
    return g


def detect_clusters(g: nx.Graph, min_nodes: int = 5, resolution: float = 1.0) -> list[dict]:
    """Run Louvain community detection. Returns cluster dicts.

    Each cluster contains:
      - id: "cluster_0", "cluster_1", ...
      - node_count: number of nodes
      - dominant_layer: most common layer (code/product/work/live)
      - label: first capability name or first directory-like node id
      - nodes: list of node ids
    """
    if g.number_of_nodes() < min_nodes:
        return []

    communities = nx.community.louvain_communities(g, resolution=resolution, seed=42)

    clusters = []
    for idx, community in enumerate(sorted(communities, key=len, reverse=True)):
        nodes = sorted(community)
        # Determine dominant layer
        layer_counts: dict[str, int] = {}
        for node_id in nodes:
            layer = _node_layer(node_id)
            layer_counts[layer] = layer_counts.get(layer, 0) + 1
        dominant_layer = max(layer_counts, key=layer_counts.get) if layer_counts else "unknown"

        # Label: first capability node name, or first node id
        label = None
        for node_id in nodes:
            if node_id.startswith("capability:"):
                label = node_id
                break
        if label is None:
            label = nodes[0] if nodes else f"cluster_{idx}"

        clusters.append(
            {
                "id": f"cluster_{idx}",
                "node_count": len(nodes),
                "dominant_layer": dominant_layer,
                "label": label,
                "nodes": nodes,
            }
        )

    return clusters


def compute_inter_cluster_edges(g: nx.Graph, clusters: list[dict]) -> list[dict]:
    """Count edges crossing cluster boundaries.

    Returns list of dicts: {"from_cluster": "cluster_0", "to_cluster": "cluster_1", "weight": N}
    """
    # Build node → cluster_id map
    node_to_cluster: dict[str, str] = {}
    for cluster in clusters:
        cid = cluster["id"]
        for node_id in cluster["nodes"]:
            node_to_cluster[node_id] = cid

    # Count cross-cluster edges
    pair_counts: dict[tuple[str, str], int] = {}
    for u, v in g.edges():
        c_u = node_to_cluster.get(u)
        c_v = node_to_cluster.get(v)
        if c_u and c_v and c_u != c_v:
            pair = tuple(sorted([c_u, c_v]))
            pair_counts[pair] = pair_counts.get(pair, 0) + 1

    return [
        {"from_cluster": pair[0], "to_cluster": pair[1], "weight": count} for pair, count in sorted(pair_counts.items())
    ]
