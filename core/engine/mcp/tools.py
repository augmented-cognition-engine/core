# engine/mcp/tools.py
"""MCP tool implementations — each wraps an existing ACE engine subsystem."""

from __future__ import annotations

import asyncio
import logging
import re
import time
from contextlib import asynccontextmanager

from core.engine.core.config import settings
from core.engine.core.db import parse_one, parse_record_ids, parse_rows, pool, serialize_record
from core.engine.core.metrics import mcp_tool_duration as _mcp_tool_duration
from core.engine.core.tasks import logged_task
from core.engine.ideas.capture import capture_idea
from core.engine.orchestrator.loader import load_intelligence
from core.engine.pm.gate_engine import GateEngine
from core.engine.product.roadmap import compute_roadmap

DEFAULT_ORG = settings.default_org

logger = logging.getLogger(__name__)


@asynccontextmanager
async def _timed_tool(tool_name: str):
    """Record duration and surface errors for an MCP tool call.

    Usage:
        async def ace_load(topic: str, ...) -> dict:
            async with _timed_tool("ace_load"):
                ... implementation ...
    """
    from core.engine.core.error_buffer import error_buffer
    from core.engine.core.log_context import get_correlation_id

    start = time.perf_counter()
    try:
        yield
    except Exception as exc:
        duration = time.perf_counter() - start
        _mcp_tool_duration.labels(tool=tool_name).observe(duration)
        error_buffer.record(
            source=f"mcp_tool.{tool_name}",
            error_type=type(exc).__name__,
            message=str(exc),
            cid=get_correlation_id(),
            context={"tool": tool_name, "duration_ms": round(duration * 1000, 1)},
        )
        raise
    else:
        duration = time.perf_counter() - start
        _mcp_tool_duration.labels(tool=tool_name).observe(duration)


# Valid observation types for ace_capture — enforced at MCP boundary
_VALID_OBSERVATION_TYPES = frozenset(["correction", "decision", "preference", "pattern", "learning", "error"])


def _validate_mcp_params(
    product_id: str | None = None,
    confidence: float | None = None,
    observation_type: str | None = None,
    file_path: str | None = None,
) -> None:
    """Validate common MCP tool parameters at the API boundary.

    Raises ValueError for invalid inputs before they reach the database or
    the orchestrator, preventing injection, path traversal, and type confusion.
    """
    from core.engine.core.exceptions import ValidationError

    if product_id is not None and (not product_id or ":" not in product_id):
        raise ValidationError(f"Invalid product_id: {product_id!r}")
    if confidence is not None and not (0.0 <= confidence <= 1.0):
        raise ValidationError(f"confidence must be in [0.0, 1.0], got {confidence}")
    if observation_type is not None and observation_type not in _VALID_OBSERVATION_TYPES:
        raise ValidationError(
            f"Unknown observation_type {observation_type!r}. Valid: {sorted(_VALID_OBSERVATION_TYPES)}"
        )
    if file_path is not None and ".." in file_path:
        raise ValidationError(f"file_path must not contain '..': {file_path!r}")


async def ace_start(product_id: str = DEFAULT_ORG) -> dict:
    """Pre-flight: session context + briefing availability."""
    briefing_available = False
    last_briefing_date = None
    active_initiatives = 0
    ideas_ready = 0

    try:
        async with pool.connection() as db:
            # Check latest briefing
            b_result = await db.query(
                "SELECT id, created_at FROM briefing WHERE product = <record>$product ORDER BY created_at DESC LIMIT 1",
                {"product": product_id},
            )
            b_rows = parse_rows(b_result)
            if b_rows:
                briefing_available = True
                last_briefing_date = str(b_rows[0].get("created_at", ""))

            # Count active initiatives
            i_result = await db.query(
                "SELECT count() AS c FROM initiative WHERE product = <record>$product AND status = 'active' GROUP ALL",
                {"product": product_id},
            )
            i_rows = parse_rows(i_result)
            if i_rows:
                active_initiatives = i_rows[0].get("c", 0)

            # Count ready ideas
            id_result = await db.query(
                "SELECT count() AS c FROM idea WHERE product = <record>$product AND status = 'ready' GROUP ALL",
                {"product": product_id},
            )
            id_rows = parse_rows(id_result)
            if id_rows:
                ideas_ready = id_rows[0].get("c", 0)

    except Exception as exc:
        logger.warning("ace_start query error: %s", exc)

    return {
        "briefing_available": briefing_available,
        "last_briefing_date": last_briefing_date,
        "active_initiatives": active_initiatives,
        "ideas_ready": ideas_ready,
        "pending_approvals": 0,
    }


async def ace_context(product_id: str = DEFAULT_ORG) -> dict:
    """Full session context — what's built, quality, decisions, gaps, active work.
    Replaces the static ace-dev-context skill with live queries.
    """
    result = {
        "capabilities": [],
        "quality_summary": {},
        "recent_decisions": [],
        "active_work": {},
        "open_gaps": [],
        "recent_activity": [],
        "efficiency": {},
    }

    try:
        async with pool.connection() as db:
            # Capabilities with status
            try:
                cap_rows = await db.query(
                    "SELECT slug, name, status, priority FROM capability WHERE product = <record>$product ORDER BY name",
                    {"product": product_id},
                )
                result["capabilities"] = [serialize_record(r) for r in parse_rows(cap_rows)]
            except Exception:
                logger.warning("ace_context: capabilities query failed", exc_info=True)

            # Quality summary by discipline
            try:
                qual_rows = await db.query(
                    """
                    SELECT dimension, math::mean(score) AS avg_score, count() AS count
                    FROM capability_quality
                    GROUP BY dimension
                    """,
                    {"product": product_id},
                )
                rows = parse_rows(qual_rows)
                by_discipline = {r["dimension"]: round(r.get("avg_score", 0), 2) for r in rows if r.get("dimension")}
                overall = sum(by_discipline.values()) / len(by_discipline) if by_discipline else 0
                result["quality_summary"] = {"overall": round(overall, 2), "by_discipline": by_discipline}
            except Exception:
                logger.warning("ace_context: quality query failed", exc_info=True)

            # Recent decisions (last 20)
            try:
                dec_rows = await db.query(
                    """
                    SELECT title, decision_type, rationale, outcome, source, created_at
                    FROM decision
                    WHERE product = <record>$product
                    ORDER BY created_at DESC
                    LIMIT 20
                    """,
                    {"product": product_id},
                )
                result["recent_decisions"] = [serialize_record(r) for r in parse_rows(dec_rows)]
            except Exception:
                logger.warning("ace_context: decisions query failed", exc_info=True)

            # Active work
            try:
                init_rows = await db.query(
                    "SELECT title, status, created_at FROM initiative WHERE product = <record>$product AND status IN ['active', 'paused'] ORDER BY created_at DESC LIMIT 10",
                    {"product": product_id},
                )
                spec_rows = await db.query(
                    "SELECT objective, status, created_at FROM agent_spec WHERE product = <record>$product AND status IN ['executing', 'approved', 'verifying'] ORDER BY created_at DESC LIMIT 5",
                    {"product": product_id},
                )
                queue_rows = await db.query(
                    "SELECT count() AS c FROM task_queue WHERE product = <record>$product AND status = 'queued' GROUP ALL",
                    {"product": product_id},
                )
                queued = parse_rows(queue_rows)
                result["active_work"] = {
                    "initiatives": [serialize_record(r) for r in parse_rows(init_rows)],
                    "specs": [serialize_record(r) for r in parse_rows(spec_rows)],
                    "queued_tasks": queued[0].get("c", 0) if queued else 0,
                }
            except Exception:
                logger.warning("ace_context: active work query failed", exc_info=True)

            # Open gaps (top 10 by lowest score)
            try:
                gap_rows = await db.query(
                    """
                    SELECT capability, dimension, score, gaps
                    FROM capability_quality
                    ORDER BY score ASC
                    LIMIT 10
                    """,
                    {"product": product_id},
                )
                result["open_gaps"] = [serialize_record(r) for r in parse_rows(gap_rows)]
            except Exception:
                logger.warning("ace_context: gaps query failed", exc_info=True)

            # Recent commits with decision classifications
            try:
                commit_rows = await db.query(
                    """
                    SELECT title, decision_type, source_commit, timestamp
                    FROM graph_decision
                    WHERE graph_id = $gid AND decision_type != NONE
                    ORDER BY timestamp DESC
                    LIMIT 10
                    """,
                    {"gid": f"{product_id}:code"},
                )
                result["recent_activity"] = [serialize_record(r) for r in parse_rows(commit_rows)]
            except Exception:
                logger.warning("ace_context: activity query failed", exc_info=True)

            # Token efficiency
            try:
                eff_rows = await db.query(
                    """
                    SELECT
                        math::sum(token_total) AS total_tokens,
                        math::sum(estimated_tokens_saved) AS estimated_saved,
                        count() AS task_count
                    FROM composition_signal
                    WHERE product = <record>$product
                    GROUP ALL
                    """,
                    {"product": product_id},
                )
                rows = parse_rows(eff_rows)
                result["efficiency"] = rows[0] if rows else {}
            except Exception:
                logger.warning("ace_context: efficiency query failed", exc_info=True)

    except Exception:
        logger.warning("ace_context: connection failed", exc_info=True)

    return result


async def ace_load(topic: str, product_id: str = DEFAULT_ORG) -> dict:
    """Load accumulated intelligence for a domain."""
    async with _timed_tool("ace_load"):
        domain_path = topic.replace(" ", "_").lower()

        snapshot = await load_intelligence(domain_path, product_id, mode="reactive")

        insights = snapshot.get("insights", [])
        # The shared expander folds 1-hop graph neighbors into `insights`; keep them
        # out of the own-insight split and surface them separately as `related`.
        own = [i for i in insights if i.get("source_graph") != "graph_neighbor"]
        corrections = [i for i in own if i.get("insight_type") == "correction"]
        preferences = [i for i in own if i.get("insight_type") == "preference"]
        general = [i for i in own if i.get("insight_type") not in ("correction", "preference")]

        graph_tensions = snapshot.get("graph_tensions", {"tensions": [], "consequences": []})
        elevated_ids = {
            str(n.get("insight_id", ""))
            for bucket in ("tensions", "consequences")
            for n in graph_tensions.get(bucket, [])
        }
        related = [
            n for n in snapshot.get("relationship_neighbors", []) if str(n.get("insight_id", "")) not in elevated_ids
        ]

        try:
            from core.engine.graph.tension_telemetry import record_tension_surfaces

            await record_tension_surfaces(graph_tensions, surface="ace_load", product_id=product_id)
        except Exception:
            pass

        return {
            "domain_path": domain_path,
            "insights": general,
            "corrections": corrections,
            "preferences": preferences,
            "related": related,
            "tensions": graph_tensions,
            "framework_recommendation": None,
            "total_count": snapshot.get("total_count", 0),
        }


async def ace_capture(
    observation_type: str,
    content: str,
    domain_path: str,
    confidence: float = 0.7,
    product_id: str = DEFAULT_ORG,
) -> dict:
    """Record an observation from the session."""
    async with _timed_tool("ace_capture"):
        _validate_mcp_params(product_id=product_id, confidence=confidence, observation_type=observation_type)
        async with pool.connection() as db:
            result = await db.query(
                """
                CREATE observation SET
                    product = <record>$product,
                    observation_type = $type,
                    content = $content,
                    domain_path = $domain_path,
                    discipline_hint = $domain_path,
                    confidence = $confidence,
                    source = 'mcp',
                    status = 'pending',
                    created_at = time::now()
                """,
                {
                    "product": product_id,
                    "type": observation_type,
                    "content": content,
                    "domain_path": domain_path,
                    "confidence": confidence,
                },
            )
            rows = parse_rows(result)

        obs_id = str(rows[0].get("id", "")) if rows else ""

        # Inline synthesis — don't wait for worker poll cycle
        if rows:
            obs_record = rows[0]
            try:
                from core.engine.capture.synthesizer import Synthesizer

                synth = Synthesizer(product_id=product_id, workspace_id=None, batch_size=1)
                synth._db_pool = pool  # required for _write_insight to flush to DB
                await synth.add_observation(obs_record)
                await synth.flush()
                async with pool.connection() as db:
                    await db.query(
                        "UPDATE <record>$id SET status = 'processed', processed_at = time::now()",
                        {"id": obs_id},
                    )
            except Exception:
                pass  # Never fail the capture — worker will retry

        # Emit event so other listeners can react
        try:
            from core.engine.events.bus import bus

            await bus.emit(
                "observation.created",
                {
                    "product_id": product_id,
                    "observation_id": obs_id,
                    "observation_type": observation_type,
                    "source": "mcp",
                },
            )
        except Exception:
            pass

        return {"status": "captured", "id": obs_id}


async def ace_task(
    description: str,
    product_id: str = DEFAULT_ORG,
    workspace_id: str = "workspace:default",
    user_id: str = "user:default",
    skill_hint: str | None = None,
    frameworks_hint: list[str] | None = None,
) -> dict:
    """Run task through full orchestrator pipeline (cognitive composition path)."""
    async with _timed_tool("ace_task"):
        from core.engine.orchestration import orchestrate
        from core.engine.orchestration.request import OrchestrationRequest

        request = OrchestrationRequest(
            description=description,
            product_id=product_id,
            workspace_id=workspace_id,
            user_id=user_id,
            force_skill=skill_hint,
            frameworks_hint=frameworks_hint,
            persist_task=True,
            run_post_hooks=True,
        )
    result = await orchestrate(request)

    cls = result.classification
    composition = cls.get("cognitive_composition")

    # Build execution trace — surfaces all intelligence layers
    trace: dict = {
        "discipline": cls.get("discipline"),
        "archetype": cls.get("archetype"),
        "mode": cls.get("mode"),
        "perspective": cls.get("perspective"),
        "specialties": cls.get("specialties", []),
    }

    # Cognitive composition — meta-skills, depth, phase→framework table
    if composition:
        from core.engine.cognition.models import derive_depth

        depth = derive_depth(cls.get("mode", "reactive"), cls.get("complexity", "moderate"))
        trace["cognition"] = {
            "meta_skills": composition.meta_skills,
            "depth": depth,
            "fusion_mode": composition.fusion_mode,
            "phases": [
                {
                    "fn": phase.cognitive_function,
                    "instruments": composition.resolved_instruments.get(str(i), []),
                }
                for i, phase in enumerate(composition.active_phases)
            ],
        }

    # Engagement routing (multi-perspective, adversarial)
    engagement = cls.get("engagement", {})
    if engagement:
        trace["engagement"] = {
            "type": engagement.get("engagement_type", "solo"),
            "perspectives": engagement.get("perspectives", []),
        }

    # Risk context (blast radius + seam gaps)
    risk = cls.get("risk_context")
    if risk:
        trace["risk"] = risk

    # Intelligence loaded — snapshot IS the intel dict (keys: total_count, cross_domain_count, ...)
    snapshot = result.snapshot
    intel_count = snapshot.get("total_count")
    if intel_count is not None:
        trace["intelligence"] = {
            "insights": intel_count,
            "cross_domain": snapshot.get("cross_domain_count", 0),
            "specialties": snapshot.get("specialties_loaded", []),
        }

    # Verification — populated by VerificationGate after engagement synthesis
    if snapshot.get("verification_verdict") not in (None, "skipped"):
        trace["verification"] = {
            "verified": snapshot.get("verified", False),
            "verdict": snapshot["verification_verdict"],
            "gaps": snapshot.get("verification_gaps", []),
        }

    # Execution pattern — present in single-agent path; multi-phase/engagement return None
    if result.pattern_result:
        trace["pattern"] = result.pattern_result.pattern_name
    elif cls.get("cognitive_composition") and not cls["cognitive_composition"].fusion_mode:
        trace["pattern"] = "multi-phase"
    elif cls.get("engagement", {}).get("perspectives", []):
        perspectives = cls["engagement"]["perspectives"]
        trace["pattern"] = f"engagement({len(perspectives)}p)"

    return {
        "id": result.task_id or "unknown",
        "output": result.output,
        "status": result.status,
        "duration_ms": result.duration_ms,
        "trace": trace,
    }


async def ace_agent(
    description: str,
    product_id: str = DEFAULT_ORG,
    workspace_id: str = "workspace:default",
    user_id: str = "user:default",
    model: str | None = None,
    max_turns: int = 50,
) -> dict:
    """Run an agentic implementation task through ACE Runtime.

    Unlike ace_task (knowledge work → text output), ace_agent runs a full tool-use
    loop: reads files, runs bash, makes edits, runs tests. Every turn is classified
    and grounded with ACE intelligence: discipline + archetype + mode instructions,
    cognitive composition phases (meta-skill → phase structure → framework slugs),
    and loaded insights from the graph.

    Use for implementation work requiring multiple tool calls.
    Use ace_task for analytical/knowledge work producing text output.
    """
    from core.engine.runtime.models import AssistantMessage
    from core.engine.runtime.runtime import Runtime

    runtime = Runtime(
        model=model or settings.llm_model,
        enable_intelligence=True,
        product_id=product_id,
        max_turns=max_turns,
    )

    output_parts: list[str] = []
    tool_call_count = 0

    async for msg in runtime.chat(description):
        if isinstance(msg, AssistantMessage):
            if msg.content:
                output_parts.append(msg.content)
            tool_call_count += len(getattr(msg, "tool_use", []))

    cls = (runtime._intelligence.last_classification or {}) if runtime._intelligence else {}

    return {
        "output": "\n\n".join(output_parts),
        "tool_calls": tool_call_count,
        "status": "completed",
        "trace": {
            "discipline": cls.get("discipline"),
            "archetype": cls.get("archetype"),
            "mode": cls.get("mode"),
            "specialties": cls.get("specialties", []),
        },
    }


async def ace_status(
    product_id: str = DEFAULT_ORG,
    filter: str | None = None,
) -> dict:
    """Check autonomous work: running jobs, ideas ready, items needing approval."""
    initiatives = []
    ideas_ready = 0
    active_sessions: list[dict] = []

    try:
        async with pool.connection() as db:
            if filter:
                i_result = await db.query(
                    "SELECT * FROM initiative WHERE product = <record>$product AND status = $status ORDER BY updated_at DESC LIMIT 10",
                    {"product": product_id, "status": filter},
                )
            else:
                i_result = await db.query(
                    "SELECT * FROM initiative WHERE product = <record>$product AND status IN ['active', 'blocked'] ORDER BY updated_at DESC LIMIT 10",
                    {"product": product_id},
                )
            initiatives = parse_rows(i_result)

            id_result = await db.query(
                "SELECT count() AS c FROM idea WHERE product = <record>$product AND status = 'ready' GROUP ALL",
                {"product": product_id},
            )
            id_rows = parse_rows(id_result)
            if id_rows:
                ideas_ready = id_rows[0].get("c", 0)

            # Active sessions — any session with activity in the last hour
            try:
                s_result = await db.query(
                    """SELECT session_id, source, started_at, last_message_at
                       FROM ace_session
                       WHERE product = $product
                         AND last_message_at > time::now() - 1h
                       ORDER BY last_message_at DESC
                       LIMIT 5""",
                    {"product": product_id},
                )
                active_sessions = parse_rows(s_result)
            except Exception:
                pass  # session table may not exist yet in older deployments
    except Exception as exc:
        logger.warning("ace_status query error: %s", exc)

    # The grounding metabolism made observable: beliefs whose canvas ground shifted
    # and are pending re-evaluation ("the pricing frame changed → 2 beliefs restless").
    # Best-effort — never break status on the metabolism.
    destabilized_beliefs: list[dict] = []
    try:
        from core.engine.graph.metabolism import pending_reevaluations

        destabilized_beliefs = await pending_reevaluations(limit=10)
    except Exception as exc:
        logger.debug("ace_status: pending_reevaluations failed: %s", exc)

    return {
        "initiatives": initiatives,
        "ideas_ready": ideas_ready,
        "pending_approvals": 0,
        "active_sessions": active_sessions,
        "destabilized_beliefs": destabilized_beliefs,
    }


async def ace_rederive(
    product_id: str = DEFAULT_ORG,
    limit: int = 5,
    llm=None,
) -> dict:
    """Re-evaluate destabilized beliefs (SHADOW): for beliefs whose canvas ground
    shifted, propose a corrected confidence from the changed evidence — WITHOUT
    applying it. Bounded (limit); the metabolism's re-evaluation queue is global,
    so product_id is reserved for future scoping. Returns the count re-derived and
    the destabilized beliefs with their proposals.
    """
    from core.engine.graph.metabolism import pending_reevaluations, rederive_pending

    rederived = await rederive_pending(limit=limit, llm=llm)
    proposals = await pending_reevaluations(limit=max(limit, 10))
    return {"rederived": rederived, "destabilized_beliefs": proposals}


