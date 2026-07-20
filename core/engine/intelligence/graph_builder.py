# engine/intelligence/graph_builder.py
"""Code graph builder — 4-phase construction pipeline.

Phase 1: Tree-sitter (instant) → file nodes, function nodes, rough import edges
Phase 2: LSP (30-60s) → accurate reference edges, replaces rough imports
Phase 3: LLM (background) → purpose, discipline, risks per file
Phase 4: Git (background) → commit history, decisions, ownership

Pass persist=False (default) for in-memory-only mode (tests, no DB needed).
Pass persist=True to also write graph_file, graph_function, and import edges
to SurrealDB after phase1.
"""

from __future__ import annotations

import logging
import os
import time
from typing import Any

import networkx as nx

from core.engine.core.llm import get_llm
from core.engine.intelligence.detector import SKIP_DIRS
from core.engine.scanner.ast_parser import LANG_MAP, parse_file

logger = logging.getLogger(__name__)

MAX_FILE_SIZE = 500_000  # Skip files over 500KB


def _rate_limit_wait(exc: Exception, default: float = 30.0) -> float:
    """Read the reset time from a 429 response header, else return default seconds."""
    try:
        headers = getattr(getattr(exc, "response", None), "headers", {})
        reset_ts = headers.get("anthropic-ratelimit-unified-reset")
        if reset_ts:
            wait = float(reset_ts) - time.time() + 2  # +2s buffer
            return max(2.0, min(wait, 300.0))  # clamp 2s–5min
    except Exception:
        pass
    return default


# Extensions we care about — superset of LANG_MAP keys
_KNOWN_EXTENSIONS: set[str] = set(LANG_MAP.keys()) | {
    ".py",
    ".pyi",
    ".ts",
    ".tsx",
    ".js",
    ".jsx",
    ".go",
    ".rs",
    ".rb",
    ".java",
    ".kt",
    ".scala",
    ".c",
    ".cpp",
    ".h",
    ".hpp",
    ".cs",
    ".php",
    ".swift",
    ".lua",
    ".zig",
}


