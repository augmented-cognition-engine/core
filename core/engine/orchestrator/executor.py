# engine/orchestrator/executor.py
"""Execute a task: classify → load intelligence → call LLM → return result.

Creates a task record in SurrealDB with intelligence_loaded snapshot.
"""

from __future__ import annotations

import asyncio
import logging
import os
import re
from pathlib import Path
from typing import Any

from core.engine.core.config import settings
from core.engine.core.db import parse_rows, pool
from core.engine.core.llm import llm
from core.engine.orchestrator.archetypes import ARCHETYPE_INSTRUCTIONS, MODE_INSTRUCTIONS
from core.engine.orchestrator.classifier import classify_task
from core.engine.orchestrator.loader import load_intelligence

# ---------------------------------------------------------------------------
# Code graph cache — avoids rebuilding the TreeSitter graph on every task.
#
# Cache key: resolved absolute path of root.
# Cache value: (max_mtime_at_build, GraphBuilder, centrality_dict)
#
# Invalidation: recomputed max mtime of all .py files is compared against
# the cached value.  When any source file is saved, the cache auto-invalidates
# on the next call.  Mtime scan cost: ~50-200 ms on SSD (acceptable vs the
# 30-60 s rebuild it avoids).
# ---------------------------------------------------------------------------
_GRAPH_CACHE: dict[str, tuple[float, Any, dict[str, float]]] = {}
_SKIP_DIRS = {".venv", "__pycache__", ".git", "node_modules", ".mypy_cache", ".pytest_cache"}


def _find_source_root(start: str | Path = ".") -> Path | None:
    """Resolve an actual project checkout for optional code-context scanning.

    Packaged runtimes contain ACE's installed sources but are not necessarily
    running *for* a source repository.  Scanning their working directory is
    irrelevant and unsafe: tree-sitter native faults cannot be caught by the
    surrounding Python exception handler.  Match the orchestration risk-context
    boundary and scan only a checkout identified by both Git and project metadata.
    """

    current = Path(start).resolve()
    for candidate in (current, *current.parents):
        if (candidate / ".git").exists() and (candidate / "pyproject.toml").is_file():
            return candidate
    return None


def _max_source_mtime(root: str) -> float:
    """Return the maximum mtime of any .py file under root (fast scandir walk)."""
    max_mtime = 0.0
    try:
        for entry in os.scandir(root):
            if entry.is_dir(follow_symlinks=False):
                if entry.name not in _SKIP_DIRS:
                    sub = _max_source_mtime(entry.path)
                    if sub > max_mtime:
                        max_mtime = sub
            elif entry.name.endswith(".py") and entry.is_file(follow_symlinks=False):
                mtime = entry.stat().st_mtime
                if mtime > max_mtime:
                    max_mtime = mtime
    except (PermissionError, OSError):
        pass
    return max_mtime


def _get_or_build_graph(root: str = ".") -> tuple[Any, dict[str, float]]:
    """Return (GraphBuilder, centrality) — rebuilt only when source files change."""
    import networkx as nx

    from core.engine.intelligence.graph_builder import GraphBuilder

    abs_root = os.path.abspath(root)
    current_mtime = _max_source_mtime(abs_root)
    cached = _GRAPH_CACHE.get(abs_root)

    if cached is not None and cached[0] >= current_mtime:
        return cached[1], cached[2]

    # Cache miss or stale — rebuild
    builder = GraphBuilder(abs_root)
    builder.phase1_treesitter()
    try:
        centrality: dict[str, float] = nx.pagerank(builder.graph, alpha=0.85)
    except Exception:
        centrality = {}

    _GRAPH_CACHE[abs_root] = (current_mtime, builder, centrality)
    logging.debug(
        "Code graph rebuilt: %d nodes, root=%s",
        len(builder.graph.nodes),
        abs_root,
    )
    return builder, centrality