async def ace_capture_idea(
    raw_idea: str,
    product_id: str = DEFAULT_ORG,
    user_id: str = "user:default",
    context: str | None = None,
) -> dict:
    """Send idea to incubator."""
    full_input = f"{raw_idea}\n\nContext: {context}" if context else raw_idea
    result = await capture_idea(
        raw_input=full_input,
        user_id=user_id,
        product_id=product_id,
    )
    return result


async def ace_search(
    query: str,
    product_id: str = DEFAULT_ORG,
    knowledge_type: str | None = None,
    tags: list[str] | None = None,
) -> dict:
    """Search insights using hybrid BM25 + vector similarity (Reciprocal Rank Fusion).

    Args:
        query: Natural language query.
        product_id: Product to scope search to.
        knowledge_type: Optional insight_type filter (e.g. "pattern", "decision").
        tags: Optional list of discipline/specialty tags to narrow results
              (e.g. ["architecture", "error_handling"]). Uses CONTAINSANY.
    """
    from core.engine.embedding.base import get_embedder

    bm25_rows: list[dict] = []
    vec_rows: list[dict] = []
    limit = 10

    # Build optional filter clauses
    type_filter = "AND insight_type = $type" if knowledge_type else ""
    tag_filter = "AND tags CONTAINSANY $tags" if tags else ""

    async with pool.connection() as db:
        # BM25 full-text search (fast, always runs)
        bm25_rows = parse_rows(
            await db.query(
                f"""
            SELECT id, content, confidence, domain_path, observation_type, tags
            FROM insight
            WHERE product = <record>$product AND status = 'active'
              AND content @@ $query
              {type_filter}
              {tag_filter}
            ORDER BY confidence DESC LIMIT $limit
            """,
                {
                    "product": product_id,
                    "query": query,
                    "limit": limit * 2,
                    **({"type": knowledge_type} if knowledge_type else {}),
                    **({"tags": tags} if tags else {}),
                },
            )
        )

        # Vector similarity search (best-effort — only if embeddings exist)
        embedder = get_embedder()
        if embedder.dimensions > 0:
            try:
                vecs = await embedder.embed([query])
                if vecs and vecs[0]:
                    vec_rows = parse_rows(
                        await db.query(
                            f"""
                        SELECT id, content, confidence, domain_path, observation_type, tags,
                               vector::similarity::cosine(embedding, $vec) AS vec_score
                        FROM insight
                        WHERE product = <record>$product AND status = 'active'
                          AND embedding IS NOT NONE
                          {type_filter}
                          {tag_filter}
                        ORDER BY vec_score DESC LIMIT $limit
                        """,
                            {
                                "product": product_id,
                                "vec": vecs[0],
                                "limit": limit * 2,
                                **({"type": knowledge_type} if knowledge_type else {}),
                                **({"tags": tags} if tags else {}),
                            },
                        )
                    )
            except Exception:
                pass  # Vector search is best-effort

    # Reciprocal Rank Fusion (k=60)
    k = 60
    scores: dict[str, float] = {}
    id_to_row: dict[str, dict] = {}

    for rank, row in enumerate(bm25_rows):
        rid = str(row.get("id", ""))
        scores[rid] = scores.get(rid, 0) + 1 / (k + rank + 1)
        id_to_row[rid] = row

    for rank, row in enumerate(vec_rows):
        rid = str(row.get("id", ""))
        scores[rid] = scores.get(rid, 0) + 1 / (k + rank + 1)
        if rid not in id_to_row:
            id_to_row[rid] = row

    # Cross-encoder rerank (when configured): fuse a LARGER pool then let the local-Ollama reranker pick
    # the final top-`limit` — so it can rescue relevant insights RRF ranked just below the cutoff. Off by
    # default → pool == limit and cross_encoder_rerank is a no-op (original RRF order).
    from core.engine.core.config import settings
    from core.engine.search.rerank import cross_encoder_rerank

    pool_size = limit * 3 if getattr(settings, "rerank_peer_host", None) else limit
    ranked = sorted(scores.items(), key=lambda x: x[1], reverse=True)[:pool_size]
    results = [{**id_to_row[rid], "score": round(score, 4)} for rid, score in ranked if rid in id_to_row]
    results = await cross_encoder_rerank(query, results, top_k=limit)

    return {"results": results, "count": len(results), "query": query}


def _slugify_path(file_path: str) -> str:
    """Convert a file path to a SurrealDB slug: engine/core/db.py → engine_core_db_py."""
    slug = re.sub(r"[^a-z0-9]", "_", file_path.lower())
    slug = re.sub(r"_+", "_", slug).strip("_")
    return slug


async def _find_graph_file(db, file_path: str, graph_id: str) -> dict | None:
    """Look up a graph_file node by path or slug. Returns the raw row or None."""
    # First try direct slug lookup
    slug = _slugify_path(file_path)
    node_id = f"graph_file:{slug}"
    result = await db.query(f"SELECT * FROM {node_id}")
    row = parse_one(result)
    if row:
        return row

    # Fall back to path field match
    result = await db.query(
        "SELECT * FROM graph_file WHERE path = $path AND graph_id = $gid LIMIT 1",
        {"path": file_path, "gid": graph_id},
    )
    return parse_one(result)


async def ace_impact(file_path: str, product_id: str = "product:platform") -> dict:
    """What breaks if I delete or change this file?"""
    _validate_mcp_params(file_path=file_path, product_id=product_id)
    async with pool.connection() as db:
        file_result = await db.query(
            "SELECT id, path, name, language, change_frequency FROM graph_file WHERE path = $path AND graph_id = 'default' LIMIT 1",
            {"path": file_path},
        )
        file_node = parse_one(file_result)
        if not file_node:
            return {"error": f"File '{file_path}' not found in graph"}

        file_id = str(serialize_record(file_node["id"]))

        importers = [
            serialize_record(r)
            for r in parse_rows(
                await db.query(
                    f"SELECT path, name, language FROM ({file_id})<-imports<-graph_file WHERE graph_id = 'default'"
                )
            )
        ]

        functions = [
            serialize_record(r)
            for r in parse_rows(
                await db.query(
                    f"SELECT name, kind, line_start, line_end FROM ({file_id})->depends_on->graph_function WHERE graph_id = 'default'"
                )
            )
        ]

        caps = [
            serialize_record(c)
            for c in parse_rows(
                await db.query(
                    "SELECT slug, name FROM capability WHERE reality.files CONTAINS $path AND product = <record>$product",
                    {"path": file_path, "product": product_id},
                )
            )
        ]

    return {
        "file": file_path,
        "importers": importers,
        "importer_count": len(importers),
        "functions": functions,
        "function_count": len(functions),
        "capabilities": caps,
        "safe_to_delete": len(importers) == 0,
        "summary": f"{'SAFE' if not importers else 'BREAKING'}: {len(importers)} file(s) import this, {len(functions)} function(s) defined",
    }


async def ace_history(file_path: str, graph_id: str = "default") -> str:
    """Get the decision history for a file.

    Shows why things were built this way — decisions, outcomes, timestamps.
    """
    try:
        async with pool.connection() as db:
            file_row = await _find_graph_file(db, file_path, graph_id)
            if not file_row:
                return f"**File not found in graph:** `{file_path}`\n\nNo graph node exists for this path. Has the graph been built for this repo?"

            node_id = serialize_record(file_row.get("id", ""))
            path = file_row.get("path", file_path)

            # Decisions connected via improves edges (inbound: decision improves file)
            decisions_result = await db.query(
                f"""
                SELECT id, title, description, outcome, created_at, tags
                FROM (({node_id})<-improves<-graph_decision)
                WHERE graph_id = $gid
                ORDER BY created_at DESC
                LIMIT 30
                """,
                {"gid": graph_id},
            )
            decisions = [serialize_record(r) for r in parse_rows(decisions_result)]

            # Also check informed_by edges (file was informed by decisions)
            informed_result = await db.query(
                f"""
                SELECT id, title, description, outcome, created_at
                FROM (({node_id})->informed_by->graph_decision)
                WHERE graph_id = $gid
                ORDER BY created_at DESC
                LIMIT 10
                """,
                {"gid": graph_id},
            )
            informed = [serialize_record(r) for r in parse_rows(informed_result)]

    except Exception as exc:
        logger.warning("ace_history error: %s", exc)
        return f"**Error loading history:** {exc}"

    lines_out = [
        f"## Decision History: `{path}`",
        "",
    ]

    if not decisions and not informed:
        lines_out.append("_No decisions recorded for this file yet._")
        lines_out.append("")
        lines_out.append(
            "Decisions are captured when Claude Code sessions record observations about this file via `ace_capture`."
        )
        return "\n".join(lines_out)

    if decisions:
        lines_out.append(f"### Decisions that shaped this file ({len(decisions)} total)")
        lines_out.append("")
        for dec in decisions:
            title = dec.get("title", "(untitled)")
            desc = dec.get("description", "")
            outcome = dec.get("outcome", "")
            ts = str(dec.get("created_at", ""))[:10]
            tags = dec.get("tags", [])

            lines_out.append(f"#### {title}")
            if ts:
                lines_out.append(f"*{ts}*")
            if desc:
                lines_out.append(f"{desc}")
            if outcome:
                lines_out.append(f"**Outcome:** {outcome}")
            if tags:
                lines_out.append(f"**Tags:** {', '.join(tags)}")
            lines_out.append("")

    if informed:
        lines_out.append("### Also informed by")
        for dec in informed:
            title = dec.get("title", "(untitled)")
            ts = str(dec.get("created_at", ""))[:10]
            lines_out.append(f"- **{title}** ({ts})")
        lines_out.append("")

    return "\n".join(lines_out)


async def ace_related(file_path: str, graph_id: str = "default") -> str:
    """Find everything connected to a file.

    Returns imports (outgoing), importers (incoming), related_to peers, and decisions — 1-2 hops.
    """
    try:
        async with pool.connection() as db:
            file_row = await _find_graph_file(db, file_path, graph_id)
            if not file_row:
                return f"**File not found in graph:** `{file_path}`\n\nNo graph node exists for this path. Has the graph been built for this repo?"

            node_id = serialize_record(file_row.get("id", ""))
            path = file_row.get("path", file_path)

            # Outgoing imports (this file imports)
            imports_result = await db.query(
                f"SELECT id, path, name FROM (({node_id})->imports->graph_file) WHERE graph_id = $gid LIMIT 30",
                {"gid": graph_id},
            )
            imports = [serialize_record(r) for r in parse_rows(imports_result)]

            # Incoming imports (who imports this)
            importers_result = await db.query(
                f"SELECT id, path, name FROM (({node_id})<-imports<-graph_file) WHERE graph_id = $gid LIMIT 30",
                {"gid": graph_id},
            )
            importers = [serialize_record(r) for r in parse_rows(importers_result)]

            # related_to edges (co-change / semantic similarity)
            related_result = await db.query(
                f"SELECT id, path, name FROM (({node_id})->related_to->graph_file) WHERE graph_id = $gid LIMIT 20",
                {"gid": graph_id},
            )
            related = [serialize_record(r) for r in parse_rows(related_result)]

            # Functions in this file
            functions_result = await db.query(
                "SELECT id, name FROM graph_function WHERE file = $fid AND graph_id = $gid LIMIT 20",
                {"fid": node_id, "gid": graph_id},
            )
            functions = [serialize_record(r) for r in parse_rows(functions_result)]

            # Decisions
            decisions_result = await db.query(
                f"SELECT id, title, created_at FROM (({node_id})<-improves<-graph_decision) WHERE graph_id = $gid ORDER BY created_at DESC LIMIT 10",
                {"gid": graph_id},
            )
            decisions = [serialize_record(r) for r in parse_rows(decisions_result)]

    except Exception as exc:
        logger.warning("ace_related error: %s", exc)
        return f"**Error finding related nodes:** {exc}"

    total = len(imports) + len(importers) + len(related) + len(decisions)
    lines_out = [
        f"## Connected Graph: `{path}`",
        "",
        f"**{total} connections** — {len(imports)} imports out, {len(importers)} imports in, "
        f"{len(related)} co-changed, {len(decisions)} decisions",
        "",
    ]

    if imports:
        lines_out.append(f"### Imports ({len(imports)} outgoing)")
        for f in imports:
            fp = f.get("path") or f.get("name") or f.get("id", "?")
            lines_out.append(f"- `{fp}`")
        lines_out.append("")

    if importers:
        lines_out.append(f"### Imported by ({len(importers)} incoming)")
        for f in importers:
            fp = f.get("path") or f.get("name") or f.get("id", "?")
            lines_out.append(f"- `{fp}`")
        lines_out.append("")

    if related:
        lines_out.append(f"### Co-changed / related ({len(related)})")
        for f in related:
            fp = f.get("path") or f.get("name") or f.get("id", "?")
            lines_out.append(f"- `{fp}`")
        lines_out.append("")

    if functions:
        lines_out.append(f"### Functions defined here ({len(functions)})")
        for fn in functions[:10]:
            lines_out.append(f"- `{fn.get('name', '?')}`")
        if len(functions) > 10:
            lines_out.append(f"- …and {len(functions) - 10} more")
        lines_out.append("")

    if decisions:
        lines_out.append(f"### Decisions ({len(decisions)})")
        for dec in decisions:
            title = dec.get("title", "(untitled)")
            ts = str(dec.get("created_at", ""))[:10]
            lines_out.append(f"- **{title}** ({ts})")
        lines_out.append("")

    if total == 0:
        lines_out.append("_No connections found. This file may be isolated or the graph may need updating._")

    return "\n".join(lines_out)


async def ace_product_health(
    product_id: str = DEFAULT_ORG,
    explain: str | None = None,
) -> dict:
    """Get product health summary — capabilities, gaps, quality scores.

    Args:
        explain: D4 — discipline name to explain (e.g. "security").
                 When set, adds per-capability gaps + evidence for that dimension.
                 Also includes D2 trend data (delta_30d, trend_arrow) per dimension.
    """
    from core.engine.product.map import ProductMap

    pm = ProductMap(pool)
    result = await pm.health_summary(product_id)

    # D2: Enrich dimensions with trend data
    try:
        from core.engine.sentinel.engines.gap_analyzer import get_score_trend

        for dim in list(result.get("dimensions", {}).keys()):
            trend = await get_score_trend(product_id, dim, days=30)
            if trend.get("trend") != "insufficient_data":
                delta = trend.get("delta", 0.0)
                result["dimensions"][dim]["trend"] = trend["trend"]
                result["dimensions"][dim]["delta_30d"] = delta
                result["dimensions"][dim]["trend_arrow"] = (
                    "↑↑" if delta > 0.10 else "↑" if delta > 0.05 else "↓" if delta < -0.05 else "→"
                )
    except Exception:
        pass  # Trend enrichment is optional

    # D4: Per-capability explanation for a specific dimension
    if explain:
        async with pool.connection() as db:
            cap_rows = parse_rows(
                await db.query(
                    "SELECT capability, score, gaps, evidence FROM capability_quality "
                    "WHERE product = <record>$product AND dimension = <string>$dim "
                    "ORDER BY score ASC LIMIT 20",
                    {"product": product_id, "dim": explain},
                )
            )
        explanation_caps = []
        for row in cap_rows:
            cap_id = str(row.get("capability", ""))
            slug = cap_id.split(":")[-1] if ":" in cap_id else cap_id
            explanation_caps.append(
                {
                    "slug": slug,
                    "score": row.get("score", 0.0),
                    "gaps": row.get("gaps", []),
                    "evidence": row.get("evidence", []),
                }
            )
        result["explanation"] = {
            "dimension": explain,
            "capabilities": explanation_caps,
        }

    return result


async def ace_explain_gap(
    capability_slug: str,
    dimension: str,
    product_id: str = DEFAULT_ORG,
) -> dict:
    """Return specific gaps and evidence for a capability × dimension.

    Answers: "Why is auth_system security score 0.2?"

    Args:
        capability_slug: Capability slug (e.g. "auth_system")
        dimension:       Discipline dimension (e.g. "security")

    Returns: {capability_slug, dimension, score, confidence, confidence_label,
              gaps[], evidence[], assessed_at, fix_priority}
    """
    from core.engine.sentinel.engines.gap_analyzer import _confidence_label

    async with pool.connection() as db:
        rows = parse_rows(
            await db.query(
                """SELECT score, confidence, gaps, evidence, assessed_at
                   FROM capability_quality
                   WHERE product = <record>$product
                   AND dimension = <string>$dim
                   AND capability = (
                       SELECT VALUE id FROM capability
                       WHERE slug = <string>$slug AND product = <record>$product
                       LIMIT 1
                   )
                   LIMIT 1""",
                {"product": product_id, "dim": dimension, "slug": capability_slug},
            )
        )

    if not rows:
        return {
            "capability_slug": capability_slug,
            "dimension": dimension,
            "error": "No quality record found for this capability × dimension",
        }

    row = rows[0]
    score = float(row.get("score", 0.0))
    confidence = float(row.get("confidence", 0.5))

    fix_priority = "high" if score < 0.3 else "medium" if score < 0.6 else "low"

    return {
        "capability_slug": capability_slug,
        "dimension": dimension,
        "score": score,
        "confidence": confidence,
        "confidence_label": _confidence_label(confidence),
        "gaps": row.get("gaps", []),
        "evidence": row.get("evidence", []),
        "assessed_at": str(row.get("assessed_at", "")),
        "fix_priority": fix_priority,
    }


async def ace_gaps(product_id: str = DEFAULT_ORG, dimension: str | None = None) -> dict:
    """Get current quality gaps, optionally filtered by dimension.

    D5: Includes confidence + confidence_label per gap.
    D1: Includes file:line findings from static analysis where available.
    """
    from core.engine.sentinel.engines.gap_analyzer import _confidence_label

    async with pool.connection() as db:
        if dimension:
            result = await db.query(
                "SELECT * FROM capability_quality WHERE product = <record>$product AND dimension = <string>$dim AND score < 0.6 ORDER BY score",
                {"product": product_id, "dim": dimension},
            )
        else:
            result = await db.query(
                "SELECT * FROM capability_quality WHERE product = <record>$product AND score < 0.6 ORDER BY score",
                {"product": product_id},
            )
        rows = parse_rows(result)

    # D5: Enrich with confidence label
    enriched = []
    for row in rows:
        conf = float(row.get("confidence", 0.5))
        row["confidence_label"] = _confidence_label(conf)
        enriched.append(row)

    # D1: Attach file:line findings from capability_finding where available
    try:
        async with pool.connection() as db:
            for row in enriched:
                cap_id = row.get("capability")
                if not cap_id:
                    continue
                dim = row.get("dimension", "")
                finding_rows = parse_rows(
                    await db.query(
                        """SELECT file, line, severity, message, fix_command, tool
                           FROM capability_finding
                           WHERE product = <record>$product
                           AND capability = <record>$cap_id
                           AND discipline = <string>$dim
                           AND resolved_at = NONE
                           ORDER BY severity DESC LIMIT 5""",
                        {"product": product_id, "cap_id": str(cap_id), "dim": dim},
                    )
                )
                if finding_rows:
                    row["findings"] = finding_rows
    except Exception:
        pass  # Findings enrichment is optional

    return {"gaps": enriched, "count": len(enriched)}


