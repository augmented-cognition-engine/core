"""Canvas REST + WebSocket API.

Mounts at /canvas/... — wired into the FastAPI app via include_router in
the app composition file (engine/api/main.py).
"""

from __future__ import annotations

import asyncio
import random
from typing import Any
from uuid import uuid4

from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect
from pydantic import BaseModel, Field

from core.engine.canvas import persistence
from core.engine.canvas.cogeneration import generate_contribution
from core.engine.canvas.event_protocol import (
    EVENT_AGENT_PHASE_END,
    EVENT_ARTIFACT_PLACED,
    EVENT_DECISION_MADE,
    EVENT_FRAMEWORK_COMPLETED,
    EVENT_PARTICIPANT_STATE_CHANGED,
    EVENT_SESSION_OPENED,
    AgentPhaseEndPayload,
    ArtifactPlacedPayload,
    DecisionMadePayload,
    FrameworkCompletedPayload,
    ParticipantStateChangedPayload,
    SessionOpenedPayload,
)
from core.engine.canvas.intent_router import ResponseType, route
from core.engine.canvas.ledger_bridge import bridge_decision_to_ledger
from core.engine.canvas.models import ParticipantKind, ShapeKind
from core.engine.canvas.orchestrated_renderer import render_via_orchestration
from core.engine.canvas.surface_adapter import CanvasSurfaceAdapter
from core.engine.cognition.composer import CognitiveComposer
from core.engine.cognition.reasoning_run import run_reasoning
from core.engine.orchestrator.classifier import classify_task
from core.engine.product.spec_generator import SpecGenerator

router = APIRouter(prefix="/canvas", tags=["canvas"])


async def _collect_recent_perspectives(session_id: str, limit: int = 5) -> list[dict]:
    """Return up to `limit` most-recent agent.perspective.end records for the session.

    Used by record_decision to attach lineage. Returns [] if no perspective
    events have been logged (e.g., reactive-mode session).
    """
    from core.engine.core.db import parse_rows
    from core.engine.core.db import pool as _pool

    async with _pool.connection() as db:
        rows = parse_rows(
            await db.query(
                "SELECT payload, created_at FROM canvas_event "
                "WHERE session_id = <record>$sid AND event_type = 'agent.perspective.end' "
                "ORDER BY created_at DESC LIMIT $lim;",
                {"sid": session_id, "lim": limit},
            )
        )
    out: list[dict] = []
    for r in rows:
        p = r.get("payload") or {}
        out.append(
            {
                "archetype": p.get("archetype", ""),
                "contribution_summary": p.get("handoff", "")[:200],
                "confidence": p.get("confidence", 0.5),
            }
        )
    # Reverse so the order matches event order (oldest perspective first)
    return list(reversed(out))


class CreateSessionIn(BaseModel):
    project_id: str
    title: str


class PlaceArtifactIn(BaseModel):
    shape_kind: str
    tldraw_shape_id: str
    payload: dict[str, Any]
    x: float = 0
    y: float = 0
    author: str = "human"


class RequestFrameworkIn(BaseModel):
    framework_kind: str
    prompt: str
    cited_artifact_ids: list[str] = []


class ContributionIn(BaseModel):
    originating_thought: str = Field(default="", max_length=4000)
    recent_texts: list[str] = []


class ContributionOut(BaseModel):
    placed: bool
    tldraw_shape_id: str | None = None
    text: str | None = None
    kind: str | None = None
    relevance: float = 0.0


class RespondIn(BaseModel):
    thought: str = Field(default="", max_length=4000)
    recent_texts: list[str] = []


class RespondOut(BaseModel):
    response_type: str
    tldraw_shape_id: str | None = None
    read: str = ""


class RecordDecisionIn(BaseModel):
    title: str
    rationale: str
    cited_artifact_ids: list[str] = []
    framework_kind: str | None = None


class PatchDecisionIn(BaseModel):
    what_it_led_to: str


class PatchSessionIn(BaseModel):
    title: str