def _extract_matched_files(description: str, root: str = ".") -> list[str]:
    """Run TreeSitter analysis to find files relevant to this task description.

    Ranks candidates by (basename token overlap DESC, centrality DESC) so
    semantically-named files (e.g. multiphase.py for a "multi-phase" query)
    surface ahead of generic high-centrality hubs.  Bypasses the context_files
    cap in code_context() by working directly from matched_files.

    Only file-level nodes are returned (symbol nodes containing '::' excluded).

    Returns a list of file paths. Never raises — returns [] on failure.
    """
    try:
        from core.engine.intelligence.queries import code_context

        source_root = _find_source_root(root)
        if source_root is None:
            logging.debug("Code context unavailable outside a source checkout")
            return []
        builder, centrality = _get_or_build_graph(str(source_root))
        ctx = code_context(description, builder)

        # Work from the full matched_files list, not the capped context_files slice
        file_paths = [p for p in ctx.get("matched_files", []) if "::" not in p]
        if not file_paths:
            return []

        # Tokens from the description for basename affinity scoring
        query_tokens = {w.lower() for w in re.split(r"\W+", description) if len(w) >= 3}

        def _score(path: str) -> tuple[int, float]:
            base = os.path.splitext(os.path.basename(path))[0].lower()
            basename_hits = sum(1 for tok in query_tokens if tok in base)
            return (basename_hits, centrality.get(path, 0.0))

        file_paths.sort(key=_score, reverse=True)
        return file_paths
    except Exception as exc:
        logging.debug("_extract_matched_files failed (non-fatal): %s", exc)
        return []


async def _load_code_context(description: str, root: str = ".", max_files: int = 4) -> dict:
    """Read content of files matched to this task description.
    Returns: {"files": [{"path": str, "content": str, "reason": str}]}
    Never raises — returns {"files": []} on any failure.
    """
    try:
        matched = _extract_matched_files(description, root)
        # Skip test files and hidden files — they add noise and burn context budget
        source_files = [p for p in matched if not os.path.basename(p).startswith(("test_", "."))]
        files = []
        for path in source_files[:max_files]:
            try:
                with open(path, encoding="utf-8", errors="replace") as fh:
                    content = fh.read()
                files.append(
                    {
                        "path": path,
                        "content": content,
                        "reason": f"matched: {path.split('/')[-1]}",
                    }
                )
            except OSError:
                continue
        return {"files": files}
    except Exception as exc:
        logging.debug("_load_code_context failed (non-fatal): %s", exc)
        return {"files": []}


def _build_intel_context(snapshot: dict, max_tokens: int = 6000) -> str:
    """Build intelligence context string from a loader snapshot.

    When snapshot["_intel_context_with_markers"] is present (set by the
    orchestration executor before calling ShellComposer.compose()), returns
    the pre-built marked context so [I-N] markers appear in the system prompt
    delivered to the model. Falls back to a fresh ContextAssembler.build()
    for all other callers (streaming, old executor paths, etc.).

    max_tokens controls the context budget for the ContextAssembler instance.
    Each call creates a new ContextAssembler so the budget can vary per task.
    """
    marked = snapshot.get("_intel_context_with_markers")
    if marked is not None:
        return marked

    from core.engine.orchestrator.context_assembler import ContextAssembler

    return ContextAssembler(max_tokens=max_tokens).build(snapshot)


_CONFIDENCE_FALLBACK_THRESHOLD = 0.6


