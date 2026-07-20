# engine/orchestration/executor.py
"""Core orchestration event loop.

Orchestrates: classify -> dispatch -> plan (if deliberative) -> select
pattern -> execute -> persist -> hooks -> done.

This is the heart of the orchestration layer.  The public API
(``orchestrate()`` / ``stream()``) in ``__init__.py`` delegates here.
"""

from __future__ import annotations

import asyncio
import logging
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from core.engine.cognition.star_trace import write_star_trace
from core.engine.core.exceptions import ValidationError
from core.engine.core.tokens import TokenAccumulator, clear_accumulator, get_accumulator, set_accumulator, set_stage
from core.engine.orchestration.agent import AgentConfig
from core.engine.orchestration.bus import OrchestrationBus
from core.engine.orchestration.composition_scorer import score_composition
from core.engine.orchestration.dispatcher import dispatch
from core.engine.orchestration.events import (
    ClassificationComplete,
    EventBus,
    IntelligenceLoaded,
    PlanCreated,
    TaskCompleted,
    TaskFailed,
    TaskReceived,
)
from core.engine.orchestration.hooks import HookContext, run_hooks
from core.engine.orchestration.patterns.base import PatternConfig, PatternResult
from core.engine.orchestration.request import OrchestrationRequest
from core.engine.orchestration.shell import ShellComposer
from core.engine.orchestrator.engagement_models import SpinOutput

logger = logging.getLogger(__name__)

# Module-level singleton — recipe cache is instance-level, so re-instantiating
# per task defeats it. One instance per process is correct.
try:
    from core.engine.cognition.composer import CognitiveComposer as _CognitiveComposer

    _cognitive_composer: _CognitiveComposer | None = _CognitiveComposer()
except Exception:  # pragma: no cover
    _cognitive_composer = None


def _spins_to_phase_traces(spins: list[SpinOutput]) -> list[dict]:
    """Convert engagement SpinOutputs into the phase_trace format expected by write_star_trace."""
    return [
        {
            "phase_name": spin.perspective,
            "confidence": spin.confidence,
            "output": spin.content,
        }
        for spin in spins
    ]


async def _record_reasoning_run(
    request: "OrchestrationRequest",
    classification: dict,
    *,
    depth: int,
    meta_skills: list,
    phases: list,
    conclusion: str,
    status: str = "complete",
) -> None:
    """Emit a reasoning_run + its events into the run_ledger — the append-only reasoning_event
    log that powers forkable foresight, the trace UI, canvas "show your reasoning", and sentinel
    realtime (one keystone, four downstreams).

    Called post-hoc at each deep orchestrate completion path (engagement / multiphase /
    deliberative-pattern). Fully fail-safe + non-fatal: create_run returns None on failure,
    finalize_run no-ops on None, and the whole body is try/except-wrapped, so the event log can
    never affect the reasoning result. Phase strings are capped at 1000 chars so unbounded phase
    outputs (e.g. branching's winning_output, a spin's full content) don't bloat the rows/events.
    """
    try:
        from core.engine.cognition import run_ledger as _run_ledger

        _rid = await _run_ledger.create_run(
            product_id=request.product_id,
            thought=request.description,
            meta_skills=[str(m) for m in (meta_skills or []) if str(m).strip()],
            depth=depth,
            discipline=classification.get("discipline"),
        )
        if not _rid:
            return
        _capped = [
            {k: (v[:1000] if isinstance(v, str) and len(v) > 1000 else v) for k, v in e.items()}
            if isinstance(e, dict)
            else e
            for e in (phases or [])
        ]
        await _run_ledger.finalize_run(
            run_id=_rid,
            conclusion=conclusion or "",
            phases=_capped,
            trace=_capped,
            status=status,
        )
    except Exception:
        logger.debug("reasoning_run instrumentation failed (non-fatal)", exc_info=True)
    finally:
        # Close the active loop: persist the conclusion as graph structure (own fail-safe, noise-gated).
        # In `finally` so it runs even when the ledger write short-circuits (create_run -> None, the
        # `if not _rid: return` above) or raises — the active loop must not be coupled to the event log.
        await _capture_conclusion_to_graph(request, classification, conclusion, status)


# Minimum conclusion length to persist — gates trivial / "I don't know" outputs out of the graph.
_MIN_CONCLUSION_CHARS = 80


async def _capture_conclusion_to_graph(
    request: "OrchestrationRequest", classification: dict, conclusion: str, status: str
) -> None:
    """Close the active loop (reasoning → graph). Persist a substantive, COMPLETED reasoning conclusion
    as a 'pending' observation (source 'reasoning_conclusion') — the existing Observer→Synthesizer→insight
    pipeline turns it into a graph insight that FUTURE reasoning retrieves, so the loop compounds (the
    standing "97% backward-flow blocked" finding).

    Noise-gated: only complete runs with a substantive conclusion; and only DEEP runs reach here (the
    sole caller is _record_reasoning_run, fired on the 3 deep orchestrate paths). Fully fail-safe — a
    write failure can never affect the reasoning result. Mirrors MultiPhaseExecutor._capture_phase_output.
    """
    text = (conclusion or "").strip()
    if status != "complete" or len(text) < _MIN_CONCLUSION_CHARS:
        return
    try:
        from core.engine.core.db import pool

        # Canonical discipline slug (not a dotted path) — keeps the observation's domain_path aligned
        # with the slug the synthesizer/worker dedup key on, so conclusion dedup actually matches.
        discipline = (classification.get("discipline") or classification.get("domain_path") or "").split(".")[0]
        async with pool.connection() as db:
            await db.query(
                """
                CREATE observation SET
                    product = <record>$product,
                    observation_type = 'conclusion',
                    content = $content,
                    discipline_hint = $discipline,
                    domain_path = $discipline,
                    confidence = 0.7,
                    source = 'reasoning_conclusion',
                    status = 'pending',
                    created_at = time::now()
                """,
                {"product": request.product_id, "content": text[:1500], "discipline": discipline},
            )
    except Exception:
        logger.debug("conclusion graph-capture failed (non-fatal)", exc_info=True)


def _validate_orchestration_request(request: OrchestrationRequest) -> None:
    """Validate an orchestration request before execution begins.

    Raises ValidationError for requests that would fail mid-execution due to
    missing product context or empty task descriptions, allowing callers to
    surface actionable errors before any LLM calls or DB writes happen.
    """
    if not request.description or not request.description.strip():
        raise ValidationError("OrchestrationRequest.description must be non-empty")
    if not request.product_id or ":" not in request.product_id:
        raise ValidationError(f"Invalid product_id: {request.product_id!r}")
    if len(request.description) > 50_000:
        raise ValidationError(
            f"OrchestrationRequest.description exceeds 50,000 char limit ({len(request.description)} chars)"
        )


async def _bridge_task_completed(event: TaskCompleted, classification: dict | None = None) -> None:
    """Bridge a TaskCompleted event from the orchestration bus to the main event bus.

    This allows the capture pipeline and product handlers to consume task outputs.
    """
    try:
        from core.engine.events.bus import bus as main_bus

        await main_bus.emit(
            "task.completed",
            {
                "product_id": event.product_id,
                "task_id": event.task_id,
                "output": event.output_summary,
                "duration_ms": event.duration_ms,
                "discipline": classification.get("discipline", "") if classification else "",
            },
        )
    except Exception as exc:
        logger.debug("Bridge to main bus failed: %s", exc)


