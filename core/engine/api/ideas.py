"""REST API for idea lifecycle management."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from core.engine.core.auth import get_current_user, verify_ownership
from core.engine.core.db import parse_one, parse_rows, pool, serialize_record

logger = logging.getLogger(__name__)

router = APIRouter(tags=["ideas"])


class IdeasListResponse(BaseModel):
    ideas: list[dict] = []


class CaptureIdeaRequest(BaseModel):
    raw_input: str
    workspace_id: str | None = None


class AnswerRequest(BaseModel):
    answers: list[str]


@router.post("/ideas", status_code=201)
async def create_idea(body: CaptureIdeaRequest, user=Depends(get_current_user)):
    """Capture a new idea."""
    from core.engine.ideas.capture import capture_idea

    result = await capture_idea(
        raw_input=body.raw_input,
        user_id=user["sub"],
        product_id=user["product"],
        workspace_id=body.workspace_id,
    )
    return serialize_record(result) if isinstance(result, dict) else result


@router.get("/ideas", response_model=IdeasListResponse)
async def list_ideas(status: str | None = None, project: str | None = None, user=Depends(get_current_user)):
    """List ideas with optional status and project filters."""
    product_id = user.get("product", "")
    project_clause = ""
    if project:
        # decision:6vacauzia2jc46hpvms8 — `= (SELECT VALUE ... LIMIT 1)` returns
        # empty in SurrealDB v3 (subquery yields 1-element array, not scalar).
        project_clause = " AND project IN (SELECT VALUE id FROM project WHERE product = <record>$product AND slug = <string>$project)"
    async with pool.connection() as db:
        if status:
            result = await db.query(
                f"SELECT * FROM idea WHERE product = <record>$product AND status = $status{project_clause} ORDER BY created_at DESC",
                {"product": product_id, "status": status, "project": project},
            )
        else:
            result = await db.query(
                f"SELECT * FROM idea WHERE product = <record>$product{project_clause} ORDER BY created_at DESC",
                {"product": product_id, "project": project},
            )
        rows = parse_rows(result)
    return {"ideas": [serialize_record(r) for r in rows]}


@router.get("/ideas/{idea_id}")
async def get_idea(idea_id: str, user=Depends(get_current_user)):
    """Get idea detail with brief and connections."""
    async with pool.connection() as db:
        result = await db.query("SELECT * FROM ONLY <record>$id", {"id": idea_id})
        idea = parse_one(result)
    if not idea:
        raise HTTPException(status_code=404, detail="Idea not found")
    verify_ownership(idea, user)
    return serialize_record(idea)


@router.post("/ideas/{idea_id}/qualify")
async def qualify_idea_endpoint(idea_id: str, body: AnswerRequest | None = None, user=Depends(get_current_user)):
    """Qualify an idea — run qualification or answer questions."""
    async with pool.connection() as db:
        result = await db.query("SELECT * FROM ONLY <record>$id", {"id": idea_id})
        idea = parse_one(result)
    if not idea:
        raise HTTPException(status_code=404, detail="Idea not found")

    product_id = user.get("product", "")

    if body and body.answers:
        from core.engine.ideas.qualify import answer_qualifying_questions

        return await answer_qualifying_questions(idea_id, body.answers)

    from core.engine.ideas.qualify import qualify_idea
    from core.engine.ideas.state_machine import IdeaStateError

    try:
        return await qualify_idea(idea, product_id)
    except IdeaStateError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/ideas/{idea_id}/incubate")
async def incubate_idea_endpoint(idea_id: str, user=Depends(get_current_user)):
    """On-demand incubation (same as overnight, just synchronous)."""
    async with pool.connection() as db:
        result = await db.query("SELECT * FROM ONLY <record>$id", {"id": idea_id})
        idea = parse_one(result)
    if not idea:
        raise HTTPException(status_code=404, detail="Idea not found")

    from core.engine.ideas.incubate import incubate_idea

    return await incubate_idea(idea, user.get("product", ""))


@router.post("/ideas/{idea_id}/activate")
async def activate_idea_endpoint(idea_id: str, user=Depends(get_current_user)):
    """Activate a ready idea — creates an initiative."""
    async with pool.connection() as db:
        result = await db.query("SELECT * FROM ONLY <record>$id", {"id": idea_id})
        idea = parse_one(result)
    if not idea:
        raise HTTPException(status_code=404, detail="Idea not found")

    from core.engine.ideas.activate import activate_idea
    from core.engine.ideas.state_machine import IdeaStateError

    try:
        return await activate_idea(idea, user["sub"], user.get("product", ""))
    except IdeaStateError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.delete("/ideas/{idea_id}")
async def archive_idea(idea_id: str, user=Depends(get_current_user)):
    """Archive (soft-delete) an idea."""
    from core.engine.ideas.state_machine import IdeaStateError, transition

    async with pool.connection() as db:
        result = await db.query("SELECT status FROM ONLY <record>$id", {"id": idea_id})
        idea = parse_one(result)
    if not idea:
        raise HTTPException(status_code=404, detail="Idea not found")

    try:
        transition(idea.get("status", ""), "archived")
    except IdeaStateError as e:
        raise HTTPException(status_code=400, detail=str(e))

    async with pool.connection() as db:
        await db.query(
            "UPDATE <record>$id SET status = 'archived', archived_at = time::now()",
            {"id": idea_id},
        )
    return {"id": idea_id, "status": "archived"}


_PATCH_ALLOWED_FIELDS = {"title", "priority", "tags", "description", "raw_input"}


@router.patch("/ideas/{idea_id}")
async def patch_idea(idea_id: str, body: dict, user=Depends(get_current_user)):
    """Update idea fields. Status changes must go through the state machine."""
    product_id = user.get("product", "")

    if "status" in body:
        raise HTTPException(status_code=400, detail="Use lifecycle endpoints to change status")

    allowed = {k: v for k, v in body.items() if k in _PATCH_ALLOWED_FIELDS}
    if not allowed:
        raise HTTPException(status_code=400, detail="No valid fields to update")

    async with pool.connection() as db:
        result = await db.query(
            "SELECT * FROM <record>$id WHERE product = <record>$product",
            {"id": idea_id, "product": product_id},
        )
        idea = parse_one(result)
        if not idea:
            raise HTTPException(status_code=404, detail="Idea not found")

        params = {"id": idea_id, **allowed}
        set_clauses = ", ".join(f"{k} = ${k}" for k in allowed)
        update_result = await db.query(
            f"UPDATE <record>$id SET {set_clauses}",
            params,
        )
        return parse_one(update_result) or {**idea, **allowed}


@router.patch("/ideas/{idea_id}/star")
async def toggle_star(idea_id: str, user=Depends(get_current_user)):
    """Toggle the starred status of an idea."""
    async with pool.connection() as db:
        # Get current starred value
        result = await db.query(
            "SELECT starred FROM ONLY <record>$id",
            {"id": idea_id},
        )
        idea = parse_one(result)
        if not idea:
            raise HTTPException(status_code=404, detail="Idea not found")
        current = idea.get("starred", False)

        # Toggle
        await db.query(
            "UPDATE <record>$id SET starred = $starred",
            {"id": idea_id, "starred": not current},
        )
        return {"id": idea_id, "starred": not current}


class PromoteRequest(BaseModel):
    target: str  # "task" | "initiative"
    title_override: str | None = None


@router.get("/ideas/{idea_id}/thread")
async def get_idea_thread(idea_id: str, user=Depends(get_current_user)):
    """Get or create a conversation thread for an idea."""
    product_id = user.get("product", "product:default")

    async with pool.connection() as db:
        # Find existing linked session
        session_result = await db.query(
            "SELECT * FROM chat_session WHERE product = <record>$product AND linked_to = $linked AND status = 'active' LIMIT 1",
            {"product": product_id, "linked": idea_id},
        )
        session_rows = parse_rows(session_result)

        if not session_rows:
            # Get idea for title context
            idea_result = await db.query("SELECT * FROM ONLY <record>$id", {"id": idea_id})
            idea_rows = parse_rows(idea_result)
            idea_title = idea_rows[0].get("title", "Idea") if idea_rows else "Idea"

            # Create linked session
            create_result = await db.query(
                """
                CREATE chat_session SET
                    workspace = workspace:default,
                    user = <record>$user,
                    title = $title,
                    linked_to = $linked,
                    linked_type = 'idea',
                    status = 'active',
                    message_count = 0,
                    created_at = time::now(),
                    last_message_at = time::now()
                """,
                {
                    "product": product_id,
                    "user": user["sub"],
                    "title": f"Developing: {idea_title[:50]}",
                    "linked": idea_id,
                },
            )
            session_rows = parse_rows(create_result)

        session = serialize_record(session_rows[0])

        # Load messages
        msg_result = await db.query(
            "SELECT * FROM chat_message WHERE session = $id ORDER BY created_at ASC",
            {"id": session["id"]},
        )
        msg_rows = parse_rows(msg_result)
        session["messages"] = [serialize_record(m) for m in msg_rows]

    return {"session": session}


@router.post("/ideas/{idea_id}/promote")
async def promote_idea(idea_id: str, body: PromoteRequest, user=Depends(get_current_user)):
    """Promote an idea to a task or initiative."""
    from core.engine.ideas.promote import promote_to_initiative, promote_to_task

    product_id = user.get("product", "product:default")

    async with pool.connection() as db:
        # Get the idea
        idea_result = await db.query("SELECT * FROM ONLY <record>$id", {"id": idea_id})
        idea_rows = parse_rows(idea_result)
        if not idea_rows:
            raise HTTPException(status_code=404, detail="Idea not found")

        idea = idea_rows[0]

        if body.target == "task":
            created_id = await promote_to_task(db, idea, product_id, user_id=user["sub"])
        elif body.target == "initiative":
            created_id = await promote_to_initiative(db, idea, product_id, user_id=user["sub"])
        else:
            raise HTTPException(status_code=400, detail=f"Invalid target: {body.target}")

    return {"created_id": created_id, "target": body.target, "idea_id": idea_id}


# ---------------------------------------------------------------------------
# Spec / plan generation & approval endpoints
# ---------------------------------------------------------------------------


@router.post("/ideas/{idea_id}/generate-spec")
async def generate_spec_endpoint(idea_id: str, user=Depends(get_current_user)):
    """Generate a spec from a ready idea. Transitions: ready -> speccing -> spec_review."""
    product_id = user.get("product", "")

    async with pool.connection() as db:
        result = await db.query("SELECT * FROM <record>$id", {"id": idea_id})
        idea = parse_one(result)
        if not idea:
            raise HTTPException(status_code=404, detail="Idea not found")

    from core.engine.ideas.state_machine import IdeaStateError, transition

    try:
        transition(idea["status"], "speccing")
    except IdeaStateError:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot generate spec from state '{idea['status']}'",
        )

    # Transition to speccing
    async with pool.connection() as db:
        await db.query(
            "UPDATE <record>$id SET status = 'speccing', speccing_at = time::now()",
            {"id": idea_id},
        )

    # Generate spec
    from core.engine.product.spec_generator import SpecGenerator

    sg = SpecGenerator(pool)
    spec = await sg.from_idea(idea, product_id)

    # Transition to spec_review, link spec
    spec_id = str(spec.get("id", ""))
    async with pool.connection() as db:
        await db.query(
            "UPDATE <record>$id SET status = 'spec_review', spec_id = $spec_id, spec_review_at = time::now()",
            {"id": idea_id, "spec_id": spec_id},
        )

    # Evaluate gate — auto-approve if low risk
    from core.engine.pm.gate_engine import GateEngine

    ge = GateEngine(pool)
    risk = await ge.evaluate_gate("idea", idea_id, "speccing", "spec_review", product_id)
    if risk.get("auto_approve"):
        await ge.auto_approve_gate("idea", idea_id, "spec_review", risk, product_id)
    else:
        from core.engine.events.bus import bus

        await bus.emit(
            "gate.pending",
            {
                "entity_type": "idea",
                "entity_id": idea_id,
                "gate_state": "spec_review",
                "product_id": product_id,
            },
        )

    return {"spec": spec, "risk": risk, "idea_id": idea_id}


@router.post("/ideas/{idea_id}/approve-spec")
async def approve_spec_endpoint(idea_id: str, user=Depends(get_current_user)):
    """Approve idea spec. Transitions: spec_review -> planned."""
    product_id = user.get("product", "")
    user_id = user.get("sub", "user:default")

    from core.engine.pm.gate_engine import GateEngine

    ge = GateEngine(pool)
    result = await ge.approve_gate("idea", idea_id, "spec_review", "Spec approved", product_id, user_id)
    return result


@router.post("/ideas/{idea_id}/generate-plan")
async def generate_plan_endpoint(idea_id: str, user=Depends(get_current_user)):
    """Generate a plan from an approved spec. Transitions: planned -> plan_review."""
    product_id = user.get("product", "")

    async with pool.connection() as db:
        result = await db.query("SELECT * FROM <record>$id", {"id": idea_id})
        idea = parse_one(result)
        if not idea:
            raise HTTPException(status_code=404, detail="Idea not found")

    if idea.get("status") != "planned":
        raise HTTPException(
            status_code=400,
            detail=f"Cannot generate plan from state '{idea['status']}'",
        )

    spec_id = str(idea.get("spec_id", ""))
    if not spec_id:
        raise HTTPException(status_code=400, detail="Idea has no linked spec")

    from core.engine.product.smart_decompose import SmartDecomposer

    decomposer = SmartDecomposer(pool)
    plan = await decomposer.decompose(spec_id, product_id)

    async with pool.connection() as db:
        await db.query(
            "UPDATE <record>$id SET status = 'plan_review', plan_review_at = time::now()",
            {"id": idea_id},
        )

    from core.engine.pm.gate_engine import GateEngine

    ge = GateEngine(pool)
    risk = await ge.evaluate_gate("idea", idea_id, "planned", "plan_review", product_id)
    if risk.get("auto_approve"):
        await ge.auto_approve_gate("idea", idea_id, "plan_review", risk, product_id)
    else:
        from core.engine.events.bus import bus

        await bus.emit(
            "gate.pending",
            {
                "entity_type": "idea",
                "entity_id": idea_id,
                "gate_state": "plan_review",
                "product_id": product_id,
            },
        )

    return {
        "plan": plan.to_dict() if hasattr(plan, "to_dict") else str(plan),
        "risk": risk,
    }


@router.post("/ideas/{idea_id}/approve-plan")
async def approve_plan_endpoint(idea_id: str, user=Depends(get_current_user)):
    """Approve idea plan. Transitions: plan_review -> promoted. Creates initiative."""
    product_id = user.get("product", "")
    user_id = user.get("sub", "user:default")

    from core.engine.pm.gate_engine import GateEngine

    ge = GateEngine(pool)
    result = await ge.approve_gate("idea", idea_id, "plan_review", "Plan approved", product_id, user_id)

    # After plan approval, create initiative directly
    async with pool.connection() as db:
        idea_result = await db.query("SELECT * FROM <record>$id", {"id": idea_id})
        idea = parse_one(idea_result)

    if idea:
        try:
            brief = idea.get("brief", {}) or {}
            context = f"Idea brief: {brief.get('what', '')}\nApproach: {brief.get('approach', '')}"
            async with pool.connection() as db:
                init_result = await db.query(
                    """CREATE initiative SET
                        title = $title, description = $description,
                        source = 'idea', source_idea = <record>$idea_id,
                        owner = <record>$user, context = $context,
                        status = 'planning', created_at = time::now()""",
                    {
                        "product": product_id,
                        "user": user_id,
                        "title": idea.get("title", "Untitled"),
                        "description": brief.get("what", idea.get("raw_input", "")),
                        "idea_id": idea_id,
                        "context": context,
                    },
                )
                initiative = parse_one(init_result)
                if initiative:
                    from core.engine.graph.edge_writer import create_edge

                    await create_edge("became", str(initiative["id"]), idea_id, pool=pool)
                    result["initiative"] = initiative
        except Exception as exc:
            logger.warning("Failed to create initiative from approved plan: %s", exc)

    return result
