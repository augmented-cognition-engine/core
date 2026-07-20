# core/engine/worker/app.py
"""ACE Worker Service — FastAPI service on port 37778.

Single consolidated worker: session intelligence + observation capture + poll loop.
All 3 hooks (ace-intelligence, ace-post-tool, ace-submit) default to this port.

Endpoints:
    POST /observe            — receive raw observation from hook, write to SurrealDB
    POST /session/message    — receive message, update session, trigger async classify
    GET  /session/context    — return cached classification + compact intelligence index
    POST /session/complete   — mark session complete
    GET  /corpus/{discipline} — query discipline knowledge agent
    GET  /health             — health check

Run:  python core/engine/worker/start.py
Port: 37778 (env: ACE_WORKER_PORT not used — port is fixed in start.py)
"""

from __future__ import annotations

import asyncio
import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware

from core.engine.core.tasks import logged_task
from core.engine.version import VERSION
from core.engine.worker.health import get_health_state
from core.engine.worker.models import (
    HarnessContext,
    MessagePayload,
    ObservationPayload,
    ObserveTurnPayload,
    SessionCompletePayload,
    SessionContext,
    SessionEndPayload,
    SignalDecisionPayload,
)

logger = logging.getLogger(__name__)

_MAX_OBSERVE_CONTENT = 10_000
_COMPRESS_EVERY = 8  # compress message buffer to rolling summary every N messages
_COMPRESS_TIMEOUT = 15.0
PRODUCT_ID = os.environ.get("ACE_PRODUCT_ID", "product:platform")

# LIVE SELECT settings
_LIVE_RECONNECT_DELAY = 5.0  # seconds between reconnect attempts on error
_LIVE_IDLE_TIMEOUT = 120.0  # reconnect if no events for 2 minutes (keepalive)


async def _live_observe_loop() -> None:
    """LIVE SELECT observation loop — replaces 1-second polling.

    SurrealDB pushes new observations immediately instead of ACE querying
    every second. Average processing latency drops from ~500ms to ~5ms.
    Eliminates ~86,400 idle DB queries per day.

    Architecture:
    - Dedicated persistent websocket connection (not from pool) so the
      subscription stays open for the worker's lifetime.
    - Drains any pending observations on each connect to fill gaps during
      downtime or reconnects.
    - Reconnects automatically on connection loss or 2-minute idle timeout
      (keepalive). Each reconnect re-drains pending observations.
    - Falls back gracefully: if LIVE SELECT unavailable, worker still starts
      and a one-time drain runs; observations will accumulate until restart.
    """
    from surrealdb import AsyncSurreal

    from core.engine.core.config import settings
    from core.engine.worker.processor import (
        dedup_insights,
        embed_new_insights,
        process_observation,
        run_poll_cycle,
    )

    logger.info("Observation LIVE SELECT starting")

    while True:
        conn: AsyncSurreal | None = None
        live_uuid = None
        try:
            conn = AsyncSurreal(settings.surreal_url)
            await conn.connect()
            await conn.signin({"username": settings.surreal_user, "password": settings.surreal_pass})
            await conn.use(settings.surreal_ns, settings.surreal_db)

            # Drain any gap that built up while disconnected / before first connect
            drained = await run_poll_cycle(PRODUCT_ID)
            if drained:
                logger.info("LIVE SELECT: drained %d pending observation(s) on connect", drained)

            live_uuid = await conn.live("observation")
            subscription = await conn.subscribe_live(live_uuid)
            logger.info("Observation LIVE SELECT active (uuid=%s)", live_uuid)

            # Idle-timeout loop: reschedule deadline on every received event so
            # the connection is declared stale only when truly silent.
            async with asyncio.timeout(_LIVE_IDLE_TIMEOUT) as timer:
                async for record in subscription:
                    timer.reschedule(asyncio.get_event_loop().time() + _LIVE_IDLE_TIMEOUT)

                    if not isinstance(record, dict) or record.get("status") != "pending":
                        continue

                    try:
                        await process_observation(record)
                        disc = record.get("domain_path") or record.get("discipline_hint", "")
                        if disc:
                            await dedup_insights(PRODUCT_ID, disc)
                        await embed_new_insights(PRODUCT_ID, limit=5)
                        logger.debug("LIVE: processed observation %s", record.get("id"))
                    except Exception as exc:
                        logger.warning("LIVE observation handler error: %s", exc)

        except asyncio.CancelledError:
            logger.info("LIVE SELECT loop cancelled")
            raise
        except TimeoutError:
            # Idle timeout — normal keepalive reconnect, not an error
            logger.debug("LIVE SELECT idle timeout — reconnecting (keepalive)")
        except Exception as exc:
            logger.warning(
                "LIVE SELECT connection error: %s — reconnecting in %.0fs",
                exc,
                _LIVE_RECONNECT_DELAY,
            )
            await asyncio.sleep(_LIVE_RECONNECT_DELAY)
        finally:
            if conn is not None:
                try:
                    if live_uuid is not None:
                        await conn.kill(live_uuid)
                    await conn.close()
                except Exception:
                    pass