async def ace_diff_impact(
    diff: str,
    product_id: str = DEFAULT_ORG,
) -> dict:
    """Predict how a code diff will change discipline scores.

    Call before merging a PR: pass the git diff output.
    Identifies affected capabilities via realizes edges, then predicts
    score changes using the gap analyzer's assessment logic.

    Args:
        diff: Raw git diff string (output of `git diff main...HEAD`)

    Returns: {affected_capabilities, score_predictions, net_impact, recommendation}
    """
    from core.engine.sentinel.engines.gap_analyzer import (
        _assess_diff_impact,
        _parse_diff_summary,
    )

    diff_summary = _parse_diff_summary(diff)

    if not diff_summary["modified_files"]:
        return {
            "affected_capabilities": [],
            "score_predictions": [],
            "net_impact": "none",
            "recommendation": "No supported files modified.",
        }

    # Find capabilities affected by modified files via realizes edges
    affected_caps: list[dict] = []
    seen_cap_ids: set[str] = set()

    async with pool.connection() as db:
        for file_path in diff_summary["modified_files"][:10]:
            rows = parse_rows(
                await db.query(
                    """SELECT out AS cap FROM realizes
                       WHERE in = (
                           SELECT id FROM graph_file WHERE path = <string>$file LIMIT 1
                       ) LIMIT 1""",
                    {"file": file_path},
                )
            )
            for row in rows:
                cap_id = str(row.get("cap", ""))
                if not cap_id or cap_id in seen_cap_ids:
                    continue
                seen_cap_ids.add(cap_id)

                cap_rows = parse_rows(
                    await db.query(
                        "SELECT id, slug, name FROM capability WHERE id = <record>$cap LIMIT 1",
                        {"cap": cap_id},
                    )
                )
                if cap_rows:
                    affected_caps.append(cap_rows[0])

    if not affected_caps:
        return {
            "affected_capabilities": [],
            "score_predictions": [],
            "net_impact": "insufficient_data",
            "recommendation": "Modified files not mapped to any capability. Run ace_scan_repo first.",
        }

    # Load current scores and generate predictions per capability
    all_predictions: list[dict] = []

    async with pool.connection() as db:
        for cap in affected_caps[:5]:
            cap_id = str(cap.get("id", ""))
            slug = cap.get("slug", "")

            score_rows = parse_rows(
                await db.query(
                    "SELECT dimension, score FROM capability_quality WHERE capability = <record>$cap",
                    {"cap": cap_id},
                )
            )
            current_scores = {r["dimension"]: r["score"] for r in score_rows if "dimension" in r}

            predictions = await _assess_diff_impact(
                diff_summary=diff_summary,
                capability=cap,
                current_scores=current_scores,
                disciplines=list(current_scores.keys()) or ["security", "testing", "code_conventions"],
            )

            for pred in predictions:
                delta = float(pred.get("predicted_delta", 0.0))
                if delta == 0.0:
                    continue
                all_predictions.append(
                    {
                        "capability": slug,
                        "dimension": pred.get("dimension", ""),
                        "current_score": current_scores.get(pred.get("dimension", ""), None),
                        "predicted_delta": delta,
                        "reason": pred.get("reason", ""),
                    }
                )

    # Summarise net impact
    negative = [p for p in all_predictions if p["predicted_delta"] < -0.1]
    positive = [p for p in all_predictions if p["predicted_delta"] > 0.1]

    if any(p["dimension"] in ("security",) and p["predicted_delta"] < -0.15 for p in all_predictions):
        net_impact = "critical"
        recommendation = "Security regression detected — address before merging."
    elif len(negative) > len(positive):
        net_impact = "negative"
        recommendation = f"{len(negative)} discipline(s) predicted to decline. Review before merging."
    elif positive:
        net_impact = "positive"
        recommendation = f"{len(positive)} discipline(s) predicted to improve."
    else:
        net_impact = "neutral"
        recommendation = "No significant score changes predicted."

    return {
        "affected_capabilities": [c.get("slug", "") for c in affected_caps],
        "diff_summary": diff_summary,
        "score_predictions": all_predictions,
        "net_impact": net_impact,
        "recommendation": recommendation,
    }


async def ace_recommend(product_id: str = DEFAULT_ORG) -> dict:
    """Get prioritized recommendations for what to work on next.

    Uses the 5-dimension StrategicPrioritizer when available (S4):
        gap_severity × 0.25, defensibility × 0.20, market_timing × 0.20,
        leverage × 0.20, compounding × 0.15

    When no gaps exist (all quality scores ≥ 0.6), returns 'mode: innovate'
    with the top whitespace opportunities to signal that ace_innovate should run.
    """
    async with _timed_tool("ace_recommend"):
        from core.engine.product.strategic_prioritizer import StrategicPrioritizer

        prioritizer = StrategicPrioritizer(pool)
        try:
            recs = await prioritizer.prioritize(product_id)
            if not recs:
                # No gaps — signal innovation mode with top whitespace opportunities
                try:
                    async with pool.connection() as db:
                        ws_rows = parse_rows(
                            await db.query(
                                """SELECT slug, title, whitespace_score
                                   FROM whitespace_opportunity
                                   WHERE product = <record>$product
                                   ORDER BY whitespace_score DESC
                                   LIMIT 3""",
                                {"product": product_id},
                            )
                        )
                except Exception:
                    ws_rows = []
                # Emit event so conductor can trigger innovation mode
                try:
                    from core.engine.events.bus import bus as _bus

                    await _bus.emit(
                        "recommend.no_gaps",
                        {"product_id": product_id, "gap_count": 0},
                    )
                except Exception:
                    pass
                return {
                    "recommendations": [],
                    "mode": "innovate",
                    "message": "All quality gaps are closed. Run ace_innovate to find next opportunities.",
                    "whitespace_preview": ws_rows,
                }
            return {"recommendations": recs[:10], "mode": "gap_driven"}
        except Exception as e:
            logger.warning("ace_recommend failed: %s", e)
            return {"recommendations": [], "error": str(e)}


def _roadmap_item_to_dict(item) -> dict:
    return {
        "title": item.title,
        "kind": item.kind,
        "gap": round(item.gap, 3),
        "rank": round(item.rank, 3),
        "rationale": item.rationale,
        "spec_status": item.spec_status,
        "staleness": item.staleness.value,
        "blocking": item.blocking_patterns,
        "capability_slug": item.capability_slug,
        "source_ref": item.source_ref,
    }


async def ace_roadmap(product_id: str = DEFAULT_ORG) -> dict:
    """The living roadmap — what's next, computed fresh from the graph (capabilities ×
    priorities × specs × staleness). This is canonical; the strategy docs are snapshots."""
    async with _timed_tool("ace_roadmap"):
        roadmap = await compute_roadmap(product_id)
        return {
            "product_id": roadmap.product_id,
            "ambition": roadmap.ambition_summary,
            "lanes": {lane: [_roadmap_item_to_dict(i) for i in items] for lane, items in roadmap.lanes.items()},
        }


async def ace_promote(spec_id: str, product_id: str = DEFAULT_ORG) -> dict:
    """Approve a built spec: merge its arm build into base (gate-validated), built->shipped."""
    async with _timed_tool("ace_promote"):
        from core.engine.arms.promotion import promote

        return await promote(spec_id, product_id=product_id)


async def ace_reject(spec_id: str, product_id: str = DEFAULT_ORG) -> dict:
    """Reject a built spec's build: discard the worktree and re-queue the spec."""
    async with _timed_tool("ace_reject"):
        from core.engine.arms.promotion import reject

        return await reject(spec_id, product_id=product_id)


async def ace_build(spec_id: str, product_id: str = DEFAULT_ORG) -> dict:
    """Build a roadmap spec via an arm (→ review lane). You promote it to ship."""
    async with _timed_tool("ace_build"):
        from core.engine.arms.builder import build_spec

        return await build_spec(spec_id, product_id=product_id)


async def ace_scan_repo(repo_path: str = ".", product_id: str = DEFAULT_ORG) -> dict:
    """Scan a code repository and build its knowledge graph.

    - GitHub URL or 'owner/repo' slug: clones and deep-scans the external repo,
      upserts a competitor record, returns scan stats.
    - Local path (or "."): full AST+git scan of the codebase (graph_id="default"),
      then refreshes capability mapping. Use this to rescan the platform after
      significant code changes.
    """
    import os

    # Route: GitHub URL or owner/repo slug → external scanner (fire-and-forget)
    _is_github = repo_path.startswith(("https://github.com/", "http://github.com/")) or (
        "/" in repo_path and not repo_path.startswith((".", "/", "~"))
    )
    if _is_github:
        try:
            import asyncio
            import re as _re

            from core.engine.scanner.external import scan_external_repo

            # Pre-compute the competitor slug so we can return it immediately
            _slug_match = _re.match(
                r"(?:https?://github\.com/)?([A-Za-z0-9_.-]+)/([A-Za-z0-9_.-]+?)(?:\.git)?/?$",
                repo_path.strip(),
            )
            if _slug_match:
                _owner, _repo = _slug_match.group(1), _slug_match.group(2)
                _comp_slug = f"{_owner}_{_repo}".lower().replace("-", "_").replace(".", "_")
            else:
                _comp_slug = None

            def _log_external_scan_error(task: asyncio.Task) -> None:
                exc = task.exception() if not task.cancelled() else None
                if exc:
                    logger.error("Background external scan failed for %s: %s", repo_path, exc)

            _ext_task = asyncio.create_task(scan_external_repo(repo_path, product_id=product_id))
            _ext_task.add_done_callback(_log_external_scan_error)
            return {
                "status": "started",
                "competitor_id": f"competitor:{_comp_slug}" if _comp_slug else None,
                "message": f"External scan running in background for {repo_path}. "
                "Graph + capability map will be ready in a few minutes.",
            }
        except Exception as e:
            logger.warning("ace_scan_repo (external) failed to start: %s", e)
            return {"error": str(e)}

    # Local path → fire-and-forget scan (scan_repo can take 10+ min; MCP has a hard timeout)
    abs_path = os.path.abspath(repo_path)
    if not os.path.isdir(abs_path):
        return {"error": f"Path not found: {abs_path}"}

    try:
        import asyncio

        from core.engine.scanner.scanner import scan_repo

        def _log_local_scan_error(task: asyncio.Task) -> None:
            exc = task.exception() if not task.cancelled() else None
            if exc:
                logger.error("Background local scan failed for %s: %s", abs_path, exc)

        _local_task = asyncio.create_task(scan_repo(abs_path, graph_id="default"))
        _local_task.add_done_callback(_log_local_scan_error)
    except Exception as e:
        logger.warning("ace_scan_repo (local scan) failed to start: %s", e)
        return {"error": str(e)}

    return {
        "status": "started",
        "message": f"Scan running in background for {abs_path}. Graph will update as files are processed.",
        "graph_id": "default",
    }


def _build_diagram_service(product_id: str):
    """Factory — isolated for test patching.

    Uses the module-level `pool` singleton already imported at the top of this
    file. Matches the pattern used by other MCP tools.
    """
    from core.engine.diagram.graph_reader import GraphReader
    from core.engine.diagram.service import DiagramService
    from core.engine.product.map import ProductMap

    reader = GraphReader(product_map=ProductMap(pool))
    return DiagramService(reader=reader)


async def ace_diagram(
    scope: str = "system",
    product_id: str = DEFAULT_ORG,
) -> dict:
    """Generate an architecture diagram from the code graph.

    Returns a Mermaid flowchart curated by the LLM abstraction pass. The
    'degraded' flag is True if the LLM fell back to raw graph grouping
    (sentinel: the container name '(ungrouped)' appearing in output).
    """
    try:
        service = _build_diagram_service(product_id)
        product_name = product_id.split(":", 1)[-1].replace("_", " ").title()
        mermaid = await service.generate(product_id=product_id, product_name=product_name)
        return {
            "scope": scope,
            "product_id": product_id,
            "format": "mermaid",
            "mermaid": mermaid,
            "degraded": "(ungrouped)" in mermaid,
        }
    except Exception as e:
        logger.exception("ace_diagram failed")
        return {"error": str(e)}


async def ace_self_audit(
    gaps_only: bool = False,
    budget: int = 50,
    product_id: str = DEFAULT_ORG,
) -> dict:
    """Run ACE on itself: load 47 human-verified capabilities into the product map,
    then evaluate each against quality disciplines. Returns gap report.

    Args:
        gaps_only: Skip capability loading, just run gap analysis on existing capabilities.
        budget: Max capability x dimension evaluations (default: 50).
        product_id: Organization ID.
    """
    results = {"loaded": 0, "analysis": {}, "worst_scores": [], "error": None}

    try:
        if not gaps_only:
            import sys

            sys.path.insert(0, ".")
            from docs.capability_manifest import load_manifest

            load_result = await load_manifest(pool, product_id)
            results["loaded"] = load_result["loaded"]

        from core.engine.sentinel.engines.gap_analyzer import run_gap_analyzer

        analysis = await run_gap_analyzer(product_id, budget=budget)
        results["analysis"] = analysis

        async with pool.connection() as db:
            worst_result = await db.query(
                """SELECT capability.slug AS slug, dimension, score, gaps
                   FROM capability_quality WHERE product = <record>$product AND score < 0.6
                   ORDER BY score LIMIT 15""",
                {"product": product_id},
            )
            results["worst_scores"] = parse_rows(worst_result)

    except Exception as e:
        logger.warning("ace_self_audit failed: %s", e)
        results["error"] = str(e)

    # Wiring audit — static analysis, always runs (non-fatal)
    try:
        from core.engine.sentinel.engines.wiring_auditor import WiringAuditor

        wiring_report = WiringAuditor().run()
        results["wiring"] = wiring_report
        if not wiring_report["clean"]:
            logger.warning(
                "ace_self_audit wiring gaps: mcp_parity=%s idle_validators=%s",
                wiring_report["mcp_parity_gaps"],
                wiring_report["idle_validators"],
            )
    except Exception as e:
        logger.warning("ace_self_audit wiring check failed (non-fatal): %s", e)
        results["wiring"] = {"error": str(e)}

    return results


async def ace_ask_product(question: str, product_id: str = DEFAULT_ORG) -> dict:
    """Ask a question about the product — creates a product question for investigation."""
    async with pool.connection() as db:
        result = await db.query(
            """CREATE product_question SET
                question = $question,
                category = 'inward',
                source = 'human',
                priority = 'medium',
                status = 'open'""",
            {"product": product_id, "question": question},
        )
        row = parse_one(result)
        q_id = str(row["id"]) if row else "unknown"
    return {"question_id": q_id, "status": "open", "question": question}


async def ace_create_spec(
    description: str,
    source: str = "human",
    capability_slug: str | None = None,
    product_id: str = DEFAULT_ORG,
) -> dict:
    """Generate an agent-executable spec from a description.

    The PM analyzes the request against the product map, code graph,
    and best practices to produce a detailed spec with acceptance criteria.
    """
    async with _timed_tool("ace_create_spec"):
        from core.engine.product.spec_generator import SpecGenerator

        gen = SpecGenerator(pool)
        try:
            if source == "gap" and capability_slug:
                # Minimal gap dict from description
                gap = {"dimension": "unknown", "score": 0.0, "gaps": [description]}
                return await gen.from_gap(gap, capability_slug, product_id)
            # source == "human" (default) convenes the deep-committee build partner team:
            # research → dynamic lenses each run deep → risk/blast-radius → team-authored spec.
            return await gen.from_request_with_team(description, product_id)
        except Exception as e:
            logger.warning("ace_create_spec failed: %s", e)
            return {"error": str(e)}


async def ace_discover(vision: str, product_id: str = DEFAULT_ORG) -> dict:
    """Explore a vague vision into candidate specs — the FRONT of the build->ship loop.

    Fans out distinct directions the vision could take, converges on the best few, and emits
    them as draft agent_specs tagged source='discover'. The human reviews the candidates and
    picks which to build (call ace_build on the chosen spec) — that choice is the partnership
    gate (there is no separate approve step; draft specs are directly buildable). Pairs with
    ace_build (build a spec) and ace_promote (ship a build)."""
    from core.engine.product.discover import discover

    return await discover(vision, product_id=product_id)


async def ace_submit_feedback(
    spec_id: str,
    feedback_type: str,
    content: str,
    product_id: str = DEFAULT_ORG,
) -> dict:
    """Submit structured feedback from an agent to the PM.

    Types: blocker, discovery, trade_off, scope_question, completion, progress.
    The PM processes the feedback and takes appropriate action.
    """
    from core.engine.product.feedback_handler import FeedbackHandler
    from core.engine.product.spec_models import AgentFeedbackCreate

    try:
        feedback = AgentFeedbackCreate(
            spec_id=spec_id,
            feedback_type=feedback_type,
            content=content,
        )
        handler = FeedbackHandler(pool)
        return await handler.handle(feedback, product_id)
    except Exception as e:
        logger.warning("ace_submit_feedback failed: %s", e)
        return {"error": str(e)}


async def ace_verify_spec(
    spec_id: str,
    product_id: str = DEFAULT_ORG,
) -> dict:
    """Trigger acceptance verification for a completed spec.

    Checks each acceptance criterion, evaluates quality delta,
    and determines if follow-up work is needed.
    """
    from core.engine.product.acceptance import AcceptanceVerifier

    verifier = AcceptanceVerifier(pool)
    try:
        return await verifier.verify(spec_id, product_id)
    except Exception as e:
        logger.warning("ace_verify_spec failed: %s", e)
        return {"error": str(e)}


async def ace_search_code(query: str, limit: int = 10) -> dict:
    """Search the codebase semantically — finds related code by meaning, not just filename."""
    from core.engine.search.hybrid import hybrid_search

    results = await hybrid_search(query, product_id="product:platform", limit=limit)
    return {"results": results, "total": len(results)}


_DECISION_TYPE_TO_DISCIPLINE: dict[str, str] = {
    "architecture": "architecture",
    "trade_off": "architecture",
    "convention": "code_conventions",
    "direction": "product_strategy",
    "prioritization": "product_strategy",
    "rejection": "architecture",
}


async def ace_capture_decision(
    title: str,
    decision_type: str,
    rationale: str,
    alternatives: list[str] | None = None,
    affected_capabilities: list[str] | None = None,
    discipline_hint: str | None = None,
    product_id: str = DEFAULT_ORG,
) -> dict:
    """Record a PM decision with rationale and alternatives."""
    from core.engine.product.decisions import create_decision

    # Derive discipline_hint from decision_type when not explicitly provided
    resolved_discipline = discipline_hint or _DECISION_TYPE_TO_DISCIPLINE.get(decision_type)

    cap_ids = None
    if affected_capabilities:
        cap_ids = []
        try:
            async with pool.connection() as db:
                for slug in affected_capabilities:
                    result = await db.query(
                        "SELECT id FROM capability WHERE product = <record>$product AND slug = <string>$slug LIMIT 1",
                        {"product": product_id, "slug": slug},
                    )
                    row = parse_one(result)
                    if row:
                        cap_ids.append(str(row["id"]))
        except Exception as exc:
            logger.warning("Failed to resolve capability slugs: %s", exc)

    result = await create_decision(
        title=title,
        decision_type=decision_type,
        rationale=rationale,
        product_id=product_id,
        alternatives=alternatives,
        affected_capabilities=cap_ids,
        discipline_hint=resolved_discipline,
        source="mcp",
    )
    return serialize_record(result)


async def ace_list_decisions(
    decision_type: str | None = None,
    limit: int = 20,
    product_id: str = DEFAULT_ORG,
) -> dict:
    """List recent decisions."""
    from core.engine.product.decisions import list_decisions

    decisions = await list_decisions(product_id, decision_type=decision_type, limit=limit)
    return {
        "decisions": [serialize_record(d) for d in decisions],
        "count": len(decisions),
    }


async def ace_active_composition(product_id: str = DEFAULT_ORG) -> dict:
    """Return the most recent L3 composition for this product, or empty if none yet.

    Surfaces "the orchestra" — which of the 22 meta-intelligences self-nominated
    for the last classified task, at what depth, and what classification drove
    the selection. Powered by the in-memory cache populated on every
    CognitiveComposer.compose() (also emits canvas.composition.selected on the
    event bus).

    Useful for: AI partners observing the substrate, debugging selection
    decisions, dashboards that show "what's ACE thinking about", any external
    surface that wants the orchestra view without subscribing to the bus.
    """
    from core.engine.cognition.composer import get_recent_composition

    snapshot = get_recent_composition(product_id)
    if snapshot is None:
        return {
            "product_id": product_id,
            "composition": None,
            "note": "No composition has been emitted yet for this product. Run a task through the runtime to populate.",
        }
    return {
        "product_id": product_id,
        "composition": snapshot,
    }


async def ace_link_decisions(
    product_id: str = DEFAULT_ORG,
    dry_run: bool = False,
) -> dict:
    """Auto-link decisions to capabilities and git commits via keyword matching.

    Enriches the traceability graph by creating:
    - affected edges:      decision → capability
    - manifested_by edges: decision → graph_decision (commit)

    Idempotent — safe to re-run; skips edges that already exist.
    Use dry_run=True to preview what would be linked without writing anything.
    """
    from core.engine.product.decision_linker import link_decisions

    return await link_decisions(product_id=product_id, dry_run=dry_run)


async def ace_trace(
    node_id: str,
) -> dict:
    """Traverse the graph from any node in all directions.

    Given any record ID (decision, capability, graph_file, graph_decision),
    returns everything directly connected to it — enabling traceability from
    any starting point.

    Examples:
      ace_trace("decision:abc123")    → capabilities, commits, specs
      ace_trace("capability:xyz")     → decisions, files
      ace_trace("graph_file:engine_core_db_py") → functions, capabilities, commits, decisions
      ace_trace("graph_decision:commit_a1b2c3") → files, decisions
    """
    from core.engine.product.decision_linker import trace_node

    return await trace_node(node_id=node_id)


async def ace_export_decisions(
    output_path: str = ".ace/decisions.yml",
    mode: str = "warn",
    product_id: str = DEFAULT_ORG,
) -> dict:
    """Export accepted decisions to lockfile for offline enforcement.

    Serializes the decision graph from SurrealDB to .ace/decisions.yml.
    The lockfile bridges the DB to git hooks and CI — which cannot make
    async DB calls but can read a YAML file instantly.

    Run this after adding or modifying decisions via ace_capture_decision.
    Regenerate whenever decisions change to keep enforcement current.

    Args:
        output_path: Where to write the lockfile. Default: .ace/decisions.yml
        mode:        Default enforcement mode for decisions without an explicit mode.
                     warn = advisory only | block = Claude Code/git hook blocks action.
        product_id:  Product to export.

    Returns dict: {exported, output_path, warnings}
    """
    from core.engine.product.enforcer import export_decisions

    return await export_decisions(product_id=product_id, output_path=output_path, mode=mode)