async def _load_snapshot(classification: dict, discipline: str, product_id: str, mode: str) -> dict:
    """Load intelligence snapshot — dual loader when specialties present, else legacy.

    Confidence routing: when discipline_confidence < threshold, also load insights
    from adjacent disciplines to fill gaps in knowledge coverage.
    """
    from core.engine.intelligence.adjacency import get_adjacent_disciplines

    discipline_confidence = classification.get("discipline_confidence", 1.0)
    adjacent: list[str] = []
    if discipline_confidence < _CONFIDENCE_FALLBACK_THRESHOLD:
        adjacent = get_adjacent_disciplines(discipline, max_n=2)
        if adjacent:
            logging.info(
                "Discipline confidence %.2f < %.2f for '%s' — loading adjacent: %s",
                discipline_confidence,
                _CONFIDENCE_FALLBACK_THRESHOLD,
                discipline,
                adjacent,
            )

    specialties = classification.get("specialties", [])
    if specialties:
        from core.engine.orchestrator.dual_loader import load_dual_intelligence
        from core.engine.orchestrator.specialty_resolver import resolve_specialties

        resolution = await resolve_specialties(specialties, product_id)
        resolved_slugs = [r["slug"] for r in resolution.get("resolved", []) if r.get("slug")]
        snapshot = await load_dual_intelligence(
            resolved_slugs,
            product_id,
            org_context=classification.get("org_context"),
            mode=mode,
            discipline=classification.get("discipline", ""),
        )
        # Annotate with adjacent disciplines even when using dual loader
        snapshot.setdefault("adjacent_disciplines", adjacent)
    else:
        snapshot = await load_intelligence(
            discipline,
            product_id,
            mode=mode,
            specialties=specialties,
            adjacent_disciplines=adjacent or None,
        )

    # Load product context (capabilities from the product map)
    try:
        from core.engine.product.map import ProductMap

        pm = ProductMap(pool)
        capabilities = await pm.get_capabilities(product_id)
        snapshot["product_context"] = {
            "capabilities": [
                {
                    "slug": c.get("slug", ""),
                    "name": c.get("name", ""),
                    "status": c.get("status", ""),
                    "description": c.get("description", "")[:100] if c.get("description") else "",
                }
                for c in (capabilities or [])[:20]
            ],
            "total_capabilities": len(capabilities or []),
        }
    except Exception:
        snapshot["product_context"] = None

    # Load full context from all graph layers
    try:
        from core.engine.orchestrator.context import load_full_context

        full_ctx = await load_full_context(product_id, discipline)
        snapshot["pm_context"] = full_ctx
    except Exception as _e:
        logging.warning("PM context load failed in _load_snapshot: %s", _e)
        snapshot["pm_context"] = None

    # Pass through risk context pre-computed by execute_task
    snapshot["risk_context"] = classification.get("risk_context")

    # Pre-task cost estimate from token ledger history (non-fatal)
    try:
        from core.engine.intelligence.cost_predictor import CostPredictor

        snapshot["cost_estimate"] = await CostPredictor().estimate(discipline, product_id)
    except Exception as _ce:
        logging.debug("Cost estimate failed (non-fatal): %s", _ce)
        snapshot["cost_estimate"] = {}

    return snapshot


async def _load_risk_context(description: str, product_id: str) -> dict:
    """Blast radius + seam gaps — injected at task time, zero LLM calls.

    Blast radius: tree-sitter scan of live codebase (instant).
    Seam gaps: read from seam_gap table (pre-computed by nightly sentinel job).
    Both are non-fatal — returns partial result on any failure.
    """
    import asyncio

    result: dict = {"blast_radius": [], "seam_gaps": []}

    async def _blast() -> list[dict]:
        try:
            from core.engine.intelligence.graph_builder import GraphBuilder
            from core.engine.intelligence.queries import blast_radius, code_context

            builder = GraphBuilder(".")
            builder.phase1_treesitter()
            ctx = code_context(description, builder)
            all_matched = [f["path"] if isinstance(f, dict) else f for f in ctx.get("matched_files", [])]
            hits = []
            for f in all_matched[:5]:
                br = blast_radius(f, builder.graph)
                if br["total_affected"] > 0:
                    hits.append(
                        {
                            "file": f,
                            "direct": br["direct_dependents"],
                            "total": br["total_affected"],
                            "total_matched": len(all_matched),
                        }
                    )
            return hits
        except Exception as exc:
            logging.debug("Blast radius load failed (non-fatal): %s", exc)
            return []

    async def _seams() -> list[dict]:
        try:
            async with pool.connection() as db:
                rows = await db.query(
                    """
                    SELECT route, method, severity, description
                    FROM seam_gap
                    WHERE product = <record>$product
                      AND severity IN ['error', 'warning']
                    ORDER BY severity ASC
                    LIMIT 10
                    """,
                    {"product": product_id},
                )
                return parse_rows(rows)
        except Exception as exc:
            logging.debug("Seam gap query failed (non-fatal): %s", exc)
            return []

    blast_hits, seam_hits = await asyncio.gather(_blast(), _seams())
    result["blast_radius"] = blast_hits
    result["seam_gaps"] = seam_hits
    return result