@asynccontextmanager
async def lifespan(app: FastAPI):
    from core.engine.core.db import parse_rows, pool

    await pool.init()

    # Auto-seed frameworks if table is empty (prevents silent fallback sentinel)
    try:
        async with pool.connection() as db:
            rows = parse_rows(await db.query("SELECT count() AS n FROM framework GROUP ALL"))
            count = rows[0].get("n", 0) if rows else 0
        if count == 0:
            logger.info("Framework table empty — running auto-seed")
            from core.engine.cognition.seed import seed_all

            await seed_all()
            logger.info("Framework auto-seed complete")
        else:
            logger.debug("Framework table has %d entries — skip seed", count)
    except Exception as exc:
        logger.warning("Framework auto-seed check failed (non-fatal): %s", exc)

    observe_task = asyncio.create_task(_live_observe_loop())

    # File system watcher — closes the out-of-Claude-Code observation gap.
    # Watches CLAUDE_PROJECT_DIR and POSTs synthetic /observe payloads on file changes.
    from core.engine.worker.fs_watcher import run_fs_watcher

    fs_watch_task = asyncio.create_task(run_fs_watcher(product_id=PRODUCT_ID))
    logger.info("ACE Worker started (v%s) — LIVE SELECT + fs_watcher active", VERSION)
    yield
    observe_task.cancel()
    fs_watch_task.cancel()
    try:
        await observe_task
    except asyncio.CancelledError:
        pass
    try:
        await fs_watch_task
    except asyncio.CancelledError:
        pass
    await pool.close()
    logger.info("ACE Worker stopped")


app = FastAPI(title="ACE Session Intelligence Worker", version=VERSION, lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost", "http://127.0.0.1"],
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type"],
)


@app.get("/health")
async def health():
    return {"status": "ok", "version": VERSION}


@app.get("/health/status")
async def health_status():
    """Detailed pipeline health — hook activity, capture counts, synthesis status."""
    state = get_health_state()
    idle = state.idle_seconds
    return {
        "pipeline_status": state.pipeline_status,
        "hook_post_count": state.hook_post_count,
        "last_hook_post_at": state.last_hook_post_at,
        "idle_seconds": round(idle, 1) if idle is not None else None,
        "capture_count": state.capture_count,
        "last_synthesis_at": state.last_synthesis_at,
        "uptime_seconds": round(state.uptime_seconds, 1),
        "last_error": state.last_error,
        "worker_version": VERSION,
    }