# In-process subscriber registry. v1 single-process — multi-host pubsub is v1.1.
_subscribers: dict[str, list[WebSocket]] = {}


def _slug() -> str:
    return uuid4().hex[:10]


async def _get_prior_decisions(product_id: str, limit: int = 5) -> list[str]:
    """Fetch the most recent decisions for context injection before framework render."""
    try:
        from core.engine.core.db import parse_rows
        from core.engine.core.db import pool as _pool

        async with _pool.connection() as db:
            result = await db.query(
                "SELECT title, rationale, created_at FROM decision "
                "WHERE product = <record>$pid "
                "ORDER BY created_at DESC LIMIT $lim;",
                {"pid": product_id, "lim": limit},
            )
        rows = parse_rows(result)
        return [f"• {r['title']}: {r['rationale']}" for r in rows if r.get("title") and r.get("rationale")]
    except Exception:
        return []


async def _get_forward_momentum(product_id: str, limit: int = 3) -> list[dict[str, Any]]:
    """Fetch next recommended initiatives enriched with rollout planner data."""
    try:
        from core.engine.core.db import parse_rows
        from core.engine.core.db import pool as _pool

        async with _pool.connection() as db:
            result = await db.query(
                "SELECT title, description, status FROM initiative "
                "WHERE product = <record>$pid "
                "AND status IN ['ready', 'planning'] "
                "LIMIT $lim;",
                {"pid": product_id, "lim": limit},
            )
        rows = parse_rows(result)
        items = [{"title": r.get("title", ""), "rationale": r.get("description", "")} for r in rows if r.get("title")]
        if not items:
            return []

        async def _enrich(item: dict[str, Any]) -> dict[str, Any]:
            try:
                from core.engine.foresight.planner import plan_rollout

                rollout = await plan_rollout(item["title"], product_id)
                if rollout.branches:
                    best = max(rollout.branches, key=lambda b: b.terminal_score)
                    item["terminal_score"] = round(best.terminal_score, 3)
                    item["forced_decisions"] = rollout.best_path[1:]
                    item["top_risk"] = best.top_risk
            except Exception:
                pass  # rollout fields absent — frontend renders fallback layout
            return item

        return list(await asyncio.gather(*[_enrich(it) for it in items]))
    except Exception:
        return []


async def _persist_and_broadcast(event: dict[str, Any]) -> None:
    await persistence.append_event(
        session_id=event["session_id"],
        event_type=event["event_type"],
        payload=event["payload"],
        surface=event["surface"],
    )
    await _broadcast(event["session_id"], event)


async def _broadcast(session_id: str, event: dict[str, Any]) -> None:
    for ws in list(_subscribers.get(session_id, [])):
        try:
            await ws.send_json(event)
        except Exception:
            pass  # subscriber gone; cleaned on next disconnect


@router.get("/sessions")
async def list_sessions(project_id: str | None = None, limit: int = 20) -> list[dict[str, Any]]:
    sessions = await persistence.list_sessions(project_id=project_id, limit=limit)
    return [s.model_dump() for s in sessions]


@router.post("/sessions")
async def create_session(body: CreateSessionIn) -> dict[str, Any]:
    s = await persistence.create_session(project_id=body.project_id, title=body.title)
    adapter = CanvasSurfaceAdapter(consumer=_persist_and_broadcast)
    await adapter.emit(
        session_id=s.id,
        event_type=EVENT_SESSION_OPENED,
        payload=SessionOpenedPayload(
            title=s.title,
            project_id=s.project_id,
            opener_kind="human",
        ),
    )
    return s.model_dump()


@router.post("/sessions/{session_id:path}/classify")
async def classify_session(session_id: str) -> dict[str, Any]:
    """Classify a session's title and return the canvas agent roster.

    Idempotent — repeated calls on the same session return the same composition
    (classify_task is deterministic for the same input). Called by the frontend
    on session open to materialize the AgentRoster overlay before the user
    submits their first prompt.
    """
    from core.engine.cognition.composer import CognitiveComposer
    from core.engine.orchestrator.classifier import classify_task

    s = await persistence.get_session(session_id)
    classification = await classify_task(description=s.title, product_id=s.project_id)
    composition = await CognitiveComposer().compose(classification, s.project_id)
    return {
        "discipline": classification.get("discipline", "architecture"),
        "archetypes": composition.roster,
        "specialties": classification.get("specialties") or [],
    }