async def _load_frameworks_by_slug(slugs: list[str], product_id: str):
    """Load frameworks by slug and construct a FrameworkSelection."""
    from core.engine.reasoning.models import Framework, FrameworkSelection

    async with pool.connection() as db:
        frameworks = []
        for slug in slugs:
            rows = await db.query(
                "SELECT * FROM framework WHERE slug = <string>$slug LIMIT 1",
                {"slug": slug},
            )
            result = rows[0] if rows and isinstance(rows[0], list) else (rows or [])
            if result:
                row = result[0]
                frameworks.append(
                    Framework(
                        slug=row["slug"],
                        name=row["name"],
                        family=row.get("family", "analytical"),
                        description=row.get("description", ""),
                        system_prompt=row.get("system_prompt", ""),
                        activation_signals=row.get("activation_signals", []),
                        archetype_affinity=row.get("archetype_affinity", {}),
                        mode_affinity=row.get("mode_affinity", {}),
                        composability=row.get("composability", {}),
                    )
                )

    if not frameworks:
        return None

    if len(frameworks) == 1:
        pattern = "stacked"
    else:
        families = {f.family for f in frameworks}
        gen = families & {"generative", "predictive"}
        eval_ = families & {"evaluative", "adversarial", "diagnostic"}
        pattern = "iterative" if gen and eval_ else "stacked"

    return FrameworkSelection(
        frameworks=frameworks,
        composition_pattern=pattern,
        scores=[1.0] * len(frameworks),
    )