@app.get("/gate/read")
async def gate_read(path: str = Query(...), product: str = Query(default=PRODUCT_ID)):
    """File Read Gate — check whether to serve an observation timeline.

    Called by the PreToolUse:Read hook before Claude reads a file.
    Returns {"action": "bypass"} or {"action": "serve_timeline", "timeline": str}.
    Fast path: idx_obs_file index makes the DB query sub-millisecond.
    """
    from core.engine.worker.gate import check_gate

    return await check_gate(path, product)


@app.post("/observe")
async def post_observe(payload: ObservationPayload):
    """Receive a raw observation from a hook and write to SurrealDB."""
    from core.engine.core.db import parse_rows, pool

    if not payload.content.strip():
        return {"error": "content required"}
    if len(payload.content) > _MAX_OBSERVE_CONTENT:
        return {"error": f"content exceeds {_MAX_OBSERVE_CONTENT:,} char limit"}
    if not (0.0 <= payload.confidence <= 1.0):
        return {"error": "confidence must be in [0.0, 1.0]"}

    try:
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
                    source = $source,
                    file_path = $file_path,
                    status = 'pending',
                    created_at = time::now()
                """,
                {
                    "product": payload.product_id,
                    "type": payload.type,
                    "content": payload.content.strip(),
                    "domain_path": payload.domain_path,
                    "confidence": payload.confidence,
                    "source": payload.source,
                    "file_path": payload.file_path,
                },
            )
            rows = parse_rows(result)
        if not rows:
            # SurrealDB reports per-statement failures (e.g. a required-field
            # violation) as an error string, not an exception; parse_rows maps
            # strings to []. Falling through here used to report "queued" for
            # a write that never happened.
            detail = result if isinstance(result, str) else "CREATE observation returned no rows"
            logger.error("Failed to write observation: %s", detail)
            get_health_state().record_error(str(detail))
            return {"error": str(detail)}
        obs_id = str(rows[0].get("id", ""))
        get_health_state().record_capture()
        return {"status": "queued", "id": obs_id}
    except Exception as exc:
        logger.error("Failed to write observation: %s", exc)
        get_health_state().record_error(str(exc))
        return {"error": str(exc)}


@app.post("/signal/decision")
async def post_signal_decision(payload: SignalDecisionPayload):
    """Promote a 'decision' ace-signal to a proper decision record.

    Called by ace-post-tool.py when it encounters type='decision' in an ace-signal block.
    Creates a decision record (with outcome tracking, edge creation, discipline routing)
    rather than just an observation — decisions are first-class PM artefacts.
    """
    if not payload.summary.strip():
        return {"error": "summary required"}

    try:
        from core.engine.product.decisions import create_decision

        decision = await create_decision(
            title=payload.summary.strip()[:200],
            decision_type=payload.decision_type,
            rationale=payload.rationale or payload.summary,
            product_id=payload.product_id,
            alternatives=[],
            source="hook:ace-signal",
            discipline_hint=payload.discipline_hint,
        )
        decision_id = str(decision.get("id", ""))
        return {"status": "created", "id": decision_id}
    except Exception as exc:
        logger.error("Failed to create decision from signal: %s", exc)
        return {"error": str(exc)}


@app.get("/decisions/recent")
async def get_recent_decisions(product_id: str = Query("product:platform"), limit: int = Query(8, ge=1, le=50)):
    """Return recent accepted decisions for use as an agent intelligence brief.

    Used by spec_lib.agent_mandate.intelligence_brief() to inject prior
    decisions into sub-agent prompts so they're not orphans.
    """
    from core.engine.core.db import parse_rows, pool

    try:
        async with pool.connection() as db:
            rows = parse_rows(
                await db.query(
                    """SELECT title, rationale, decision_type, source, created_at
                       FROM decision
                       WHERE product = <record>$product
                         AND outcome = 'accepted'
                       ORDER BY created_at DESC
                       LIMIT $limit""",
                    {"product": product_id, "limit": limit},
                )
            )
        return {
            "decisions": [
                {
                    "title": r.get("title", ""),
                    "rationale": r.get("rationale", ""),
                    "decision_type": r.get("decision_type", "decision"),
                    "source": r.get("source", ""),
                }
                for r in rows
            ]
        }
    except Exception as exc:
        logger.warning("get_recent_decisions failed: %s", exc)
        return {"decisions": []}


async def _background_recognize_turn(text: str, product_id: str, actor: str, capabilities: list[str]) -> None:
    """Run A5 classifier on a turn; if it's a high-confidence decision, persist it."""
    try:
        from core.engine.product.decisions import create_decision
        from core.engine.recognition import decision_classifier

        result = await decision_classifier.classify(
            turn_text=text,
            conversation_context="",
            capabilities=capabilities,
        )
        if not result.is_decision or result.confidence < 0.7:
            return  # Below threshold for auto-capture; UI may still surface as draft

        title = (result.extracted_title or text[:120]).strip()
        rationale = result.extracted_rationale or result.classifier_reasoning or "Detected by A5 from agent turn"
        await create_decision(
            title=title[:200],
            decision_type=result.decision_type or "direction",
            rationale=rationale,
            product_id=product_id,
            alternatives=result.extracted_alternatives,
            source=f"recognition:{actor}",
            affected_capabilities=[result.likely_affected_capability] if result.likely_affected_capability else [],
        )
        logger.info("Auto-captured decision from %s turn: %s", actor, title[:80])
    except Exception as exc:
        logger.debug("background_recognize_turn failed (non-fatal): %s", exc)


