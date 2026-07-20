# engine/runtime/init_project.py
"""ace init — bootstrap a project's intelligence graph.

Two-phase approach:
  Phase 1 (fast, blocking): Tree-sitter code scan + CLAUDE.md import
  Phase 2 (slow, background): Git history analysis via pydriller

Phase 1 gives you a working code graph in seconds. Phase 2 enriches it
with commit history, decisions, and file ownership in the background.
"""

from __future__ import annotations

import asyncio
import logging
import os
from typing import Any

from core.engine.core.db import pool

logger = logging.getLogger(__name__)


async def _background_analyze(builder: Any, product_id: str, graph_id: str = "default") -> None:
    """Background LLM analysis of all files (Phase 3).

    After phase3 completes, write_to_db() is called again to persist the
    enriched data (file purposes, module summaries, architecture overview).
    Phase 1 data is already in DB; this second write upserts with Phase 3 fields.
    """
    try:
        stats = await builder.phase3_analyze(product_id=product_id)
        logger.info("Phase 3 complete: %d files analyzed", stats.get("analyzed", 0))
    except Exception as exc:
        logger.warning("Background analysis failed: %s", exc)
        return

    try:
        await builder.write_to_db(graph_id=graph_id)
        logger.info("Phase 3 data persisted to SurrealDB (graph_id=%s)", graph_id)
    except Exception as exc:
        logger.warning("Phase 3 write_to_db failed: %s", exc)


async def init_project(
    repo_path: str = ".",
    product_id: str = "product:platform",
    import_claude_md: bool = True,
    include_git_history: bool = True,
    analyze_files: bool = False,
    analyze_foreground: bool = False,
) -> dict:
    """Bootstrap a project's intelligence graph.

    Returns summary of what was seeded.
    """
    repo_path = os.path.abspath(repo_path)
    results = {
        "repo_path": repo_path,
        "product_id": product_id,
        "phase1_files": 0,
        "phase1_functions": 0,
        "phase1_imports": 0,
        "capabilities": 0,
        "claude_md_imported": False,
        "git_history": "skipped" if not include_git_history else "background",
    }

    # ------------------------------------------------------------------
    # Phase 1: Fast code scan (tree-sitter AST — no git history)
    # ------------------------------------------------------------------
    logger.info("Phase 1: Scanning code structure at %s ...", repo_path)
    try:
        scan_result = await _fast_code_scan(repo_path)
        results["phase1_files"] = scan_result.get("files_created", 0)
        results["phase1_functions"] = scan_result.get("functions_created", 0)
        results["phase1_imports"] = scan_result.get("imports_created", 0)
        logger.info(
            "Phase 1 complete: %d files, %d functions, %d imports",
            results["phase1_files"],
            results["phase1_functions"],
            results["phase1_imports"],
        )
        # Link the default graph record to this product so capability mapper can find it
        try:
            async with pool.connection() as db:
                await db.query(
                    """
                    UPDATE graph SET product = <record>$product
                    WHERE graph_id = 'default' AND repo_path = $path
                    """,
                    {"product": product_id, "path": repo_path},
                )
        except Exception as exc:
            logger.debug("Graph product link failed (non-fatal): %s", exc)
    except Exception as exc:
        logger.warning("Phase 1 scan failed: %s", exc)
        results["phase1_files"] = -1

    # ------------------------------------------------------------------
    # Phase 3: LLM analysis (optional, background — doesn't block)
    # ------------------------------------------------------------------
    if analyze_files:
        logger.info("Phase 3: LLM analysis (%s)...", "foreground" if analyze_foreground else "background")
        try:
            from core.engine.intelligence.graph_builder import GraphBuilder

            builder = GraphBuilder(repo_path)
            builder.phase1_treesitter()  # rebuild (fast)
            if analyze_foreground:
                await _background_analyze(builder, product_id, graph_id="default")
                results["analysis"] = "complete"
            else:
                loop = asyncio.get_running_loop()
                loop.create_task(_background_analyze(builder, product_id, graph_id="default"))
                results["analysis"] = "background"
        except Exception as exc:
            logger.warning("LLM analysis queue failed: %s", exc)

    # ------------------------------------------------------------------
    # Phase 2: Git history (background — doesn't block)
    # ------------------------------------------------------------------
    if include_git_history:
        logger.info("Phase 2: Git history scan queued in background...")
        try:
            loop = asyncio.get_running_loop()
            loop.create_task(_background_git_scan(repo_path))
        except Exception as exc:
            logger.warning("Failed to queue git history scan: %s", exc)
            results["git_history"] = f"failed: {exc}"

    # ------------------------------------------------------------------
    # Capabilities detection
    # ------------------------------------------------------------------
    try:
        from core.engine.product.capability_mapper import CapabilityMapper

        mapper = CapabilityMapper(pool)
        caps = await mapper.bootstrap_from_graph(product_id)
        results["capabilities"] = len(caps) if caps else 0
        logger.info("Mapped %d capabilities", results["capabilities"])
    except Exception as exc:
        logger.warning("Capability mapping failed (non-critical): %s", exc)

    # ------------------------------------------------------------------
    # CLAUDE.md import
    # ------------------------------------------------------------------
    if import_claude_md:
        for candidate in ["CLAUDE.md", ".claude/CLAUDE.md"]:
            claude_md_path = os.path.join(repo_path, candidate)
            if os.path.exists(claude_md_path):
                try:
                    await _import_claude_md(claude_md_path, product_id)
                    results["claude_md_imported"] = True
                    logger.info("Imported %s as graph observations", candidate)
                except Exception as exc:
                    logger.warning("CLAUDE.md import failed: %s", exc)
                break

    return results