async def _write_failure_memory(
    product_id: str,
    discipline: str,
    task_summary: str,
    gaps: list[str],
    verdict: str,
    confidence: float = 0.0,
) -> None:
    """Write VerificationGate gaps to failure_memory for Reflexion-style learning.

    Non-fatal: any DB error is logged and silently swallowed.
    Only writes on non-clean, non-skipped verdicts with actual gaps.
    """
    if verdict in ("clean", "skipped") or not gaps:
        return
    try:
        from core.engine.core.db import parse_rows, pool
        from core.engine.intelligence.failure_replay import detect_repeat_failures, record_repeat_failure

        async with pool.connection() as db:
            # Detect whether this failure repeats a prior one — if so, the
            # system failed to learn from its own failure_memory and that's
            # a measurable counterfactual signal worth surfacing.
            repeats = await detect_repeat_failures(
                db=db,
                product_id=product_id,
                discipline=discipline,
                gaps=gaps,
            )

            result = await db.query(
                """CREATE failure_memory SET
                   product = <record>$product,
                   discipline = $discipline,
                   task_summary = $task_summary,
                   gaps = $gaps,
                   verdict = $verdict,
                   confidence = $confidence,
                   is_repeat = $is_repeat,
                   created_at = time::now()""",
                {
                    "product": product_id,
                    "discipline": discipline,
                    "task_summary": task_summary[:200],
                    "gaps": gaps,
                    "verdict": verdict,
                    "confidence": confidence,
                    "is_repeat": bool(repeats),
                },
            )

            if repeats:
                new_rows = parse_rows(result)
                new_id = str(new_rows[0].get("id")) if new_rows else ""
                if new_id:
                    try:
                        from core.engine.events.bus import bus

                        await record_repeat_failure(
                            db=db,
                            bus=bus,
                            product_id=product_id,
                            new_failure_id=new_id,
                            repeat_of_ids=[str(r.get("id", "")) for r in repeats],
                        )
                    except Exception as exc:
                        logger.debug("repeat-failure event emit failed (non-fatal): %s", exc)
    except Exception as exc:
        logger.warning("failure_memory write failed (non-fatal): %s", exc)


# ---------------------------------------------------------------------------
# Result
# ---------------------------------------------------------------------------


@dataclass
class OrchestrationResult:
    """Final result of an orchestrate() call."""

    task_id: str | None = None
    output: str = ""
    classification: dict[str, Any] = field(default_factory=dict)
    snapshot: dict[str, Any] = field(default_factory=dict)
    pattern_result: PatternResult | None = None
    events: list = field(default_factory=list)
    status: str = "completed"
    error: str | None = None
    duration_ms: int = 0


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _get_strategy(pattern_name: str, bus: OrchestrationBus, factory):
    """Get a PatternStrategy instance by name."""
    from core.engine.orchestration.patterns.adversarial import AdversarialPattern
    from core.engine.orchestration.patterns.fanout import FanOutPattern
    from core.engine.orchestration.patterns.independent import IndependentPattern
    from core.engine.orchestration.patterns.pipeline import PipelinePattern
    from core.engine.orchestration.patterns.team import TeamPattern

    strategies: dict[str, type] = {
        "independent": IndependentPattern,
        "pipeline": PipelinePattern,
        "adversarial": AdversarialPattern,
        "fanout": FanOutPattern,
        "team": TeamPattern,
    }

    cls = strategies.get(pattern_name, IndependentPattern)
    return cls(bus=bus, factory=factory)


async def _persist_events(
    run_id: str,
    product_id: str,
    events: list,
    classification: dict,
    pattern_name: str,
    status: str,
    source: str,
    duration_ms: int,
    task_id: str | None,
    agent_count: int,
    error: str | None = None,
) -> None:
    """Persist orchestration run + events to SurrealDB for debugging/replay."""
    try:
        from core.engine.core.db import pool

        async with pool.connection() as db:
            # Write the run record
            await db.query(
                """
                CREATE orchestration_run SET
                    run_id = $run_id,
                    pattern = $pattern,
                    status = $status,
                    source = $source,
                    domain_path = $domain_path,
                    agent_count = $agent_count,
                    duration_ms = $duration_ms,
                    task_id = $task_id,
                    error = $error
                """,
                {
                    "product": product_id,
                    "run_id": run_id,
                    "pattern": pattern_name,
                    "status": status,
                    "source": source,
                    "domain_path": classification.get("discipline", classification.get("domain_path")),
                    "agent_count": agent_count,
                    "duration_ms": duration_ms,
                    "task_id": task_id,
                    "error": error,
                },
            )

            # Write individual events (skip agent_token to avoid noise)
            for event in events:
                if event.event_type == "agent_token":
                    continue
                payload = {}
                for attr in (
                    "description",
                    "source",
                    "domain_path",
                    "archetype",
                    "mode",
                    "complexity",
                    "insights_count",
                    "cross_domain_count",
                    "pattern",
                    "agent_count",
                    "steps",
                    "agent_id",
                    "role",
                    "output_summary",
                    "duration_ms",
                    "error",
                    "phase",
                    "hook_name",
                    "result_summary",
                    "task_id",
                    "content",
                    "confidence",
                    "severity",
                    "from_agent",
                    "to_agent",
                    "context_summary",
                    "reason",
                ):
                    val = getattr(event, attr, None)
                    if val is not None:
                        payload[attr] = val if not isinstance(val, list) else [str(v) for v in val]

                await db.query(
                    """
                    CREATE orchestration_event SET
                        product = <record>$product,
                        run_id = $run_id,
                        event_type = $event_type,
                        payload = $payload
                    """,
                    {
                        "product": product_id,
                        "run_id": run_id,
                        "event_type": event.event_type,
                        "payload": payload,
                    },
                )
    except Exception as exc:
        logger.warning("Failed to persist orchestration events: %s", exc)


async def _persist_task(
    request: OrchestrationRequest,
    classification: dict,
    snapshot: dict,
    output: str,
    engagement_data: dict | None = None,
    phase_traces: list[dict] | None = None,
) -> str | None:
    """Persist task record to SurrealDB. Returns task_id or None."""
    try:
        from core.engine.core.config import settings
        from core.engine.core.db import pool

        engagement_clause = ""
        engagement_params: dict = {}
        if engagement_data:
            engagement_clause = ", engagement = $engagement"
            engagement_params["engagement"] = engagement_data

        phase_traces_clause = ""
        phase_traces_params: dict = {}
        if phase_traces:
            phase_traces_clause = ", phase_traces = $phase_traces"
            phase_traces_params["phase_traces"] = phase_traces

        discipline = classification.get("discipline", classification.get("domain_path", ""))
        # Keep the public result and the persisted task aligned.  Previously the
        # accumulator was written only to SurrealDB and then cleared by hooks,
        # which made live evaluation through MCP unable to report observable
        # usage/cost data without reaching into an internal store.
        token_usage = get_accumulator().summary() if get_accumulator() else None
        snapshot["token_usage"] = token_usage
        async with pool.connection() as db:
            task_target = "UPDATE <record>$task_id" if request.task_id else "CREATE task"
            lifecycle_clause = (
                "status = 'running', updated_at = time::now()"
                if request.task_id
                else "status = 'completed', completed_at = time::now()"
            )
            result = await db.query(
                f"""
                {task_target} SET
                    product = <record>$product,
                    workspace = <record>$workspace,
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
                    source = $source,
                    {lifecycle_clause},
                    specialties_loaded = $specialties_loaded,
                    token_usage = $token_usage
                    {engagement_clause}
                    {phase_traces_clause}
                """,
                {
                    "task_id": request.task_id,
                    "product": request.product_id,
                    "workspace": request.workspace_id,
                    "user": request.user_id,
                    "description": request.description,
                    "discipline": discipline,
                    "archetype": classification.get("archetype", ""),
                    "mode": classification.get("mode", ""),
                    "perspective": classification.get("perspective", "practitioner"),
                    "intel": snapshot,
                    "output": output,
                    "model": request.model or settings.llm_model,
                    "source": request.source,
                    "specialties_loaded": snapshot.get("specialties_loaded", []),
                    "token_usage": token_usage,
                    **engagement_params,
                    **phase_traces_params,
                },
            )
            from core.engine.core.db import parse_one

            task_record = parse_one(result) or {}
            task_id = str(task_record.get("id") or request.task_id or "unknown")

            # Fire-and-forget ledger record (non-fatal).
            # Caller and callee had drifted (pass_count vs passes, flat token
            # counts vs tokens_by_stage object, missing task_type/tier/model
            # fields). Adapter pattern: derive what the ledger expects from
            # what the executor naturally has.
            if token_usage:
                import asyncio as _asyncio

                from core.engine.intelligence.token_ledger import TokenLedger

                input_tokens = token_usage.get("input_tokens", 0)
                output_tokens = token_usage.get("output_tokens", 0)
                cache_read = token_usage.get("cache_read_input_tokens", 0)
                cache_create = token_usage.get("cache_creation_input_tokens", 0)
                total_input = input_tokens + cache_read + cache_create
                cache_hit_rate = (cache_read / total_input) if total_input > 0 else 0.0
                tokens_by_stage = {
                    "input": input_tokens,
                    "output": output_tokens,
                    "cache_read": cache_read,
                    "cache_creation": cache_create,
                }

                _asyncio.ensure_future(
                    TokenLedger().record(
                        task_id=task_id,
                        discipline=discipline,
                        task_type=classification.get("archetype", "unknown"),
                        tier=classification.get("mode", "reactive"),
                        executor_model=request.model or settings.llm_model,
                        reviewer_model=None,
                        passes=len(token_usage.get("calls", [])),
                        escalated=False,
                        cost_usd=token_usage.get("cost_usd", 0.0),
                        tokens_by_stage=tokens_by_stage,
                        cache_hit_rate=cache_hit_rate,
                        failure_categories=[],
                        product_id=request.product_id,
                    )
                )

            return task_id
    except Exception as exc:
        logger.error("Failed to persist task record: %s", exc)
        return None


