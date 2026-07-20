"""Repository map — relevance-ranked code context from ACE's code graph.

Instead of re-parsing files (Aider approach), queries the existing
code graph built by engine/scanner/scanner.py. The scanner already
extracted files, functions, imports, and decisions into SurrealDB.

PageRank runs on the graph database's edge data for relevance ranking.
"""

from __future__ import annotations

import logging
from typing import Any

import networkx as nx

logger = logging.getLogger(__name__)


class RepoMap:
    """Queries ACE's existing code graph for relevance-ranked context."""

    def __init__(self, graph_id: str = "default") -> None:
        self._graph_id = graph_id
        self._nx_graph: nx.DiGraph | None = None

    async def build_from_db(self) -> int:
        """Build NetworkX graph from ACE's scanner data in SurrealDB."""
        try:
            from core.engine.core.db import parse_rows, pool

            async with pool.connection() as db:
                # Load files from scanner's graph
                files = parse_rows(
                    await db.query(
                        "SELECT path, function_count FROM code_file WHERE graph_id = $gid",
                        {"gid": self._graph_id},
                    )
                )

                # Load import edges
                imports = parse_rows(
                    await db.query(
                        "SELECT from_path, to_path FROM code_import WHERE graph_id = $gid",
                        {"gid": self._graph_id},
                    )
                )

            self._nx_graph = nx.DiGraph()
            for f in files:
                self._nx_graph.add_node(f.get("path", ""), **f)
            for imp in imports:
                from_p = imp.get("from_path", "")
                to_p = imp.get("to_path", "")
                if from_p and to_p:
                    self._nx_graph.add_edge(from_p, to_p)

            return len(files)
        except Exception as exc:
            logger.warning("Failed to build repo map from DB: %s", exc)
            self._nx_graph = nx.DiGraph()
            return 0

    def build(self, file_paths: list[str] | None = None) -> int:
        """Sync fallback: build from filesystem (for when DB is unavailable)."""
        # Keep the original regex-based parsing as fallback
        return self._build_from_files(file_paths)

    def rank(
        self,
        query: str = "",
        focused_files: list[str] | None = None,
        max_results: int = 20,
    ) -> list[dict[str, Any]]:
        """Rank files by relevance using personalized PageRank."""
        if not self._nx_graph or not self._nx_graph.nodes:
            return []

        personalization = {}
        query_terms = set(query.lower().split()) if query else set()

        for node in self._nx_graph.nodes:
            weight = 1.0
            if focused_files and node in focused_files:
                weight *= 50.0
            if query_terms:
                node_lower = node.lower()
                matches = sum(1 for term in query_terms if term in node_lower)
                if matches:
                    weight *= 1 + matches * 10
            personalization[node] = weight

        total = sum(personalization.values())
        if total > 0:
            personalization = {k: v / total for k, v in personalization.items()}

        try:
            scores = nx.pagerank(self._nx_graph, alpha=0.85, personalization=personalization)
        except Exception:
            scores = {n: 1.0 / max(len(self._nx_graph), 1) for n in self._nx_graph.nodes}

        ranked = sorted(scores.items(), key=lambda x: x[1], reverse=True)
        return [{"path": p, "score": round(s, 6)} for p, s in ranked[:max_results]]

    def get_context(self, query: str = "", focused_files: list[str] | None = None, token_budget: int = 2000) -> str:
        """Get token-efficient context string of most relevant code."""
        ranked = self.rank(query=query, focused_files=focused_files, max_results=30)
        parts = []
        tokens_used = 0
        for item in ranked:
            line = item["path"]
            chunk_tokens = len(line) // 4
            if tokens_used + chunk_tokens > token_budget:
                break
            parts.append(line)
            tokens_used += chunk_tokens
        return "\n".join(parts)

    def _build_from_files(self, file_paths: list[str] | None = None) -> int:
        """Fallback: regex-based file parsing (original implementation)."""
        import os
        from pathlib import Path

        PARSEABLE = {".py", ".js", ".ts", ".tsx", ".jsx", ".java", ".go", ".rs", ".rb"}

        # Detect if graph_id looks like a filesystem path (legacy usage)
        repo_path = "."
        if self._graph_id != "default":
            import os as _os

            if _os.path.isdir(self._graph_id):
                repo_path = self._graph_id

        if not file_paths:
            file_paths = []
            for root, dirs, files in os.walk(repo_path):
                dirs[:] = [
                    d
                    for d in dirs
                    if not d.startswith(".")
                    and d not in {"node_modules", "__pycache__", ".venv", "venv", "dist", "build", ".git"}
                ]
                for f in files:
                    if Path(f).suffix in PARSEABLE:
                        file_paths.append(os.path.relpath(os.path.join(root, f), repo_path))

        self._nx_graph = nx.DiGraph()
        self._definitions: dict[str, list[dict]] = {}
        self._references: dict[str, set[str]] = {}
        self._file_symbols: dict[str, set[str]] = {}

        for path in file_paths:
            full_path = os.path.join(repo_path, path) if repo_path != "." else path
            try:
                content = open(full_path, encoding="utf-8", errors="replace").read()
            except Exception:
                try:
                    content = open(path, encoding="utf-8", errors="replace").read()
                except Exception:
                    continue

            ext = Path(path).suffix
            defs: list[dict] = []
            refs: set[str] = set()

            if ext == ".py":
                defs, refs = self._parse_python(content)
            elif ext in {".js", ".ts", ".tsx", ".jsx"}:
                defs, refs = self._parse_javascript(content)
            else:
                defs, refs = self._parse_generic(content)

            if defs or refs:
                self._definitions[path] = defs
                self._references[path] = refs
                self._file_symbols[path] = {d["name"] for d in defs}
                self._nx_graph.add_node(path)

        # Build edges from cross-file references
        symbol_to_files: dict[str, list[str]] = {}
        for fpath, defs in self._definitions.items():
            for d in defs:
                symbol_to_files.setdefault(d["name"], []).append(fpath)

        for fpath, refs in self._references.items():
            for ref_name in refs:
                if ref_name in symbol_to_files:
                    for target in symbol_to_files[ref_name]:
                        if target != fpath:
                            self._nx_graph.add_edge(fpath, target)

        return len(self._nx_graph.nodes)

    def _parse_python(self, content: str) -> tuple[list[dict], set[str]]:
        import re

        defs = []
        refs: set[str] = set()
        for i, line in enumerate(content.splitlines(), 1):
            stripped = line.strip()
            m = re.match(r"^(class|def|async\s+def)\s+(\w+)", stripped)
            if m:
                kind = "class" if m.group(1) == "class" else "function"
                defs.append({"name": m.group(2), "line": i, "kind": kind})
            m = re.match(r"^from\s+\S+\s+import\s+(.+)", stripped)
            if m:
                for name in re.findall(r"\b(\w+)\b", m.group(1)):
                    if name[0].isupper() or len(name) > 5:
                        refs.add(name)
            m = re.match(r"^import\s+(.+)", stripped)
            if m:
                for name in re.findall(r"\b(\w+)\b", m.group(1)):
                    refs.add(name)
        return defs, refs

    def _parse_javascript(self, content: str) -> tuple[list[dict], set[str]]:
        import re

        defs = []
        refs: set[str] = set()
        for i, line in enumerate(content.splitlines(), 1):
            stripped = line.strip()
            m = re.match(r"^(?:export\s+)?(?:default\s+)?(?:async\s+)?(?:function|class)\s+(\w+)", stripped)
            if m:
                kind = "class" if "class" in stripped else "function"
                defs.append({"name": m.group(1), "line": i, "kind": kind})
            m = re.match(r"^(?:export\s+)?(?:const|let|var)\s+(\w+)\s*=", stripped)
            if m and ("=>" in line or "function" in line):
                defs.append({"name": m.group(1), "line": i, "kind": "function"})
            m = re.match(r"^import\s+.*from\s+", stripped)
            if m:
                for name in re.findall(r"\b([A-Z]\w+)\b", stripped):
                    refs.add(name)
        return defs, refs

    def _parse_generic(self, content: str) -> tuple[list[dict], set[str]]:
        import re

        defs = []
        refs: set[str] = set()
        for i, line in enumerate(content.splitlines(), 1):
            stripped = line.strip()
            m = re.match(r"^(?:pub\s+)?(?:fn|func|def|function|class|struct|interface|type|enum)\s+(\w+)", stripped)
            if m:
                defs.append({"name": m.group(1), "line": i, "kind": "definition"})
        return defs, refs

    @property
    def file_count(self) -> int:
        return len(self._nx_graph.nodes) if self._nx_graph else 0

    @property
    def edge_count(self) -> int:
        return self._nx_graph.number_of_edges() if self._nx_graph else 0