@router.get("/sessions/{session_id:path}/timeline")
async def get_timeline(session_id: str) -> dict[str, Any]:
    from core.engine.core.db import parse_rows
    from core.engine.core.db import pool as _pool

    async with _pool.connection() as db:
        result = await db.query(
            "SELECT * FROM canvas_event WHERE session_id = <record>$sid ORDER BY created_at;",
            {"sid": session_id},
        )
    events = parse_rows(result)
    sess = await persistence.get_session(session_id)
    forward_momentum = await _get_forward_momentum(sess.project_id) if sess else []
    return {"events": events, "forward_momentum": forward_momentum}


class ForkReasoningIn(BaseModel):
    run_id: str
    # 0 (the canvas default) = 'fork the conclusion' — the route resolves it to the run's
    # second-to-last phase so the partner re-reasons the DECISION, not an early phase.
    checkpoint_seq: int = 0
    with_capability_lens: bool = False


def _fork_branch_out(b: dict[str, Any]) -> dict[str, Any]:
    """Map a tool fork-branch (snake_case) to the canvas JourneyForkBranch (camelCase)."""
    out: dict[str, Any] = {
        "label": b.get("label", ""),
        "lens": b.get("lens", ""),
        "score": b.get("score", 0.0),
        "conclusion": b.get("conclusion", ""),
    }
    if b.get("capability_delta_score") is not None:
        out["capabilityDeltaScore"] = b["capability_delta_score"]
    return out


@router.post("/sessions/{session_id:path}/fork")
async def fork_reasoning(session_id: str, body: ForkReasoningIn) -> dict[str, Any]:
    """Fork a logged reasoning run at a checkpoint — re-reason the tail under alternative lenses and
    compare, returning the best continuation BEFORE acting (the canvas 'paths not taken' surface).

    Computed on-demand: the fork runs N MultiPhaseExecutor passes, so it fires only when the partner
    clicks 'compare', not on every run. Returns the JourneyForkTrace shape (camelCase) the canvas
    consumes, or {error} if the run can't be reconstructed.
    """
    from core.engine.mcp.tools import ace_fork_reasoning as _fork

    sess = await persistence.get_session(session_id)
    result = await _fork(
        run_id=body.run_id,
        checkpoint_seq=body.checkpoint_seq,
        product_id=sess.project_id,
        with_capability_lens=body.with_capability_lens,
    )
    if result.get("error"):
        return {
            "error": result["error"],
            "runId": result.get("run_id"),
            "checkpointSeq": result.get("checkpoint_seq"),
        }
    return {
        "runId": result.get("run_id"),
        "checkpointSeq": result.get("checkpoint_seq"),
        "recommendation": result.get("recommendation"),
        "best": _fork_branch_out(result.get("best", {})),
        "original": _fork_branch_out(result.get("original", {})),
        "forks": [_fork_branch_out(f) for f in result.get("forks", [])],
    }


@router.get("/runs/{run_id:path}/trace")
async def get_run_trace(run_id: str) -> dict[str, Any]:
    """Replay a logged reasoning run's trace — the 'why did ACE conclude this' data, read from the
    append-only reasoning_event log (run_started → phase×N → run_complete). The design-independent
    data layer behind the Trace UI: makes ACE's reasoning legible (the partnership thesis). Returns
    {available: False} when the run has no events."""
    from core.engine.cognition import run_ledger

    events = await run_ledger.get_run_events(run_id)
    if not events:
        return {"runId": run_id, "available": False, "phases": [], "conclusion": None}

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
            "output": (e.get("payload") or {}).get("output") or "",
            "confidence": (e.get("payload") or {}).get("confidence"),
        }
        for e in events
        if e.get("event_type") == "phase"
    ]
    return {
        "runId": run_id,
        "available": True,
        "thought": sp.get("thought"),
        "discipline": sp.get("discipline"),
        "depth": sp.get("depth"),
        "metaSkills": sp.get("meta_skills") or [],
        "phases": phases,
        "conclusion": tp.get("conclusion"),
        "status": tp.get("status") or "complete",
    }