# ---------------------------------------------------------------------------
# Loop-context / L5 decision reconciliation
# ---------------------------------------------------------------------------


def _reconcile_loop_context_decisions(loop_ctx: dict, recent_decisions: list) -> dict:
    """Single decision source at the executor site: the L5 loader already put
    TieredDecision objects into classification["recent_decisions"] from the
    same `decision` table. When L5 surfaced any, REPLACE loop_ctx's
    prior_decisions with the first 5 of those (mapped to the plain-dict shape
    load_loop_context._shape produces) so the prompt never carries two
    semantic copies of the ledger. Calibration is untouched — loop_ctx is
    still the only source for that.

    When recent_decisions is empty, loop_ctx's own prior_decisions stand.
    """
    if not recent_decisions:
        return loop_ctx
    loop_ctx["prior_decisions"] = [
        {
            "title": getattr(d, "title", "") or "",
            "rationale": (getattr(d, "rationale", "") or "")[:280],
            "decision_type": getattr(d, "decision_type", "") or "",
        }
        for d in recent_decisions[:5]
    ]
    return loop_ctx


# ---------------------------------------------------------------------------
# Risk context loader (blast radius + seam gaps)
# ---------------------------------------------------------------------------


def _find_source_root(start: Path | None = None) -> Path | None:
    """Return the nearest source checkout, or ``None`` for installed runtimes.

    Risk-context scanning used to construct ``GraphBuilder(".")`` unconditionally.
    An artifact launched from a directory containing a virtualenv therefore parsed
    third-party packages (and their generated/native-adjacent files) as if they were
    the user's repository. Besides being irrelevant and expensive, one tree-sitter
    binding can terminate the process with SIGBUS before Python can catch it. Only a
    real project checkout is an eligible blast-radius source.
    """

    current = (start or Path.cwd()).resolve()
    for candidate in (current, *current.parents):
        if (candidate / ".git").exists() and (candidate / "pyproject.toml").is_file():
            return candidate
    return None


async def _load_risk_context(description: str, product_id: str) -> dict:
    """Blast radius + seam gaps — injected at task time, zero LLM calls.

    Blast radius: tree-sitter scan of live codebase (instant).
    Seam gaps: read from seam_gap table (pre-computed by nightly sentinel job).
    Both are non-fatal — returns partial result on any failure.
    """
    import asyncio as _asyncio

    result: dict = {"blast_radius": [], "seam_gaps": []}

    async def _blast() -> list[dict]:
        try:
            from core.engine.intelligence.graph_builder import GraphBuilder
            from core.engine.intelligence.queries import blast_radius, code_context

            source_root = _find_source_root()
            if source_root is None:
                logger.debug("Blast radius unavailable outside a source checkout")
                return []
            builder = GraphBuilder(str(source_root))
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
            logger.debug("Blast radius load failed (non-fatal): %s", exc)
            return []

    async def _seams() -> list[dict]:
        try:
            from core.engine.core.db import parse_rows, pool

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
            logger.debug("Seam gap query failed (non-fatal): %s", exc)
            return []

    blast_hits, seam_hits = await _asyncio.gather(_blast(), _seams())
    result["blast_radius"] = blast_hits
    result["seam_gaps"] = seam_hits
    return result


# ---------------------------------------------------------------------------
# Core event loop
# ---------------------------------------------------------------------------