@app.post("/observe-turn")
async def post_observe_turn(payload: ObserveTurnPayload):
    """Submit a conversation turn (agent or user) to the A5 recognition classifier.

    Fire-and-forget: classification runs as a background task. High-confidence
    (>= 0.7) decisions are persisted automatically to the decision table.
    Lower-confidence detections are dropped here (the UI flow B4 surfaces them
    as drafts via the /recognition/draft path; this endpoint is for headless
    agent-turn observation where there's no UI to confirm).
    """
    if not payload.text.strip():
        return {"status": "skipped", "reason": "empty text"}
    get_health_state().record_hook_post()
    # decision:znalk48vc0rluxl1ejdg — logged_task instead of raw create_task
    # so background-task exceptions land in error_buffer + logs.
    logged_task(
        _background_recognize_turn(
            payload.text,
            payload.product_id,
            payload.actor,
            payload.capabilities,
        ),
        label="worker.recognize_turn",
    )
    return {"status": "queued"}


@app.post("/session/message")
async def post_message(payload: MessagePayload):
    """Receive a message from the hook. Fire-and-forget: queues async processing."""
    from core.engine.worker.classifier import keyword_classify
    from core.engine.worker.session import session_manager

    # Record the message; seq is this message's position (message_count).
    seq = await session_manager.on_message(payload.session_id, payload.message, payload.product_id)

    # Provisional: classify the CURRENT message instantly and persist it tagged
    # with seq, so the immediately-following GET /session/context reflects THIS
    # prompt instead of the previous one's — closing the one-turn fast-path lag.
    # The LLM refines it below (also seq-tagged), and the seq guard keeps a slow
    # refine from clobbering a newer message's classification.
    kw = keyword_classify(payload.message)
    if kw:
        await session_manager.update_classification(payload.session_id, kw, seq=seq)

    # Background: LLM classify with full session context, refining the provisional.
    # decision:znalk48vc0rluxl1ejdg — logged_task captures exceptions.
    logged_task(
        _background_classify(payload.session_id, payload.message, payload.product_id, seq=seq),
        label="worker.classify_message",
    )

    return {"status": "queued", "session_id": payload.session_id}


