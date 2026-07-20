# engine/intelligence/queries.py
"""Graph query API — importance, blast radius, dead code, context, coupling.

All queries operate on a NetworkX DiGraph (from GraphBuilder) or a GraphBuilder
instance directly.  No DB access required — all computation is in-memory.
"""

from __future__ import annotations

import os
import re
from typing import TYPE_CHECKING, Any

import networkx as nx

if TYPE_CHECKING:
    pass


# ---------------------------------------------------------------------------
# 1. Symbol importance (PageRank)
# ---------------------------------------------------------------------------


def symbol_importance(graph: nx.DiGraph, limit: int = 50) -> list[dict]:
    """Top files ranked by PageRank centrality.

    Returns list of dicts: {path, score, dependents}.
    """
    if not graph.nodes:
        return []
    try:
        scores = nx.pagerank(graph, alpha=0.85)
    except Exception:
        scores = {n: 1.0 / max(len(graph), 1) for n in graph.nodes}

    # Filter to file nodes only — symbol nodes (containing "::") are excluded here;
    # use symbol_blast_radius() for symbol-level importance.
    ranked = sorted(
        [(p, s) for p, s in scores.items() if "::" not in p],
        key=lambda x: x[1],
        reverse=True,
    )
    return [
        {"path": path, "score": round(score, 6), "dependents": graph.in_degree(path)} for path, score in ranked[:limit]
    ]


# ---------------------------------------------------------------------------
# 2. Blast radius
# ---------------------------------------------------------------------------


def blast_radius(file_path: str, graph: nx.DiGraph) -> dict:
    """All files that transitively depend on the given file.

    Returns dict: {file, direct_dependents, total_affected, affected_files}.
    """
    if file_path not in graph:
        return {
            "file": file_path,
            "direct_dependents": 0,
            "total_affected": 0,
            "affected_files": [],
        }

    # Direct dependents — files that have an edge pointing TO file_path
    direct = list(graph.predecessors(file_path))

    # Transitive dependents via BFS
    visited: set[str] = set()
    queue = list(direct)
    while queue:
        node = queue.pop(0)
        if node in visited or node == file_path:
            continue
        visited.add(node)
        queue.extend(graph.predecessors(node))

    return {
        "file": file_path,
        "direct_dependents": len(direct),
        "total_affected": len(visited),
        "affected_files": sorted(visited),
    }


def symbol_blast_radius(symbol_id: str, graph: nx.DiGraph) -> dict:
    """All symbols that transitively call the given symbol.

    Returns {symbol, direct_callers, total_affected, caller_symbols}.
    """
    if symbol_id not in graph:
        return {"symbol": symbol_id, "direct_callers": 0, "total_affected": 0, "caller_symbols": []}

    direct = [n for n in graph.predecessors(symbol_id) if "::" in n]

    visited: set[str] = set()
    queue = list(direct)
    while queue:
        node = queue.pop(0)
        if node in visited or node == symbol_id:
            continue
        visited.add(node)
        queue.extend(n for n in graph.predecessors(node) if "::" in n)

    return {
        "symbol": symbol_id,
        "direct_callers": len(direct),
        "total_affected": len(visited),
        "caller_symbols": sorted(visited),
    }


def symbol_callers(symbol_id: str, graph: nx.DiGraph) -> list[str]:
    """Return direct callers of a symbol (immediate predecessors that are symbols)."""
    if symbol_id not in graph:
        return []
    return [n for n in graph.predecessors(symbol_id) if "::" in n]


# ---------------------------------------------------------------------------
# 3. Dead code
# ---------------------------------------------------------------------------


def find_dead_code(builder: Any) -> list[dict]:
    """Symbols defined in files that nothing imports.

    A file is "dead" when its in-degree is 0 (no other file depends on it).
    Returns list of symbol dicts from those files.
    """
    graph: nx.DiGraph = builder.graph
    symbols: list[dict] = builder.get_symbols()

    # Files with no incoming edges
    dead_files: set[str] = {node for node in graph.nodes if graph.in_degree(node) == 0}

    return [s for s in symbols if s["file"] in dead_files]


# ---------------------------------------------------------------------------
# 4. Dependency chain
# ---------------------------------------------------------------------------


def dependency_chain(from_file: str, to_file: str, graph: nx.DiGraph) -> list[str]:
    """Shortest path between two files in the dependency graph.

    Returns the path as a list of file strings, or [] if no path exists.
    """
    try:
        return nx.shortest_path(graph, from_file, to_file)
    except (nx.NetworkXNoPath, nx.NodeNotFound):
        return []


# ---------------------------------------------------------------------------
# 5. Module coupling
# ---------------------------------------------------------------------------