@router.get("/sessions/{session_id:path}")
async def get_session(session_id: str) -> dict[str, Any]:
    try:
        s = await persistence.get_session(session_id)
    except (ValueError, Exception) as e:
        if "not found" in str(e):
            raise HTTPException(status_code=404, detail=str(e))
        raise
    artifacts = await persistence.list_artifacts(session_id)
    return {**s.model_dump(), "artifacts": [a.model_dump() for a in artifacts]}


@router.patch("/sessions/{session_id:path}")
async def patch_session(session_id: str, body: PatchSessionIn) -> dict[str, Any]:
    s = await persistence.patch_session(session_id, title=body.title.strip()[:120])
    return s.model_dump()


@router.delete("/sessions/{session_id:path}", status_code=204)
async def delete_session(session_id: str) -> None:
    from core.engine.core.db import pool as _pool

    try:
        await persistence.get_session(session_id)
    except (ValueError, Exception):
        raise HTTPException(status_code=404, detail=f"Session {session_id!r} not found")

    async with _pool.connection() as db:
        await db.query(
            "DELETE canvas_artifact WHERE session_id = <record>$sid;",
            {"sid": session_id},
        )
        await db.query(
            "DELETE canvas_event WHERE session_id = <record>$sid;",
            {"sid": session_id},
        )
        await db.query(
            "DELETE decision WHERE canvas_session_id = <record>$sid;",
            {"sid": session_id},
        )
        await db.query(
            "DELETE <record>$sid;",
            {"sid": session_id},
        )


@router.post("/sessions/{session_id:path}/artifacts")
async def place_artifact(session_id: str, body: PlaceArtifactIn) -> dict[str, Any]:
    a = await persistence.upsert_artifact(
        session_id=session_id,
        shape_kind=ShapeKind(body.shape_kind),
        tldraw_shape_id=body.tldraw_shape_id,
        payload=body.payload,
        x=body.x,
        y=body.y,
        author=ParticipantKind(body.author),
    )
    adapter = CanvasSurfaceAdapter(consumer=_persist_and_broadcast)
    await adapter.emit(
        session_id=session_id,
        event_type=EVENT_ARTIFACT_PLACED,
        payload=ArtifactPlacedPayload(
            shape_kind=body.shape_kind,
            payload=body.payload,
            author=body.author,
            tldraw_shape_id=body.tldraw_shape_id,
            x=body.x,
            y=body.y,
        ),
    )
    return a.model_dump()