@app.get("/session/context")
async def get_context(session_id: str = Query(...)):
    """Return cached classification + compact intelligence index for the hook."""
    from core.engine.worker.session import session_manager

    state = await session_manager.get_or_create(session_id, "product:platform")
    cls = state.get("classification") or {}

    return SessionContext(
        session_id=session_id,
        discipline=cls.get("discipline") or state.get("current_discipline", "architecture"),
        archetype=cls.get("archetype", "executor"),
        mode=cls.get("mode") or state.get("current_mode", "reactive"),
        perspective=cls.get("perspective", "practitioner"),
        specialties=cls.get("specialties", []),
        rolling_summary=state.get("rolling_summary", ""),
        message_count=state.get("message_count", 0),
        compact_index=state.get("compact_index", ""),
    )


@app.get("/harness/context")
async def get_harness_context(
    session_id: str = Query(...),
    product_id: str = Query(default=PRODUCT_ID),
) -> HarnessContext:
    """Return voice-enriched context for harness hook rendering.

    Hooks call this instead of composing voice themselves. Deterministic,
    sub-100ms, never raises (degrades to fallback greeting on any error).
    """
    from core.engine.worker.harness import build_harness_context

    return await build_harness_context(session_id, product_id)


@app.post("/session/complete")
async def post_complete(payload: SessionCompletePayload):
    """Mark a session as complete (called by SessionEnd hook)."""
    from core.engine.worker.session import session_manager

    await session_manager.mark_complete(payload.session_id)
    return {"status": "ok", "session_id": payload.session_id}


@app.post("/session/end")
async def post_session_end(payload: SessionEndPayload):
    """Receive session end event. Fire-and-forget transcript synthesis."""
    from core.engine.worker.session import session_manager

    await session_manager.mark_complete(payload.session_id)
    # decision:znalk48vc0rluxl1ejdg — logged_task captures exceptions.
    logged_task(
        _synthesize_transcript(payload.session_id, payload.transcript_path, payload.product_id),
        label="worker.synthesize_transcript",
    )
    return {"status": "queued", "session_id": payload.session_id}