def module_coupling(module_a: str, module_b: str, graph: nx.DiGraph) -> dict:
    """Coupling score between two modules/directories.

    Coupling = number of cross-module edges / total possible cross-module edges.
    Works at the file level: module_a and module_b are path prefixes or
    exact file paths.

    Returns dict: {module_a, module_b, edges, coupling_score, shared_files}.
    """

    # Collect files in each module (match by prefix or exact path)
    def _files_for_module(prefix: str) -> set[str]:
        result: set[str] = set()
        for node in graph.nodes:
            if node == prefix or node.startswith(prefix.rstrip("/") + "/"):
                result.add(node)
        # If no prefix match found, try basename match (e.g. "core" matches "core.py")
        if not result:
            mod_basename = os.path.splitext(prefix)[0]
            for node in graph.nodes:
                if os.path.splitext(node)[0] == mod_basename or node == prefix:
                    result.add(node)
        return result

    files_a = _files_for_module(module_a)
    files_b = _files_for_module(module_b)

    if not files_a or not files_b:
        return {
            "module_a": module_a,
            "module_b": module_b,
            "edges": 0,
            "coupling_score": 0.0,
            "shared_files": [],
        }

    # Count directed edges between the two sets
    cross_edges = 0
    shared_nodes: set[str] = set()
    for u, v in graph.edges:
        if (u in files_a and v in files_b) or (u in files_b and v in files_a):
            cross_edges += 1
            shared_nodes.add(u)
            shared_nodes.add(v)

    # Max possible edges (directed: a→b + b→a for each pair)
    max_edges = len(files_a) * len(files_b) * 2
    coupling_score = round(cross_edges / max_edges, 4) if max_edges > 0 else 0.0

    return {
        "module_a": module_a,
        "module_b": module_b,
        "edges": cross_edges,
        "coupling_score": coupling_score,
        "shared_files": sorted(shared_nodes),
    }


# ---------------------------------------------------------------------------
# 6. Code context (graph-aware RAG endpoint)
# ---------------------------------------------------------------------------

# Regex to detect file-path-like tokens in a query
_PATH_RE = re.compile(r"[\w./\\-]+\.\w{1,10}")
# Regex for dotted Python-style names (e.g. engine.scanner.ast_parser)
_DOTTED_RE = re.compile(r"\b[a-zA-Z_]\w*(?:\.[a-zA-Z_]\w*){1,}\b")


def code_context(query: str, builder: Any) -> dict:
    """Graph-aware RAG — extract references from query, traverse graph, return context.

    1. Extract file paths and symbol names mentioned in the query.
    2. Find matching nodes in the graph.
    3. For each match, get its neighbors (dependents + dependencies).
    4. Rank results by centrality.
    5. Return structured context dict.

    Args:
        query:   Natural language query (may contain file paths or symbol names).
        builder: GraphBuilder instance (after phase1_treesitter).

    Returns:
        {
            "query": str,
            "matched_files": list[str],
            "context_files": list[dict],  # {path, role, score}
            "symbols": list[dict],
            "total_context_files": int,
        }
    """
    graph: nx.DiGraph = builder.graph
    symbols: list[dict] = builder.get_symbols()

    if not graph.nodes:
        return {
            "query": query,
            "matched_files": [],
            "context_files": [],
            "symbols": [],
            "total_context_files": 0,
        }

    # -- Step 1: compute centrality for ranking --
    try:
        centrality = nx.pagerank(graph, alpha=0.85)
    except Exception:
        centrality = {n: 1.0 / max(len(graph), 1) for n in graph.nodes}

    # -- Step 2: extract candidate tokens from query --
    candidate_tokens: set[str] = set()

    # File-path patterns
    for m in _PATH_RE.finditer(query):
        candidate_tokens.add(m.group())

    # Dotted module paths
    for m in _DOTTED_RE.finditer(query):
        candidate_tokens.add(m.group())
        # Also add the last component (e.g. "ast_parser" from "engine.scanner.ast_parser")
        candidate_tokens.add(m.group().split(".")[-1])

    # Plain words (potential symbol / file names)
    for word in re.split(r"\W+", query):
        if len(word) >= 3:
            candidate_tokens.add(word)
            candidate_tokens.add(word.lower())

    # -- Step 3: find matching graph nodes --
    matched_files: set[str] = set()
    for node in graph.nodes:
        node_lower = node.lower()
        node_base = os.path.splitext(os.path.basename(node))[0].lower()
        for token in candidate_tokens:
            tok_lower = token.lower()
            if tok_lower == node_lower or tok_lower in node_lower or tok_lower == node_base:
                matched_files.add(node)
                break

    # Also match by symbol name
    matched_symbols: list[dict] = []
    for sym in symbols:
        sym_name_lower = sym["name"].lower()
        for token in candidate_tokens:
            if token.lower() == sym_name_lower or sym_name_lower in token.lower():
                matched_symbols.append(sym)
                matched_files.add(sym["file"])
                break

    # -- Step 4: gather context neighbors for matched files --
    context_nodes: dict[str, str] = {}  # path -> role
    for f in matched_files:
        context_nodes[f] = "direct_match"
        # Dependencies (files this file imports)
        for successor in graph.successors(f):
            if successor not in context_nodes:
                context_nodes[successor] = "dependency"
        # Dependents (files that import this file)
        for predecessor in graph.predecessors(f):
            if predecessor not in context_nodes:
                context_nodes[predecessor] = "dependent"

    # -- Step 5: rank by centrality --
    context_files = sorted(
        [
            {
                "path": path,
                "role": role,
                "score": round(centrality.get(path, 0.0), 6),
            }
            for path, role in context_nodes.items()
        ],
        key=lambda x: (x["role"] == "direct_match", x["score"]),
        reverse=True,
    )

    return {
        "query": query,
        "matched_files": sorted(matched_files),
        "context_files": context_files[:20],  # cap at 20 to keep context focused
        "symbols": matched_symbols[:10],
        "total_context_files": len(context_files),
    }