@router.post("/sessions/{session_id:path}/framework")
async def request_framework(session_id: str, body: RequestFrameworkIn) -> dict[str, Any]:
    tldraw_shape_id = f"shape:fw_{_slug()}"
    adapter = CanvasSurfaceAdapter(consumer=_persist_and_broadcast)

    # Fetch session — needed for product_id (decision context)
    sess = await persistence.get_session(session_id)

    # State: WATCHING → DRAFTING
    await adapter.emit(
        session_id=session_id,
        event_type=EVENT_PARTICIPANT_STATE_CHANGED,
        payload=ParticipantStateChangedPayload(
            participant_id=f"canvas_participant:ai_{session_id}",
            new_state="drafting",
        ),
    )

    # Resolve cited text + pull prior decision context
    artifacts = await persistence.list_artifacts(session_id)
    id_set = set(body.cited_artifact_ids)
    cited_text = [a.payload.get("text", "") for a in artifacts if a.id in id_set and isinstance(a.payload, dict)]
    prior_decisions = await _get_prior_decisions(sess.project_id)

    async def on_canvas_event(event_type: str, event_payload: dict[str, Any]) -> None:
        await adapter.emit(session_id=session_id, event_type=event_type, payload=event_payload)

    async def _reset_state() -> None:
        await adapter.emit(
            session_id=session_id,
            event_type=EVENT_PARTICIPANT_STATE_CHANGED,
            payload=ParticipantStateChangedPayload(
                participant_id=f"canvas_participant:ai_{session_id}",
                new_state="watching",
            ),
        )

    try:
        spec = await asyncio.wait_for(
            render_via_orchestration(
                kind=body.framework_kind,
                prompt=body.prompt,
                cited_text=cited_text,
                prior_decisions=prior_decisions,
                product_id=sess.project_id,
                on_canvas_event=on_canvas_event,
            ),
            timeout=90.0,
        )
    except asyncio.TimeoutError:
        await _reset_state()
        raise HTTPException(status_code=504, detail="Framework generation timed out — try again")
    except Exception:
        await _reset_state()
        raise

    # Persist artifact
    await persistence.upsert_artifact(
        session_id=session_id,
        shape_kind=ShapeKind.FRAMEWORK_ARTIFACT,
        tldraw_shape_id=tldraw_shape_id,
        payload=spec.payload,
        x=200,
        y=200,
        author=ParticipantKind.AI,
    )

    # Emit FRAMEWORK_COMPLETED (not artifact.placed — frontend upserts on this event)
    await adapter.emit(
        session_id=session_id,
        event_type=EVENT_FRAMEWORK_COMPLETED,
        payload=FrameworkCompletedPayload(
            tldraw_shape_id=tldraw_shape_id,
            shape_kind=spec.shape_kind,
            framework_kind=body.framework_kind,
            payload=spec.payload,
            reasoning_trace=spec.reasoning_trace if isinstance(spec.reasoning_trace, dict) else None,
        ),
    )

    await _reset_state()
    return {"tldraw_shape_id": tldraw_shape_id}


@router.post("/sessions/{session_id:path}/contribution")
async def request_contribution(session_id: str, body: ContributionIn) -> ContributionOut:
    """Proactive co-generation: produce <=1 grounded contribution and place it on
    the canvas via the existing artifact.placed path. Returns placed=False when
    nothing clears the relevance floor (silence beats noise)."""
    try:
        await persistence.get_session(session_id)
    except (ValueError, Exception) as e:
        if "not found" in str(e):
            raise HTTPException(status_code=404, detail=str(e))
        raise

    # Co-generation is a background heuristic — a provider error/timeout must
    # degrade to silence, never crash the request (silence beats noise).
    try:
        contribution = await asyncio.wait_for(
            generate_contribution(body.originating_thought, body.recent_texts),
            timeout=15.0,
        )
    except (asyncio.TimeoutError, Exception):
        return ContributionOut(placed=False)
    if contribution is None:
        return ContributionOut(placed=False)

    tldraw_shape_id = f"shape:cg_{_slug()}"
    payload = {"text": contribution.text, "source": "cogen", "kind": contribution.kind}
    # Scatter contributions across a bounded region so they don't stack on top of
    # each other (the endpoint is stateless, so we randomize rather than tile).
    cg_x = float(random.randint(200, 1000))
    cg_y = float(random.randint(120, 640))

    await persistence.upsert_artifact(
        session_id=session_id,
        shape_kind=ShapeKind.STICKY,
        tldraw_shape_id=tldraw_shape_id,
        payload=payload,
        x=cg_x,
        y=cg_y,
        author=ParticipantKind.AI,
    )
    adapter = CanvasSurfaceAdapter(consumer=_persist_and_broadcast)
    await adapter.emit(
        session_id=session_id,
        event_type=EVENT_ARTIFACT_PLACED,
        payload=ArtifactPlacedPayload(
            shape_kind=ShapeKind.STICKY.value,
            payload=payload,
            author=ParticipantKind.AI.value,
            tldraw_shape_id=tldraw_shape_id,
            x=cg_x,
            y=cg_y,
        ),
    )
    return ContributionOut(
        placed=True,
        tldraw_shape_id=tldraw_shape_id,
        text=contribution.text,
        kind=contribution.kind,
        relevance=contribution.relevance,
    )