async def ace_enforce(
    action: str,
    target: str | None = None,
    product_id: str = DEFAULT_ORG,
) -> dict:
    """Enforcement engine control.

    Actions:
        status          Show current enforcement config + lockfile age
        check <file>    Check a specific file path against the lockfile
        check-staged    Check all staged git files against lockfile
        install-hook    Install git pre-commit hook
        regen           Re-export lockfile from DB (alias for ace_export_decisions)

    Args:
        action:  One of: status | check | check-staged | install-hook | regen
        target:  File path (for action=check only)
    """
    import os
    import time

    from core.engine.product.enforcer import (
        _LOCKFILE_DEFAULT,
        check_file,
        check_staged,
        export_decisions,
        install_git_hook,
    )

    lockfile = _LOCKFILE_DEFAULT

    if action == "status":
        exists = os.path.exists(lockfile)
        age_hours = None
        decision_count = 0
        if exists:
            age_hours = round((time.time() - os.path.getmtime(lockfile)) / 3600, 1)
            try:
                import yaml

                with open(lockfile) as f:
                    data = yaml.safe_load(f) or {}
                decision_count = len(data.get("decisions", []))
            except Exception:
                pass
        config_exists = os.path.exists(".ace/enforce.config.yml")
        return {
            "lockfile_exists": exists,
            "lockfile_path": lockfile,
            "lockfile_age_hours": age_hours,
            "decisions_exported": decision_count,
            "config_exists": config_exists,
        }

    if action == "check":
        if not target:
            return {"error": "target file path required for action=check"}
        return await check_file(file_path=target)

    if action == "check-staged":
        return await check_staged()

    if action == "install-hook":
        return install_git_hook()

    if action == "regen":
        return await export_decisions(product_id=product_id)

    return {"error": f"Unknown action: {action!r}. Valid: status | check | check-staged | install-hook | regen"}


async def ace_scan_hardening(
    repo_path: str = ".",
    stack_override: list[str] | None = None,
    fast: bool = False,
    store: bool = True,
    product_id: str = DEFAULT_ORG,
) -> dict:
    """Run full static analysis suite. Returns Production Readiness Report.

    Dispatches relevant tools based on detected stack:
    - Always: Semgrep (OWASP) + TruffleHog (secrets)
    - Python: + Bandit + Ruff + pip-audit
    - Node: + npm audit (v2)
    - IaC (tf/k8s): + Checkov (v2)

    Results stored in capability_finding table (queryable via ace_findings).

    Args:
        repo_path:      Path to repo root. Default: current directory.
        stack_override: Override stack detection. e.g. ["python", "terraform"]
        fast:           Fast mode — secrets + critical security only.
        store:          Write findings to capability_finding table. Default: True.
        product_id:     Product context for capability linking.

    Returns: HardeningReport as dict with findings, summary, tools_run.
    """
    import os

    from core.engine.scanner.hardening import _write_findings, run_hardening

    abs_path = os.path.abspath(repo_path)
    report = await run_hardening(
        repo_path=abs_path,
        stack=stack_override,
        fast=fast,
    )

    stored = False
    if store and report.findings:
        await _write_findings(report.findings, report.scan_id, product_id)
        stored = True

    top_findings = [
        {
            "severity": f.severity,
            "discipline": f.discipline,
            "file": f.file,
            "line": f.line,
            "message": f.message[:120],
            "tool": f.tool,
            "fix_command": f.fix_command or None,
        }
        for f in report.findings[:20]
    ]

    return {
        "scan_id": report.scan_id,
        "stack": report.stack,
        "tools_run": report.tools_run,
        "tools_skipped": report.tools_skipped,
        "total_findings": len(report.findings),
        "summary": report.summary,
        "top_findings": top_findings,
        "duration_seconds": report.duration_seconds,
        "stored": stored,
    }


async def ace_cost_estimate(
    users: int = 1000,
    providers: list[str] | None = None,
    product_id: str = DEFAULT_ORG,
) -> dict:
    """Estimate monthly infrastructure + API costs at a given user scale.

    Three-pass analysis using the ACE code graph:
      Pass 1 — Query Cost: detects N+1, unbounded selects, data layer issues
      Pass 2 — Compute Cost: detects deployment topology (Vercel, Railway, Lambda)
      Pass 3 — API Cost: detects third-party integrations (OpenAI, Stripe, SendGrid)

    All estimates are parameterized from your actual capability graph — not generic.

    Args:
        users:     Monthly active users for the estimate. Default: 1000.
        providers: Limit to specific provider keys (e.g. ['vercel', 'openai']).
                   None = auto-detect from graph.

    Returns: {users, total_monthly_usd, compute_costs, api_costs, warnings, report}

    Example output (users=10000):
        Vercel:   $87/mo  (4.2M invocations, 180GB bandwidth)
        OpenAI:   $340/mo (3 completion calls per user session)
        ⚠ Supabase hits Pro tier at ~8,200 users
    """
    from core.engine.product.cost_intelligence import run_cost_estimate

    return await run_cost_estimate(product_id=product_id, users=users, providers=providers)


async def ace_generate_ci(
    target: str = "github_actions",
    repo_path: str = ".",
    product_id: str = DEFAULT_ORG,
) -> dict:
    """Generate a CI/CD workflow file parameterized from the ACE code graph.

    Reads your discipline gap profile and stack capabilities to produce a
    production-ready CI workflow with coverage gates calibrated to your
    current quality scores.

    Args:
        target:     CI system — 'github_actions', 'gitlab_ci', 'circleci'
        repo_path:  Path to repo root (default: current directory)

    Returns: {target, content (YAML), suggested_path, stack, coverage_gates}
    """
    from core.engine.product.generation_engine import run_ci_generator

    return await run_ci_generator(product_id=product_id, target=target, repo_path=repo_path)


async def ace_generate_deploy(
    target: str = "docker_compose",
    repo_path: str = ".",
    product_id: str = DEFAULT_ORG,
) -> dict:
    """Generate a deployment manifest parameterized from the ACE code graph.

    Reads your capability graph to detect services, ports, databases, and
    authentication patterns, then generates a deployment config that
    reflects your actual service topology — not a generic template.

    Args:
        target:     Deploy target — 'docker_compose', 'railway', 'coolify', 'kamal'
        repo_path:  Path to repo root (default: current directory)

    Returns: {target, content (YAML/TOML), suggested_path, services_detected}
    """
    from core.engine.product.generation_engine import run_deploy_generator

    return await run_deploy_generator(product_id=product_id, target=target, repo_path=repo_path)


async def ace_generate_docs(
    format: str = "onboarding_guide",
    repo_path: str = ".",
    product_id: str = DEFAULT_ORG,
) -> dict:
    """Generate documentation artifacts from the ACE intelligence graph.

    Three formats:
        'onboarding_guide'  — Stack, setup, conventions, gotchas for new devs
        'mermaid'           — Architecture diagram from module coupling data
        'api_reference'     — API surface doc from capability + decision graph

    All formats are enriched with captured decisions — not generic stubs.

    Args:
        format:     Output format — 'mermaid', 'onboarding_guide', 'api_reference'
        repo_path:  Path to repo root (default: current directory)

    Returns: {format, content (markdown/mermaid), title}
    """
    from core.engine.product.generation_engine import run_docs_generator

    return await run_docs_generator(product_id=product_id, format=format, repo_path=repo_path)


async def ace_changelog(
    since_tag: str | None = None,
    max_entries: int = 50,
    repo_path: str = ".",
    product_id: str = DEFAULT_ORG,
) -> dict:
    """Generate a decision-enriched changelog from git history.

    Reads git log and enriches commit entries with captured decision rationale
    from the ACE graph, linking each code change to its 'why'.

    Args:
        since_tag:   Git tag to start from (e.g., 'v1.2.0'). None = last 50 commits.
        max_entries: Maximum commits to process. Default: 50.
        repo_path:   Path to git repo. Default: current directory.

    Returns: {changelog (markdown), commit_count, decisions_linked}
    """
    from core.engine.product.generation_engine import run_changelog_generator

    return await run_changelog_generator(
        product_id=product_id,
        since_tag=since_tag,
        max_entries=max_entries,
        repo_path=repo_path,
    )


async def ace_instrument(
    stack: list[str] | None = None,
    repo_path: str = ".",
    product_id: str = DEFAULT_ORG,
) -> dict:
    """Generate production-ready OpenTelemetry configuration for the detected stack.

    Reads stack from ACE capabilities if not provided, then generates:
      - Python/FastAPI: otel_config.py (middleware + structlog integration)
      - Node.js/TypeScript: otel.ts (SDK setup with OTLP export)
      - Always: docker-compose.otel.yml + otel-collector-config.yml (Jaeger)

    Each file is parameterized with your service name and stack — not a generic template.

    Args:
        stack:     Override auto-detected stack (e.g. ['python', 'fastapi']).
                   None = auto-detect from capability graph.
        repo_path: Path to repo root (default: current directory, unused — for future write mode)

    Returns: {stack, files: [{path, content}], files_count, install_commands, quickstart}

    Quickstart:
        1. ace_instrument()  → get files[]
        2. Write files to repo root
        3. docker compose -f docker-compose.otel.yml up -d
        4. Open http://localhost:16686 — traces appear after first request
    """
    from core.engine.product.runtime_bridge import run_instrument

    return await run_instrument(product_id=product_id, stack=stack)


async def ace_explain_error(
    error: str,
    stack_trace: str = "",
    product_id: str = DEFAULT_ORG,
) -> dict:
    """Explain a runtime error using ACE intelligence and your decision graph.

    Five-step pipeline:
      1. Parses stack trace → identifies affected modules/files
      2. Loads ACE decisions relevant to those modules
      3. Checks runbook table for known similar patterns
      4. LLM synthesizes plain-English explanation + actionable fix commands
      5. Auto-captures new patterns as runbooks (compounds over time)

    The compounding loop: every new error explanation adds a runbook entry,
    so future similar errors get faster diagnosis without LLM synthesis.

    Args:
        error:       The error message / exception string.
        stack_trace: Full stack trace (optional but improves module targeting).

    Returns: {explanation, affected_modules, decisions_loaded, runbook_match, captured_as_runbook}

    Example:
        ace_explain_error(
            error="UNIQUE constraint failed: users.email",
            stack_trace="File 'engine/user/create.py', line 45, in create_user\\n  db.insert(user)"
        )
    """
    from core.engine.product.runtime_bridge import run_explain_error

    return await run_explain_error(error=error, stack_trace=stack_trace, product_id=product_id)


async def ace_update_deps(
    strategy: str = "minor",
    repo_path: str = ".",
    product_id: str = DEFAULT_ORG,
) -> dict:
    """Generate a decision-aware dependency update plan.

    Runs pip-audit and npm audit, then cross-references results with the ACE
    decision graph. Packages pinned or mentioned in captured decisions are
    flagged as blocked with the decision rationale attached.

    Three strategies:
      'patch'  — patch-level only (safest, apply immediately)
      'minor'  — minor + patch (recommended, backward-compatible)
      'semver' — all updates including major (requires review)

    Args:
        strategy:   Update scope — 'patch', 'minor', or 'semver'. Default: 'minor'.
        repo_path:  Path to repo root containing requirements*.txt / package.json.

    Returns:
        {strategy, updates: [{package, current, latest, update_type, risk, blocked_by_decision}],
         vulnerabilities, blocked_count, safe_count, total_updates}

    Example output:
        safe to update:   requests 2.28.0 → 2.31.0 (patch, no decision conflict)
        blocked:          surrealdb 0.3.2 → 1.0.0 (major, blocked by "pin SurrealDB for v3 API")
        vulnerability:    cryptography 41.0.0 — CVE-2024-12345 (upgrade to 42.0.0)
    """
    from core.engine.product.runtime_bridge import run_update_deps

    return await run_update_deps(strategy=strategy, repo_path=repo_path, product_id=product_id)


async def ace_findings(
    discipline: str | None = None,
    severity: str | None = None,
    file_path: str | None = None,
    unresolved_only: bool = True,
    limit: int = 50,
    product_id: str = DEFAULT_ORG,
) -> dict:
    """Query persisted static analysis findings.

    Findings are stored by ace_scan_hardening and linked to capabilities.
    Use to drill into specific discipline failures from ace_product_health scores.

    Args:
        discipline:      Filter by discipline (security|testing|code_conventions|...)
        severity:        Filter by severity (critical|high|medium|low|info)
        file_path:       Filter by file path (partial match)
        unresolved_only: Only return unresolved findings. Default: True.
        limit:           Max findings to return. Default: 50.
    """
    where_parts = ["product = <record>$product"]
    params: dict = {"product": product_id, "limit": limit}

    if unresolved_only:
        where_parts.append("resolved_at = NONE")
    if discipline:
        where_parts.append("discipline = <string>$discipline")
        params["discipline"] = discipline
    if severity:
        where_parts.append("severity = <string>$severity")
        params["severity"] = severity
    if file_path:
        where_parts.append("file CONTAINS <string>$file_path")
        params["file_path"] = file_path

    where = " AND ".join(where_parts)

    async with pool.connection() as db:
        rows = parse_rows(
            await db.query(
                f"SELECT * FROM capability_finding WHERE {where} ORDER BY created_at DESC LIMIT $limit",
                params,
            )
        )

    return {
        "findings": [serialize_record(r) for r in rows],
        "count": len(rows),
        "filters": {
            "discipline": discipline,
            "severity": severity,
            "file_path": file_path,
            "unresolved_only": unresolved_only,
        },
    }


async def ace_briefing(
    product_id: str = DEFAULT_ORG,
    date: str | None = None,
    briefing_id: str | None = None,
) -> dict:
    """Retrieve morning briefing with live PM Central intelligence overlay.

    Returns the stored briefing content plus a 'pm_central' section built
    from live DB state (not stale at briefing-write time):

        market_moves      — competitive signals from last 24h
        whitespace        — top 3 whitespace opportunities right now
        product_health    — dimensions with declining scores this week
        next_30_days      — top 5 strategic recommendations

    Pass briefing_id to retrieve a specific version by its stable ID.
    Pass date (YYYY-MM-DD) to retrieve by date. Defaults to latest.
    """
    async with pool.connection() as db:
        if briefing_id:
            result = await db.query(
                "SELECT * FROM ONLY <record>$id",
                {"id": briefing_id},
            )
            # parse_one returns dict; wrap in list for uniform handling below
            from core.engine.core.db import parse_one as _parse_one

            single = _parse_one(result)
            rows_override = [single] if single else []
        elif date:
            result = await db.query(
                """
                SELECT * FROM briefing
                WHERE product = <record>$product AND time::format(created_at, '%Y-%m-%d') = $date
                ORDER BY created_at DESC LIMIT 1
                """,
                {"product": product_id, "date": date},
            )
            rows_override = None
        else:
            result = await db.query(
                "SELECT * FROM briefing WHERE product = <record>$product ORDER BY created_at DESC LIMIT 1",
                {"product": product_id},
            )
            rows_override = None
        rows = rows_override if rows_override is not None else parse_rows(result)
        pm_central = await _build_pm_central(product_id, db)

    if not rows:
        return {
            "content": None,
            "period": "",
            "created_at": "",
            "metrics": {},
            "available": False,
            "pm_central": pm_central,
        }

    briefing = rows[0]
    return {
        "content": briefing.get("content", ""),
        "period": briefing.get("period", ""),
        "created_at": str(briefing.get("created_at", "")),
        "metrics": briefing.get("metrics", {}),
        "available": True,
        "pm_central": pm_central,
    }


async def _build_pm_central(product_id: str, db) -> dict:
    """Build live PM Central intelligence overlay for ace_briefing.

    All sections are best-effort — failures return empty lists, never raise.

    Sections:
        market_moves     — competitive signals last 24h (competitor, summary, created_at)
        whitespace       — top 3 whitespace opportunities (slug, title, whitespace_score)
        product_health   — dimensions with score changes this week (dim, avg_score, trend)
        next_30_days     — top 5 strategic gaps (capability_slug, dimension, priority_score)
    """
    pm: dict = {
        "market_moves": [],
        "whitespace": [],
        "product_health": [],
        "next_30_days": [],
    }

    # MARKET MOVES — competitive signals in last 24h
    try:
        signal_rows = parse_rows(
            await db.query(
                """SELECT competitor, title, signal_type, created_at
                   FROM competitive_signal
                   WHERE product = <record>$product
                     AND created_at > time::now() - 1d
                   ORDER BY created_at DESC
                   LIMIT 5""",
                {"product": product_id},
            )
        )
        pm["market_moves"] = [
            {
                "competitor": r.get("competitor", ""),
                "summary": r.get("title", ""),
                "signal_type": r.get("signal_type", ""),
                "created_at": str(r.get("created_at", "")),
            }
            for r in signal_rows
        ]
    except Exception:
        pass

    # WHITESPACE — top 3 current opportunities
    try:
        ws_rows = parse_rows(
            await db.query(
                """SELECT slug, title, whitespace_score, pain_intensity
                   FROM whitespace_opportunity
                   WHERE product = <record>$product
                   ORDER BY whitespace_score DESC
                   LIMIT 3""",
                {"product": product_id},
            )
        )
        pm["whitespace"] = [
            {
                "slug": r.get("slug", ""),
                "title": r.get("title", ""),
                "whitespace_score": r.get("whitespace_score", 0.0),
            }
            for r in ws_rows
        ]
    except Exception:
        pass

    # PRODUCT HEALTH — dimensions with weekly score changes
    try:
        health_rows = parse_rows(
            await db.query(
                """SELECT dimension, math::mean(score) AS avg_score, count() AS gap_count
                   FROM capability_quality
                   WHERE product = <record>$product AND score < 0.7
                   GROUP BY dimension
                   ORDER BY avg_score ASC
                   LIMIT 5""",
                {"product": product_id},
            )
        )
        pm["product_health"] = [
            {
                "dimension": r.get("dimension", ""),
                "avg_score": round(float(r.get("avg_score") or 0.0), 3),
                "gap_count": r.get("gap_count", 0),
            }
            for r in health_rows
        ]
    except Exception:
        pass

    # NEXT 30 DAYS — top strategic gaps (direct query, no prioritizer instantiation needed)
    try:
        next_rows = parse_rows(
            await db.query(
                """SELECT capability, dimension, score, gaps
                   FROM capability_quality
                   WHERE product = <record>$product AND score < 0.6
                   ORDER BY score ASC
                   LIMIT 5""",
                {"product": product_id},
            )
        )
        # Resolve capability slugs
        cap_ids = [str(r.get("capability", "")) for r in next_rows if r.get("capability")]
        cap_slugs: dict[str, str] = {}
        if cap_ids:
            cap_rows = parse_rows(
                await db.query(
                    "SELECT id, slug FROM capability WHERE id IN $ids",
                    {"ids": parse_record_ids(cap_ids)},
                )
            )
            cap_slugs = {str(c["id"]): c.get("slug", "") for c in cap_rows if c.get("id")}

        pm["next_30_days"] = [
            {
                "capability_slug": cap_slugs.get(str(r.get("capability", "")), "unknown"),
                "dimension": r.get("dimension", ""),
                "current_score": r.get("score", 0),
                "gap_count": len(r.get("gaps") or []),
            }
            for r in next_rows
        ]
    except Exception:
        pass

    return pm


async def ace_seam_check(severity: str | None = None, route: str | None = None, product_id: str = DEFAULT_ORG) -> dict:
    """Check for API contract mismatches between backend and frontend."""
    async with pool.connection() as db:
        query = "SELECT * FROM seam_gap WHERE product = <record>$product"
        params: dict = {"product": product_id}
        if severity:
            query += " AND severity = <string>$sev"
            params["sev"] = severity
        if route:
            query += " AND route = <string>$route"
            params["route"] = route
        query += " ORDER BY severity ASC, route ASC"
        result = await db.query(query, params)
        rows = parse_rows(result)

    gaps = [serialize_record(r) for r in rows]
    summary = {
        "errors": sum(1 for g in gaps if g.get("severity") == "error"),
        "warnings": sum(1 for g in gaps if g.get("severity") == "warning"),
        "info": sum(1 for g in gaps if g.get("severity") == "info"),
    }
    return {"gaps": gaps, "summary": summary}


async def ace_pending_gates(product_id: str = DEFAULT_ORG) -> dict:
    """List all entities waiting for quality gate review."""
    ge = GateEngine(pool)
    gates = await ge.list_pending(product_id)
    return {"gates": gates, "count": len(gates)}