async def _synthesize_transcript(session_id: str, transcript_path: str, product_id: str) -> None:
    """Read transcript JSONL, extract decisions/learnings, write pending observations.

    Runs after session ends — no time pressure. Failures are logged and ignored.
    """
    import json as _json

    try:
        # Read transcript, extract assistant text (skip system-reminders + tool blocks)
        text_chunks: list[str] = []
        try:
            with open(transcript_path) as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        obj = _json.loads(line)
                    except Exception:
                        continue
                    if obj.get("type") != "assistant":
                        continue
                    msg = obj.get("message") or obj
                    content = msg.get("content", "")
                    if isinstance(content, str):
                        # Strip system-reminder tags
                        import re

                        content = re.sub(r"<system-reminder>.*?</system-reminder>", "", content, flags=re.DOTALL)
                        if content.strip():
                            text_chunks.append(content.strip())
                    elif isinstance(content, list):
                        for block in content:
                            if isinstance(block, dict) and block.get("type") == "text":
                                t = block.get("text", "")
                                t = re.sub(r"<system-reminder>.*?</system-reminder>", "", t, flags=re.DOTALL)
                                if t.strip():
                                    text_chunks.append(t.strip())
        except FileNotFoundError:
            logger.debug("Transcript not found: %s", transcript_path)
            return

        if not text_chunks:
            return

        # Take last ~4000 chars — enough context without flooding LLM
        combined = "\n\n---\n\n".join(text_chunks)
        excerpt = combined[-4000:] if len(combined) > 4000 else combined

        from core.engine.core.config import settings
        from core.engine.core.llm import get_llm

        prompt = (
            "Analyze this Claude Code session excerpt and extract reusable intelligence.\n\n"
            "Return a JSON object with:\n"
            '  "summary": "2-3 sentence description of what was built/fixed/decided"\n'
            '  "decisions": [{"title": str, "rationale": str}]  — architectural choices made (max 3)\n'
            '  "learnings": [str]  — reusable patterns or discoveries (max 3)\n\n'
            f"Session excerpt:\n{excerpt}\n\n"
            "JSON only, no prose:"
        )

        llm = get_llm()
        result = await asyncio.wait_for(
            llm.complete_json(prompt, model=settings.llm_budget_model),
            timeout=20.0,
        )

        # Write observations to SurrealDB
        from core.engine.core.db import pool

        async with pool.connection() as db:
            summary = str(result.get("summary", ""))[:500]
            if summary:
                await db.query(
                    """CREATE observation SET product = <record>$product,
                    observation_type = 'learning', content = $content,
                    discipline_hint = 'architecture', domain_path = 'architecture',
                    confidence = 0.7, source = 'session_end', status = 'pending',
                    created_at = time::now()""",
                    {"product": product_id, "content": f"Session summary: {summary}"},
                )

            for dec in (result.get("decisions") or [])[:3]:
                title = str(dec.get("title", ""))[:200]
                rationale = str(dec.get("rationale", ""))[:400]
                if title:
                    await db.query(
                        """CREATE observation SET product = <record>$product,
                        observation_type = 'decision', content = $content,
                        discipline_hint = 'architecture', domain_path = 'architecture',
                        confidence = 0.75, source = 'session_end', status = 'pending',
                        created_at = time::now()""",
                        {"product": product_id, "content": f"{title}: {rationale}"},
                    )

            for learning in (result.get("learnings") or [])[:3]:
                text = str(learning)[:400]
                if text:
                    await db.query(
                        """CREATE observation SET product = <record>$product,
                        observation_type = 'pattern', content = $content,
                        discipline_hint = 'architecture', domain_path = 'architecture',
                        confidence = 0.7, source = 'session_end', status = 'pending',
                        created_at = time::now()""",
                        {"product": product_id, "content": text},
                    )

        logger.info(
            "Session synthesis complete: session=%s decisions=%d learnings=%d",
            session_id,
            len(result.get("decisions") or []),
            len(result.get("learnings") or []),
        )
        get_health_state().record_synthesis()

    except asyncio.TimeoutError:
        logger.warning("Session synthesis timed out for session=%s", session_id)
        get_health_state().record_error("synthesis_timeout")
    except Exception as exc:
        logger.warning("Session synthesis failed for session=%s: %s", session_id, exc)
        get_health_state().record_error(str(exc))


async def _compress_session_buffer(session_id: str, product_id: str) -> None:
    """Compress message buffer into a rolling summary via LLM.

    Called every _COMPRESS_EVERY messages by _background_classify.
    The rolling summary is passed to the classifier on future messages,
    enabling meaningful context-aware classification across long sessions.

    Never raises — failures are logged and the buffer is left uncompressed.
    """
    from core.engine.core.db import pool
    from core.engine.core.llm import get_llm
    from core.engine.worker.session import session_manager

    try:
        ctx = await session_manager.get_or_create(session_id, product_id)
        buffer = ctx.get("message_buffer", [])
        if len(buffer) < _COMPRESS_EVERY:
            return

        prior_summary = ctx.get("rolling_summary", "")
        to_compress = buffer[:_COMPRESS_EVERY]
        messages_text = "\n".join(f"- {m[:200]}" for m in to_compress)

        prior_line = f"Prior context: {prior_summary[:300]}\n" if prior_summary else ""
        prompt = (
            f"Compress this software engineering conversation into 2-3 sentences.\n"
            f"Focus: what discipline, what decisions, what we're building.\n\n"
            f"{prior_line}"
            f"New messages:\n{messages_text}\n\n"
            f"Summary:"
        )

        from core.engine.core.config import settings

        llm = get_llm()
        raw = await asyncio.wait_for(
            llm.complete(prompt, model=settings.llm_budget_model),
            timeout=_COMPRESS_TIMEOUT,
        )
        summary = str(raw).strip()[:800]

        async with pool.connection() as db:
            await db.query(
                """
                UPDATE type::record('ace_session', $session_id) SET
                    rolling_summary = $summary,
                    message_buffer = array::slice(message_buffer, $consumed)
                """,
                {
                    "session_id": session_id,
                    "summary": summary,
                    "consumed": _COMPRESS_EVERY,
                },
            )
        logger.info("Compressed session %s buffer (%d msgs) → summary", session_id, _COMPRESS_EVERY)
    except Exception as exc:
        logger.warning("Buffer compression failed for session %s: %s", session_id, exc)