# NOTE: This function is being deprecated in favor of engine.orchestration.orchestrate().
# The runner daemon and API now use the orchestration layer directly.
# This function remains for backward compatibility with tests and scripts.
async def execute_task(
    description: str,
    product_id: str,
    workspace_id: str,
    user_id: str,
    model: str | None = None,
    force_skill: str | None = None,
    force_frameworks: bool = False,
    frameworks_hint: list[str] | None = None,
) -> dict:
    """Full task execution pipeline. Returns task result dict.

    .. deprecated::
        Use ``engine.orchestration.orchestrate()`` directly.
        This function remains for backward compatibility.

    If a skill matches (or force_skill is set), delegates to the skill executor.
    Otherwise, runs vanilla single-step execution.
    """
    # Validate product_id up front (mirrors orchestration.executor:75). The CREATE task statements
    # below cast <record>$product, so an empty/colon-less product_id (e.g. a conductor payload missing
    # product_id, which rule_actions defaults to "") would either fail the CREATE opaquely or — worse —
    # write a product-orphan task invisible to every product-scoped query. Fail closed, legibly.
    from core.engine.core.exceptions import ValidationError

    if not product_id or ":" not in product_id:
        raise ValidationError(f"Invalid product_id for execute_task: {product_id!r}")

    # Set correlation ID for this task so all downstream log records are traceable
    from core.engine.core.log_context import new_correlation_id

    cid = new_correlation_id()
    logging.debug("execute_task start: cid=%s product=%s", cid, product_id)

    # 0. Try graph-based classification (falls back to old flow if empty)
    graph_context: dict | None = None
    try:
        from core.engine.graph.context import load_graph_context

        graph_context = await load_graph_context(description)
    except Exception as exc:
        logging.debug("Graph context load failed (best-effort): %s", exc)

    if graph_context and graph_context.get("relevant_files"):
        # Graph-based classification
        try:
            from core.engine.graph.classifier import classify_with_graph

            classification = await classify_with_graph(description, graph_context, product_id)
        except Exception as exc:
            logging.warning("Graph classifier failed, falling back to old: %s", exc)
            classification = await classify_task(description, product_id)
    else:
        # 1. Classify (old flow)
        classification = await classify_task(description, product_id)

    discipline = classification.get("discipline", "architecture")
    archetype = classification["archetype"]
    mode = classification["mode"]
    perspective = classification.get("perspective", "practitioner")

    # 1b+1c+code — parallel: composition scoring, risk context, and code context
    # are all independent of each other — fire simultaneously after classification.
    engagement = classification.get("engagement", {})
    engagement_perspectives = engagement.get("perspectives", [])

    from core.engine.orchestration.composition_scorer import score_composition

    _scored_r, _risk_r, _code_r = await asyncio.gather(
        score_composition(classification, product_id),
        _load_risk_context(description, product_id),
        _load_code_context(description),
        return_exceptions=True,
    )

    # Apply composition scoring result
    perspective_weights: dict[str, float] | None = None
    if isinstance(_scored_r, Exception):
        logging.warning("Composition scoring failed in legacy executor: %s", _scored_r)
    else:
        perspective_weights = _scored_r.perspective_weights
        classification["perspective_weights"] = perspective_weights
        if _scored_r.perspectives != engagement_perspectives:
            engagement["perspectives"] = _scored_r.perspectives
            engagement_perspectives = _scored_r.perspectives
            classification["engagement"] = engagement

    # Apply risk context result
    if isinstance(_risk_r, Exception):
        logging.debug("Risk context load failed (non-fatal): %s", _risk_r)
    else:
        classification["risk_context"] = _risk_r

    # Apply code context result
    code_ctx: dict = {"files": []}
    if isinstance(_code_r, Exception):
        logging.debug("Code context load failed (non-fatal): %s", _code_r)
    else:
        code_ctx = _code_r

    if len(engagement_perspectives) > 1:
        from core.engine.orchestrator.engagement import execute_engagement
        from core.engine.orchestrator.injection import inject_missing_perspectives

        classification = await inject_missing_perspectives(classification, product_id)
        engagement_result = await execute_engagement(
            description,
            classification,
            product_id,
            workspace_id,
            perspective_weights=perspective_weights,
        )
        output = engagement_result.merged_output
        snapshot = {
            "perspectives_used": engagement_result.perspectives_used,
            "spin_count": len(engagement_result.spins),
            "engagement_rationale": engagement_result.engagement_rationale,
        }

        # Inject PM context into engagement snapshot
        try:
            from core.engine.orchestrator.context import load_full_context

            snapshot["pm_context"] = await load_full_context(product_id, discipline)
        except Exception as _e:
            logging.warning("PM context load failed in engagement path: %s", _e)
            snapshot["pm_context"] = None

        # Inject code context into engagement snapshot
        if code_ctx.get("files"):
            snapshot["code_context"] = code_ctx

        engagement_data = {
            "perspectives": engagement_result.perspectives_used,
            "adversarial_pair": engagement.get("adversarial_pair"),
            "rationale": engagement_result.engagement_rationale,
            "injected": engagement_result.injected_perspectives,
            "spin_count": len(engagement_result.spins),
        }

        # Persist task record
        try:
            all_specialties = list(set(s for spin in engagement_result.spins for s in spin.specialties_used))
            async with pool.connection() as db:
                result = await db.query(
                    """
                    CREATE task SET
                        product = <record>$product,
                        user = <record>$user,
                        description = $description,
                        discipline = $discipline,
                        domain_path = $discipline,
                        archetype = $archetype,
                        mode = $mode,
                        perspective = $perspective,
                        intelligence_loaded = $intel,
                        output = $output,
                        model_used = $model,
                        source = 'direct',
                        status = 'completed',
                        completed_at = time::now(),
                        specialties_loaded = $specialties_loaded,
                        engagement = $engagement
                    """,
                    {
                        "product": product_id,
                        "workspace": workspace_id,
                        "user": user_id,
                        "description": description,
                        "discipline": discipline,
                        "archetype": archetype,
                        "mode": mode,
                        "perspective": perspective,
                        "intel": snapshot,
                        "output": output,
                        "model": settings.llm_budget_model if model == "budget" else settings.llm_model,
                        "specialties_loaded": all_specialties,
                        "engagement": engagement_data,
                    },
                )
                from core.engine.core.db import parse_one

                task_record = parse_one(result) or {}
                task_id = task_record.get("id", "unknown")
        except Exception as e:
            logging.error("Failed to persist engagement task record: %s", e)
            raise

        # Write task + agent nodes to graph (best-effort dual-write)
        try:
            from core.engine.graph.writer import write_task_to_graph

            await write_task_to_graph(
                task_id=str(task_id),
                description=description,
                status="completed",
                output=output,
                feedback=None,
                classification=classification,
            )
        except Exception:
            pass  # graph write is best-effort

        return {
            "id": str(task_id),
            "discipline": discipline,
            "domain_path": discipline,
            "archetype": archetype,
            "mode": mode,
            "perspective": perspective,
            "output": output,
            "intelligence_loaded": snapshot,
            "status": "completed",
            "engagement": engagement_data,
        }

    # 2. Skill selection
    skill_used = None
    skill_result = None

    try:
        from core.engine.skills.executor import execute_skill as _execute_skill
        from core.engine.skills.selector import select_skill as _select_skill

        if force_skill:
            # Force a specific skill by slug
            from core.engine.skills.models import Job, Skill

            async with pool.connection() as db:
                rows = await db.query(
                    "SELECT * FROM skill WHERE slug = <string>$slug LIMIT 1",
                    {"slug": force_skill},
                )
                skill_rows = rows[0] if rows and isinstance(rows[0], list) else (rows or [])
                if skill_rows:
                    row = skill_rows[0]
                    forced = Skill(
                        slug=row["slug"],
                        name=row["name"],
                        description=row["description"],
                        domain_path=row.get("domain_path"),
                        tier=row.get("tier", "built-in"),
                        jobs=[Job(**j) for j in row.get("jobs", row.get("steps", []))],
                        activation_signals=row.get("activation_signals", []),
                    )
                    skill_result = await _execute_skill(
                        forced,
                        description,
                        product_id,
                        workspace_id,
                        user_id,
                        model=model,
                    )
                    skill_used = str(row.get("id", ""))
        else:
            match = await _select_skill(classification, product_id, description=description)
            if match:
                skill_result = await _execute_skill(
                    match.skill,
                    description,
                    product_id,
                    workspace_id,
                    user_id,
                    model=model,
                )
                # Look up skill record ID for the task record
                async with pool.connection() as db:
                    id_rows = await db.query(
                        "SELECT id FROM skill WHERE slug = <string>$slug LIMIT 1",
                        {"slug": match.skill.slug},
                    )
                    id_result = parse_rows(id_rows)
                    skill_used = str(id_result[0]["id"]) if id_result else None
    except Exception as exc:
        logging.warning("Skill selection/execution failed, falling back to vanilla: %s", exc)

    # 3. Framework selection (only if no skill matched)
    strategies_used = None
    framework_result = None

    if not skill_result:
        try:
            from core.engine.reasoning.executor import execute_with_frameworks as _execute_with_frameworks
            from core.engine.reasoning.selector import select_frameworks as _select_frameworks

            if frameworks_hint:
                fw_selection = await _load_frameworks_by_slug(frameworks_hint, product_id)
            elif force_frameworks:
                fw_selection = await _select_frameworks(
                    classification,
                    product_id,
                    description=description,
                    force=True,
                )
            else:
                fw_selection = await _select_frameworks(classification, product_id, description=description)
            if fw_selection:
                # Load intelligence for framework context
                snapshot = await _load_snapshot(classification, discipline, product_id, mode)
                if graph_context and graph_context.get("relevant_files"):
                    snapshot["graph_context"] = graph_context
                if code_ctx.get("files"):
                    snapshot["code_context"] = code_ctx
                intel_context = _build_intel_context(snapshot)

                framework_result = await _execute_with_frameworks(
                    fw_selection,
                    description,
                    intel_context,
                    model=settings.llm_budget_model if model == "budget" else settings.llm_model,
                )
                strategies_used = framework_result.get("frameworks_used", [])
        except Exception as exc:
            logging.warning("Framework selection/execution failed, falling back to vanilla: %s", exc)

    if skill_result:
        output = skill_result["output"]
        snapshot = {"insights": [], "total_count": 0}
    elif framework_result:
        output = framework_result["output"]
        # snapshot already loaded above
    else:
        # 4. Vanilla execution: load intelligence + single LLM call
        snapshot = await _load_snapshot(classification, discipline, product_id, mode)
        if graph_context and graph_context.get("relevant_files"):
            snapshot["graph_context"] = graph_context
        if code_ctx.get("files"):
            snapshot["code_context"] = code_ctx
        intel_context = _build_intel_context(snapshot)

        archetype_instruction = ARCHETYPE_INSTRUCTIONS.get(archetype, ARCHETYPE_INSTRUCTIONS["executor"])
        mode_instruction = MODE_INSTRUCTIONS.get(mode, MODE_INSTRUCTIONS["reactive"])

        prompt = f"""You are ACE, an AI intelligence engine built by QueryLabs. You help users by leveraging organizational intelligence — insights, patterns, and knowledge accumulated from ongoing work. When you reference your capabilities, refer to yourself as ACE, not as Claude or any other AI assistant.

{archetype_instruction}
{mode_instruction}

Task: {description}
{intel_context}

Provide a thorough, high-quality response."""

        try:
            llm_model = settings.llm_budget_model if model == "budget" else settings.llm_model
            output = await llm.complete(prompt, model=llm_model)
        except Exception as e:
            logging.error("LLM execution failed for task '%s': %s", description[:100], e)
            raise

    # 4. Create task record
    try:
        async with pool.connection() as db:
            extra_clauses = ""
            extra_params: dict = {}
            if skill_used:
                extra_clauses += ", skill_used = $skill_used"
                extra_params["skill_used"] = skill_used
            if strategies_used:
                extra_clauses += ", strategies_used = $strategies_used"
                extra_params["strategies_used"] = strategies_used

            result = await db.query(
                f"""
                CREATE task SET
                    product = <record>$product,
                    user = <record>$user,
                    description = $description,
                    discipline = $discipline,
                    domain_path = $discipline,
                    archetype = $archetype,
                    mode = $mode,
                    perspective = $perspective,
                    intelligence_loaded = $intel,
                    output = $output,
                    model_used = $model,
                    source = 'direct',
                    status = 'completed',
                    completed_at = time::now(),
                    specialties_loaded = $specialties_loaded
                    {extra_clauses}
                """,
                {
                    "product": product_id,
                    "workspace": workspace_id,
                    "user": user_id,
                    "description": description,
                    "discipline": discipline,
                    "archetype": archetype,
                    "mode": mode,
                    "perspective": perspective,
                    "intel": snapshot,
                    "output": output,
                    "model": settings.llm_budget_model if model == "budget" else settings.llm_model,
                    "specialties_loaded": snapshot.get("specialties_loaded", []),
                    **extra_params,
                },
            )
            from core.engine.core.db import parse_one

            task_record = parse_one(result) or {}
            task_id = task_record.get("id", "unknown")
    except Exception as e:
        logging.error("Failed to persist task record: %s", e)
        raise

    # Post-task: write task + agent nodes to graph (best-effort dual-write)
    try:
        from core.engine.graph.writer import write_task_to_graph

        await write_task_to_graph(
            task_id=str(task_id),
            description=description,
            status="completed",
            output=output,
            feedback=None,
            classification=classification,
        )
    except Exception:
        pass  # graph write is best-effort

    # Post-task: track co-occurrence for synaptic graph
    try:
        from core.engine.graph.cooccurrence import track as track_cooccurrence

        task_for_tracking = {
            "domain_path": discipline,
            "intelligence_loaded": snapshot,
        }
        await track_cooccurrence(task_for_tracking, product_id)
    except Exception as exc:
        logging.warning("Co-occurrence tracking failed: %s", exc)

    # Post-task: write self_assessment (baseline proxy for calibration engine)
    _self_assessment = 0.75 if output and len(output.strip()) > 100 else 0.7
    try:
        if str(task_id) != "unknown":
            async with pool.connection() as db:
                await db.query(
                    "UPDATE <record>$tid SET self_assessment = $sa",
                    {"tid": str(task_id), "sa": _self_assessment},
                )
    except Exception as exc:
        logging.warning("self_assessment write failed: %s", exc)

    # Post-task: ROI detection (best-effort)
    try:
        from core.engine.intelligence.roi_detector import detect_roi_events

        async with pool.connection() as db:
            task_for_roi = {
                "id": str(task_id),
                "domain_path": discipline,
                "intelligence_loaded": snapshot,
            }
            utilization = snapshot.get("intelligence_utilization", {})
            await detect_roi_events(task_for_roi, utilization, product_id, db)
    except Exception as exc:
        logging.warning("ROI tracking failed: %s", exc)

    # Post-task: calibrated assessment (best-effort)
    try:
        from core.engine.intelligence.calibration import apply_calibration

        async with pool.connection() as db:
            cal_result = await db.query(
                "SELECT data FROM calibration WHERE product = <record>$product LIMIT 1",
                {"product": product_id},
            )
            cal_rows = cal_result[0] if cal_result and isinstance(cal_result[0], list) else (cal_result or [])
            if cal_rows and cal_rows[0].get("data"):
                adjusted = apply_calibration(_self_assessment, discipline, cal_rows[0]["data"])
                await db.query(
                    "UPDATE <record>$tid SET calibrated_assessment = $cal",
                    {"tid": str(task_id), "cal": adjusted},
                )
    except Exception as exc:
        logging.warning("Calibration application failed: %s", exc)

    # Post-task: feed output into always-on capture service (best-effort)
    try:
        from core.engine.capture.service import capture_service

        await capture_service.emit_task_completion(
            product_id=product_id,
            task_id=str(task_id),
            description=description,
            output=output,
            discipline=discipline,
            workspace_id=workspace_id,
        )
    except Exception as exc:
        logging.debug("Capture service emit failed: %s", exc)

    result_dict = {
        "id": str(task_id),
        "discipline": discipline,
        "domain_path": discipline,
        "archetype": archetype,
        "mode": mode,
        "perspective": perspective,
        "output": output,
        "intelligence_loaded": snapshot,
        "status": "completed",
    }
    if skill_used:
        result_dict["skill_used"] = skill_used
    if skill_result:
        result_dict["skill_slug"] = skill_result.get("skill_slug")
        result_dict["jobs_completed"] = skill_result.get("jobs_completed")
    if strategies_used:
        result_dict["strategies_used"] = strategies_used
    if framework_result:
        result_dict["composition_pattern"] = framework_result.get("composition_pattern")

    return result_dict


async def execute_task_v2(
    description: str,
    product_id: str,
    workspace_id: str,
    user_id: str,
    model: str | None = None,
    force_skill: str | None = None,
    force_frameworks: bool = False,
    frameworks_hint: list[str] | None = None,
) -> dict:
    """Task execution via orchestration layer.

    New entry point that delegates to the orchestration layer.
    Callers should prefer ``engine.orchestration.orchestrate()`` directly.
    """
    from core.engine.orchestration import orchestrate
    from core.engine.orchestration.request import OrchestrationRequest

    request = OrchestrationRequest(
        description=description,
        product_id=product_id,
        workspace_id=workspace_id,
        user_id=user_id,
        model=model,
        force_skill=force_skill,
        force_frameworks=force_frameworks,
        frameworks_hint=frameworks_hint,
    )
    result = await orchestrate(request)

    _discipline = result.classification.get("discipline", result.classification.get("domain_path", ""))
    return {
        "id": result.task_id or "unknown",
        "discipline": _discipline,
        "domain_path": _discipline,
        "archetype": result.classification.get("archetype", ""),
        "mode": result.classification.get("mode", ""),
        "output": result.output,
        "intelligence_loaded": result.snapshot,
        "status": result.status,
    }