async def ace_spec_reality_check(product_id: str = DEFAULT_ORG) -> dict:
    """Which of your DRAFT specs are already built? Run this BEFORE approving anything.

    Five of sixteen drafts audited by hand were already fully implemented — approve those and walk
    away, and ACE spends the night rebuilding a synthesizer it already has. This is the check that
    stops the backlog lying to an autonomous builder.
    """
    from core.engine.arms.spec_reality import check_spec_reality

    out = []
    try:
        async with pool.connection() as db:
            rows = parse_rows(
                await db.query(
                    "SELECT id, objective FROM agent_spec WHERE product = <record>$p AND status IN ['draft', 'approved']",
                    {"p": product_id},
                )
            )
        for r in rows:
            obj = r.get("objective") or ""
            reality = await check_spec_reality(obj, product_id=product_id)
            if reality.already_exists:
                out.append(
                    {
                        "spec": str(r["id"]),
                        "objective": obj[:100],
                        "confidence": reality.confidence,
                        "evidence": reality.evidence,
                    }
                )
    except Exception as exc:
        logger.warning("ace_spec_reality_check failed (non-fatal): %s", exc)
        return {"already_built": [], "count": 0, "error": str(exc)}
    return {"already_built": out, "count": len(out)}


async def ace_provider_probe() -> dict:
    """Can the CURRENTLY CONFIGURED model actually drive the build loop?

    Exercises the three contracts the arms depend on — structured output (router + critic),
    strict-JSON codegen, and whole-file output — against whatever provider get_llm() resolves to.
    The on-ramp for pointing ACE at a local/open model: find out in a minute instead of after a
    night of parked builds.
    """
    from core.engine.arms.provider_probe import probe_provider

    try:
        r = await probe_provider()
        return {
            "provider": r.provider,
            "ok": r.ok,
            "structured_output": r.structured_output,
            "json_codegen": r.json_codegen,
            "whole_file_output": r.whole_file_output,
            "diagnosis": r.diagnosis,
            "report": r.render(),
        }
    except Exception as exc:  # a probe that becomes the outage is worse than no probe
        logger.warning("ace_provider_probe failed (non-fatal): %s", exc)
        return {"ok": False, "provider": "unknown", "diagnosis": f"{type(exc).__name__}: {exc}"}


async def ace_build_session(product_id: str = DEFAULT_ORG, max_builds: int = 5) -> dict:
    """Run an UNATTENDED build session: build approved specs one at a time until work, budget or
    health runs out. Stops itself on a parked build (the environment is broken) or a run of
    consecutive failures (the engine is broken) rather than grinding the backlog into garbage.

    Fail-safe: an error is reported as a summary with needs_human, never raised at the caller.
    """
    from core.engine.arms import session as _session

    try:
        return await _session.run_build_session(product_id=product_id, max_builds=max_builds)
    except Exception as exc:
        logger.warning("ace_build_session failed (non-fatal): %s", exc)
        return {
            "built": [],
            "failed": [],
            "reconciled_zombies": 0,
            "stopped_because": "error",
            "diagnosis": f"{type(exc).__name__}: {exc}",
            "needs_human": True,
        }


async def ace_parked_runs(product_id: str = DEFAULT_ORG, pool=None) -> dict:
    """Builds that stopped and need a human — the read that makes unattended work reviewable.

    Two shapes, one meaning ("nobody is coming unless you look"):
      - PARKED: the environment broke mid-build (model unreachable, DB down). The build was never
        judged and its workspace is PRESERVED. `diagnosis` says what to fix.
      - RUNNING: a row nobody ever finalized — i.e. the process was killed mid-build. A park the
        engine never got the chance to write.

    A failed build is deliberately NOT here: it was judged, it was wrong, it was discarded. That
    is a normal outcome, not an interruption.

    Fail-safe: returns an empty list on any DB error. A status read must never raise.
    """
    from core.engine.arms import run_ledger

    # Read THROUGH the ledger — it owns the arm_run schema. A hand-written query here would be a
    # second place that has to stay in step with what dispatch writes, and the two would drift.
    try:
        rows = await run_ledger.get_runs_needing_attention(product_id=product_id, pool=pool)
    except Exception as exc:
        logger.warning("ace_parked_runs failed (non-fatal): %s", exc)
        return {"runs": [], "count": 0}

    runs = [
        {
            "id": str(r.get("id")),
            "intent": r.get("intent", ""),
            "arm_domain": r.get("arm_domain", ""),
            "status": r.get("status", ""),
            "diagnosis": r.get("diagnosis") or r.get("reason") or "",
            "attempts": r.get("attempts", 0),
        }
        for r in rows
    ]
    return {"runs": runs, "count": len(runs)}


async def ace_approve_gate(
    entity_type: str,
    entity_id: str,
    rationale: str = "",
    product_id: str = DEFAULT_ORG,
) -> dict:
    """Approve a pending quality gate (spec review, plan review, etc.)."""
    ge = GateEngine(pool)
    gate_state = ""
    try:
        async with pool.connection() as db:
            result = await db.query("SELECT status FROM <record>$id", {"id": entity_id})
            entity = parse_one(result)
            gate_state = entity.get("status", "") if entity else ""
    except Exception:
        pass

    return await ge.approve_gate(entity_type, entity_id, gate_state, rationale, product_id, "user:default")


async def ace_reject_gate(
    entity_type: str,
    entity_id: str,
    reason: str,
    product_id: str = DEFAULT_ORG,
) -> dict:
    """Reject a pending quality gate with reason."""
    ge = GateEngine(pool)
    gate_state = ""
    try:
        async with pool.connection() as db:
            result = await db.query("SELECT status FROM <record>$id", {"id": entity_id})
            entity = parse_one(result)
            gate_state = entity.get("status", "") if entity else ""
    except Exception:
        pass

    return await ge.reject_gate(entity_type, entity_id, gate_state, reason, product_id, "user:default")


async def ace_pr_review(
    pr_url: str = "",
    source: str = "",
    disciplines: list[str] | None = None,
    post_review: bool = False,
    product_id: str = DEFAULT_ORG,
) -> dict:
    """Review a GitHub/GitLab PR or local git branch using ACE's multi-discipline intelligence.

    source formats:
    - "local" or "local:/path/to/repo" — review current branch vs main
    - "github:owner/repo#123" — GitHub PR
    - "gitlab:group/project!42" — GitLab MR
    - Or pass pr_url for GitHub PR URLs (backward compatible)
    """
    from core.engine.review.providers import create_provider

    # Backward compat: pr_url takes precedence
    if pr_url and not source:
        source = pr_url

    if not source:
        # Default to local repo
        source = "local"

    try:
        provider = create_provider(source)
    except ValueError as exc:
        return {"error": str(exc)}

    try:
        pr, files = await provider.get_diff()
    except Exception as exc:
        return {"error": f"Failed to get diff: {exc}"}

    if not files:
        return {
            "pr_number": pr.number,
            "title": pr.title,
            "findings_count": 0,
            "findings": [],
            "summary": "No changes to review.",
            "discipline_scores": {},
            "pass_quality_gate": True,
            "gate_failures": [],
            "impact": {},
        }

    # Load per-repo config from .ace.yaml
    from core.engine.review.config import ReviewConfig
    from core.engine.review.providers import GitHubProvider, LocalGitProvider

    review_config = None
    try:
        if isinstance(provider, GitHubProvider):
            yaml_content = await provider.gh.fetch_file(
                provider.owner,
                provider.repo,
                ".ace.yaml",
                ref=pr.base_branch,
            )
            if yaml_content:
                review_config = ReviewConfig.from_yaml(yaml_content)
        elif isinstance(provider, LocalGitProvider):
            ace_yaml = provider.repo_path / ".ace.yaml"
            if ace_yaml.exists():
                review_config = ReviewConfig.from_yaml(ace_yaml.read_text())
    except Exception:
        pass

    from core.engine.review.engine import ReviewEngine
    from core.engine.review.impact import PRImpactAnalyzer
    from core.engine.review.judge import Judge

    engine = ReviewEngine(product_id=product_id)
    passes = await engine.run_passes(pr, files, disciplines=disciplines)

    judge = Judge()
    synthesis = await judge.synthesize(passes)

    # Re-check quality gate with repo-specific thresholds from .ace.yaml (only when config was found)
    if review_config is not None and review_config.gate:
        gate_result = judge.check_quality_gate(
            synthesis.findings,
            critical_threshold=review_config.gate.critical_threshold,
            high_threshold=review_config.gate.high_threshold,
        )
        synthesis = synthesis.model_copy(
            update={
                "pass_quality_gate": gate_result.pass_quality_gate,
                "gate_failures": gate_result.gate_failures,
            }
        )

    analyzer = PRImpactAnalyzer()
    impact = await analyzer.full_impact([f.path for f in files], product_id)

    if post_review:
        try:
            await provider.post_review(synthesis)
        except Exception as exc:
            logger.warning("Failed to post review: %s", exc)

    # Auto-fix: apply fixes for critical/high findings with suggested fixes
    autofix_result = None
    try:
        from core.engine.review.autofix import AutofixAgent

        agent = AutofixAgent()
        if agent.should_autofix(synthesis):
            if isinstance(provider, GitHubProvider):
                fix_pr = await agent.run(provider.owner, provider.repo, pr.number, pr.base_branch, synthesis)
                if fix_pr:
                    autofix_result = {
                        "type": "github_pr",
                        "pr_number": fix_pr.get("number"),
                        "pr_url": fix_pr.get("html_url"),
                    }
            elif isinstance(provider, LocalGitProvider):
                branch_name = f"ace/fix-{pr.head_branch}" if pr.head_branch else "ace/fix"
                autofix_result = await agent.apply_local_fixes(
                    str(provider.repo_path), synthesis, branch_name=branch_name
                )
                autofix_result["type"] = "local"
    except Exception as exc:
        logger.warning("Autofix failed: %s", exc)

    # Auto-capture review decisions (fire-and-forget, never blocks)
    try:
        from core.engine.review.capture import capture_review_decisions

        logged_task(
            capture_review_decisions(
                pr_title=pr.title,
                disciplines=engine.select_disciplines(files) if files else [],
                synthesis_summary=synthesis.summary,
                findings_count=len(synthesis.findings),
                findings_before_judge=synthesis.findings_before_judge,
                findings_after_judge=synthesis.findings_after_judge,
                pass_quality_gate=synthesis.pass_quality_gate,
                gate_failures=synthesis.gate_failures,
                discipline_scores=synthesis.discipline_scores,
                autofix_result=autofix_result,
                source=source or "local",
                product_id=product_id,
            ),
            label="mcp.pr_review.capture_decisions",
        )
    except Exception:
        pass

    return {
        "pr_number": pr.number,
        "title": pr.title,
        "findings_count": len(synthesis.findings),
        "findings": [f.model_dump() for f in synthesis.findings],
        "summary": synthesis.summary,
        "discipline_scores": synthesis.discipline_scores,
        "pass_quality_gate": synthesis.pass_quality_gate,
        "gate_failures": synthesis.gate_failures,
        "impact": impact,
        "autofix": autofix_result,
    }


async def ace_generate_tests(
    capability_slug: str = "",
    acceptance_criteria: list[str] | None = None,
    context: str = "",
    mode: str = "spec",
    product_id: str = DEFAULT_ORG,
) -> dict:
    """Generate test suites from capability specs or acceptance criteria.

    Modes:
        spec      - load capability_slug spec from DB (default)
        criteria  - use acceptance_criteria list directly
        priority  - auto-pick the worst-coverage capability via coverage_priority

    If capability_slug is provided, loads the spec from the agent_spec table.
    If acceptance_criteria are provided directly, uses them without a DB lookup.
    Returns rendered test code ready to save.
    """
    from core.engine.review.testgen import TestGenerator

    if mode == "priority":
        from core.engine.intelligence.coverage_priority import rank_capabilities

        ranked = await rank_capabilities(product_id=product_id, limit=1)
        if not ranked:
            return {"error": "No capabilities found to prioritize. Run ace_test_coverage first."}
        capability_slug = ranked[0]["slug"]
        context = (
            context + f"\n\nAuto-selected: {capability_slug} "
            f"(function_pct={ranked[0]['function_pct']:.0%}, score={ranked[0]['score']})"
        ).strip()

    gen = TestGenerator()

    if capability_slug:
        # Load spec from DB
        spec: dict = {}
        try:
            async with pool.connection() as db:
                result = await db.query(
                    "SELECT * FROM agent_spec WHERE slug = <string>$slug LIMIT 1",
                    {"slug": capability_slug},
                )
                rows = parse_rows(result)
                if rows:
                    spec = rows[0]
        except Exception as exc:
            logger.warning("ace_generate_tests DB lookup failed: %s", exc)

        if not spec:
            return {"error": f"No spec found for capability_slug={capability_slug!r}"}

        suite = await gen.from_spec(spec)

    elif acceptance_criteria:
        capability_name = context.split("\n")[0][:80] if context else "feature"
        suite = await gen.from_acceptance_criteria(
            criteria=acceptance_criteria,
            capability_name=capability_name,
            context=context,
        )

    else:
        return {"error": "Provide either capability_slug, acceptance_criteria, or mode='priority'"}

    rendered = gen.render(suite)
    categories: list[str] = sorted({tc.category for tc in suite.test_cases if tc.category})

    return {
        "capability": suite.capability,
        "file_path": suite.file_path,
        "test_count": len(suite.test_cases),
        "categories": categories,
        "rendered_code": rendered,
    }


async def _run_pr_review(
    owner: str,
    repo: str,
    pr_number: int,
    product_id: str = DEFAULT_ORG,
    disciplines: list[str] | None = None,
    post_review: bool = False,
) -> dict:
    """Internal: run the full PR review pipeline."""
    from core.engine.core.config import settings
    from core.engine.github.client import GitHubClient
    from core.engine.github.diff_parser import parse_diff
    from core.engine.review.engine import ReviewEngine
    from core.engine.review.impact import PRImpactAnalyzer
    from core.engine.review.judge import Judge

    gh = GitHubClient(token=settings.github_token)
    pr = await gh.fetch_pr(owner, repo, pr_number)
    diff_text = await gh.fetch_diff(owner, repo, pr_number)
    files = parse_diff(diff_text)

    if not files:
        return {
            "pr_number": pr.number,
            "title": pr.title,
            "findings_count": 0,
            "findings": [],
            "summary": "No changes to review.",
            "discipline_scores": {},
            "pass_quality_gate": True,
            "gate_failures": [],
            "impact": {},
        }

    engine = ReviewEngine(product_id=product_id)
    passes = await engine.run_passes(pr, files, disciplines=disciplines)

    judge = Judge()
    synthesis = await judge.synthesize(passes)

    analyzer = PRImpactAnalyzer()
    impact = await analyzer.full_impact([f.path for f in files], product_id)

    return {
        "pr_number": pr.number,
        "title": pr.title,
        "findings_count": len(synthesis.findings),
        "findings": [f.model_dump() for f in synthesis.findings],
        "summary": synthesis.summary,
        "discipline_scores": synthesis.discipline_scores,
        "pass_quality_gate": synthesis.pass_quality_gate,
        "gate_failures": synthesis.gate_failures,
        "impact": impact,
    }


# ---------------------------------------------------------------------------
# Product management
# ---------------------------------------------------------------------------


async def ace_add_product(
    name: str,
    repo_path: str | None = None,
    description: str | None = None,
    ecosystem_slug: str | None = None,
    active_disciplines: list[str] | None = None,
    product_id: str = DEFAULT_ORG,
) -> dict:
    """Add a product to the portfolio. Creates a project record and triggers onboarding."""
    from core.engine.product.ecosystem import EcosystemManager

    slug = name.lower().replace(" ", "-").replace("_", "-")

    project_data = {
        "name": name,
        "slug": slug,
        "description": description or "",
        "repo_path": repo_path,
        "active_disciplines": active_disciplines or [],
    }

    if ecosystem_slug:
        project_data["ecosystem_slug"] = ecosystem_slug

    em = EcosystemManager(pool)
    project = await em.create_project(project_data, product_id)

    # Trigger scan if repo path provided
    if repo_path:
        try:
            from core.engine.events.bus import bus

            await bus.emit(
                "project.onboarded",
                {"project_slug": slug, "repo_path": repo_path, "product_id": product_id},
            )
        except Exception:
            pass

    return {
        "status": "created",
        "slug": slug,
        "name": name,
        "repo_path": repo_path,
        "ecosystem": ecosystem_slug,
        "project": serialize_record(project) if project else {},
    }


# ---------------------------------------------------------------------------
# Code Intelligence tools (Task 8)
# ---------------------------------------------------------------------------

import os  # noqa: E402 — imported here to avoid polluting the top of the file

_cached_builder = None
_cached_mtime: float = 0


def _get_builder():
    """Return a cached GraphBuilder, rebuilding only when repo files changed."""
    global _cached_builder, _cached_mtime

    try:
        current_mtime = os.path.getmtime(".")
    except OSError:
        current_mtime = 0.0

    if _cached_builder is None or current_mtime != _cached_mtime:
        from core.engine.intelligence.graph_builder import GraphBuilder

        _cached_builder = GraphBuilder(".")
        _cached_builder.phase1_treesitter()
        _cached_mtime = current_mtime

    return _cached_builder


async def ace_symbol_importance(limit: int = 20, product_id: str = DEFAULT_ORG) -> dict:
    """Get the most architecturally important files ranked by graph centrality."""
    try:
        from core.engine.intelligence.queries import symbol_importance

        builder = _get_builder()
        scores = symbol_importance(builder.graph, limit=limit)
        return {"symbols": scores, "count": len(scores)}
    except Exception as e:
        return {"error": str(e)}


async def ace_blast_radius(target: str, product_id: str = DEFAULT_ORG) -> dict:
    """Analyze blast radius: what files are affected if this file/symbol changes?"""
    try:
        from core.engine.intelligence.queries import blast_radius

        builder = _get_builder()
        return blast_radius(target, builder.graph)
    except Exception as e:
        return {"error": str(e)}


async def ace_find_dead_code(product_id: str = DEFAULT_ORG) -> dict:
    """Find symbols and files that nothing references (potentially dead code)."""
    try:
        from core.engine.intelligence.queries import find_dead_code

        builder = _get_builder()
        dead = find_dead_code(builder)
        return {"dead_symbols": dead[:50], "count": len(dead)}
    except Exception as e:
        return {"error": str(e)}


async def ace_code_context(query: str, product_id: str = DEFAULT_ORG) -> dict:
    """Graph-aware RAG: extract references from a natural language query and return relevant code context."""
    try:
        from core.engine.intelligence.queries import code_context

        builder = _get_builder()
        return code_context(query, builder)
    except Exception as e:
        return {"error": str(e)}


async def ace_dependency_chain(from_file: str, to_file: str, product_id: str = DEFAULT_ORG) -> dict:
    """Find the shortest dependency path between two files."""
    try:
        from core.engine.intelligence.queries import dependency_chain

        builder = _get_builder()
        chain = dependency_chain(from_file, to_file, builder.graph)
        return {"chain": chain, "length": len(chain)}
    except Exception as e:
        return {"error": str(e)}


async def ace_module_coupling(module_a: str, module_b: str, product_id: str = DEFAULT_ORG) -> dict:
    """Measure coupling between two modules/directories."""
    try:
        from core.engine.intelligence.queries import module_coupling

        builder = _get_builder()
        return module_coupling(module_a, module_b, builder.graph)
    except Exception as e:
        return {"error": str(e)}


async def ace_research(
    topic: str,
    research_type: str = "grounded_how_to",
    product_id: str = DEFAULT_ORG,
    ceiling: str = "sonnet",
) -> dict:
    """Run multi-mode research on a topic and write synthesis to the intelligence graph.

    research_type options:
      "internal"        — Query ACE graph only (zero web calls, instant)
      "grounded_how_to" — How should WE implement X given our stack? (default)
      "competitive"     — What is the landscape? What are others building?
      "greenfield"      — What should we build and why? (Opus, strategic synthesis)
    """
    valid_types = {"internal", "grounded_how_to", "competitive", "greenfield"}
    if research_type not in valid_types:
        return {"error": f"Invalid research_type {research_type!r}. Valid: {sorted(valid_types)}"}

    try:
        from core.engine.research.agent import ResearchAgent

        agent = ResearchAgent(product_id=product_id)
        result = await agent.run(topic=topic, research_type=research_type, ceiling=ceiling)
        return {
            "topic": result.topic,
            "discipline": result.discipline,
            "research_type": result.research_type,
            "synthesis": result.synthesis,
            "confidence": result.confidence,
            "observation_id": result.observation_id,
            "evidence_count": len(result.evidence),
        }
    except Exception as exc:
        return {"error": str(exc)}