async def _respond_bespoke(
    session_id: str,
    s: Any,
    thought: str,
    kind: str,
    read: str,
    adapter: Any,
) -> RespondOut:
    """Run one of the three bespoke framework paths (trade_off_matrix /
    design_options / code_architecture) via the existing render_via_orchestration
    pipeline — mirrors request_framework exactly."""
    tldraw_shape_id = f"shape:fw_{_slug()}"

    async def _on_event(event_type: str, event_payload: dict[str, Any]) -> None:
        await adapter.emit(session_id=session_id, event_type=event_type, payload=event_payload)

    spec = await render_via_orchestration(
        kind=kind,
        prompt=thought,
        cited_text=[],
        prior_decisions=None,
        product_id=s.project_id,
        on_canvas_event=_on_event,
    )

    # Build payload: merge spec.payload with framework metadata — mirror
    # request_framework which reads spec.payload (ArtifactSpec.payload field).
    payload = {**spec.payload, "framework_kind": kind, "read": read}

    await persistence.upsert_artifact(
        session_id=session_id,
        shape_kind=ShapeKind.FRAMEWORK_ARTIFACT,
        tldraw_shape_id=tldraw_shape_id,
        payload=payload,
        x=200,
        y=200,
        author=ParticipantKind.AI,
    )

    # Emit FRAMEWORK_COMPLETED — mirrors request_framework exactly:
    # spec.shape_kind (ArtifactSpec.shape_kind) + spec.reasoning_trace
    await adapter.emit(
        session_id=session_id,
        event_type=EVENT_FRAMEWORK_COMPLETED,
        payload=FrameworkCompletedPayload(
            tldraw_shape_id=tldraw_shape_id,
            shape_kind=spec.shape_kind,
            framework_kind=kind,
            payload=payload,
            reasoning_trace=spec.reasoning_trace if isinstance(spec.reasoning_trace, dict) else None,
        ),
    )

    return RespondOut(response_type=kind, tldraw_shape_id=tldraw_shape_id, read=read)