async def _background_classify(session_id: str, message: str, product_id: str, seq: int | None = None) -> None:
    """Background LLM classification with full session context.

    Runs after on_message() has already stored the message. Fetches session
    state (summary, message_count, recent decisions), classifies with full
    context, and writes the result back to SurrealDB. Available for the hook's
    NEXT GET /session/context call.

    Never raises — failures are logged and the stale/default context is kept.
    """
    from core.engine.worker.classifier import classify_with_context
    from core.engine.worker.session import session_manager

    try:
        state = await session_manager.get_or_create(session_id, product_id)
        message_count = state.get("message_count", 0)

        # Trigger buffer compression every _COMPRESS_EVERY messages
        if message_count > 0 and message_count % _COMPRESS_EVERY == 0:
            await _compress_session_buffer(session_id, product_id)
            # Re-read state to get the freshly written rolling_summary
            state = await session_manager.get_or_create(session_id, product_id)

        rolling_summary = state.get("rolling_summary", "")
        message_count = state.get("message_count", 0)

        # Fetch recent decisions from DB for context
        recent_decisions = await _fetch_recent_decisions(product_id)

        classification = await classify_with_context(
            message=message,
            session_summary=rolling_summary,
            message_count=message_count,
            recent_decisions=recent_decisions,
            product_id=product_id,
        )

        await session_manager.update_classification(session_id, classification, seq=seq)

        # Build compact intelligence index for next hook injection
        discipline = classification.get("discipline", "architecture")
        from core.engine.worker.intelligence import build_compact_index

        compact_index = await build_compact_index(
            discipline=discipline,
            session_summary=rolling_summary,
            message_count=message_count,
            product_id=product_id,
        )
        if compact_index:
            await session_manager.update_compact_index(session_id, compact_index)

        logger.debug(
            "Classified session=%s discipline=%s mode=%s depth=%d index_chars=%d",
            session_id,
            classification.get("discipline"),
            classification.get("mode"),
            classification.get("depth", 1),
            len(compact_index),
        )

    except Exception as exc:
        logger.warning("_background_classify failed for session=%s: %s", session_id, exc)


@app.get("/corpus/{discipline}")
async def get_corpus(
    discipline: str, product_id: str = Query(default="product:platform"), question: str = Query(default="")
):
    """Query the discipline knowledge agent.

    If question is provided, returns an LLM answer grounded in accumulated intelligence.
    Otherwise, returns the raw corpus for this discipline.
    """
    from core.engine.worker.knowledge import knowledge_agent

    if question:
        answer = await knowledge_agent.query(discipline, question, product_id)
        return {"discipline": discipline, "question": question, "answer": answer}

    corpus = await knowledge_agent.build_corpus(discipline, product_id)
    return {
        "discipline": discipline,
        "corpus_chars": len(corpus),
        "corpus": corpus if corpus else None,
    }


async def _fetch_recent_decisions(product_id: str) -> list[dict]:
    """Fetch the 3 most recent active decisions for context injection."""
    from core.engine.core.db import parse_rows, pool

    try:
        async with pool.connection() as db:
            result = await db.query(
                """SELECT title, decision_type, created_at
                FROM decision WHERE product = <record>$product AND status = 'active'
                ORDER BY created_at DESC LIMIT 3""",
                {"product": product_id},
            )
            return parse_rows(result)
    except Exception as exc:
        logger.debug("_fetch_recent_decisions failed: %s", exc)
        return []