async def ace_competitor_matrix(product_id: str = DEFAULT_ORG) -> dict:
    """Return the capability matrix: competitor × capability → coverage (full/partial/none).

    Shows which capabilities each competitor covers. Empty cells (none) are our
    differentiation surface. Use this to identify moats and gaps at a glance.

    Returns: {matrix: {competitor: {capability_slug: coverage}}, differentiation: [slugs]}
    """
    try:
        async with pool.connection() as db:
            rows = parse_rows(
                await db.query(
                    """SELECT competitor, capability_slug, coverage
                       FROM competitor_capability
                       WHERE product = <record>$product
                       ORDER BY competitor, capability_slug""",
                    {"product": product_id},
                )
            )

        # Build nested dict: {competitor: {capability_slug: coverage}}
        matrix: dict[str, dict[str, str]] = {}
        for row in rows:
            comp = row.get("competitor", "")
            slug = row.get("capability_slug", "")
            coverage = row.get("coverage", "none")
            if comp and slug:
                matrix.setdefault(comp, {})[slug] = coverage

        # Differentiation = capabilities where NO competitor has "full" coverage
        all_caps: set[str] = set()
        for caps in matrix.values():
            all_caps.update(caps.keys())

        differentiation = [slug for slug in sorted(all_caps) if not any(matrix[c].get(slug) == "full" for c in matrix)]

        return {
            "matrix": matrix,
            "competitors": sorted(matrix.keys()),
            "capabilities_tracked": sorted(all_caps),
            "differentiation": differentiation,
            "total_entries": len(rows),
        }
    except Exception as exc:
        logger.warning("ace_competitor_matrix failed: %s", exc)
        return {"matrix": {}, "competitors": [], "capabilities_tracked": [], "differentiation": [], "error": str(exc)}


async def ace_whitespace(
    product_id: str = DEFAULT_ORG,
    limit: int = 10,
    min_score: float = 0.0,
) -> dict:
    """Return top whitespace opportunities sorted by score (highest first).

    Whitespace Score = pain_intensity × user_count × (1 - max_competitor_coverage)
                     × feasibility_coefficient × timing_coefficient

    Use this to identify where ACE can differentiate from competitors.

    Args:
        limit:     Max opportunities to return (default 10)
        min_score: Filter opportunities below this threshold

    Returns: {opportunities: [{slug, title, whitespace_score, source, description}], count}
    """
    try:
        async with pool.connection() as db:
            rows = parse_rows(
                await db.query(
                    """SELECT slug, title, description, source, whitespace_score,
                              pain_intensity, user_count, max_competitor_coverage,
                              feasibility_coefficient, timing_coefficient
                       FROM whitespace_opportunity
                       WHERE product = <record>$product
                       AND whitespace_score >= $min_score
                       ORDER BY whitespace_score DESC
                       LIMIT $limit""",
                    {"product": product_id, "min_score": min_score, "limit": limit},
                )
            )

        return {
            "opportunities": rows,
            "count": len(rows),
        }
    except Exception as exc:
        logger.warning("ace_whitespace failed: %s", exc)
        return {"opportunities": [], "count": 0, "error": str(exc)}


async def ace_innovate(
    mode: str = "all",
    product_id: str = DEFAULT_ORG,
) -> dict:
    """Run innovation mode(s) when all gaps are closed.

    Activates when ace_recommend() returns no recommendations.
    Four modes explore different innovation vectors:

    Modes:
        "frontier"     — Frontier benchmarking: A++ beyond current best practices
                         Sources: research papers, professional tooling, adjacent industries
        "cross_domain" — Cross-domain pattern transfer from aviation, film, manufacturing
        "emerging_tech"— Map emerging model capabilities to new ACE capabilities
        "compounding"  — Find features that make other features better over time
        "all"          — Run all four modes sequentially (default)

    Returns: {modes: {...}, total_count, top_impact} or single {mode, results, count}
    """
    from core.engine.product.innovate import run_all_modes, run_innovate_mode

    if mode == "all":
        return await run_all_modes()
    return await run_innovate_mode(mode)


async def ace_list_competitors(product_id: str = DEFAULT_ORG) -> dict:
    """List all tracked competitors and their scan status.

    Returns each competitor with name, tier, last_scanned, and signal counts.
    """
    try:
        async with pool.connection() as db:
            rows = parse_rows(
                await db.query(
                    """
                    SELECT id, name, tier, domains, product, last_scanned,
                           (SELECT count() FROM competitive_signal WHERE competitor = $parent.name AND product = $parent.product GROUP ALL)[0].count AS signal_count
                    FROM competitor
                    WHERE product = <record>$product
                    ORDER BY tier ASC, name ASC
                    """,
                    {"product": product_id},
                )
            )
        return {
            "competitors": [
                {
                    "id": str(r.get("id", "")),
                    "name": r.get("name", ""),
                    "tier": r.get("tier", 2),
                    "domains": r.get("domains", []),
                    "last_scanned": str(r["last_scanned"]) if r.get("last_scanned") else None,
                    "signal_count": r.get("signal_count") or 0,
                }
                for r in rows
            ],
            "count": len(rows),
        }
    except Exception as e:
        logger.warning("ace_list_competitors failed: %s", e)
        return {"competitors": [], "count": 0, "error": str(e)}


async def ace_competitor_signals(
    competitor: str,
    product_id: str = DEFAULT_ORG,
    min_relevance: float = 0.0,
    limit: int = 20,
) -> dict:
    """Fetch competitive signals for a specific competitor.

    Args:
        competitor:    Name of the competitor (e.g. "paul-gauthier/aider")
        product_id:    ACE product ID
        min_relevance: Filter signals below this relevance_score (0.0–1.0)
        limit:         Max signals to return (default 20)
    """
    try:
        async with pool.connection() as db:
            rows = parse_rows(
                await db.query(
                    """
                    SELECT title, description, relevance, relevance_score,
                           action, urgency, rationale, source_url, created_at
                    FROM competitive_signal
                    WHERE competitor = $competitor
                      AND product = <record>$product
                      AND relevance_score >= $min_rel
                    ORDER BY relevance_score DESC
                    LIMIT $limit
                    """,
                    {
                        "competitor": competitor,
                        "product": product_id,
                        "min_rel": min_relevance,
                        "limit": limit,
                    },
                )
            )
        return {
            "competitor": competitor,
            "signals": [
                {
                    "title": r.get("title", ""),
                    "description": r.get("description", ""),
                    "relevance": r.get("relevance", ""),
                    "relevance_score": r.get("relevance_score", 0.0),
                    "action": r.get("action", "monitor"),
                    "urgency": r.get("urgency", "low"),
                    "rationale": r.get("rationale", ""),
                    "source_url": r.get("source_url", ""),
                    "created_at": str(r["created_at"]) if r.get("created_at") else None,
                }
                for r in rows
            ],
            "count": len(rows),
        }
    except Exception as e:
        logger.warning("ace_competitor_signals failed: %s", e)
        return {"competitor": competitor, "signals": [], "count": 0, "error": str(e)}


async def ace_scan_competitors(
    product_id: str = DEFAULT_ORG,
    github_urls: list[str] | None = None,
    tier: int = 2,
) -> dict:
    """Clone and deep-scan a batch of competitor repos.

    If github_urls is provided, scans those repos and upserts them as competitors.
    Otherwise scans all existing competitors in DB that have a github source URL.

    Each repo is scanned sequentially to avoid overwhelming the LAN server.
    Returns a summary of results per repo.
    """
    from core.engine.scanner.external import scan_external_repo

    results = []

    if github_urls:
        # Explicit list — scan each and register as competitors
        for url in github_urls:
            try:
                result = await scan_external_repo(url, product_id=product_id, tier=tier)
                results.append(
                    {
                        "repo": url,
                        "status": "ok",
                        "graph_id": result.get("graph_id"),
                        "files": result.get("stats", {}).get("files_created", 0),
                        "signals": result.get("signals_written", 0),
                        "stars": result.get("metadata", {}).get("stars", 0),
                    }
                )
            except Exception as exc:
                logger.warning("Batch scan failed for %s: %s", url, exc)
                results.append({"repo": url, "status": "error", "error": str(exc)})
    else:
        # Re-scan all existing competitors that have a github source
        async with pool.connection() as db:
            rows = parse_rows(
                await db.query(
                    "SELECT name, sources FROM competitor WHERE product = <record>$product ORDER BY tier ASC",
                    {"product": product_id},
                )
            )

        for comp in rows:
            github_url = None
            for src in comp.get("sources", []):
                if src.get("type") == "github" and src.get("url"):
                    github_url = src["url"]
                    break
            if not github_url:
                results.append({"repo": comp["name"], "status": "skipped", "reason": "no github source"})
                continue

            try:
                result = await scan_external_repo(github_url, product_id=product_id)
                results.append(
                    {
                        "repo": comp["name"],
                        "status": "ok",
                        "graph_id": result.get("graph_id"),
                        "files": result.get("stats", {}).get("files_created", 0),
                        "signals": result.get("signals_written", 0),
                    }
                )
            except Exception as exc:
                logger.warning("Batch rescan failed for %s: %s", comp["name"], exc)
                results.append({"repo": comp["name"], "status": "error", "error": str(exc)})

    ok = sum(1 for r in results if r.get("status") == "ok")
    return {"scanned": ok, "total": len(results), "results": results}


async def ace_web_fetch(url: str, mode: str = "auto") -> dict:
    """Fetch any URL and return clean markdown. Bypasses anti-bot protection.

    mode options:
      "auto"    — try curl_cffi → scrapling → patchright → httpx (default)
      "fast"    — curl_cffi → httpx only (no browser launch)
      "stealth" — scrapling StealthyFetcher (camoufox, best for Cloudflare/DataDome)
      "cdp"     — patchright Chrome CDP (for JS-heavy/interactive pages)
    """
    try:
        from core.engine.research.fetcher import fetch

        result = await fetch(url, mode=mode)
        return {
            "url": result.url,
            "title": result.title,
            "markdown": result.markdown,
            "status": result.status,
            "engine": result.engine,
            "success": result.success,
            **({"error": result.error} if result.error else {}),
        }
    except Exception as exc:
        return {"error": str(exc)}


async def ace_web_search(query: str, limit: int = 10, fetch_content: bool = False) -> dict:
    """Search the web and return results. Optionally fetch full content of top results.

    Uses DuckDuckGo (no API key) with Tavily fallback if TAVILY_API_KEY is set.
    Set fetch_content=True to return full markdown for each result (slower).
    """
    try:
        import os

        import httpx as _httpx

        results = []
        api_key = os.environ.get("TAVILY_API_KEY", "")

        if api_key:
            try:
                async with _httpx.AsyncClient(timeout=15) as client:
                    resp = await client.post(
                        "https://api.tavily.com/search",
                        json={"api_key": api_key, "query": query, "max_results": limit},
                    )
                    resp.raise_for_status()
                    data = resp.json()
                for r in data.get("results", []):
                    results.append(
                        {
                            "url": r.get("url", ""),
                            "title": r.get("title", ""),
                            "snippet": r.get("content", "")[:300],
                        }
                    )
            except Exception:
                pass

        if not results:
            try:
                from ddgs import DDGS

                def _ddg():
                    return list(DDGS().text(query, max_results=limit))

                raw = await asyncio.to_thread(_ddg)
                for r in raw:
                    results.append(
                        {
                            "url": r.get("href", ""),
                            "title": r.get("title", ""),
                            "snippet": r.get("body", "")[:300],
                        }
                    )
            except Exception as exc:
                return {"error": f"Search failed: {exc}"}

        if fetch_content and results:
            from core.engine.research.fetcher import fetch as web_fetch

            async def _fetch_one(r: dict) -> dict:
                try:
                    fr = await web_fetch(r["url"], mode="fast")
                    return {**r, "markdown": fr.markdown[:3000], "engine": fr.engine}
                except Exception:
                    return r

            results = list(await asyncio.gather(*[_fetch_one(r) for r in results[:5]]))

        return {"query": query, "results": results, "count": len(results)}
    except Exception as exc:
        return {"error": str(exc)}


async def ace_discovery_sprint(
    client_name: str,
    product_id: str = DEFAULT_ORG,
    loaded_hourly_rate: float = 150.0,
) -> dict:
    """Generate a client-ready discovery sprint report for an MSP engagement.

    Orchestrates: scan data + gaps + recommendations → DiscoveryReport with:
    - Executive summary (plain language, ≤300 words, no jargon)
    - Top 5 automation candidates with grounded ROI (hours × rate × 52)
    - Spec stubs passable directly to ace_create_spec
    - Markdown + JSON export

    If synthesizer output is available it enriches the report; otherwise
    the report is marked preliminary and uses gaps + recommend only.

    Returns: markdown, summary, automation_candidates, preliminary flag, json
    """
    try:
        from core.engine.product.discovery_sprint import DiscoverySprintPackager
        from core.engine.product.report_models import DiscoveryReport

        # Fetch gaps and recommendations from existing engines
        gaps_result_raw = await ace_gaps(product_id=product_id)
        recommend_result_raw = await ace_recommend(product_id=product_id)

        gaps_list = gaps_result_raw.get("gaps", [])
        recommend_list = recommend_result_raw.get("recommendations", [])

        # Normalise recommend entries so packager can find hours_per_week_saved
        for rec in recommend_list:
            if "hours_per_week_saved" not in rec:
                rec["hours_per_week_saved"] = 2.0  # conservative default

        # Minimal scan summary from product health
        scan_result: dict = {"total_files": 0, "languages": [], "capabilities": []}
        try:
            async with pool.connection() as db:
                cap_rows = parse_rows(
                    await db.query(
                        "SELECT slug, description FROM capability WHERE product = <record>$product LIMIT 20",
                        {"product": product_id},
                    )
                )
                scan_result["capabilities"] = [
                    {"slug": r.get("slug", ""), "description": r.get("description", "")} for r in cap_rows
                ]
        except Exception:
            pass

        packager = DiscoverySprintPackager()
        report: DiscoveryReport = await packager.generate(
            product_id=product_id,
            client_name=client_name,
            scan_result=scan_result,
            gaps_result=gaps_list,
            recommend_result=recommend_list,
            synthesis_result=None,  # preliminary — synthesis requires an active task context
            loaded_hourly_rate=loaded_hourly_rate,
        )

        # Persist report for retainer tracker to reference
        try:
            async with pool.connection() as db:
                await db.query(
                    """
                    CREATE discovery_report SET
                        product    = <record>$product,
                        client_name = $client_name,
                        report_json = $report_json,
                        preliminary = $preliminary,
                        created_at  = time::now()
                    """,
                    {
                        "product": product_id,
                        "client_name": client_name,
                        "report_json": report.to_json(),
                        "preliminary": report.preliminary,
                    },
                )
        except Exception as exc:
            logger.debug("Failed to persist discovery report (non-fatal): %s", exc)

        return {
            "client_name": client_name,
            "preliminary": report.preliminary,
            "automation_count": len(report.automation_candidates),
            "automation_candidates": [c.to_dict() for c in report.automation_candidates],
            "total_annual_value": sum(c.annual_value for c in report.automation_candidates),
            "executive_summary": report.executive_summary,
            "markdown": report.to_markdown(),
            "json": report.to_json(),
        }

    except Exception as exc:
        logger.warning("ace_discovery_sprint failed: %s", exc)
        return {"error": str(exc)}


async def ace_retainer_status(
    product_id: str = DEFAULT_ORG,
    record_delivery_spec_id: str | None = None,
    record_delivery_title: str | None = None,
) -> dict:
    """Get engagement state and next retainer expansion for a client product.

    Optionally record a new delivery: pass record_delivery_spec_id + record_delivery_title
    to append a delivery to the engagement history before computing next expansion.

    Returns:
    - delivery_history: list of all delivered specs
    - next_expansion: title, description, annual_value, retainer framing
    - engagement_complete: True if all discovery sprint candidates are delivered
    """
    import json as _json

    from core.engine.product.retainer import RetainerTracker

    try:
        tracker = RetainerTracker(product_id=product_id)

        # Load existing delivery history from DB
        try:
            async with pool.connection() as db:
                delivery_rows = parse_rows(
                    await db.query(
                        """
                        SELECT spec_id, title, created_at FROM retainer_delivery
                        WHERE product = <record>$product
                        ORDER BY created_at ASC
                        """,
                        {"product": product_id},
                    )
                )
                for row in delivery_rows:
                    tracker.engagement_state.record_delivery(
                        spec_id=row.get("spec_id", ""),
                        title=row.get("title", ""),
                    )
        except Exception as exc:
            logger.debug("Failed to load delivery history (non-fatal): %s", exc)

        # Record a new delivery if requested
        if record_delivery_spec_id and record_delivery_title:
            tracker.record_delivery(
                spec_id=record_delivery_spec_id,
                title=record_delivery_title,
            )
            try:
                async with pool.connection() as db:
                    await db.query(
                        """
                        CREATE retainer_delivery SET
                            product   = <record>$product,
                            spec_id   = $spec_id,
                            title     = $title,
                            created_at = time::now()
                        """,
                        {
                            "product": product_id,
                            "spec_id": record_delivery_spec_id,
                            "title": record_delivery_title,
                        },
                    )
            except Exception as exc:
                logger.warning("Failed to persist retainer delivery: %s", exc)

        # Load latest discovery report for expansion recommendations
        discovery_report = None
        try:
            async with pool.connection() as db:
                rows = parse_rows(
                    await db.query(
                        """
                        SELECT report_json, created_at FROM discovery_report
                        WHERE product = <record>$product
                        ORDER BY created_at DESC LIMIT 1
                        """,
                        {"product": product_id},
                    )
                )
                if rows:
                    from core.engine.product.report_models import AutomationCandidate, DiscoveryReport

                    raw = _json.loads(rows[0].get("report_json", "{}"))
                    candidates = [
                        AutomationCandidate(
                            title=c.get("title", ""),
                            description=c.get("description", ""),
                            hours_per_week_saved=float(c.get("hours_per_week_saved", 2.0)),
                            loaded_hourly_rate=float(c.get("loaded_hourly_rate", 150.0)),
                            effort_tier=c.get("effort_tier", "medium"),
                            spec_stub=None,
                        )
                        for c in raw.get("automation_candidates", [])
                    ]
                    if candidates:
                        discovery_report = DiscoveryReport(
                            product_id=product_id,
                            client_name=raw.get("client_name", ""),
                            executive_summary=raw.get("executive_summary", ""),
                            automation_candidates=candidates,
                            systems_map_summary=raw.get("systems_map_summary", ""),
                            preliminary=raw.get("preliminary", True),
                        )
        except Exception as exc:
            logger.debug("Failed to load discovery report for retainer (non-fatal): %s", exc)

        expansion = tracker.next_expansion(discovery_report=discovery_report)

        return {
            "product_id": product_id,
            "delivery_count": len(tracker.engagement_state.deliveries),
            "delivery_history": tracker.engagement_state.delivered_titles(),
            "next_expansion": expansion.to_dict() if expansion else None,
            "engagement_complete": expansion is None and len(tracker.engagement_state.deliveries) > 0,
        }

    except Exception as exc:
        logger.warning("ace_retainer_status failed: %s", exc)
        return {"error": str(exc)}


async def ace_agent_verified(
    task: str,
    criteria: list[str],
    product_id: str = DEFAULT_ORG,
    model: str | None = None,
    max_iterations: int = 3,
) -> dict:
    """Run an agentic task with iterative grader verification — done means actually done.

    Agents do NOT see the criteria. Only the isolated GraderAgent does.
    This prevents the agent from gaming the criteria or rationalizing incomplete work.

    Flow:
      1. ace_agent runs the task (full intelligence stack)
      2. Isolated GraderAgent evaluates output against criteria (fresh subprocess, no context)
      3. Unmet criteria are fed back as grader feedback
      4. Repeat until all criteria met or max_iterations reached

    Verdict: "satisfied" (all criteria met) or "max_iterations_reached".
    Returns final output, per-iteration grades, token counts, cost, and duration.

    Use this instead of ace_agent when you need verifiable completion,
    not just a reasonable-looking response.
    """
    from core.engine.verification.quality_gate import QualityGateLoop

    gate = QualityGateLoop()
    return await gate.run(
        task=task,
        criteria=criteria,
        product_id=product_id,
        model=model,
        max_iterations=max_iterations,
    )


async def ace_benchmark(
    task: str,
    rubric: list[str],
    discipline: str = "",
    product_id: str = DEFAULT_ORG,
    model: str | None = None,
    max_turns: int = 20,
) -> dict:
    """Benchmark ACE vs baseline on a task with an isolated grader.

    Runs the same task through two runtimes — identical model, identical infrastructure:
      • Baseline: Runtime(enable_intelligence=False) — raw LLM, no ACE context
      • ACE:      Runtime(enable_intelligence=True)  — full cognitive composition,
                  discipline loading, insights from graph

    An isolated GraderAgent subprocess (separate process, no session history) evaluates
    both outputs against the same rubric. The grader cannot see which agent produced
    which artifact, preventing verdict contamination.

    Metrics per run:
      - criteria met / total (quality score 0-1)
      - token consumption (input + output, separately)
      - estimated cost (USD via TokenTracker)
      - wall-clock duration (seconds)
      - ROI = quality_gain / cost_overhead (quality delta per dollar of ACE overhead)

    Results persist to benchmark_result table for discipline-level trend analysis.
    """
    from core.engine.verification.benchmark import BenchmarkRunner

    runner = BenchmarkRunner()
    return await runner.run(
        task=task,
        rubric=rubric,
        discipline=discipline,
        product_id=product_id,
        model=model,
        max_turns=max_turns,
    )