@router.post("/sessions/{session_id:path}/respond")
async def respond(session_id: str, body: RespondIn) -> RespondOut:
    """Dynamic intent router: classify the thought, route to the best-fit response,
    and (for the reasoning path) run the real multi-phase recipe while streaming
    each phase. Degrades to a sticky of the raw thought on any failure.

    The 404 guard runs OUTSIDE the degrade try/except — mirrors request_contribution.
    """
    try:
        s = await persistence.get_session(session_id)
    except (ValueError, Exception) as e:
        if "not found" in str(e):
            raise HTTPException(status_code=404, detail=str(e))
        raise

    adapter = CanvasSurfaceAdapter(consumer=_persist_and_broadcast)

    async def _place_sticky(text: str, author: str, read: str = "") -> RespondOut:
        sid = f"shape:rs_{_slug()}"
        payload = {"text": text, "source": "router", "read": read}
        participant = ParticipantKind.AI if author == "ai" else ParticipantKind.HUMAN
        await persistence.upsert_artifact(
            session_id=session_id,
            shape_kind=ShapeKind.STICKY,
            tldraw_shape_id=sid,
            payload=payload,
            x=0,
            y=0,
            author=participant,
        )
        await adapter.emit(
            session_id=session_id,
            event_type=EVENT_ARTIFACT_PLACED,
            payload=ArtifactPlacedPayload(
                shape_kind=ShapeKind.STICKY.value,
                payload=payload,
                author=participant.value,
                tldraw_shape_id=sid,
                x=0,
                y=0,
            ),
        )
        return RespondOut(response_type="sticky", tldraw_shape_id=sid, read=read)

    try:
        classification = await classify_task(body.thought, s.project_id)
        rt = route(classification)
        read = f"{classification.get('discipline', '')} · {classification.get('task_type', '')}"

        if rt is ResponseType.STICKY:
            return await _place_sticky(body.thought, "user", read)

        if rt is ResponseType.ANGLE:
            c = await generate_contribution(body.thought, body.recent_texts)
            return await _place_sticky(c.text if c else body.thought, "ai", read)

        if rt in (
            ResponseType.TRADE_OFF_MATRIX,
            ResponseType.DESIGN_OPTIONS,
            ResponseType.CODE_ARCHITECTURE,
        ):
            return await _respond_bespoke(session_id, s, body.thought, rt.value, read, adapter)

        # REASONING: run the real multi-phase recipe, streaming phases as they complete.
        composition = await CognitiveComposer().compose(classification, s.project_id)
        tldraw_shape_id = f"shape:rs_{_slug()}"

        async def _on_phase(
            idx: int,
            total: int,
            fn: str,
            output: str,
            confidence: float,
            gaps: list[str],
        ) -> None:
            await adapter.emit(
                session_id=session_id,
                event_type=EVENT_AGENT_PHASE_END,
                payload=AgentPhaseEndPayload(
                    phase_idx=idx,
                    cognitive_function=fn,
                    confidence=confidence,
                    gaps=gaps,
                ),
            )

        result = await run_reasoning(
            thought=body.thought,
            classification=classification,
            composition=composition,
            product_id=s.project_id,
            model=None,
            on_phase=_on_phase,
        )

        payload = {
            "text": result.conclusion,
            "source": "reasoning",
            "read": read,
            "framework": (composition.meta_skills or ["reasoning"])[0],
            "sections": result.phases,
        }
        await persistence.upsert_artifact(
            session_id=session_id,
            shape_kind=ShapeKind.STICKY,
            tldraw_shape_id=tldraw_shape_id,
            payload=payload,
            x=0,
            y=0,
            author=ParticipantKind.AI,
        )
        await adapter.emit(
            session_id=session_id,
            event_type=EVENT_ARTIFACT_PLACED,
            payload=ArtifactPlacedPayload(
                shape_kind="reasoning",
                payload=payload,
                author="ai",
                tldraw_shape_id=tldraw_shape_id,
                x=0,
                y=0,
            ),
        )
        return RespondOut(response_type="reasoning", tldraw_shape_id=tldraw_shape_id, read=read)

    except Exception:
        return await _place_sticky(body.thought, "user")


@router.post("/sessions/{session_id:path}/decision")
async def record_decision(session_id: str, body: RecordDecisionIn) -> dict[str, Any]:
    sess = await persistence.get_session(session_id)
    perspectives = await _collect_recent_perspectives(session_id)
    frameworks_used = [body.framework_kind] if body.framework_kind else []
    decision_id = await bridge_decision_to_ledger(
        session_id=session_id,
        product_id=sess.project_id,
        title=body.title,
        rationale=body.rationale,
        cited_artifact_ids=body.cited_artifact_ids,
        framework_kind=body.framework_kind,
        perspectives=perspectives,
        frameworks_used=frameworks_used,
    )
    adapter = CanvasSurfaceAdapter(consumer=_persist_and_broadcast)
    await adapter.emit(
        session_id=session_id,
        event_type=EVENT_DECISION_MADE,
        payload=DecisionMadePayload(
            title=body.title,
            rationale=body.rationale,
            cited_artifact_ids=body.cited_artifact_ids,
            framework_kind=body.framework_kind,
        ),
    )
    return {"decision_id": decision_id}


@router.patch("/decisions/{decision_id:path}")
async def patch_decision(decision_id: str, body: PatchDecisionIn) -> dict[str, Any]:
    from surrealdb import RecordID

    from core.engine.core.db import parse_one
    from core.engine.core.db import pool as _pool

    table, _, key = decision_id.partition(":")
    async with _pool.connection() as db:
        result = await db.query(
            "UPDATE $rid SET what_it_led_to = $val;",
            {"rid": RecordID(table, key), "val": body.what_it_led_to},
        )
    row = parse_one(result)
    if row is None:
        raise HTTPException(status_code=404, detail=f"Decision {decision_id!r} not found")
    return row