async def run(
    request: OrchestrationRequest,
    event_bus: EventBus | None = None,
) -> OrchestrationResult:
    """Core orchestration loop.

    Called by ``orchestrate()`` (one-shot) and ``stream()`` (SSE).

    Parameters
    ----------
    request:
        The fully-formed orchestration request.
    event_bus:
        Optional shared EventBus.  When provided (by ``stream()``), the
        run emits events onto it so the SSE consumer can yield them in
        real time.  When *None* a private bus is created for book-keeping.
    """
    _validate_orchestration_request(request)
    start = time.monotonic()
    started_at_epoch = time.time()
    run_id = f"run_{uuid.uuid4().hex[:12]}"

    # Correlation ID — propagates to all log records for this task's async context
    from core.engine.core.log_context import set_correlation_id

    set_correlation_id(run_id)

    # OTel — annotate the active HTTP span (created by FastAPI auto-instrumentation)
    # with executor-level attributes so traces are searchable by run/product.
    from opentelemetry import trace as _otel_trace

    _current_span = _otel_trace.get_current_span()
    _current_span.set_attribute("ace.run_id", run_id)
    _current_span.set_attribute("ace.product_id", request.product_id or "")
    _current_span.set_attribute("ace.source", request.source or "")

    from core.engine.core.metrics import orchestration_active

    orchestration_active.inc()

    # Token accumulator for this task execution
    accumulator = TokenAccumulator()
    set_accumulator(accumulator)

    bus = event_bus or EventBus(run_id=run_id, product_id=request.product_id)

    # 1. Emit task_received
    await bus.emit(
        TaskReceived(
            run_id=run_id,
            product_id=request.product_id,
            description=request.description[:200],
            source=request.source,
        )
    )

    try:
        # 1b. Load graph context (best-effort, used for classification + intelligence)
        graph_context: dict | None = None
        try:
            from core.engine.graph.context import load_graph_context

            graph_context = await load_graph_context(request.description)
        except Exception as exc:
            logger.debug("Graph context load failed (best-effort): %s", exc)

        # 2. Classify (or use override)
        set_stage("classification")
        _cache_entry_id: str | None = None
        if request.classification_override:
            classification = request.classification_override
        else:
            # ── Classification cache lookup (Phase 2) ─────────────────────
            _cached_classification: dict | None = None
            try:
                from core.engine.intelligence.classification_cache import lookup_with_entry as _cc_lookup_with_entry

                _cc_result = await _cc_lookup_with_entry(request.description, request.product_id)
                if _cc_result is not None:
                    _cached_classification, _cache_entry_id = _cc_result
            except Exception as _cache_lookup_err:
                logger.debug("classification cache lookup failed (non-fatal): %s", _cache_lookup_err)

            if _cached_classification is not None:
                classification = _cached_classification
            elif graph_context and graph_context.get("relevant_files"):
                # Graph-aware classification
                try:
                    from core.engine.graph.classifier import classify_with_graph

                    classification = await classify_with_graph(request.description, graph_context, request.product_id)
                except Exception as exc:
                    logger.warning("Graph classifier failed, falling back to old: %s", exc)
                    from core.engine.orchestrator.classifier import classify_task

                    classification = await classify_task(request.description, request.product_id)
            else:
                from core.engine.orchestrator.classifier import classify_task

                classification = await classify_task(request.description, request.product_id)

            # ── Store result in cache if it was freshly computed ──────────
            if _cached_classification is None:
                try:
                    from core.engine.intelligence.classification_cache import store as _cache_store

                    await _cache_store(request.description, classification, request.product_id)
                except Exception as _cache_store_err:
                    logger.debug("classification cache store failed (non-fatal): %s", _cache_store_err)

        await bus.emit(
            ClassificationComplete(
                run_id=run_id,
                product_id=request.product_id,
                domain_path=classification.get("domain_path", ""),
                archetype=classification.get("archetype", ""),
                mode=classification.get("mode", ""),
                complexity=classification.get("complexity", "simple"),
            )
        )

        # 2b+2d. Score composition + risk context — independent, run in parallel.
        # cognitive_composer (2c) depends on score_composition output so runs after.
        _scored_r, _risk_r = await asyncio.gather(
            score_composition(classification, request.product_id),
            _load_risk_context(request.description, request.product_id),
            return_exceptions=True,
        )

        # Apply composition scoring result
        try:
            if isinstance(_scored_r, Exception):
                raise _scored_r
            classification["perspective_weights"] = _scored_r.perspective_weights
            engagement = classification.get("engagement", {})
            if _scored_r.perspectives != engagement.get("perspectives", []):
                engagement["perspectives"] = _scored_r.perspectives
                classification["engagement"] = engagement
            if _scored_r.engagement_type == "adversarial" and not engagement.get("adversarial_pair"):
                if len(_scored_r.perspectives) >= 2:
                    engagement["adversarial_pair"] = _scored_r.perspectives[:2]
                    classification["engagement"] = engagement
        except Exception:
            logger.warning("Composition scoring failed, using raw classification", exc_info=True)

        # Apply risk context result
        if isinstance(_risk_r, Exception):
            logger.debug("Risk context load failed (non-fatal): %s", _risk_r)
        else:
            classification["risk_context"] = _risk_r

        # ── Intelligence budget from task depth (Phase 3) ─────────────────
        from core.engine.intelligence.depth_budget import _DEFAULT_BUDGET as _intel_budget

        try:
            from core.engine.cognition.models import derive_depth as _derive_depth
            from core.engine.intelligence.depth_budget import budget_for_depth as _budget_for_depth

            _task_depth = _derive_depth(
                classification.get("mode", "reactive"),
                classification.get("complexity", "simple"),
            )
            _intel_budget = _budget_for_depth(_task_depth)
        except Exception as _budget_err:
            logger.warning("depth budget computation failed (non-fatal): %s", _budget_err)

        # 2c-pre. Layer 5 context assembly — load prior decisions BEFORE the
        # cognitive composer runs so the prompt is grounded in lineage.
        # Best-effort: never blocks; degrades to today's stateless behavior on
        # any failure. decision:lv6stu70piemfwypde2e closes the gap where every
        # engagement started cold despite the canvas ledger existing.
        try:
            from core.engine.orchestrator.context import load_decision_context

            l5_result = await load_decision_context(
                task_description=request.description,
                classification=classification,
                product_id=request.product_id,
            )
            classification["recent_decisions"] = l5_result.decisions
            classification["recent_decisions_degraded_tiers"] = l5_result.degraded_tiers
            classification["recent_decisions_elapsed_ms"] = l5_result.elapsed_ms
            classification["recent_decisions_contradictions"] = l5_result.contradictions

            # 2c-pre.b — L5 precedent tie-breaker (decision:lv6stu70piemfwypde2e §6.4)
            # On low-confidence discipline classifications, override with the
            # highest-relevance capability-tier precedent's discipline_hint.
            # TODO-12 multi-turn guard reads task.metadata.tiebreaker_history_last_turn
            # to avoid re-firing the same precedent across turns.
            try:
                from core.engine.orchestrator.classifier import apply_precedent_tiebreaker

                _task_meta = getattr(request, "metadata", None) or {}
                _tiebroken = apply_precedent_tiebreaker(
                    classifier_output=classification,
                    classification=classification,
                    task_meta=_task_meta,
                )
                # Merge any new keys back (discipline override, history, observability).
                for _k in ("discipline", "discipline_tiebreaker", "tiebreaker_history"):
                    if _k in _tiebroken:
                        classification[_k] = _tiebroken[_k]
            except Exception:
                logger.debug("L5 precedent tiebreaker failed (non-fatal)", exc_info=True)
        except Exception:
            logger.warning("L5 decision context load failed (non-fatal)", exc_info=True)
            classification["recent_decisions"] = []
            classification["recent_decisions_degraded_tiers"] = frozenset({"capability", "discipline", "recency"})
            classification["recent_decisions_elapsed_ms"] = 0.0
            classification["recent_decisions_contradictions"] = []

        # 2c-pre-loop. Load loop context (prior decisions + calibration) so the
        # composer prompt is grounded in the decision ledger. Fail-open: any
        # failure or timeout returns {} and composition proceeds stateless (same
        # as before). Loaded ONCE here; the same dict rides into every subsequent
        # compose/lens call via classification["loop_context"].
        try:
            from core.engine.orchestration.loop_context import load_loop_context

            loop_ctx = await load_loop_context(request.product_id, classification)
            if loop_ctx:
                # Decisions are reconciled from L5 (recent_decisions) when present —
                # loop_ctx is then only authoritative for calibration at this site.
                loop_ctx = _reconcile_loop_context_decisions(loop_ctx, classification.get("recent_decisions") or [])
                if request.eval_no_calibration:
                    loop_ctx["calibration"] = {}
                classification["loop_context"] = loop_ctx
                # Emit layer5.context_loaded so canvas can show "informed by N decisions"
                try:
                    from core.engine.canvas.event_protocol import EVENT_LAYER5_CONTEXT_LOADED
                    from core.engine.events.bus import bus as _main_bus

                    await _main_bus.emit(
                        EVENT_LAYER5_CONTEXT_LOADED,
                        {
                            "decision_count": len(loop_ctx.get("prior_decisions", [])),
                            "capability_count": 0,
                            "discipline_count": 0,
                            "recency_count": 0,
                            "degraded_tiers": [],
                            "contradictions_count": 0,
                            "elapsed_ms": 0.0,
                            "calibration_archetypes": len(loop_ctx.get("calibration", {})),
                        },
                    )
                except Exception:
                    logger.debug("layer5.context_loaded emit failed (non-fatal)", exc_info=True)
        except Exception:
            logger.debug("loop_context load failed (non-fatal)", exc_info=True)

        # 2c. Cognitive composition — attaches CognitiveComposition to classification
        # Runs after score_composition so it sees updated perspective_weights.
        try:
            if _cognitive_composer is not None:
                _composition = await _cognitive_composer.compose(classification, request.product_id)
                classification["cognitive_composition"] = _composition
        except Exception:
            logger.warning("Cognitive composition failed, continuing without it", exc_info=True)

        # 2e. Multi-perspective engagement routing
        engagement = classification.get("engagement", {})
        perspectives = engagement.get("perspectives", [])

        if len(perspectives) > 1:
            from core.engine.orchestrator.engagement import execute_engagement
            from core.engine.orchestrator.injection import inject_missing_perspectives

            classification = await inject_missing_perspectives(classification, request.product_id)
            engagement_result = await execute_engagement(
                request.description,
                classification,
                request.product_id,
                request.workspace_id,
                perspective_weights=classification.get("perspective_weights"),
            )
            output = engagement_result.merged_output
            snapshot = {
                "perspectives_used": engagement_result.perspectives_used,
                "spin_count": len(engagement_result.spins),
                "engagement_rationale": engagement_result.engagement_rationale,
                "verified": engagement_result.verified,
                "verification_verdict": engagement_result.verification_verdict,
                "verification_gaps": engagement_result.verification_gaps,
            }

            # Inject PM context from all 4 graph layers
            try:
                from core.engine.orchestrator.context import load_full_context

                discipline = classification.get("discipline", classification.get("domain_path", ""))
                snapshot["pm_context"] = await load_full_context(request.product_id, discipline)
            except Exception as _pm_e:
                logger.warning("PM context load failed (engagement): %s", _pm_e)
                snapshot["pm_context"] = None

            engagement_data = {
                "perspectives": engagement_result.perspectives_used,
                "adversarial_pair": engagement.get("adversarial_pair"),
                "rationale": engagement_result.engagement_rationale,
                "injected": engagement_result.injected_perspectives,
                "spin_count": len(engagement_result.spins),
            }

            # Failure memory: persist gaps for Reflexion-style self-improvement
            if snapshot.get("verification_gaps") and snapshot.get("verification_verdict") not in ("clean", "skipped"):
                try:
                    await _write_failure_memory(
                        product_id=request.product_id,
                        discipline=classification.get("discipline", ""),
                        task_summary=str(request.description)[:200],
                        gaps=snapshot["verification_gaps"],
                        verdict=snapshot["verification_verdict"],
                        confidence=0.0,
                    )
                except Exception:
                    pass  # non-fatal

            # STaR: persist successful reasoning trace when VerificationGate passes cleanly
            if snapshot.get("verification_verdict") == "clean":
                try:
                    from core.engine.core.db import pool as _db_pool

                    _phase_traces = _spins_to_phase_traces(engagement_result.spins)
                    await write_star_trace(
                        pool=_db_pool,
                        product_id=request.product_id,
                        discipline=classification.get("discipline", ""),
                        task_description=str(request.description),
                        phase_traces=_phase_traces,
                        final_output=str(output),
                    )
                except Exception as _star_exc:
                    logger.warning("star_trace write failed (non-fatal): %s", _star_exc)

            # Persist task record
            task_id = None
            if request.persist_task:
                task_id = await _persist_task(
                    request,
                    classification,
                    snapshot,
                    output,
                    engagement_data=engagement_data,
                )

            # Run post-task hooks
            if request.run_post_hooks and task_id:
                hook_ctx = HookContext(
                    task_id=str(task_id),
                    product_id=request.product_id,
                    domain_path=classification.get("domain_path", ""),
                    output=output,
                    snapshot=snapshot,
                    classification=classification,
                    frameworks_used=[],
                    engagement_result={
                        "spin_count": len(engagement_result.spins) if engagement_result else 1,
                        "adversarial_diversity": getattr(engagement_result, "adversarial_diversity", None),
                        "engagement_type": "adversarial"
                        if (engagement_result and engagement_result.adversarial_resolution)
                        else "pipeline",
                    }
                    if engagement_result
                    else None,
                    token_accumulator=accumulator,
                    task_description=request.description,
                    started_at=started_at_epoch,
                )
                await run_hooks(hook_ctx, event_bus=bus)
                clear_accumulator()

            # Write task + agent nodes to graph (best-effort dual-write)
            if task_id:
                try:
                    from core.engine.graph.writer import write_task_to_graph

                    await write_task_to_graph(
                        task_id=str(task_id),
                        description=request.description,
                        status="completed",
                        output=output,
                        feedback=None,
                        classification=classification,
                    )
                except Exception:
                    pass  # graph write is best-effort

            # Post-task: create loaded edges (task -> top 5 insights by confidence, best-effort)
            if task_id:
                try:
                    from core.engine.graph.edge_writer import create_edges

                    all_insights = snapshot.get("insights", [])
                    top_insights = sorted(all_insights, key=lambda x: x.get("confidence", 0), reverse=True)[:5]
                    if top_insights:
                        edges = [("loaded", str(task_id), str(ins["id"])) for ins in top_insights if ins.get("id")]
                        await create_edges(edges)
                except Exception:
                    pass  # best-effort

            duration = int((time.monotonic() - start) * 1000)
            orchestration_active.dec()

            discipline = classification.get("discipline", "unknown")
            from core.engine.core.metrics import task_counter, task_duration

            task_counter.labels(discipline=discipline, status="completed").inc()
            task_duration.labels(discipline=discipline).observe(duration / 1000)
            _otel_trace.get_current_span().set_attribute("ace.discipline", discipline)

            if duration > 30_000:
                logger.warning(
                    "SLOW TASK: run_id=%s duration=%dms product=%s discipline=%s",
                    run_id,
                    duration,
                    request.product_id,
                    classification.get("discipline", "?"),
                    extra={"slow_task": True, "duration_ms": duration, "run_id": run_id},
                )

            tc_event = TaskCompleted(
                run_id=run_id,
                product_id=request.product_id,
                task_id=str(task_id) if task_id else "",
                output_summary=output,  # send full output, not truncated
                duration_ms=duration,
            )
            await bus.emit(tc_event)
            await _bridge_task_completed(tc_event, classification)

            if request.persist_events:
                await _persist_events(
                    run_id=run_id,
                    product_id=request.product_id,
                    events=bus.events(),
                    classification=classification,
                    pattern_name="engagement",
                    status="completed",
                    source=request.source,
                    duration_ms=duration,
                    task_id=str(task_id) if task_id else None,
                    agent_count=len(engagement_result.spins),
                )

            # Record the multi-perspective engagement run into the reasoning_event log — the deepest,
            # most fork-worthy cohort (one keystone, four downstreams). Spins become the phase trace.
            await _record_reasoning_run(
                request,
                classification,
                depth=len(engagement_result.perspectives_used or []),
                meta_skills=list(engagement_result.perspectives_used or []),
                phases=_spins_to_phase_traces(engagement_result.spins),
                conclusion=output or "",
                status="complete",
            )

            snapshot["token_usage"] = accumulator.summary()
            return OrchestrationResult(
                task_id=str(task_id) if task_id else None,
                output=output,
                classification=classification,
                snapshot=snapshot,
                events=bus.events(),
                status="completed",
                duration_ms=duration,
            )

        # 3. Load intelligence (or use override)
        set_stage("intelligence_load")
        if request.intelligence_override is not None:
            snapshot = request.intelligence_override
        else:
            specialties = classification.get("specialties", [])
            if specialties:
                from core.engine.orchestrator.dual_loader import load_dual_intelligence
                from core.engine.orchestrator.specialty_resolver import resolve_specialties

                resolution = await resolve_specialties(specialties, request.product_id)
                resolved_slugs = [r["slug"] for r in resolution.get("resolved", []) if r.get("slug")]
                snapshot = await load_dual_intelligence(
                    resolved_slugs,
                    request.product_id,
                    org_context=classification.get("org_context"),
                    mode=classification.get("mode", "reactive"),
                    discipline=classification.get("discipline", ""),
                    budget_multiplier=_intel_budget.recall_multiplier,
                )
            else:
                from core.engine.orchestrator.loader import load_intelligence

                snapshot = await load_intelligence(
                    discipline=classification.get("discipline", "") or classification.get("domain_path", ""),
                    product_id=request.product_id,
                    mode=classification.get("mode", "reactive"),
                )

        # Inject graph context into snapshot for prompt building
        if graph_context and graph_context.get("relevant_files"):
            snapshot["graph_context"] = graph_context

        # Forward risk context from classification into snapshot so _build_intel_context renders it
        if classification.get("risk_context"):
            snapshot["risk_context"] = classification["risk_context"]

        # code_ctx — always loaded (file context is cheap and always useful).
        from core.engine.orchestrator.executor import _load_code_context

        _discipline = classification.get("discipline", classification.get("domain_path", ""))

        try:
            _cc_r = await _load_code_context(request.description)
        except Exception as _cc_err:
            logger.debug("Code context load failed (non-fatal): %s", _cc_err)
            _cc_r = {"files": []}

        if _cc_r.get("files"):
            snapshot["code_context"] = _cc_r

        # PM context — gated by depth budget (Phase 3).
        # Depth 1-2 tasks skip PM context to conserve token budget.
        if _intel_budget.load_pm_context:
            try:
                from core.engine.orchestrator.context import load_full_context

                snapshot["pm_context"] = await load_full_context(request.product_id, _discipline)
            except Exception as _pm_e:
                logger.warning("PM context load failed: %s", _pm_e)
                snapshot["pm_context"] = None
        else:
            snapshot["pm_context"] = None

        # ── Relevance ranking (Phase 2) ─────────────────────────────────────
        try:
            from core.engine.intelligence.ranker import rank_insights as _rank_insights

            snapshot = await _rank_insights(snapshot, request.description, request.product_id)
        except Exception as _rank_err:
            logger.warning("ranker failed (non-fatal): %s", _rank_err)

        # ── Near-duplicate compression (Phase 2) ────────────────────────────
        try:
            from core.engine.intelligence.compressor import compress_insights as _compress_insights

            snapshot["insights"] = _compress_insights(snapshot.get("insights", []))
            snapshot["specialty_insights"] = _compress_insights(snapshot.get("specialty_insights", []))
            snapshot["org_insights"] = _compress_insights(snapshot.get("org_insights", []))
        except Exception as _compress_err:
            logger.warning("compressor failed (non-fatal): %s", _compress_err)

        try:
            from core.engine.graph.tension_telemetry import record_tension_surfaces

            await record_tension_surfaces(
                snapshot.get("graph_tensions", {}), surface="reasoning_context", product_id=request.product_id
            )
        except Exception:
            pass

        await bus.emit(
            IntelligenceLoaded(
                run_id=run_id,
                product_id=request.product_id,
                insights_count=snapshot.get("total_count", 0),
                cross_domain_count=snapshot.get("cross_domain_count", 0),
            )
        )

        # 4. Dispatch: select mode + pattern
        decision = dispatch(request, classification)

        # 5. Plan (if deliberative and no explicit agent_configs)
        agent_configs = request.agent_configs
        pattern_name = decision.pattern

        if decision.mode == "deliberative" and not agent_configs:
            from core.engine.core.llm import llm
            from core.engine.orchestration.planner import plan_execution

            plan = await plan_execution(
                request.description,
                classification,
                snapshot,
                llm=llm,
            )
            pattern_name = plan.pattern
            # Convert plan steps to AgentConfigs
            agent_configs = [
                AgentConfig(
                    role=step.role,
                    system_prompt=(
                        f"You are a {step.role}. {step.description}\n\n"
                        "Return at most 800 words. Prioritize decision-relevant evidence, "
                        "explicit tradeoffs, and a concise handoff; do not restate the full task."
                    ),
                    use_agent_sdk=request.use_agent_sdk,
                )
                for step in plan.steps
            ]

        if not agent_configs:
            composition = classification.get("cognitive_composition")

            # Depth 3-4: run phases sequentially via MultiPhaseExecutor
            if composition and not composition.fusion_mode and composition.active_phases:
                try:
                    from core.engine.cognition.multiphase import MultiPhaseExecutor, resolve_moa_config
                    from core.engine.core.db import parse_rows, pool

                    # Fetch framework prompts for all resolved slugs
                    all_slugs = {slug for slugs in composition.resolved_instruments.values() for slug in slugs}
                    _fw_prompts: dict[str, str] = {}
                    try:
                        async with pool.connection() as _db:
                            _fw_rows = await _db.query(
                                "SELECT slug, system_prompt FROM framework WHERE slug IN $slugs",
                                {"slugs": list(all_slugs)},
                            )
                            for row in parse_rows(_fw_rows):
                                if row.get("system_prompt"):
                                    _fw_prompts[row["slug"]] = row["system_prompt"]
                    except Exception:
                        logger.warning(
                            "Framework prompt fetch failed for multi-phase execution — "
                            "slugs=%r. PromptFusion will use fallback text.",
                            all_slugs,
                            exc_info=True,
                        )

                    async def _llm_call(system_prompt: str, user_prompt: str) -> str:
                        from core.engine.core.llm import get_llm

                        _llm = get_llm()
                        return await _llm.complete(
                            user_prompt,
                            system=system_prompt,
                            model=request.model,
                        )

                    async def _retrieval_fn(gap_terms: list[str]) -> str:
                        """Fetch additional intelligence for gap terms during mid-phase retrieval."""
                        try:
                            from core.engine.orchestrator.loader import load_intelligence

                            snap = await load_intelligence(
                                discipline=classification.get("discipline", ""),
                                product_id=request.product_id,
                                specialties=gap_terms[:3],
                                mode="reactive",
                            )
                            top = snap.get("insights", [])[:3]
                            if not top:
                                return ""
                            return "Additional context: " + "; ".join(i.get("content", "") for i in top)
                        except Exception:
                            return ""

                    from core.engine.cognition.phase_evaluator import PhaseEvaluator
                    from core.engine.core.config import settings as _settings

                    _phase_evaluator = PhaseEvaluator(advisor_model=_settings.llm_model)
                    # MoA Part 2: cross-model ensemble at the high-stakes ("choose") phase, confidence-
                    # gated. Off unless settings.moa_models is configured (then non-Claude proposers
                    # route through moa_peer_host, Part 1). Strong Claude aggregator by default.
                    _moa_models, _moa_aggregator = resolve_moa_config(_settings)
                    multi_exec = MultiPhaseExecutor(
                        llm_call=_llm_call,
                        retrieval_fn=_retrieval_fn,
                        phase_evaluator=_phase_evaluator,
                        # Phase 3: activate evaluator-guided refinement (monotonic — accepts
                        # a revision only if the evaluator scores it no worse). Gated by
                        # confidence; SELF_REFINE_ROUNDS=0 disables for A/B comparison.
                        self_refine_rounds=_settings.self_refine_rounds,
                        moa_models=_moa_models,
                        moa_aggregator_model=_moa_aggregator,
                    )

                    # Build intelligence context string for phase-1 injection
                    _intel_ctx = ""
                    try:
                        from core.engine.orchestration.shell import ShellComposer as _SC

                        _intel_ctx = _SC()._build_intel_context_safe(snapshot)
                    except Exception:
                        pass

                    multi_output = await multi_exec.execute(
                        description=request.description,
                        composition=composition,
                        framework_prompts=_fw_prompts,
                        intel_context=_intel_ctx,
                        product_id=request.product_id,
                    )

                    # Record the deep-reasoning run into the reasoning_event log — the keystone
                    # substrate (one keystone, four downstreams: forkable foresight, trace UI, canvas
                    # reasoning, sentinel realtime). The MAIN orchestrate path previously emitted nothing
                    # (only reasoning_run.py did), so the log sat empty.
                    _active_phases = list(composition.active_phases or [])
                    await _record_reasoning_run(
                        request,
                        classification,
                        depth=len(_active_phases),
                        meta_skills=[getattr(p, "cognitive_function", "") for p in _active_phases],
                        phases=list(getattr(multi_exec, "_last_trace", None) or []),
                        conclusion=multi_output or "",
                        status="complete" if multi_output else "failed",
                    )
                    if multi_output:
                        from core.engine.orchestration.agent import AgentResult
                        from core.engine.orchestration.patterns.base import PatternResult

                        pattern_result = PatternResult(
                            run_id=run_id,
                            pattern_name="multi-phase",
                            output=multi_output,
                            status="completed",
                            agent_results=[
                                AgentResult(agent_id="multi-phase", output=multi_output, status="completed")
                            ],
                        )
                        pattern_name = "multi-phase"
                        task_id = None
                        if request.persist_task:
                            task_id = await _persist_task(
                                request,
                                classification,
                                snapshot,
                                multi_output,
                                phase_traces=multi_exec._last_trace,
                            )
                        if request.run_post_hooks and task_id:
                            hook_ctx = HookContext(
                                task_id=str(task_id),
                                product_id=request.product_id,
                                domain_path=classification.get("domain_path", ""),
                                output=multi_output,
                                snapshot=snapshot,
                                classification=classification,
                                frameworks_used=list(all_slugs),
                                engagement_result=None,
                                token_accumulator=accumulator,
                                phase_traces=list(multi_exec._last_trace),
                                task_description=request.description,
                                started_at=started_at_epoch,
                            )
                            await run_hooks(hook_ctx, event_bus=bus)
                            clear_accumulator()
                        duration = int((time.monotonic() - start) * 1000)
                        orchestration_active.dec()
                        _disc = classification.get("discipline", "unknown")
                        from core.engine.core.metrics import task_counter, task_duration

                        task_counter.labels(discipline=_disc, status="completed").inc()
                        task_duration.labels(discipline=_disc).observe(duration / 1000)
                        tc_event = TaskCompleted(
                            run_id=run_id,
                            product_id=request.product_id,
                            task_id=str(task_id) if task_id else "",
                            output_summary=multi_output,
                            duration_ms=duration,
                        )
                        await bus.emit(tc_event)
                        await _bridge_task_completed(tc_event, classification)
                        snapshot["token_usage"] = accumulator.summary()
                        return OrchestrationResult(
                            task_id=str(task_id) if task_id else None,
                            output=multi_output,
                            classification=classification,
                            snapshot=snapshot,
                            events=bus.events(),
                            status="completed",
                            duration_ms=duration,
                        )
                except Exception as exc:
                    logger.warning("Multi-phase execution failed, falling back to single-agent: %s", exc)

            # Default: single agent with classification-based shell (depth 1-2 or fallback)
            # Problem 1 fix: load framework prompts for fusion mode (depth 1-2).
            # ShellComposer._build_cognitive_section reads snapshot["_framework_prompts"];
            # without this, PromptFusion falls back to generic phase labels with no content.
            _fusion_composition = classification.get("cognitive_composition")
            if _fusion_composition and _fusion_composition.fusion_mode and _fusion_composition.resolved_instruments:
                _fusion_slugs = {slug for slugs in _fusion_composition.resolved_instruments.values() for slug in slugs}
                if _fusion_slugs:
                    try:
                        from core.engine.core.db import parse_rows, pool

                        async with pool.connection() as _db:
                            _fw_rows = await _db.query(
                                "SELECT slug, system_prompt FROM framework WHERE slug IN $slugs",
                                {"slugs": list(_fusion_slugs)},
                            )
                            snapshot["_framework_prompts"] = {
                                row["slug"]: row.get("system_prompt", "")
                                for row in parse_rows(_fw_rows)
                                if row.get("system_prompt")
                            }
                    except Exception:
                        logger.debug("Framework prompt load failed for fusion path (non-fatal)", exc_info=True)

            # Build marked context FIRST so the model receives [I-N] markers in
            # its system prompt. Without this, build_with_markers() was called
            # after compose() and its context string was thrown away — Pass 1
            # marker-based attribution was permanently dead.
            try:
                from core.engine.orchestrator.context_assembler import ContextAssembler as _CA

                _assembler = _CA(max_tokens=_intel_budget.context_tokens)
                _marked_context, _marker_map = _assembler.build_with_markers(snapshot)
                snapshot["_marker_map"] = _marker_map
                # Store the marked context so _build_intel_context returns it
                # instead of rebuilding without markers.
                snapshot["_intel_context_with_markers"] = _marked_context
            except Exception:
                pass

            composer = ShellComposer()
            shell = composer.compose(
                classification,
                snapshot,
                request.description,
                conversation_messages=request.conversation_messages,
                model=request.model,
                max_tokens=_intel_budget.context_tokens,
            )
            system_prompt = shell.system_prompt
            if request.system_prompt_override:
                intel_ctx = ShellComposer()._build_intel_context_safe(snapshot)
                system_prompt = request.system_prompt_override + "\n\n" + intel_ctx

            # Record context injection tokens
            snapshot["_context_injection_tokens"] = len(system_prompt) // 4

            _acc = get_accumulator()
            if _acc is not None:
                _context_chars = len(system_prompt)
                _context_tokens = _context_chars // 4
                _acc.record(
                    method="context_injection",
                    input_tokens=_context_tokens,
                    output_tokens=0,
                    purpose="system_prompt_injection",
                    stage="context_injection",
                )

            agent_configs = [
                AgentConfig(
                    role=classification.get("archetype", "executor"),
                    system_prompt=system_prompt,
                    model=shell.model,
                    use_agent_sdk=request.use_agent_sdk,
                )
            ]

        await bus.emit(
            PlanCreated(
                run_id=run_id,
                product_id=request.product_id,
                pattern=pattern_name,
                agent_count=len(agent_configs),
                steps=[ac.role for ac in agent_configs],
            )
        )

        # 6. Create orchestration bus, factory, and select strategy
        from core.engine.core.llm import llm as llm_provider
        from core.engine.orchestration.factory import AgentFactory

        orchestration_bus = OrchestrationBus()
        factory = AgentFactory(llm_provider=llm_provider, bus=orchestration_bus)

        strategy = _get_strategy(pattern_name, orchestration_bus, factory)

        pattern_config = PatternConfig(
            run_id=run_id,
            product_id=request.product_id,
            workspace_id=request.workspace_id,
            user_id=request.user_id,
            intel_context=ShellComposer()._build_intel_context_safe(snapshot),
            stream_tokens=request.stream_tokens,
            event_bus=bus,
            conversation_messages=request.conversation_messages,
        )

        # 7. Execute pattern
        set_stage("execution")
        pattern_result = await strategy.execute(
            request.description,
            pattern_config,
            agent_configs,
        )

        # Record deliberative (planned multi-agent) reasoning into the reasoning_event log — the
        # keystone substrate. This is the reviewer's "complex deliberative" cohort (agent_configs from
        # the planner), the other deep path forkable foresight needs. Scoped to deliberative runs so
        # the high-volume depth-1/2 single-agent fallback doesn't take two inline DB writes per call
        # (the shallow single-pass is a spec non-goal).
        if decision.mode == "deliberative":
            await _record_reasoning_run(
                request,
                classification,
                depth=len(agent_configs),
                meta_skills=[getattr(ac, "role", "") for ac in agent_configs],
                phases=[
                    {
                        "phase_name": getattr(ar, "role", ""),
                        "output": getattr(ar, "output", ""),
                        "status": getattr(ar, "status", ""),
                    }
                    for ar in (getattr(pattern_result, "agent_results", None) or [])
                ],
                conclusion=getattr(pattern_result, "output", "") or "",
                status="complete" if getattr(pattern_result, "status", "") == "completed" else "failed",
            )

        # 8. Persist task record (if requested)
        task_id = None
        if request.persist_task:
            task_id = await _persist_task(
                request,
                classification,
                snapshot,
                pattern_result.output,
            )

        # 8b. Attribution + utilization tracking (best-effort, non-fatal)
        try:
            from core.engine.intelligence.attribution import (
                attribute_llm,
                attribute_structural,
                should_run_llm_attribution,
                weight_attributions,
            )
            from core.engine.intelligence.utilization import update_utilization

            _marker_map = snapshot.get("_marker_map", {})
            _injected = snapshot.get("specialty_insights", []) + snapshot.get("org_insights", [])
            if _injected:
                _structural = attribute_structural(
                    output=pattern_result.output,
                    marker_map=_marker_map,
                    injected_insights=_injected,
                )
                _attribution_result = _structural
                _context_injection_tokens = snapshot.get("_context_injection_tokens", 0)
                _total_tokens = accumulator.total() if accumulator else 0
                _context_ratio = (_context_injection_tokens / _total_tokens) if _total_tokens > 0 else 0.0
                if should_run_llm_attribution(
                    structural_attributed=_structural.attributed_ids,
                    injected_count=len(_injected),
                    context_ratio=_context_ratio,
                ):
                    try:
                        from core.engine.core.llm import get_llm as _get_llm

                        _attribution_result = await attribute_llm(
                            output=pattern_result.output,
                            marker_map=_marker_map,
                            injected_insights=_injected,
                            llm=_get_llm(),
                        )
                    except Exception:
                        _attribution_result = _structural

                _attribution_result.weights = weight_attributions(
                    attributed_ids=_attribution_result.attributed_ids,
                    injected_insights=_injected,
                    output=pattern_result.output,
                )

                if task_id:
                    try:
                        from core.engine.core.config import settings as _settings_for_affinity
                        from core.engine.core.db import pool as _db_pool
                        from core.engine.intelligence.model_affinity import update_model_affinity
                        from core.engine.intelligence.roi_detector import detect_roi_events_from_attribution

                        _loaded_ids = [str(ins.get("id", "")) for ins in _injected if ins.get("id")]
                        _model_id = request.model or _settings_for_affinity.llm_model
                        async with _db_pool.connection() as _db:
                            await update_utilization(
                                product_id=request.product_id,
                                loaded_ids=_loaded_ids,
                                attributed_ids=_attribution_result.attributed_ids,
                                db=_db,
                            )
                            await update_model_affinity(
                                product_id=request.product_id,
                                loaded_ids=_loaded_ids,
                                attributed_ids=_attribution_result.attributed_ids,
                                model_class=_model_id or "",
                                db=_db,
                            )
                            await detect_roi_events_from_attribution(
                                task_record={"id": task_id},
                                attribution_result=_attribution_result,
                                product_id=request.product_id,
                                db=_db,
                            )
                    except Exception as _util_exc:
                        logger.warning("Utilization update failed (non-fatal): %s", _util_exc)

                # ── Classification cache feedback (Phase 4) ─────────────────────
                if _cache_entry_id and _attribution_result and _attribution_result.injected_count > 0:
                    try:
                        from core.engine.intelligence.classification_cache import (
                            on_utilization_hit as _cc_util_hit,
                        )
                        from core.engine.intelligence.classification_cache import (
                            on_zero_utilization_hit as _cc_zero_hit,
                        )

                        if _attribution_result.utilization_rate == 0.0:
                            await _cc_zero_hit(_cache_entry_id)
                        else:
                            await _cc_util_hit(_cache_entry_id)
                    except Exception as _cc_fb_err:
                        logger.warning("cache feedback failed (non-fatal): %s", _cc_fb_err)
        except Exception as _attr_exc:
            logger.debug("Attribution block failed (non-fatal): %s", _attr_exc)

        # ── A/B shadow baseline — 1-in-20 tasks (Phase 4) ────────────────────
        if not request.shadow_run and not request.intelligence_override:
            import random

            if random.random() < 0.05:  # 5% ≈ 1-in-20
                try:
                    from core.engine.core.db import pool as _ab_pool
                    from core.engine.intelligence.ab_judge import run_shadow_comparison as _ab_compare

                    _ab_result = await _ab_compare(
                        description=request.description,
                        classification=classification,
                        product_id=request.product_id,
                        treatment_output=pattern_result.output,
                    )
                    if _ab_result and task_id:
                        from core.engine.cognition.models import derive_depth as _derive_depth_ab

                        _ab_depth = _derive_depth_ab(
                            classification.get("mode", "reactive"),
                            classification.get("complexity", "simple"),
                        )
                        async with _ab_pool.connection() as _ab_db:
                            await _ab_db.query(
                                """CREATE ab_result SET
                                    product = <record>$product,
                                    task_id = <record>$task_id,
                                    discipline = $discipline,
                                    depth = $depth,
                                    judge_preference = $preference,
                                    judge_rationale = $rationale,
                                    created_at = time::now()
                                """,
                                {
                                    "product": request.product_id,
                                    "task_id": str(task_id),
                                    "discipline": classification.get("discipline", ""),
                                    "depth": _ab_depth,
                                    "preference": _ab_result["judge_preference"],
                                    "rationale": _ab_result["judge_rationale"],
                                },
                            )
                except Exception as _ab_err:
                    logger.warning("A/B shadow baseline failed (non-fatal): %s", _ab_err)

        # 9. Run post-task hooks (if requested)
        if request.run_post_hooks and task_id:
            hook_ctx = HookContext(
                task_id=str(task_id),
                product_id=request.product_id,
                domain_path=classification.get("domain_path", ""),
                output=pattern_result.output,
                snapshot=snapshot,
                classification=classification,
                frameworks_used=[],
                engagement_result=None,
                token_accumulator=accumulator,
                task_description=request.description,
                started_at=started_at_epoch,
            )
            await run_hooks(hook_ctx, event_bus=bus)
            clear_accumulator()

        # 9b. Write task + agent nodes to graph (best-effort dual-write)
        if task_id:
            try:
                from core.engine.graph.writer import write_task_to_graph

                await write_task_to_graph(
                    task_id=str(task_id),
                    description=request.description,
                    status=pattern_result.status,
                    output=pattern_result.output if pattern_result.status == "completed" else None,
                    feedback=None,
                    classification=classification,
                )
            except Exception:
                pass  # graph write is best-effort

        duration = int((time.monotonic() - start) * 1000)
        orchestration_active.dec()

        discipline = classification.get("discipline", "unknown")
        from core.engine.core.metrics import task_counter, task_duration

        task_counter.labels(discipline=discipline, status=pattern_result.status).inc()
        task_duration.labels(discipline=discipline).observe(duration / 1000)

        if duration > 30_000:
            logger.warning(
                "SLOW TASK: run_id=%s duration=%dms product=%s discipline=%s",
                run_id,
                duration,
                request.product_id,
                discipline,
                extra={"slow_task": True, "duration_ms": duration, "run_id": run_id},
            )

        # 10. Emit task_completed or task_failed based on pattern result
        if pattern_result.status == "failed":
            error_msg = ""
            for ar in pattern_result.agent_results or []:
                if ar.error:
                    error_msg = ar.error
                    break
            error_msg = error_msg or pattern_result.output or "Agent execution failed"

            await bus.emit(
                TaskFailed(
                    run_id=run_id,
                    product_id=request.product_id,
                    error=error_msg,
                    phase="execution",
                    duration_ms=duration,
                )
            )
        else:
            tc_event = TaskCompleted(
                run_id=run_id,
                product_id=request.product_id,
                task_id=str(task_id) if task_id else "",
                output_summary=pattern_result.output,
                duration_ms=duration,
            )
            await bus.emit(tc_event)
            await _bridge_task_completed(tc_event, classification)

        # 11. Persist events (if requested)
        if request.persist_events:
            await _persist_events(
                run_id=run_id,
                product_id=request.product_id,
                events=bus.events(),
                classification=classification,
                pattern_name=pattern_name,
                status=pattern_result.status,
                source=request.source,
                duration_ms=duration,
                task_id=str(task_id) if task_id else None,
                agent_count=len(agent_configs),
            )

        snapshot["token_usage"] = accumulator.summary()
        return OrchestrationResult(
            task_id=str(task_id) if task_id else None,
            output=pattern_result.output,
            classification=classification,
            snapshot=snapshot,
            pattern_result=pattern_result,
            events=bus.events(),
            status=pattern_result.status,
            duration_ms=duration,
        )

    except Exception as exc:
        duration = int((time.monotonic() - start) * 1000)
        orchestration_active.dec()

        error_type = type(exc).__name__
        from core.engine.core.metrics import orchestration_failures_total

        orchestration_failures_total.labels(error_type=error_type).inc()

        logger.error(
            "Orchestration failed: %s — run_id=%s duration=%dms",
            exc,
            run_id,
            duration,
            exc_info=True,
            extra={"run_id": run_id, "duration_ms": duration, "product_id": request.product_id},
        )

        try:
            from core.engine.core.error_buffer import error_buffer
            from core.engine.core.log_context import get_correlation_id

            error_buffer.record(
                source="orchestration",
                error_type=error_type,
                message=str(exc),
                cid=get_correlation_id(),
                context={
                    "run_id": run_id,
                    "product_id": request.product_id,
                    "duration_ms": duration,
                },
            )
        except Exception:
            pass

        await bus.emit(
            TaskFailed(
                run_id=run_id,
                product_id=request.product_id,
                error=str(exc),
                phase="execution",
                duration_ms=duration,
            )
        )

        # Persist failure events too
        if request.persist_events:
            await _persist_events(
                run_id=run_id,
                product_id=request.product_id,
                events=bus.events(),
                classification={},
                pattern_name="unknown",
                status="failed",
                source=request.source,
                duration_ms=duration,
                task_id=None,
                agent_count=0,
                error=str(exc),
            )

        return OrchestrationResult(
            output="",
            events=bus.events(),
            status="failed",
            error=str(exc),
            duration_ms=duration,
        )