async def ace_query_discipline(
    discipline: str,
    question: str,
    product_id: str = DEFAULT_ORG,
) -> dict:
    """Ask a question against ACE's accumulated knowledge for a specific discipline.

    Queries the product graph for insights, decisions, and capabilities in this
    discipline, then answers using an LLM grounded in that accumulated intelligence.

    Example:
        ace_query_discipline("ux", "what design decisions have been made for the portal?")
        ace_query_discipline("architecture", "what patterns are established for async processing?")
        ace_query_discipline("security", "what auth decisions have been captured?")

    Returns the LLM answer grounded in product intelligence — no hallucination beyond
    what has been captured via ace_capture / ace_capture_decision.
    """
    async with _timed_tool("ace_query_discipline"):
        from core.engine.worker.knowledge import knowledge_agent

        try:
            answer = await knowledge_agent.query(discipline, question, product_id)
            return {
                "discipline": discipline,
                "question": question,
                "answer": answer,
            }
        except Exception as exc:
            logger.warning("ace_query_discipline failed: %s", exc)
            return {"error": str(exc), "discipline": discipline, "question": question}


import sys as _sys
from pathlib import Path as _Path

_WORKER_URL = "http://localhost:37778"
_WORKER_START_SCRIPT = _Path(__file__).resolve().parents[2] / "engine" / "worker" / "start.py"
_WORKER_START_CMD = [_sys.executable, str(_WORKER_START_SCRIPT)]


async def _fetch_worker_health_status() -> dict:
    """Fetch /health/status from the ACE worker. Raises on network error."""
    import json as _json
    import urllib.request as _ur

    req = _ur.Request(f"{_WORKER_URL}/health/status", method="GET")
    with _ur.urlopen(req, timeout=2) as resp:
        return _json.loads(resp.read().decode())


async def _try_restart_worker() -> bool:
    """Attempt to restart the ACE worker subprocess. Returns True if it came back up."""
    import asyncio as _asyncio
    import os

    project_dir = os.environ.get("CLAUDE_PROJECT_DIR", os.getcwd())
    try:
        await _asyncio.create_subprocess_exec(
            *_WORKER_START_CMD,
            cwd=project_dir,
            stdout=_asyncio.subprocess.DEVNULL,
            stderr=_asyncio.subprocess.DEVNULL,
        )
        await _asyncio.sleep(3.0)
        await _fetch_worker_health_status()
        return True
    except Exception:
        return False


async def ace_health(product_id: str = DEFAULT_ORG) -> dict:
    """Check ACE pipeline health. Self-heals when possible.

    - Worker unreachable → attempt restart → re-probe → 'recovered' or 'down'
    - Pipeline stale (>30m no hook activity) → 'degraded' with reason
    - Everything working → 'healthy' with one-line summary
    """
    import asyncio

    worker = None
    worker_error: str | None = None
    self_healed = False

    try:
        worker = await _fetch_worker_health_status()
    except Exception as exc:
        worker_error = str(exc)[:120]
        # Worker unreachable — attempt self-heal
        try:
            recovered = await asyncio.wait_for(_try_restart_worker(), timeout=8.0)
        except (asyncio.TimeoutError, Exception):
            recovered = False
        if recovered:
            self_healed = True
            try:
                worker = await _fetch_worker_health_status()
                worker_error = None
            except Exception:
                pass

    decisions_today = 0
    observations_today = 0
    try:
        async with pool.connection() as db:
            d_rows = parse_rows(
                await db.query(
                    "SELECT count() AS n FROM decision WHERE product = <record>$p AND created_at > time::now() - 24h GROUP ALL",
                    {"p": product_id},
                )
            )
            decisions_today = d_rows[0]["n"] if d_rows else 0

            o_rows = parse_rows(
                await db.query(
                    "SELECT count() AS n FROM observation WHERE product = <record>$p AND created_at > time::now() - 24h GROUP ALL",
                    {"p": product_id},
                )
            )
            observations_today = o_rows[0]["n"] if o_rows else 0
    except Exception:
        pass

    if worker is None:
        status = "down"
        summary = f"worker unreachable and restart failed — run: python core/engine/worker/start.py ({worker_error})"
    elif self_healed:
        status = "recovered"
        posts = worker.get("hook_post_count", 0)
        summary = f"worker was down — restarted successfully ({posts} hook fires since restart)"
    else:
        pipeline = worker.get("pipeline_status", "unknown")
        idle = worker.get("idle_seconds")

        if pipeline == "stale":
            idle_min = round((idle or 0) / 60)
            status = "degraded"
            summary = f"pipeline stale — no hook activity in {idle_min}m; check that ace-post-tool hook is wired"
        elif pipeline == "never_used":
            status = "healthy"
            summary = "worker running, no hook activity yet this session"
        else:
            status = "healthy"
            posts = worker.get("hook_post_count", 0)
            captures = worker.get("capture_count", 0)
            summary = f"✓ working — {posts} hook fires, {captures} captures, {decisions_today} decisions today"

    return {
        "status": status,
        "summary": summary,
        "pipeline_status": worker.get("pipeline_status") if worker else "unknown",
        "hook_post_count": worker.get("hook_post_count", 0) if worker else 0,
        "capture_count": worker.get("capture_count", 0) if worker else 0,
        "decisions_today": decisions_today,
        "observations_today": observations_today,
        "uptime_seconds": worker.get("uptime_seconds") if worker else None,
        "last_error": worker.get("last_error") if worker else worker_error,
    }


async def ace_diagnostics(product_id: str = DEFAULT_ORG) -> dict:
    """Run real probes on every ACE subsystem. Returns status per probe.

    Each probe has a 2-second timeout and never raises — failures are reported
    as probe errors. Overall status: healthy (all pass), degraded (some fail),
    down (DB or worker unreachable).
    """
    import urllib.request

    async def _probe(name: str, coro):
        try:
            result = await asyncio.wait_for(coro, timeout=2.0)
            return name, {"ok": True, **result}
        except asyncio.TimeoutError:
            return name, {"ok": False, "error": "timeout"}
        except Exception as exc:
            return name, {"ok": False, "error": str(exc)[:120]}

    async def _probe_db():
        async with pool.connection() as db:
            await db.query("RETURN 1")
        return {"detail": "db ok"}

    async def _probe_worker():
        import time

        t0 = time.monotonic()
        req = urllib.request.Request("http://localhost:37778/health")
        urllib.request.urlopen(req, timeout=1)
        ms = int((time.monotonic() - t0) * 1000)
        return {"latency_ms": ms}

    async def _probe_llm():
        from core.engine.core.llm import get_llm

        get_llm()
        return {"detail": "get_llm() ok"}

    async def _probe_event_bus():
        from core.engine.events.bus import bus

        stats = bus.get_stats()
        return {"emit_count": stats["emit_count"], "handlers": stats["total_handlers"]}

    async def _probe_event_log():
        async with pool.connection() as db:
            rows = parse_rows(await db.query("SELECT count() AS n FROM event_log GROUP ALL"))
        count = rows[0]["n"] if rows else 0
        return {"count": count}

    async def _probe_frameworks():
        async with pool.connection() as db:
            rows = parse_rows(await db.query("SELECT count() AS n FROM framework GROUP ALL"))
        count = rows[0]["n"] if rows else 0
        return {"count": count, "ok_threshold": count > 0}

    async def _probe_insights():
        async with pool.connection() as db:
            rows = parse_rows(
                await db.query(
                    "SELECT count() AS n FROM insight WHERE product = <record>$p AND status = 'active' GROUP ALL",
                    {"p": product_id},
                )
            )
        count = rows[0]["n"] if rows else 0
        return {"active": count}

    async def _probe_sentinel():
        async with pool.connection() as db:
            rows = parse_rows(
                await db.query(
                    "SELECT engine, started_at FROM engine_run WHERE product = <record>$p ORDER BY started_at DESC LIMIT 5",
                    {"p": product_id},
                )
            )
        return {"recent_runs": len(rows), "last_engines": [r.get("engine", "?") for r in rows[:3]]}

    async def _probe_composition():
        async with pool.connection() as db:
            rows = parse_rows(
                await db.query(
                    """SELECT discipline, count() AS n FROM composition_signal
                       WHERE product = <record>$p AND created_at > time::now() - 90d
                       GROUP BY discipline""",
                    {"p": product_id},
                )
            )
        warm = [r["discipline"] for r in rows if r.get("n", 0) >= 5]
        cold = [r["discipline"] for r in rows if r.get("n", 0) < 5]
        return {
            "warm_disciplines": len(warm),
            "cold_disciplines": len(cold),
            "total_signals": sum(r.get("n", 0) for r in rows),
        }

    async def _probe_conductor():
        async with pool.connection() as db:
            rows = parse_rows(
                await db.query(
                    "SELECT count() AS n FROM conductor_track WHERE product = <record>$p GROUP ALL",
                    {"p": product_id},
                )
            )
        count = rows[0]["n"] if rows else 0
        return {"active_tracks": count}

    async def _probe_pending_gates():
        async with pool.connection() as db:
            rows = parse_rows(
                await db.query(
                    "SELECT count() AS n FROM spec WHERE product = <record>$p AND status = 'pending_review' GROUP ALL",
                    {"p": product_id},
                )
            )
        count = rows[0]["n"] if rows else 0
        return {"pending": count}

    named_results = dict(
        await asyncio.gather(
            _probe("db", _probe_db()),
            _probe("worker", _probe_worker()),
            _probe("llm", _probe_llm()),
            _probe("event_bus", _probe_event_bus()),
            _probe("event_log", _probe_event_log()),
            _probe("frameworks", _probe_frameworks()),
            _probe("insights", _probe_insights()),
            _probe("sentinel", _probe_sentinel()),
            _probe("composition", _probe_composition()),
            _probe("conductor", _probe_conductor()),
            _probe("gates", _probe_pending_gates()),
        )
    )

    failed = [k for k, v in named_results.items() if not v.get("ok", True)]
    critical_failed = [k for k in failed if k in ("db", "worker")]

    if critical_failed:
        overall = "down"
    elif failed:
        overall = "degraded"
    else:
        overall = "healthy"

    return {
        "status": overall,
        "probes": named_results,
        "failed": failed,
        "product_id": product_id,
    }


# ---------------------------------------------------------------------------
# Smart Explore tools (Item 1 — context engineering wave)
# ---------------------------------------------------------------------------


async def ace_smart_outline(file_path: str) -> dict:
    """Parse a source file with AST and return its structural outline.

    Returns functions, classes, and imports without requiring a full file read.
    Useful for orienting quickly when the File Read Gate serves a cached timeline.

    Supports: Python, TypeScript, JavaScript, TSX, Java (via tree-sitter).
    Returns `{"error": "unsupported"}` for unrecognised extensions.
    """
    import os
    from pathlib import Path

    from core.engine.scanner.ast_parser import LANG_MAP, get_language_for_extension, parse_file

    # Resolve path relative to project root when not absolute
    path = Path(file_path)
    if not path.is_absolute():
        project_root = Path(os.environ.get("CLAUDE_PROJECT_DIR", Path.cwd()))
        path = project_root / path

    if not path.exists():
        return {"error": f"file not found: {file_path}"}

    ext = path.suffix
    language = get_language_for_extension(ext)
    if not language:
        return {"error": f"unsupported extension: {ext}", "supported": list(LANG_MAP.keys())}

    try:
        content = path.read_bytes()
    except OSError as exc:
        return {"error": f"read error: {exc}"}

    result = parse_file(content, language)

    functions = [
        {
            "name": f.name,
            "kind": f.kind,
            "lines": f"{f.line_start}-{f.line_end}",
            "params": f.parameters[:80] if f.parameters else "",
            "returns": f.return_type[:40] if f.return_type else "",
        }
        for f in result.functions
    ]
    classes = [
        {
            "name": c.name,
            "lines": f"{c.line_start}-{c.line_end}",
            "methods": [m.name.split(".")[-1] for m in c.methods],
        }
        for c in result.classes
    ]
    imports = [{"module": i.module, "name": i.name or "*", "alias": i.alias or ""} for i in result.imports]

    return {
        "file": str(path),
        "language": language,
        "functions": functions,
        "classes": classes,
        "imports": imports,
        "imports_count": len(imports),
        "total_symbols": len(functions) + len(classes),
    }


async def ace_smart_search(
    query: str,
    product_id: str = DEFAULT_ORG,
    limit: int = 10,
) -> dict:
    """Search the code graph by symbol name using FTS.

    Searches graph_function.name via the fn_search BM25 index (v084).
    Returns matching functions with file context and capability associations.
    Complements ace_search_code (semantic) — this is name/identifier-focused.
    """
    async with pool.connection() as db:
        fn_rows = parse_rows(
            await db.query(
                """
                SELECT id, name, kind, line_start, line_end,
                       <-contains<-graph_file.path AS file_path,
                       <-realizes<-capability.name AS capabilities
                FROM graph_function
                WHERE name @@ $query
                LIMIT $limit
                """,
                {"query": query, "limit": limit},
            )
        )

        # Also search graph_file paths
        file_rows = parse_rows(
            await db.query(
                """
                SELECT id, path, language, graph_id,
                       ->contains->graph_function.name AS symbols
                FROM graph_file
                WHERE path @@ $query
                LIMIT $limit
                """,
                {"query": query, "limit": limit},
            )
        )

    functions = [
        {
            "name": r.get("name", ""),
            "kind": r.get("kind", "function"),
            "file": (r.get("file_path") or [None])[0],
            "lines": f"{r.get('line_start', '?')}-{r.get('line_end', '?')}",
            "capabilities": r.get("capabilities") or [],
        }
        for r in fn_rows
    ]
    files = [
        {
            "path": r.get("path", ""),
            "language": r.get("language", ""),
            "symbols": (r.get("symbols") or [])[:8],
        }
        for r in file_rows
    ]

    return {
        "query": query,
        "functions": functions,
        "files": files,
        "total": len(functions) + len(files),
    }


async def ace_smart_unfold(
    symbol: str,
    file_path: str | None = None,
    product_id: str = DEFAULT_ORG,
    depth: int = 1,
) -> dict:
    """Progressive context expansion starting from a symbol.

    Given a symbol name (function, class, method):
    1. Finds its definition in graph_function
    2. Traverses graph edges to find callers / callees (depth=1 default)
    3. Surfaces recent observations that reference its source file
    4. Returns its associated capability context

    depth=1 returns immediate callers/callees.
    depth=2 returns two hops (callers of callers).
    """
    async with pool.connection() as db:
        # 1. Find the symbol definition
        where_parts = ["name = $symbol"]
        params: dict = {"symbol": symbol, "product": product_id, "depth": depth}
        if file_path:
            where_parts.append("(<-contains<-graph_file.path) CONTAINS $file_path")
            params["file_path"] = file_path

        fn_result = parse_rows(
            await db.query(
                f"""
                SELECT id, name, kind, line_start, line_end,
                       <-contains<-graph_file.path AS file_paths,
                       <-realizes<-capability.name AS capabilities
                FROM graph_function
                WHERE {" AND ".join(where_parts)}
                LIMIT 5
                """,
                params,
            )
        )

        if not fn_result:
            return {"error": f"symbol not found: {symbol}", "tip": "try ace_smart_search first"}

        target = fn_result[0]
        target_id = str(target.get("id", ""))
        source_files = target.get("file_paths") or []

        # 2. Callers: who calls this symbol (->calls-> edges pointing to us)
        callers = parse_rows(
            await db.query(
                """
                SELECT <-calls<-graph_function.name AS callers
                FROM ONLY <record>$id
                """,
                {"id": target_id},
            )
        )
        caller_names = (callers[0].get("callers") or []) if callers else []

        # 3. Callees: what this symbol calls (->calls-> edges from us)
        callees = parse_rows(
            await db.query(
                """
                SELECT ->calls->graph_function.name AS callees
                FROM ONLY <record>$id
                """,
                {"id": target_id},
            )
        )
        callee_names = (callees[0].get("callees") or []) if callees else []

        # 4. Recent observations for source files
        recent_obs: list[dict] = []
        if source_files:
            obs_result = parse_rows(
                await db.query(
                    """
                    SELECT content, observation_type, confidence, created_at
                    FROM observation
                    WHERE file_path IN $paths
                      AND product = <record>$product
                      AND status IN ['pending', 'processed']
                    ORDER BY created_at DESC
                    LIMIT 5
                    """,
                    {"paths": source_files[:3], "product": product_id},
                )
            )
            recent_obs = [
                {
                    "type": o.get("observation_type", ""),
                    "content": o.get("content", "")[:100],
                    "confidence": o.get("confidence", 0),
                }
                for o in obs_result
            ]

    return {
        "symbol": symbol,
        "definition": {
            "name": target.get("name", ""),
            "kind": target.get("kind", "function"),
            "files": source_files[:3],
            "lines": f"{target.get('line_start', '?')}-{target.get('line_end', '?')}",
            "capabilities": target.get("capabilities") or [],
        },
        "callers": caller_names[:10],
        "callees": callee_names[:10],
        "recent_observations": recent_obs,
        "depth": depth,
    }


async def ace_verify_implementation(
    topic: str,
    product_id: str = DEFAULT_ORG,
) -> dict:
    """Verify what's actually implemented for a topic by querying the code graph.

    Use before making any claim about what exists or doesn't exist in the codebase.
    Searches graph_file (paths + LLM-analyzed purpose/discipline/role), graph_function
    (symbol names via BM25), and graph_decision (architectural decisions) for evidence.

    Returns ground-truth evidence from the scanned graph — not memory or inference.
    Verdict: 'implemented' (3+ hits), 'partial' (1-2 hits), 'not_found' (0 hits).
    """
    async with _timed_tool("ace_verify_implementation"):
        topic_lower = topic.lower()
        params: dict = {"topic": topic, "topic_lower": topic_lower, "limit": 15}

        async with pool.connection() as db:
            file_rows = parse_rows(
                await db.query(
                    """
                    SELECT path, language, line_count, change_frequency,
                           purpose, discipline, architectural_role, key_exports
                    FROM graph_file
                    WHERE string::lowercase(path) CONTAINS $topic_lower
                       OR (purpose IS NOT NONE AND string::lowercase(purpose) CONTAINS $topic_lower)
                       OR (discipline IS NOT NONE AND string::lowercase(discipline) CONTAINS $topic_lower)
                       OR (architectural_role IS NOT NONE AND string::lowercase(architectural_role) CONTAINS $topic_lower)
                    LIMIT $limit
                    """,
                    params,
                )
            )

            fn_rows = parse_rows(
                await db.query(
                    """
                    SELECT name, kind, line_start, line_end,
                           <-contains<-graph_file.path AS file_path
                    FROM graph_function
                    WHERE name @@ $topic
                    LIMIT $limit
                    """,
                    params,
                )
            )

            decision_rows = parse_rows(
                await db.query(
                    """
                    SELECT title, description, outcome, timestamp
                    FROM graph_decision
                    WHERE title @@ $topic OR description @@ $topic
                    ORDER BY timestamp DESC
                    LIMIT 5
                    """,
                    params,
                )
            )

        files = [
            {
                "path": r.get("path", ""),
                "language": r.get("language", ""),
                "lines": r.get("line_count", 0),
                "purpose": r.get("purpose"),
                "discipline": r.get("discipline"),
                "role": r.get("architectural_role"),
                "exports": (r.get("key_exports") or [])[:5],
            }
            for r in file_rows
        ]
        functions = [
            {
                "name": r.get("name", ""),
                "kind": r.get("kind", "function"),
                "file": (r.get("file_path") or [None])[0],
                "lines": f"{r.get('line_start', '?')}-{r.get('line_end', '?')}",
            }
            for r in fn_rows
        ]
        decisions = [
            {
                "title": r.get("title", ""),
                "outcome": r.get("outcome", "unknown"),
                "description": (r.get("description") or "")[:120],
            }
            for r in decision_rows
        ]

        total = len(files) + len(functions) + len(decisions)
        verdict = "implemented" if total >= 3 else "partial" if total >= 1 else "not_found"

        return {
            "topic": topic,
            "verdict": verdict,
            "evidence_count": total,
            "files": files,
            "functions": functions,
            "decisions": decisions,
            "tip": (
                "Evidence found — read the actual files to confirm before making claims."
                if total > 0
                else "No graph evidence. Either not implemented or graph not yet scanned."
            ),
        }