@router.delete("/decisions/{decision_id:path}", status_code=204)
async def delete_decision(decision_id: str) -> None:
    from surrealdb import RecordID

    from core.engine.core.db import parse_one
    from core.engine.core.db import pool as _pool

    table, _, key = decision_id.partition(":")
    async with _pool.connection() as db:
        result = await db.query(
            "SELECT id FROM $rid;",
            {"rid": RecordID(table, key)},
        )
    row = parse_one(result)
    if row is None:
        raise HTTPException(status_code=404, detail=f"Decision {decision_id!r} not found")

    async with _pool.connection() as db:
        await db.query("DELETE $rid;", {"rid": RecordID(table, key)})


@router.get("/decisions/{decision_id:path}/prediction")
async def get_decision_prediction(decision_id: str) -> dict[str, Any]:
    """Return the open prediction attached to a decision, plus outcome if closed."""
    from core.engine.core.db import parse_one, parse_rows
    from core.engine.core.db import pool as _pool
    from core.engine.foresight.contracts import normalize_forecast_record, normalize_resolution_record

    async with _pool.connection() as db:
        pred_result = await db.query(
            """SELECT * FROM decision_prediction
               WHERE decision = <record>$decision
               ORDER BY created_at DESC LIMIT 1""",
            {"decision": decision_id},
        )
    prediction = parse_one(pred_result)
    if prediction is None:
        raise HTTPException(status_code=404, detail="No prediction found for this decision")

    pred_id = str(prediction["id"])
    outcome = None
    if prediction.get("closed"):
        async with _pool.connection() as db:
            out_result = await db.query(
                "SELECT * FROM prediction_outcome WHERE prediction = <record>$pred LIMIT 1",
                {"pred": pred_id},
            )
        rows = parse_rows(out_result)
        outcome = rows[0] if rows else None

    prediction["contract"] = normalize_forecast_record(prediction)
    prediction["forecast_contract"] = prediction["contract"]
    if outcome is not None:
        outcome["contract"] = normalize_resolution_record(outcome)
        outcome["resolution_contract"] = outcome["contract"]

    return {"prediction": prediction, "outcome": outcome}


@router.post("/sessions/{session_id:path}/compile")
async def compile_session(session_id: str) -> dict[str, Any]:
    """Synthesize canvas decisions into an agent-executable spec.

    Collects the session title, all sticky text, and all framework
    recommendations, then calls SpecGenerator.from_request with that context.
    """
    sess = await persistence.get_session(session_id)
    artifacts = await persistence.list_artifacts(session_id)

    stickies = [
        a.payload.get("text", "")
        for a in artifacts
        if a.shape_kind.value in ("sticky", "decision_sticky", "note")
        and isinstance(a.payload, dict)
        and a.payload.get("text")
    ]
    recommendations = [
        a.payload.get("recommendation", "")
        for a in artifacts
        if a.shape_kind.value == "framework_artifact"
        and isinstance(a.payload, dict)
        and a.payload.get("recommendation")
    ]

    request_parts = [f"Decision session: {sess.title}"]
    if stickies:
        request_parts.append("Context from canvas:\n" + "\n".join(f"- {s}" for s in stickies))
    if recommendations:
        request_parts.append("Framework recommendations:\n" + "\n".join(f"- {r}" for r in recommendations))

    from core.engine.core.db import pool as _pool

    gen = SpecGenerator(_pool)
    return await gen.from_request(request="\n\n".join(request_parts), product_id=sess.project_id)


@router.websocket("/sessions/{session_id:path}/stream")
async def stream(websocket: WebSocket, session_id: str) -> None:
    await websocket.accept()
    _subscribers.setdefault(session_id, []).append(websocket)
    try:
        while True:
            # Client → server messages reserved for future affordances; v1 ignores.
            await websocket.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        subs = _subscribers.get(session_id, [])
        if websocket in subs:
            subs.remove(websocket)