class GraphBuilder:
    """Builds a code graph from a repository.

    Args:
        repo_path: Root directory of the repository.
        persist:   If True, write graph data to SurrealDB after phase1.
                   Default False — safe for tests that have no DB.
    """

    def __init__(self, repo_path: str, persist: bool = False) -> None:
        self._repo_path = os.path.abspath(repo_path)
        self._persist = persist
        self._files: list[dict] = []
        self._symbols: list[dict] = []
        self._imports: list[dict] = []
        self._nx_graph: nx.DiGraph = nx.DiGraph()
        self._module_summaries: dict[str, dict] = {}
        self._architectural_overview: dict | None = None

    # ------------------------------------------------------------------
    # Phase 1 — tree-sitter structural scan
    # ------------------------------------------------------------------

    def phase1_treesitter(self) -> dict:
        """Phase 1: Fast structural scan via tree-sitter.

        Returns stats dict: {files, functions, classes, imports}.
        """
        self._files = self._walk_files()
        stats = {"files": len(self._files), "functions": 0, "classes": 0, "imports": 0}

        for f in self._files:
            ext = os.path.splitext(f["path"])[1]
            lang = LANG_MAP.get(ext)
            if not lang:
                continue

            try:
                with open(f["full_path"], "rb") as fh:
                    content = fh.read()
                result = parse_file(content, lang)

                # File node
                self._nx_graph.add_node(f["path"], **{k: v for k, v in f.items() if k != "full_path"})

                # Function/method symbols
                for func in result.functions:
                    symbol = {
                        "name": func.name,
                        "kind": func.kind,
                        "file": f["path"],
                        "line_start": func.line_start,
                        "line_end": func.line_end,
                        "language": lang,
                    }
                    self._symbols.append(symbol)
                    stats["functions"] += 1
                    symbol_id = f"{f['path']}::{func.name}"
                    self._nx_graph.add_node(symbol_id, node_type="symbol", **symbol)
                    self._nx_graph.add_edge(f["path"], symbol_id, edge_type="contains")

                # Class symbols
                for cls in result.classes:
                    symbol = {
                        "name": cls.name,
                        "kind": "class",
                        "file": f["path"],
                        "line_start": cls.line_start,
                        "line_end": cls.line_end,
                        "language": lang,
                    }
                    self._symbols.append(symbol)
                    stats["classes"] += 1
                    symbol_id = f"{f['path']}::{cls.name}"
                    self._nx_graph.add_node(symbol_id, node_type="symbol", **symbol)
                    self._nx_graph.add_edge(f["path"], symbol_id, edge_type="contains")

                # Import records
                for imp in result.imports:
                    self._imports.append(
                        {
                            "from_file": f["path"],
                            "module": imp.module,
                            "name": imp.name,
                            "language": lang,
                        }
                    )
                    stats["imports"] += 1

            except Exception as exc:
                logger.debug("Failed to parse %s: %s", f["path"], exc)

        # Build rough edges from import data
        self._build_import_edges()

        return stats

    # ------------------------------------------------------------------
    # Phase 2 — LSP semantic reference edges
    # ------------------------------------------------------------------

    async def phase2_lsp(self, lsp_manager: Any) -> dict:
        """Phase 2: Replace rough edges with LSP-accurate references.

        1. Open all supported files in the LSP server
        2. Readiness check — poll until workspace/symbol returns results
        3. Query find_references for every public class/function
        4. Add accurate edges to the graph

        No timeout. No cap. Runs until complete.
        """
        import asyncio

        stats = {"references": 0, "files_opened": 0, "symbols_queried": 0, "symbols_found": 0}

        # Step 1: Open all files so pyright indexes them
        abs_repo = os.path.abspath(self._repo_path)
        for f in self._files:
            ext = os.path.splitext(f["path"])[1]
            lang = LANG_MAP.get(ext)
            if not lang or not lsp_manager.is_running(lang):
                continue
            full = os.path.join(abs_repo, f["path"]) if not os.path.isabs(f.get("full_path", "")) else f["full_path"]
            uri = f"file://{full}"
            try:
                with open(full, encoding="utf-8", errors="replace") as fh:
                    content = fh.read()
                await lsp_manager.notify_change(uri, content, lang)
                stats["files_opened"] += 1
            except Exception as exc:
                logger.debug("Failed to open %s in LSP: %s", f["path"], exc)

        logger.info("Phase 2: opened %d files, waiting for pyright to index...", stats["files_opened"])

        # Step 2: Readiness check — poll workspace/symbol with a known symbol
        # Find a class name that should exist
        test_name = None
        for s in self._symbols:
            if s.get("kind") == "class" and not s["name"].startswith("_"):
                test_name = s["name"]
                break

        if test_name:
            for wait in range(30):  # poll up to 30 times, 2s each = 60s max
                for lang in ["python", "typescript", "javascript"]:
                    if not lsp_manager.is_running(lang):
                        continue
                    ws = await lsp_manager.workspace_symbols(test_name, lang)
                    if ws:
                        logger.info("Phase 2: pyright ready after %ds (found '%s')", (wait + 1) * 2, test_name)
                        break
                else:
                    await asyncio.sleep(2)
                    continue
                break
            else:
                logger.warning("Phase 2: pyright never returned symbols after 60s — continuing anyway")
        else:
            # No classes found — wait a fixed time
            await asyncio.sleep(10)

        # Step 3: Query every public class and function — no cap
        query_names: list[str] = []
        seen = set()
        # Classes first (higher architectural value), then functions
        for s in self._symbols:
            if s.get("kind") == "class" and not s["name"].startswith("_") and s["name"] not in seen:
                query_names.append(s["name"])
                seen.add(s["name"])
        for s in self._symbols:
            if s.get("kind") == "function" and not s["name"].startswith("_") and s["name"] not in seen:
                query_names.append(s["name"])
                seen.add(s["name"])

        logger.info("Phase 2: querying %d unique symbols (no cap)...", len(query_names))

        for idx, name in enumerate(query_names):
            for lang in ["python", "typescript", "javascript"]:
                if not lsp_manager.is_running(lang):
                    continue

                ws_symbols = await lsp_manager.workspace_symbols(name, lang)
                exact = [s for s in ws_symbols if s.name == name]
                if not exact:
                    continue

                sym = exact[0]
                stats["symbols_found"] += 1
                stats["symbols_queried"] += 1

                try:
                    refs = await lsp_manager.find_references(
                        sym.location.uri,
                        sym.location.line,
                        sym.location.character,
                        lang,
                    )
                    for ref in refs:
                        ref_file = ref.uri.replace("file://", "")
                        sym_file = sym.location.uri.replace("file://", "")
                        try:
                            ref_rel = os.path.relpath(ref_file, abs_repo)
                            sym_rel = os.path.relpath(sym_file, abs_repo)
                        except ValueError:
                            continue
                        if ref_rel != sym_rel and not ref_rel.startswith(".."):
                            self._nx_graph.add_edge(
                                ref_rel,
                                sym_rel,
                                type="lsp_reference",
                                symbol=name,
                            )
                            stats["references"] += 1
                except Exception as exc:
                    logger.debug("find_references failed for %s: %s", name, exc)

                break  # found in this language

            # Progress every 100 symbols
            if (idx + 1) % 100 == 0:
                logger.info(
                    "Phase 2: %d/%d symbols queried, %d references so far",
                    idx + 1,
                    len(query_names),
                    stats["references"],
                )

        logger.info(
            "Phase 2 complete: %d references from %d symbols queried (%d found in workspace)",
            stats["references"],
            stats["symbols_queried"],
            stats["symbols_found"],
        )
        return stats

    # ------------------------------------------------------------------
    # Phase 3 — Three-tier LLM analysis
    # ------------------------------------------------------------------

    _ANALYSIS_SCHEMA_KEYS = {"purpose", "discipline", "quality_risks", "key_exports", "architectural_role"}

    async def phase3_analyze(self, product_id: str = "product:platform", num_workers: int = 5) -> dict:
        """Phase 3: Three-tier LLM analysis.

        3a: Haiku sub-agents analyze every file (full content, parallel workers)
        3b: Sonnet synthesizes per module/capability (grouped by directory)
        3c: Sonnet produces architectural overview + writes metadata to graph

        Args:
            num_workers: Parallel Haiku workers for Phase 3a (default 5)
        """
        import asyncio

        stats_3a = await self._phase3a_file_analysis(num_workers)

        # Cooldown — after bulk 3a, probe once and wait if still throttled
        analyzed = stats_3a.get("analyzed", 0)
        if analyzed > 500:
            logger.info("Phase 3a→3b: probing rate limit status...")
            try:
                probe_llm = get_llm()
                await probe_llm.complete_json('{"ok": true}', model="claude-haiku-4-5-20251001")
                logger.info("Phase 3a→3b: rate limit OK, proceeding")
            except Exception as exc:
                wait = _rate_limit_wait(exc, default=60.0)
                logger.info("Phase 3a→3b: rate limited, waiting %ds...", wait)
                await asyncio.sleep(wait)

        stats_3b = await self._phase3b_module_synthesis()
        stats_3c = await self._phase3c_architectural_overview()

        return {
            "phase3a": stats_3a,
            "phase3b": stats_3b,
            "phase3c": stats_3c,
        }

    async def _phase3a_file_analysis(self, num_workers: int = 5) -> dict:
        """Phase 3a: Haiku reads every file. Worker pool, full content, JSON validated."""
        import asyncio
        import json

        from core.engine.intelligence.model_router import route_model

        model = route_model("code_analysis")  # routes to Haiku
        stats = {"analyzed": 0, "skipped": 0, "errors": 0, "retried": 0, "total": 0}
        stats_lock = asyncio.Lock()

        queue: asyncio.Queue = asyncio.Queue()
        for f in self._files:
            stats["total"] += 1
            try:
                with open(f["full_path"], encoding="utf-8", errors="replace") as fh:
                    content = fh.read()
                if len(content) < 50:
                    stats["skipped"] += 1
                    continue
                await queue.put((f, content))
            except Exception:
                stats["skipped"] += 1

        queued = queue.qsize()
        logger.info("Phase 3a: %d files queued, %d Haiku workers", queued, num_workers)

        # Cacheable prefix — identical across all 2800+ calls.
        # Marked with cache_control so Anthropic reuses the KV cache.
        # Only uncached input tokens count against rate limits.
        _CACHED_SCHEMA = (
            "Analyze this source file. Return ONLY valid JSON:\n"
            '{"purpose": "one sentence", "discipline": "one of: security, testing, '
            "ux, performance, devops, data, accessibility, documentation, architecture, "
            "api_design, data_modeling, business_logic, integration, error_handling, "
            "observability, configuration, deployment, versioning, code_conventions, "
            'dependency_management", "quality_risks": ["risk1"], '
            '"key_exports": ["name1"], "architectural_role": "how it fits"}\n\n'
        )

        async def worker(worker_id: int) -> None:
            from core.engine.runtime.model_adapter import ClaudeAdapter

            adapter = ClaudeAdapter(model=model)

            while True:
                try:
                    f, content = queue.get_nowait()
                except asyncio.QueueEmpty:
                    return

                # Split message: cached schema prefix + uncached file content.
                # Cache prefix is reused across all workers — only charged once per window.
                messages = [
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "text",
                                "text": _CACHED_SCHEMA,
                                "cache_control": {"type": "ephemeral"},
                            },
                            {
                                "type": "text",
                                "text": f"File: {f['path']}\n```\n{content}\n```",
                            },
                        ],
                    }
                ]

                for attempt in range(3):
                    try:
                        result_msg = None
                        async for msg in adapter.call_model(
                            system="You are a code analyzer. Return only valid JSON. No markdown.",
                            messages=messages,
                            tools=[],
                            thinking="disabled",
                        ):
                            result_msg = msg

                        if result_msg and result_msg.content:
                            text = result_msg.content.strip()
                            if text.startswith("```"):
                                text = text.split("\n", 1)[1].rsplit("```", 1)[0].strip()
                            analysis = json.loads(text)

                            # Schema validation — retry if missing required keys
                            if not self._ANALYSIS_SCHEMA_KEYS.issubset(analysis.keys()):
                                if attempt < 2:
                                    async with stats_lock:
                                        stats["retried"] += 1
                                    continue
                                # Accept partial on last attempt
                            f["analysis"] = analysis
                            async with stats_lock:
                                stats["analyzed"] += 1
                            break
                    except json.JSONDecodeError:
                        if attempt < 2:
                            async with stats_lock:
                                stats["retried"] += 1
                            continue
                        async with stats_lock:
                            stats["errors"] += 1
                        break
                    except Exception as exc:
                        error_code = getattr(exc, "status_code", 0)
                        if error_code in (429, 401) and attempt < 2:
                            # 429: rate limit — back off
                            # 401: OAuth token expired — wait for Claude Code to refresh it
                            await asyncio.sleep((attempt + 1) * 5)
                            if error_code == 401:
                                adapter = ClaudeAdapter(model=model)  # fresh client reads new token
                        else:
                            async with stats_lock:
                                stats["errors"] += 1
                            logger.debug("Worker %d: %s failed: %s", worker_id, f["path"], exc)
                            break

                queue.task_done()
                remaining = queue.qsize()
                done = queued - remaining
                if done % 100 == 0 and done > 0:
                    logger.info(
                        "Phase 3a: %d/%d done (%d errors, %d retried)", done, queued, stats["errors"], stats["retried"]
                    )

        workers = [asyncio.create_task(worker(i)) for i in range(num_workers)]
        await asyncio.gather(*workers)
        logger.info(
            "Phase 3a complete: %d/%d analyzed, %d errors, %d retried",
            stats["analyzed"],
            stats["total"],
            stats["errors"],
            stats["retried"],
        )
        return stats

    async def _phase3b_module_synthesis(self) -> dict:
        """Phase 3b: Haiku synthesizes per module — one call per directory group."""
        import asyncio

        from core.engine.intelligence.model_router import route_model

        model = route_model("module_synthesis")  # Haiku — bounded input synthesis

        # Group analyzed files by top-level directory
        modules: dict[str, list[dict]] = {}
        for f in self._files:
            if not f.get("analysis"):
                continue
            parts = f["path"].split("/")
            module = "/".join(parts[:2]) if len(parts) >= 2 else parts[0]
            modules.setdefault(module, []).append(f)

        stats = {"modules": 0, "errors": 0, "retried": 0, "skipped": 0}
        self._module_summaries: dict[str, dict] = {}

        llm = get_llm()

        for module, files in modules.items():
            if len(files) < 2:
                stats["skipped"] += 1
                continue  # skip single-file modules

            # Build summary input from Haiku analyses
            file_summaries = []
            for f in files:
                a = f["analysis"]
                file_summaries.append(
                    f"- {f['path']}: {a.get('purpose', '?')} [{a.get('discipline', '?')}] "
                    f"risks: {a.get('quality_risks', [])}"
                )

            prompt = (
                f"These are file analyses from the '{module}' module.\n"
                "Synthesize into a module-level understanding. Return JSON:\n"
                '{"purpose": "what this module does", "key_files": ["most important files"], '
                '"internal_patterns": ["architectural patterns used"], '
                '"quality_gaps": ["cross-file quality issues"], '
                '"dependencies": ["external modules this depends on"], '
                '"risk_summary": "highest risk in this module"}\n\n'
                "Files:\n" + "\n".join(file_summaries)
            )

            for attempt in range(3):
                try:
                    result = await llm.complete_json(prompt, model=model)
                    self._module_summaries[module] = result
                    stats["modules"] += 1
                    break
                except Exception as exc:
                    error_code = getattr(exc, "status_code", 0)
                    if error_code == 429 and attempt < 2:
                        stats["retried"] += 1
                        wait = _rate_limit_wait(exc, default=(attempt + 1) * 15)
                        logger.info("Phase 3b: rate limited, waiting %ds...", wait)
                        await asyncio.sleep(wait)
                        continue
                    stats["errors"] += 1
                    logger.debug("Phase 3b: module %s failed (attempt %d): %s", module, attempt + 1, exc)
                    break

        logger.info(
            "Phase 3b complete: %d modules synthesized, %d errors, %d retried, %d skipped",
            stats["modules"],
            stats["errors"],
            stats["retried"],
            stats["skipped"],
        )
        return stats

    async def _phase3c_architectural_overview(self) -> dict:
        """Phase 3c: Sonnet produces architectural overview from module summaries.

        Writes metadata back to graph nodes: subsystem labels, blast radius,
        quality gap annotations.
        """

        if not self._module_summaries:
            return {"status": "skipped", "reason": "no module summaries"}

        from core.engine.intelligence.model_router import route_model

        model = route_model("architectural_overview")  # Sonnet for cross-module synthesis

        # Build input from module summaries
        module_lines = []
        for module, summary in self._module_summaries.items():
            module_lines.append(
                f"## {module}\n"
                f"Purpose: {summary.get('purpose', '?')}\n"
                f"Key files: {summary.get('key_files', [])}\n"
                f"Patterns: {summary.get('internal_patterns', [])}\n"
                f"Quality gaps: {summary.get('quality_gaps', [])}\n"
                f"Risk: {summary.get('risk_summary', '?')}"
            )

        prompt = (
            "These are module-level analyses of a codebase.\n"
            "Produce an architectural overview. Return JSON:\n"
            '{"subsystems": [{"name": "...", "modules": ["..."], "role": "..."}], '
            '"critical_paths": ["highest blast radius chains"], '
            '"cross_cutting_concerns": ["concerns spanning multiple modules"], '
            '"quality_gaps": [{"area": "...", "severity": "high/medium/low", "description": "..."}], '
            '"architectural_risks": ["top risks"]}\n\n' + "\n\n".join(module_lines)
        )

        import asyncio

        llm = get_llm()

        for attempt in range(3):
            try:
                result = await llm.complete_json(prompt, model=model, max_tokens=16384)

                # Write architectural metadata back to graph nodes
                for subsystem in result.get("subsystems", []):
                    for module in subsystem.get("modules", []):
                        if module in self._nx_graph:
                            self._nx_graph.nodes[module]["subsystem"] = subsystem.get("name", "")
                            self._nx_graph.nodes[module]["architectural_role"] = subsystem.get("role", "")

                self._architectural_overview = result
                logger.info(
                    "Phase 3c complete: %d subsystems, %d quality gaps identified",
                    len(result.get("subsystems", [])),
                    len(result.get("quality_gaps", [])),
                )
                return {
                    "status": "complete",
                    "subsystems": len(result.get("subsystems", [])),
                    "quality_gaps": len(result.get("quality_gaps", [])),
                }
            except Exception as exc:
                error_code = getattr(exc, "status_code", 0)
                if error_code == 429 and attempt < 2:
                    wait = _rate_limit_wait(exc, default=(attempt + 1) * 30)
                    logger.info("Phase 3c: rate limited, waiting %ds...", wait)
                    await asyncio.sleep(wait)
                    continue
                logger.warning("Phase 3c failed (attempt %d): %s", attempt + 1, exc)
                return {"status": "error", "error": str(exc)}

        return {"status": "error", "error": "exhausted retries"}

    # ------------------------------------------------------------------
    # SurrealDB persistence
    # ------------------------------------------------------------------

    @staticmethod
    async def clear_graph(graph_id: str) -> dict:
        """Delete all records for a graph_id from code intelligence tables."""
        from core.engine.core.db import pool

        tables = ["graph_file", "graph_function", "graph_module", "graph_architecture", "imports"]
        stats: dict[str, int] = {}
        try:
            async with pool.connection() as db:
                for table in tables:
                    if table == "imports":
                        # Relation table — delete edges where source file has this graph_id
                        await db.query(
                            "DELETE imports WHERE in.graph_id = $gid OR out.graph_id = $gid",
                            {"gid": graph_id},
                        )
                    else:
                        await db.query(
                            f"DELETE {table} WHERE graph_id = $gid",  # noqa: S608
                            {"gid": graph_id},
                        )
                    stats[table] = 0  # SurrealDB DELETE doesn't return count
                # Also clear graph entry
                await db.query(
                    "DELETE graph WHERE graph_id = $gid",
                    {"gid": graph_id},
                )
            logger.info("Cleared graph %s: %s", graph_id, list(tables))
        except Exception as exc:
            logger.warning("clear_graph failed for %s: %s", graph_id, exc)
        return stats

    async def write_to_db(self, graph_id: str = "ace") -> dict:
        """Write full pipeline results to SurrealDB.

        Writes: graph_file (with Phase 3a analysis), graph_function, imports edges,
        graph_module (Phase 3b), graph_architecture (Phase 3c), graph metadata.
        """
        from surrealdb import RecordID

        from core.engine.core.db import pool
        from core.engine.scanner.scanner import _slug

        stats = {
            "files_written": 0,
            "symbols_written": 0,
            "imports_written": 0,
            "modules_written": 0,
            "architecture_written": 0,
        }

        try:
            async with pool.connection() as db:
                # --- graph_file (Phase 1 + Phase 3a analysis) ---
                for f in self._files:
                    slug = _slug(f["path"])
                    analysis = f.get("analysis") or {}
                    try:
                        await db.query(
                            """UPSERT $id SET
                                path = $path, name = $name, extension = $ext,
                                size_bytes = $size, graph_id = $gid,
                                purpose = $purpose, discipline = $discipline,
                                quality_risks = $risks, key_exports = $exports,
                                architectural_role = $role,
                                analyzed_at = IF $analyzed THEN time::now() ELSE None END""",
                            {
                                "id": RecordID("graph_file", slug),
                                "path": f["path"],
                                "name": f["name"],
                                "ext": f["extension"],
                                "size": f["size_bytes"],
                                "gid": graph_id,
                                "purpose": analysis.get("purpose"),
                                "discipline": analysis.get("discipline"),
                                "risks": analysis.get("quality_risks", []),
                                "exports": analysis.get("key_exports", []),
                                "role": analysis.get("architectural_role"),
                                "analyzed": bool(analysis),
                            },
                        )
                        stats["files_written"] += 1
                    except Exception as exc:
                        logger.debug("Failed to write file %s: %s", f["path"], exc)

                # --- graph_function (Phase 1 symbols) ---
                for sym in self._symbols:
                    file_slug = _slug(sym["file"])
                    sym_slug = _slug(f"{sym['file']}_{sym['name']}")
                    try:
                        await db.query(
                            """UPSERT $id SET
                                name = $name, file = $file,
                                line_start = $ls, line_end = $le,
                                kind = $kind, language = $lang,
                                graph_id = $gid""",
                            {
                                "id": RecordID("graph_function", sym_slug),
                                "name": sym["name"],
                                "file": RecordID("graph_file", file_slug),
                                "ls": sym["line_start"],
                                "le": sym["line_end"],
                                "kind": sym["kind"],
                                "lang": sym["language"],
                                "gid": graph_id,
                            },
                        )
                        stats["symbols_written"] += 1
                    except Exception as exc:
                        logger.debug("Failed to write symbol %s: %s", sym["name"], exc)

                # --- imports edges (Phase 1 + Phase 2 LSP) ---
                for imp in self._imports:
                    from_slug = _slug(imp["from_file"])
                    for f in self._files:
                        module_name = os.path.splitext(os.path.basename(f["path"]))[0]
                        if (
                            module_name == imp["module"]
                            or f["path"].replace("/", ".").replace(".py", "") == imp["module"]
                        ):
                            to_slug = _slug(f["path"])
                            try:
                                await db.query(
                                    """RELATE $from -> imports -> $to SET
                                        import_name = $name, source = 'graph_builder'""",
                                    {
                                        "from": RecordID("graph_file", from_slug),
                                        "to": RecordID("graph_file", to_slug),
                                        "name": imp.get("name") or imp["module"],
                                    },
                                )
                                stats["imports_written"] += 1
                            except Exception as exc:
                                logger.debug("Failed to write import edge: %s", exc)
                            break

                # --- graph_module (Phase 3b) ---
                for module_path, summary in (self._module_summaries or {}).items():
                    mod_slug = _slug(f"{graph_id}_{module_path}")
                    try:
                        await db.query(
                            """UPSERT $id SET
                                module_path = $path, graph_id = $gid,
                                purpose = $purpose, key_files = $key_files,
                                internal_patterns = $patterns, quality_gaps = $gaps,
                                dependencies = $deps, risk_summary = $risk,
                                synthesized_at = time::now()""",
                            {
                                "id": RecordID("graph_module", mod_slug),
                                "path": module_path,
                                "gid": graph_id,
                                "purpose": summary.get("purpose"),
                                "key_files": summary.get("key_files", []),
                                "patterns": summary.get("internal_patterns", []),
                                "gaps": summary.get("quality_gaps", []),
                                "deps": summary.get("dependencies", []),
                                "risk": summary.get("risk_summary"),
                            },
                        )
                        stats["modules_written"] += 1
                    except Exception as exc:
                        logger.debug("Failed to write module %s: %s", module_path, exc)

                # --- graph_architecture (Phase 3c) ---
                arch = getattr(self, "_architectural_overview", None)
                if arch:
                    arch_slug = _slug(graph_id)
                    try:
                        await db.query(
                            """UPSERT $id SET
                                graph_id = $gid, subsystems = $subsystems,
                                critical_paths = $paths, cross_cutting = $cross,
                                quality_gaps = $gaps, architectural_risks = $risks,
                                synthesized_at = time::now()""",
                            {
                                "id": RecordID("graph_architecture", arch_slug),
                                "gid": graph_id,
                                "subsystems": arch.get("subsystems", []),
                                "paths": arch.get("critical_paths", []),
                                "cross": arch.get("cross_cutting_concerns", []),
                                "gaps": arch.get("quality_gaps", []),
                                "risks": arch.get("architectural_risks", []),
                            },
                        )
                        stats["architecture_written"] += 1
                    except Exception as exc:
                        logger.debug("Failed to write architecture: %s", exc)

                # --- graph metadata ---
                inst_slug = _slug(graph_id)
                await db.query(
                    """UPSERT $id SET
                        graph_id = $gid, name = $name,
                        repo_path = $path, mode = $mode,
                        node_count = $nodes, scanned_at = time::now()""",
                    {
                        "id": RecordID("graph", inst_slug),
                        "gid": graph_id,
                        "name": graph_id,
                        "path": self._repo_path,
                        "mode": "temporary" if graph_id.startswith("inspiration:") else "permanent",
                        "nodes": len(self._files),
                    },
                )

        except Exception as exc:
            logger.warning("write_to_db failed: %s", exc)

        logger.info(
            "write_to_db(%s): %d files, %d symbols, %d imports, %d modules, %d arch",
            graph_id,
            stats["files_written"],
            stats["symbols_written"],
            stats["imports_written"],
            stats["modules_written"],
            stats["architecture_written"],
        )
        return stats

    # ------------------------------------------------------------------
    # Graph analytics
    # ------------------------------------------------------------------

    def compute_centrality(self) -> dict[str, float]:
        """Compute PageRank centrality on the code graph."""
        if not self._nx_graph.nodes:
            return {}
        try:
            return nx.pagerank(self._nx_graph, alpha=0.85)
        except Exception:
            return {n: 1.0 / max(len(self._nx_graph), 1) for n in self._nx_graph.nodes}

    # ------------------------------------------------------------------
    # Accessors
    # ------------------------------------------------------------------

    def get_symbols(self) -> list[dict]:
        """Return all extracted symbols (functions, methods, classes)."""
        return list(self._symbols)

    def get_imports(self) -> list[dict]:
        """Return all extracted import records."""
        return list(self._imports)

    def get_files(self) -> list[dict]:
        """Return all scanned file records."""
        return list(self._files)

    @property
    def graph(self) -> nx.DiGraph:
        """The underlying NetworkX directed graph."""
        return self._nx_graph

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _walk_files(self) -> list[dict]:
        """Walk the repo, returning file metadata for supported extensions."""
        files = []
        for dirpath, dirnames, filenames in os.walk(self._repo_path):
            dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS and not d.startswith(".")]
            for fname in filenames:
                full_path = os.path.join(dirpath, fname)
                rel_path = os.path.relpath(full_path, self._repo_path)
                _, ext = os.path.splitext(fname)

                if ext not in _KNOWN_EXTENSIONS:
                    continue
                try:
                    size = os.path.getsize(full_path)
                except OSError:
                    continue
                if size > MAX_FILE_SIZE:
                    continue

                files.append(
                    {
                        "path": rel_path,
                        "full_path": full_path,
                        "name": fname,
                        "extension": ext,
                        "size_bytes": size,
                    }
                )
        return files

    # ------------------------------------------------------------------
    # Incremental updates
    # ------------------------------------------------------------------

    def incremental_update(self, changed_files: list[str]) -> dict:
        """Re-index only changed files. Returns stats."""
        stats = {"updated": 0, "symbols_added": 0}

        for rel_path in changed_files:
            full_path = os.path.join(self._repo_path, rel_path)
            if not os.path.exists(full_path):
                # File deleted — remove from graph
                if rel_path in self._nx_graph:
                    self._nx_graph.remove_node(rel_path)
                self._symbols = [s for s in self._symbols if s["file"] != rel_path]
                self._files = [f for f in self._files if f["path"] != rel_path]
                continue

            # Remove old edges for this file
            if rel_path in self._nx_graph:
                edges_to_remove = list(self._nx_graph.edges(rel_path))
                self._nx_graph.remove_edges_from(edges_to_remove)

            # Re-parse the file
            ext = os.path.splitext(rel_path)[1]
            lang = LANG_MAP.get(ext, "")
            if not lang:
                continue

            try:
                with open(full_path, "rb") as fh:
                    content = fh.read()
                result = parse_file(content, lang)

                # Ensure the file node exists in the graph
                if rel_path not in self._nx_graph:
                    try:
                        size = os.path.getsize(full_path)
                    except OSError:
                        size = 0
                    self._nx_graph.add_node(
                        rel_path,
                        path=rel_path,
                        name=os.path.basename(rel_path),
                        extension=ext,
                        size_bytes=size,
                    )
                    # Update _files list too
                    self._files = [f for f in self._files if f["path"] != rel_path]
                    self._files.append(
                        {
                            "path": rel_path,
                            "full_path": full_path,
                            "name": os.path.basename(rel_path),
                            "extension": ext,
                            "size_bytes": size,
                        }
                    )

                # Remove old symbols for this file
                self._symbols = [s for s in self._symbols if s["file"] != rel_path]

                # Add new symbols
                for func in result.functions:
                    self._symbols.append(
                        {
                            "name": func.name,
                            "kind": func.kind,
                            "file": rel_path,
                            "line_start": func.line_start,
                            "line_end": func.line_end,
                            "language": lang,
                        }
                    )
                    stats["symbols_added"] += 1

                for cls in result.classes:
                    self._symbols.append(
                        {
                            "name": cls.name,
                            "kind": "class",
                            "file": rel_path,
                            "line_start": cls.line_start,
                            "line_end": cls.line_end,
                            "language": lang,
                        }
                    )
                    stats["symbols_added"] += 1

                # Rebuild import edges for this file
                self._build_import_edges()
                stats["updated"] += 1
            except Exception as exc:
                logger.debug("Incremental update failed for %s: %s", rel_path, exc)

        return stats

    def _build_import_edges(self) -> None:
        """Build rough dependency edges from parsed import data."""
        # Index: symbol name → list of files that define it
        symbol_files: dict[str, list[str]] = {}
        for s in self._symbols:
            symbol_files.setdefault(s["name"], []).append(s["file"])

        # Index: module name (basename without ext) → file path
        module_to_file: dict[str, str] = {}
        for f in self._files:
            mod = os.path.splitext(os.path.basename(f["path"]))[0]
            module_to_file[mod] = f["path"]

        for imp in self._imports:
            # Strategy 1: resolve by imported symbol name
            if imp.get("name") and imp["name"] in symbol_files:
                for target in symbol_files[imp["name"]]:
                    if target != imp["from_file"]:
                        self._nx_graph.add_edge(
                            imp["from_file"],
                            target,
                            edge_type="imports",
                            symbol=imp["name"],
                        )
            # Strategy 2: resolve by module basename
            elif imp["module"] in module_to_file:
                target = module_to_file[imp["module"]]
                if target != imp["from_file"]:
                    self._nx_graph.add_edge(
                        imp["from_file"],
                        target,
                        edge_type="imports",
                        symbol=imp["module"],
                    )