async def _fast_code_scan(repo_path: str, graph_id: str = "default") -> dict:
    """Phase 1: Fast scan using the intelligence GraphBuilder pipeline.

    Uses tree-sitter for structural extraction, then optionally persists
    to SurrealDB via GraphBuilder.write_to_db().
    """
    from core.engine.intelligence.graph_builder import GraphBuilder

    repo_path = os.path.abspath(repo_path)
    builder = GraphBuilder(repo_path)
    stats = builder.phase1_treesitter()

    # Persist to SurrealDB (best-effort — failure is non-fatal)
    try:
        await builder.write_to_db(graph_id=graph_id)
    except Exception as exc:
        logger.debug("write_to_db skipped (no DB?): %s", exc)

    # Compute centrality for high-value file detection
    centrality = builder.compute_centrality()
    stats["high_centrality_files"] = sum(1 for s in centrality.values() if s > 0.01)

    # Map legacy keys expected by callers
    stats["files_created"] = stats.get("files", 0)
    stats["functions_created"] = stats.get("functions", 0) + stats.get("classes", 0)
    stats["imports_created"] = stats.get("imports", 0)

    return stats


async def _background_git_scan(repo_path: str) -> None:
    """Phase 2: Git history in background thread (pydriller is blocking)."""
    loop = asyncio.get_running_loop()

    def _run():
        import asyncio as _asyncio

        _loop = _asyncio.new_event_loop()
        try:
            from core.engine.scanner.scanner import scan_repo

            _loop.run_until_complete(scan_repo(repo_path))
        except Exception as exc:
            # scan_repo uses the module-level pool (bound to main loop) — this
            # fails when run in a thread's own event loop. Non-fatal; git
            # history is enrichment only.
            logger.debug("Background git scan skipped (event loop mismatch): %s", exc)
        finally:
            _loop.close()

    await loop.run_in_executor(None, _run)
    logger.info("Background git history scan complete for %s", repo_path)


async def _import_claude_md(path: str, product_id: str) -> None:
    """Parse a CLAUDE.md file and write its sections as observations."""
    content = open(path, encoding="utf-8").read()
    if not content.strip():
        return

    sections = []
    current_section = ""
    current_title = ""
    for line in content.splitlines():
        if line.startswith("## "):
            if current_section.strip():
                sections.append({"title": current_title, "content": current_section.strip()})
            current_title = line[3:].strip()
            current_section = ""
        else:
            current_section += line + "\n"
    if current_section.strip():
        sections.append({"title": current_title, "content": current_section.strip()})

    try:
        async with pool.connection() as db:
            for section in sections:
                if len(section["content"]) < 10:
                    continue
                await db.query(
                    """CREATE observation SET
                        content = $content,
                        observation_type = 'convention',
                        confidence = 0.95,
                        discipline_hint = 'code_conventions',
                        source_memory = 'claude_md_import',
                        synthesized = false,
                        created_at = time::now()""",
                    {
                        "product": product_id,
                        "content": f"[{section['title']}] {section['content'][:2000]}",
                    },
                )
    except Exception as exc:
        logger.warning("Failed to write CLAUDE.md observations: %s", exc)