async def ace_test_coverage(
    repo_path: str = ".",
    stack: str | None = None,
    persist: bool = True,
    product_id: str = DEFAULT_ORG,
) -> dict:
    """Run test coverage and persist results to capability_coverage.

    Runs the stack-appropriate coverage tool (pytest --cov for Python),
    binds results to capabilities via the graph, and persists:
    - capability_coverage (current state, UPSERT)
    - capability_coverage_snapshot (history, INSERT-only)
    - capability_finding with tool='coverage' for untested functions

    Args:
        repo_path:  Repo root. Default: current directory.
        stack:      Override stack detection. Default: detect from graph_file.
        persist:    Write to capability_coverage + capability_finding. Default: True.
        product_id: Product context for capability binding.

    Returns:
        {scan_id, tool, stack, duration_seconds, capabilities, summary, findings_created}
    """
    import os

    from core.engine.intelligence.coverage_binder import bind_and_persist
    from core.engine.scanner.coverage_extractor import run_coverage

    abs_path = os.path.abspath(repo_path)
    detected_stack = stack
    if not detected_stack:
        from core.engine.scanner.hardening import _detect_stack

        stacks = await _detect_stack(abs_path)
        detected_stack = stacks[0] if stacks else "python"

    report = await run_coverage(abs_path, stack=detected_stack)
    if not report.rows:
        return {
            "tool": report.tool,
            "stack": report.stack,
            "duration_seconds": report.duration_seconds,
            "warnings": ["No coverage data produced — tool may not be installed or no tests ran"],
            "capabilities": [],
            "summary": {},
        }

    persist_result: dict = {}
    if persist:
        persist_result = await bind_and_persist(report.rows, product_id=product_id)

    async with pool.connection() as db:
        cap_rows = parse_rows(
            await db.query(
                """SELECT cap.slug AS slug, cc.line_pct AS line_pct,
                cc.branch_pct AS branch_pct, cc.function_pct AS function_pct,
                cc.untested_functions_count AS untested
            FROM capability_coverage AS cc
            JOIN capability AS cap ON cap.id = cc.capability
            WHERE cc.product = <record>$product
            ORDER BY cc.function_pct ASC LIMIT 50
            """,
                {"product": product_id},
            )
        )

    avg_line = sum(c.get("line_pct") or 0.0 for c in cap_rows) / max(len(cap_rows), 1)
    below_60 = sum(1 for c in cap_rows if (c.get("line_pct") or 0.0) < 0.6)
    total_untested = sum(c.get("untested") or 0 for c in cap_rows)

    return {
        "scan_id": persist_result.get("scan_id"),
        "tool": report.tool,
        "stack": report.stack,
        "duration_seconds": report.duration_seconds,
        "capabilities": cap_rows,
        "summary": {
            "avg_line_pct": round(avg_line, 3),
            "capabilities_below_60pct": below_60,
            "total_untested_functions": total_untested,
        },
        "findings_created": persist_result.get("findings_created", 0),
    }


async def ace_test_gaps(
    capability_slug: str | None = None,
    severity: str | None = None,
    limit: int = 50,
    product_id: str = DEFAULT_ORG,
) -> dict:
    """Query persisted test-gap findings (capability_finding rows where tool='coverage').

    Use to drill into specific capabilities flagged by ace_product_health 'testing' dimension.

    Args:
        capability_slug: Filter to one capability.
        severity:        Filter by severity (high|medium|low).
        limit:           Max findings. Default: 50.

    Returns:
        {gaps, total_gaps, ranked_capabilities, filters}
    """
    from core.engine.intelligence.coverage_priority import rank_capabilities

    where = ["product = <record>$product", "tool = 'coverage'", "resolved_at = NONE"]
    params: dict = {"product": product_id, "limit": limit}

    if capability_slug:
        where.append("capability.slug = <string>$slug")
        params["slug"] = capability_slug
    if severity:
        where.append("severity = <string>$sev")
        params["sev"] = severity

    where_clause = " AND ".join(where)
    async with pool.connection() as db:
        gaps = parse_rows(
            await db.query(
                f"SELECT * FROM capability_finding WHERE {where_clause} "
                f"ORDER BY severity DESC, created_at DESC LIMIT $limit",
                params,
            )
        )

    ranked = await rank_capabilities(product_id=product_id, limit=10)

    return {
        "gaps": [serialize_record(g) for g in gaps],
        "total_gaps": len(gaps),
        "ranked_capabilities": ranked,
        "filters": {"capability_slug": capability_slug, "severity": severity},
    }


# ─── Ambition + Phase + Pillar tools (spec v1.2 — phase-aware substrate) ──────


async def ace_ambition(product_id: str = "product:platform") -> dict:
    """Return current ambition snapshot for a product."""
    from core.engine.product.ambition import AmbitionRepository

    repo = AmbitionRepository(pool)
    ambition = await repo.get(product_id)
    if ambition is None:
        return {
            "product_id": product_id,
            "ambition": None,
            "message": "No ambition row yet; run scripts/ingest_ambition.py.",
        }
    return {
        "product_id": product_id,
        "phase": ambition.phase.current if ambition.phase else None,
        "target_demo": (ambition.target.demo_target.name if ambition.target and ambition.target.demo_target else None),
    }


async def ace_set_phase(product_id: str, phase: str, reason: str) -> dict:
    """Set phase explicitly. reason is required for audit trail."""
    if not reason:
        raise ValueError("reason is required for audit trail")
    if phase not in ("discovery", "poc", "alpha", "beta", "ga", "mature"):
        raise ValueError(f"invalid phase: {phase}")
    async with pool.connection() as db:
        await db.query(
            """UPDATE ambition SET
                phase_json.current = <string>$phase,
                phase_json.entered_at = time::now(),
                last_ingested_at = time::now()
               WHERE product = <record>$pid""",
            {"pid": product_id, "phase": phase},
        )
    return {"product_id": product_id, "phase": phase, "reason": reason}


async def ace_set_product_type(product_id: str, product_type: str) -> dict:
    """Set product_type (ai_native | trading_system | dev_tool | ...)."""
    async with pool.connection() as db:
        await db.query(
            "UPDATE <record>$pid SET product_type = <string>$pt",
            {"pid": product_id, "pt": product_type},
        )
    return {"product_id": product_id, "product_type": product_type}


async def ace_set_product_scale(product_id: str, scale: str) -> dict:
    """Set product_scale (atomic | component | application | platform | enterprise)."""
    async with pool.connection() as db:
        await db.query(
            "UPDATE <record>$pid SET product_scale = <string>$s",
            {"pid": product_id, "s": scale},
        )
    return {"product_id": product_id, "product_scale": scale}


async def ace_pillar_status(product_id: str = "product:platform") -> dict:
    """Return all 7 pillar scores for a product."""
    from core.engine.product.pillar_aggregator import PillarAggregator

    agg = PillarAggregator(pool)
    scores = await agg.get_pillar_scores(product_id)
    return {pillar.value: round(score, 3) for pillar, score in scores.items()}


async def ace_phase_status(product_id: str = "product:platform") -> dict:
    """Return current phase + pillar blockers for advancing."""
    from core.engine.product.ambition import AmbitionRepository
    from core.engine.product.phase_floors import effective_floor
    from core.engine.product.pillar_aggregator import PillarAggregator

    repo = AmbitionRepository(pool)
    ambition = await repo.get(product_id)
    if not ambition or not ambition.phase:
        return {"product_id": product_id, "phase": None, "message": "No phase set."}

    agg = PillarAggregator(pool)
    pillar_scores = await agg.get_pillar_scores(product_id)
    async with pool.connection() as db:
        prod_rows = parse_rows(
            await db.query(
                "SELECT product_type, product_scale FROM <record>$pid",
                {"pid": product_id},
            )
        )
    pt = prod_rows[0].get("product_type", "ai_native") if prod_rows else "ai_native"
    scale = prod_rows[0].get("product_scale", "application") if prod_rows else "application"
    blockers = []
    for pillar, score in pillar_scores.items():
        floor = effective_floor(pillar, ambition.phase.current, pt, scale)
        if score < floor:
            blockers.append(
                {
                    "pillar": pillar.value,
                    "score": round(score, 3),
                    "floor": round(floor, 3),
                }
            )
    return {
        "product_id": product_id,
        "current_phase": ambition.phase.current,
        "days_in_phase": ambition.phase.compute_days_in_phase(),
        "blockers_to_advance": blockers,
    }


async def ace_query_uncertainty(product_id: str, scope: str, question: str, fallback_action: str) -> dict:
    """Raise an uncertainty query — surfaces to the Proactive Line instead of silently defaulting."""
    from core.engine.product.uncertainty import query_uncertainty as _query_uncertainty

    q = await _query_uncertainty(pool, product_id, scope, question, fallback_action)
    return {
        "id": q.id,
        "scope": q.scope,
        "question": q.question,
        "status": q.status,
    }


async def ace_acknowledge_recommendation(rec_id: str) -> dict:
    """Acknowledge a recommendation — resets its decay counter."""
    from core.engine.product.recommendation_decay import acknowledge as _acknowledge_rec

    await _acknowledge_rec(pool, rec_id)
    return {"rec_id": rec_id, "status": "acknowledged"}


async def ace_suggest_phase(product_id: str = "product:platform") -> dict:
    """Suggest a phase from observable state (capability count + completion rate)."""
    from core.engine.product.phase_inference import suggest_phase as _suggest_phase

    suggestion = await _suggest_phase(pool, product_id)
    return {
        "product_id": product_id,
        "suggested_phase": suggestion.phase,
        "confidence": suggestion.confidence,
        "rationale": suggestion.rationale,
        "signals": suggestion.signals,
    }


async def ace_briefing_payload(product_id: str = "product:platform") -> dict:
    """Return the structured BriefingPayload (phase-aware substrate contract).

    Distinct from ace_briefing (markdown text). This is the data contract for
    consumers that need structured fields: current_phase, phase_floors,
    pillar_scores, top_recommendations, blocked_patterns, open uncertainty queries.
    """
    from core.engine.sentinel.engines.briefing import build_briefing_payload

    return await build_briefing_payload(product_id)


async def ace_journey_count(product: str = "product:platform", since: str = "week") -> dict:
    """Return the count of journey events for a product within a time window.

    Used by the SessionStart hook footer to show 'N events this week' tease.
    """
    interval = {"day": "1d", "week": "7d", "month": "30d"}.get(since, "7d")
    await pool.init()
    async with pool.connection() as db:
        rows = parse_rows(
            await db.query(
                f"SELECT count() AS c FROM journey_event "
                f"WHERE product = <record>$pid AND occurred_at > time::now() - {interval} GROUP ALL",
                {"pid": product},
            )
        )
    count = rows[0]["c"] if rows else 0
    return {"count": count, "since": since, "product": product}


async def ace_voice_audit_summary(product: str = "product:platform") -> dict:
    """Return latest voice audit summary {overall_score, surface_count, violations_count}.

    Used by the SessionStart hook footer for the voice teaser line.
    """
    await pool.init()
    async with pool.connection() as db:
        latest = parse_one(
            await db.query(
                "SELECT overall_score, surface_scores, violations, ran_at FROM voice_audit_run "
                "WHERE product = <record>$pid ORDER BY ran_at DESC LIMIT 1",
                {"pid": product},
            )
        )
    if not latest:
        return {"overall_score": 1.0, "surface_count": 0, "violations_count": 0}
    return {
        "overall_score": latest.get("overall_score", 1.0),
        "surface_count": len(latest.get("surface_scores", {})),
        "violations_count": len(latest.get("violations", [])),
    }


async def ace_forecast(product_id: str = DEFAULT_ORG) -> dict:
    """List open predictions for a product with horizon, risk, and falsification condition."""
    async with pool.connection() as db:
        result = await db.query(
            """SELECT id, decision, archetype, discipline, horizon_days,
                      primary_risk, falsification_condition, leading_indicators,
                      closed, created_at
               FROM decision_prediction
               WHERE product = <record>$product AND closed = false
               ORDER BY created_at DESC
               LIMIT 50""",
            {"product": product_id},
        )
    predictions = parse_rows(result)
    return {
        "total_open": len(predictions),
        "predictions": predictions,
    }


async def ace_calibration(product_id: str = DEFAULT_ORG) -> dict:
    """View per-archetype calibration scores accumulated by the reconciler."""
    async with pool.connection() as db:
        result = await db.query(
            "SELECT archetype, discipline, calibration_score, sample_count, updated_at FROM archetype_calibration ORDER BY calibration_score DESC",
        )
    calibrations = parse_rows(result)
    if not calibrations:
        return {
            "calibrations": [],
            "message": "no calibration data yet — predictions must be closed by the reconciler first",
        }
    return {"calibrations": calibrations}


async def ace_rollout(candidate: str, product_id: str = DEFAULT_ORG) -> dict:
    """Run the depth-3 rollout planner on a candidate decision and return scored branches."""
    from core.engine.foresight.planner import plan_rollout

    result = await plan_rollout(candidate, product_id)
    return {
        "candidate": result.candidate,
        "product_id": result.product_id,
        "best_path": result.best_path,
        "branches": [
            {
                "path": b.path,
                "terminal_score": b.terminal_score,
                "top_risk": b.top_risk,
            }
            for b in result.branches
        ],
        "created_at": result.created_at,
    }


async def ace_fork_reasoning(
    run_id: str,
    checkpoint_seq: int = 1,
    product_id: str = DEFAULT_ORG,
    with_capability_lens: bool = False,
) -> dict:
    """Fork a logged reasoning run at a phase checkpoint — re-reason the tail under alternative lenses
    and compare, returning the best continuation BEFORE acting (which may be the original).

    Args:
        run_id: a reasoning_run record id (from the reasoning_event log).
        checkpoint_seq: the phase seq to fork at (>= 1; must leave >= 1 tail phase to re-reason).
        product_id: the product the run belongs to.
        with_capability_lens: also score each branch's predicted capability-quality trajectory
            (value_model) and blend it into the ranking — opt-in (an extra LLM + value_model call per
            branch); default off.

    Returns:
        {"run_id", "checkpoint_seq", "recommendation": "fork"|"keep_original", "best", "original",
         "forks", "created_at"} — or {"error": ...} if the run can't be reconstructed.
    """
    from core.engine.core.llm import get_llm
    from core.engine.foresight import fork_planner

    async def _llm_call(system_prompt: str, user_prompt: str) -> str:
        return await get_llm().complete(user_prompt, system=system_prompt)

    try:
        checkpoint = int(checkpoint_seq)
        if checkpoint <= 0:
            # 'fork the conclusion' — resolve to n_phases-1 without the caller knowing the phase count.
            checkpoint = await fork_planner.resolve_conclusion_checkpoint(run_id)
        result = await fork_planner.fork_and_compare(
            run_id,
            checkpoint,
            product_id=product_id,
            llm_call=_llm_call,
            with_capability_lens=with_capability_lens,
        )
    except Exception as exc:
        logger.warning("ace_fork_reasoning failed: %s", exc)
        return {"error": str(exc), "run_id": run_id, "checkpoint_seq": checkpoint_seq}
    if result is None:
        return {
            "error": "could not reconstruct a fork point (missing run, out-of-range checkpoint, or no tail to fork)",
            "run_id": run_id,
            "checkpoint_seq": checkpoint_seq,
        }

    def _branch(b, *, n: int) -> dict:
        d = {
            "label": b.variation_label,
            "lens": b.lens,
            "score": round(b.combined_score, 4),
            "conclusion": (b.conclusion or "")[:n],
        }
        if b.capability_delta_score is not None:
            d["capability_delta_score"] = round(b.capability_delta_score, 4)
        return d

    return {
        "run_id": result.run_id,
        "checkpoint_seq": result.checkpoint_seq,
        "recommendation": "fork" if result.best.variation_label != "original" else "keep_original",
        "best": _branch(result.best, n=2000),
        "original": _branch(result.original, n=2000),
        "forks": [_branch(f, n=500) for f in result.forks],
        "created_at": result.created_at,
    }


async def ace_explain_run(run_id: str = "", product_id: str = DEFAULT_ORG) -> dict:
    """Replay a reasoning run's trace — 'why did ACE conclude this?'. Reads the append-only
    reasoning_event log (run_started → phase×N → run_complete) into a legible trace: the thought, the
    cognitive phases ACE moved through (with confidences), and the conclusion. With no run_id, explains
    the MOST RECENT run for the product. Makes ACE's reasoning legible — the partnership thesis.

    Returns {"available", "run_id", "thought", "discipline", "depth", "phases": [{seq, function,
    output, confidence}], "conclusion", "status"}.
    """
    from core.engine.cognition import run_ledger

    rid = run_id
    if not rid:
        recent = await run_ledger.get_recent_runs(product_id=product_id, limit=1)
        if not recent:
            return {"available": False, "error": "no reasoning runs found for this product"}
        rid = str(recent[0].get("id") or "")

    events = await run_ledger.get_run_events(rid)
    if not events:
        return {"available": False, "run_id": rid}

    started = next((e for e in events if e.get("event_type") == "run_started"), {})
    terminal = next((e for e in reversed(events) if e.get("event_type") in ("run_complete", "run_failed")), {})
    sp = started.get("payload") or {}
    tp = terminal.get("payload") or {}
    phases = [
        {
            "seq": e.get("seq"),
            "function": (e.get("payload") or {}).get("cognitive_function")
            or (e.get("payload") or {}).get("phase_name")
            or "",
            "output": ((e.get("payload") or {}).get("output") or "")[:1500],
            "confidence": (e.get("payload") or {}).get("confidence"),
        }
        for e in events
        if e.get("event_type") == "phase"
    ]
    return {
        "available": True,
        "run_id": rid,
        "thought": sp.get("thought"),
        "discipline": sp.get("discipline"),
        "depth": sp.get("depth"),
        "phases": phases,
        "conclusion": tp.get("conclusion"),
        "status": tp.get("status") or "complete",
    }


async def ace_signals(
    product_id: str = DEFAULT_ORG,
    kind: str = "",
    limit: int = 10,
) -> dict:
    """List recent internal foresight signals for a product.

    Args:
        product_id: Product record ID.
        kind: Optional filter — "capability_decline" | "gap_persistence" | "decision_velocity_drop" | "" (all).
        limit: Maximum signals to return (default 10).

    Returns:
        {"signals": [{"id", "kind", "subject", "description", "confidence", "scenario_built", "created_at"}]}
    """
    try:
        params: dict = {"product": product_id}
        kind_filter = ""
        if kind in ("capability_decline", "gap_persistence", "decision_velocity_drop"):
            kind_filter = "AND kind = $kind"
            params["kind"] = kind

        async with pool.connection() as db:
            result = await db.query(
                f"""SELECT id, kind, subject, description, confidence, scenario_built, created_at
                    FROM signal
                    WHERE product = <record>$product {kind_filter}
                    ORDER BY confidence DESC, created_at DESC
                    LIMIT {int(limit)}""",
                params,
            )
        rows = parse_rows(result)
        return {"signals": rows}
    except Exception as exc:
        return {"signals": [], "error": str(exc)}


async def ace_scenario(
    signal_id: str,
    product_id: str = DEFAULT_ORG,
) -> dict:
    """Get the scenario tree (probability-weighted branches) for an internal signal.

    Args:
        signal_id: Signal record ID (e.g. "signal:abc123").
        product_id: Product record ID.

    Returns:
        {"scenario": {"id", "kind", "root_signal_id", "branches": [{"probability",
                       "description", "implication_for_product", "horizon"}]}}
    """
    try:
        async with pool.connection() as db:
            scenario_result = await db.query(
                """SELECT id, kind, root_signal_id, created_at FROM scenario
                   WHERE product = <record>$product AND root_signal_id = $signal_id
                   ORDER BY created_at DESC LIMIT 1""",
                {"product": product_id, "signal_id": signal_id},
            )
        scenarios = parse_rows(scenario_result)
        if not scenarios:
            return {"scenario": None, "message": f"No scenario built yet for signal {signal_id}"}

        sc = scenarios[0]
        scenario_id = str(sc["id"])
        raw_id = scenario_id.split(":")[-1] if ":" in scenario_id else scenario_id

        async with pool.connection() as db:
            branch_result = await db.query(
                """SELECT probability, description, implication_for_product, horizon
                   FROM scenario_branch
                   WHERE scenario = type::record('scenario', $id)
                   ORDER BY probability DESC""",
                {"id": raw_id},
            )
        branches = parse_rows(branch_result)

        return {
            "scenario": {
                "id": scenario_id,
                "kind": sc.get("kind"),
                "root_signal_id": sc.get("root_signal_id"),
                "created_at": str(sc.get("created_at", "")),
                "branches": branches,
            }
        }
    except Exception as exc:
        return {"scenario": None, "error": str(exc)}


async def ace_forget(
    insight_id: str,
    reason: str,
    actor: str = "mcp",
    confirm: bool = False,
    product_id: str = "product:default",
) -> dict:
    """Erase one insight by id. Dry-run preview unless confirm=True."""
    from core.engine.capture.forget import forget_insight
    from core.engine.core.db import pool

    return await forget_insight(
        pool,
        insight_id,
        product_id=product_id,
        reason=reason,
        actor=actor,
        confirm=confirm,
    )


async def ace_forget_by_hash(
    content_hash: str,
    reason: str,
    actor: str = "mcp",
    confirm: bool = False,
    product_id: str = "product:default",
) -> dict:
    """Erase every insight whose content matches content_hash. Dry-run unless confirm=True."""
    from core.engine.capture.forget import forget_by_hash
    from core.engine.core.db import pool

    return await forget_by_hash(
        pool,
        content_hash,
        product_id=product_id,
        reason=reason,
        actor=actor,
        confirm=confirm,
    )
