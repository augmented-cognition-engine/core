"""
E2E JTBD tests — ACE canvas + intelligence loop, no real LLM required.

Five jobs-to-be-done covering every user-facing surface and API contract
the frontend depends on. Each test seeds its own data and is fully independent.

JTBD-1  Make a technical architecture decision
  When I'm choosing between two approaches and need structured analysis,
  I want ACE to produce a scored trade-off matrix I can act on,
  so I can commit with confidence and leave context for anyone revisiting later.

JTBD-2  Explore design options before committing
  When I have several implementation directions but no clear winner,
  I want to compare them with weighted axes in a focused design session,
  so I can pick the best fit and document the reasoning in one place.

JTBD-3  Return to the product and pick up where I left off
  When I come back after time away and need to orient fast,
  I want to see accumulated decisions, signals, briefing, and domain coverage,
  so I can identify the most important thread without digging through history.

JTBD-4  Close the loop — update a decision with what it led to
  When time has passed and a decision's outcome is clear,
  I want to annotate the original record with what actually happened,
  so future decisions can learn from this one.

JTBD-5  Map the code architecture before a risky change
  When I'm about to refactor a core module and need to quantify blast radius,
  I want a code architecture artifact with risk rating and affected file count,
  so I can plan review and rollback before touching anything.

Run:
    uv run pytest tests/canvas/test_e2e_jtbd.py -v
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from core.engine.api.main import app
from core.engine.canvas.framework_renderer import ArtifactSpec
from core.engine.core.auth import create_access_token

pytestmark = pytest.mark.e2e

PRODUCT_ID = "product:platform"


@pytest.fixture
def auth_headers() -> dict[str, str]:
    """JWT scoped to product:platform — required by auth-gated endpoints."""
    token = create_access_token({"sub": "user:test", "product": PRODUCT_ID})
    return {"Authorization": f"Bearer {token}"}


def _mock_render(artifact: ArtifactSpec):
    """Patch render_via_orchestration to return a pre-built artifact (no LLM)."""
    return patch(
        "core.engine.api.canvas.render_via_orchestration",
        new=AsyncMock(return_value=artifact),
    )


# ---------------------------------------------------------------------------
# Shared fake artifacts (one per framework kind)
# ---------------------------------------------------------------------------

TRADE_OFF_ARTIFACT = ArtifactSpec(
    shape_kind="framework_artifact",
    payload={
        "framework_kind": "trade_off_matrix",
        "title": "SurrealDB vs PostgreSQL",
        "question": "Which DB fits ACE's data model best?",
        "options": [
            {
                "name": "SurrealDB",
                "scores": {"graph_support": 9, "operational_simplicity": 7},
                "note": "Native graph traversal; single binary",
            },
            {
                "name": "PostgreSQL",
                "scores": {"graph_support": 5, "operational_simplicity": 9},
                "note": "Mature ecosystem; strong team familiarity",
            },
        ],
        "axes": [
            {"name": "graph_support", "weight": 0.55},
            {"name": "operational_simplicity", "weight": 0.45},
        ],
        "recommendation": "SurrealDB — graph traversal removes join overhead on insight-specialty edges.",
    },
)

DESIGN_OPTIONS_ARTIFACT = ArtifactSpec(
    shape_kind="framework_artifact",
    payload={
        "framework_kind": "design_options",
        "title": "Streaming transport for canvas events",
        "question": "SSE vs WebSocket vs long-poll for canvas event delivery?",
        "options": [
            {
                "name": "SSE",
                "scores": {"simplicity": 9, "browser_support": 8, "bidirectionality": 3},
                "note": "Unidirectional; trivial to proxy; no library needed",
            },
            {
                "name": "WebSocket",
                "scores": {"simplicity": 6, "browser_support": 8, "bidirectionality": 9},
                "note": "Full duplex; needed if client sends high-freq events",
            },
            {
                "name": "Long-poll",
                "scores": {"simplicity": 7, "browser_support": 10, "bidirectionality": 4},
                "note": "Works everywhere; high server overhead at scale",
            },
        ],
        "axes": [
            {"name": "simplicity", "weight": 0.4},
            {"name": "browser_support", "weight": 0.25},
            {"name": "bidirectionality", "weight": 0.35},
        ],
        "recommendation": "SSE — ACE canvas is server-push only; simplicity wins.",
    },
)

CODE_ARCH_ARTIFACT = ArtifactSpec(
    shape_kind="framework_artifact",
    payload={
        "framework_kind": "code_architecture",
        "title": "Canvas orchestration pipeline",
        "module": "core/engine/canvas/orchestrated_renderer.py",
        "nodes": [
            {"id": "n1", "label": "orchestrated_renderer", "type": "core"},
            {"id": "n2", "label": "canvas_engagement", "type": "core"},
            {"id": "n3", "label": "engagement.py", "type": "core"},
            {"id": "n4", "label": "canvas API", "type": "consumer"},
        ],
        "edges": [
            {"from": "n4", "to": "n1", "label": "calls render_via_orchestration"},
            {"from": "n1", "to": "n2", "label": "delegates engagement"},
            {"from": "n2", "to": "n3", "label": "calls _execute_single_spin"},
        ],
        "blast_radius": {
            "score": 0.72,
            "affected_files": 7,
            "risk": "medium",
        },
        "recommendation": "Extract spin execution into a canvas-specific adapter to decouple max_tokens from the shared engagement path.",
    },
)


# ---------------------------------------------------------------------------
# JTBD-1: Make a technical architecture decision
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_jtbd_make_architecture_decision(db_pool, auth_headers):
    """
    When I'm choosing between two approaches and need structured analysis,
    I want ACE to produce a scored trade-off matrix I can act on,
    so I can commit with confidence and leave context for anyone revisiting later.

    Covers: session creation, sticky placement, framework rendering,
            decision capture, decision history, timeline, session compile.
    """
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        # Open a canvas session
        sess = (
            await ac.post(
                "/canvas/sessions",
                json={"project_id": PRODUCT_ID, "title": "DB selection — SurrealDB vs PostgreSQL"},
            )
        ).json()
        sid = sess["id"]
        assert sess["title"] == "DB selection — SurrealDB vs PostgreSQL"

        # Place context stickies
        for i, text in enumerate(
            [
                "ACE stores insight→specialty graph edges; traversal must be fast",
                "Team has strong PostgreSQL experience; SurrealDB is newer but fits the data model",
            ]
        ):
            r = await ac.post(
                f"/canvas/sessions/{sid}/artifacts",
                json={
                    "shape_kind": "sticky",
                    "tldraw_shape_id": f"shape:s{i}",
                    "payload": {"text": text},
                    "x": i * 200,
                    "y": 100,
                    "author": "human",
                },
            )
            assert r.status_code == 200

        # Request a trade-off matrix (LLM mocked)
        with _mock_render(TRADE_OFF_ARTIFACT):
            fw = await ac.post(
                f"/canvas/sessions/{sid}/framework",
                json={
                    "framework_kind": "trade_off_matrix",
                    "prompt": "SurrealDB or PostgreSQL as ACE primary store?",
                    "cited_artifact_ids": [],
                },
            )
        assert fw.status_code == 200
        assert "tldraw_shape_id" in fw.json()

        # Verify the artifact was persisted with correct structure
        detail = (await ac.get(f"/canvas/sessions/{sid}")).json()
        fw_art = next((a for a in detail["artifacts"] if a["shape_kind"] == "framework_artifact"), None)
        assert fw_art is not None, "framework artifact not persisted"
        pl = fw_art["payload"]
        assert pl["framework_kind"] == "trade_off_matrix"
        assert len(pl["options"]) >= 2
        assert len(pl["axes"]) >= 2
        axis_names = {ax["name"] for ax in pl["axes"]}
        for opt in pl["options"]:
            missing = axis_names - set(opt["scores"])
            assert not missing, f"Option '{opt['name']}' missing scores for axes: {missing}"
        assert pl.get("recommendation"), "recommendation must be non-empty"

        # Record the decision
        dec = (
            await ac.post(
                f"/canvas/sessions/{sid}/decision",
                json={
                    "title": "Use SurrealDB as primary store",
                    "rationale": "Native graph traversal; single-binary simplicity for v1.",
                    "cited_artifact_ids": [fw_art["id"]],
                    "framework_kind": "trade_off_matrix",
                },
            )
        ).json()
        assert dec.get("decision_id"), "decision_id must be returned"

        # Decision appears in product history
        history = (await ac.get(f"/decisions?product={PRODUCT_ID}&limit=10", headers=auth_headers)).json()
        titles = [d["title"] for d in history.get("decisions", [])]
        assert any("SurrealDB" in t for t in titles), f"decision missing from history: {titles}"

        # Timeline reflects session events
        tl = (await ac.get(f"/canvas/sessions/{sid}/timeline")).json()
        event_types = [e.get("event_type") for e in tl.get("events", [])]
        assert "session.opened" in event_types
        assert "decision.made" in event_types

        # Compile session into an agent-executable spec
        spec = (await ac.post(f"/canvas/sessions/{sid}/compile", json={})).json()
        assert spec, "compiled spec must not be empty"


# ---------------------------------------------------------------------------
# JTBD-2: Explore design options before committing
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_jtbd_explore_design_options(db_pool, auth_headers):
    """
    When I have several implementation directions but no clear winner,
    I want to compare them with weighted axes in a focused design session,
    so I can pick the best fit and document the reasoning in one place.

    Covers: design_options framework kind, multi-option artifact structure,
            all axes present in every option's scores.
    """
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        sess = (
            await ac.post(
                "/canvas/sessions",
                json={
                    "project_id": PRODUCT_ID,
                    "title": "Canvas streaming transport — SSE vs WS vs long-poll",
                },
            )
        ).json()
        sid = sess["id"]

        with _mock_render(DESIGN_OPTIONS_ARTIFACT):
            fw = await ac.post(
                f"/canvas/sessions/{sid}/framework",
                json={
                    "framework_kind": "design_options",
                    "prompt": "Which streaming transport for canvas events?",
                    "cited_artifact_ids": [],
                },
            )
        assert fw.status_code == 200

        detail = (await ac.get(f"/canvas/sessions/{sid}")).json()
        fw_art = next((a for a in detail["artifacts"] if a["shape_kind"] == "framework_artifact"), None)
        assert fw_art is not None
        pl = fw_art["payload"]
        assert pl["framework_kind"] == "design_options"
        assert len(pl["options"]) >= 2
        assert len(pl["axes"]) >= 1
        axis_names = {ax["name"] for ax in pl["axes"]}
        for opt in pl["options"]:
            missing = axis_names - set(opt["scores"])
            assert not missing, f"Option '{opt['name']}' missing axes: {missing}"

        # Record the chosen design direction
        dec = (
            await ac.post(
                f"/canvas/sessions/{sid}/decision",
                json={
                    "title": "Use SSE for canvas event delivery",
                    "rationale": "Server-push only flow; SSE is simpler to proxy and requires no library.",
                    "cited_artifact_ids": [fw_art["id"]],
                    "framework_kind": "design_options",
                },
            )
        ).json()
        assert dec.get("decision_id")

        # Verify it appears with correct decision_type
        history = (await ac.get(f"/decisions?product={PRODUCT_ID}&limit=10", headers=auth_headers)).json()
        sse_decisions = [d for d in history.get("decisions", []) if "SSE" in d.get("title", "")]
        assert sse_decisions, "SSE design decision missing from history"
        assert sse_decisions[0].get("decision_type"), "decision_type must be set"


# ---------------------------------------------------------------------------
# JTBD-3: Return to the product and pick up where I left off
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_jtbd_return_and_orient(db_pool, auth_headers):
    """
    When I come back after time away and need to orient fast,
    I want to see accumulated decisions, signals, briefing, and domain coverage,
    so I can identify the most important thread without digging through history.

    Covers: decision history, briefing endpoint, recommendations endpoint,
            pulse endpoint, MapView revisit session creation.
    """
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        # Seed three decisions across domains
        scenarios = [
            (
                "Adopt event sourcing for the audit log",
                "architecture",
                "Immutable append-only satisfies compliance without a separate audit table.",
            ),
            (
                "Ship Intel panel as v1 intelligence surface",
                "product",
                "Briefing + signals give a useful summary without full map maturity.",
            ),
            (
                "Standardise error boundaries in React shell",
                "technical",
                "Consistent fallback UI prevents blank-screen failures on panel errors.",
            ),
        ]
        seeded_ids = []
        for title, kind, rationale in scenarios:
            s = (
                await ac.post(
                    "/canvas/sessions",
                    json={
                        "project_id": PRODUCT_ID,
                        "title": f"Decision: {title}",
                    },
                )
            ).json()
            r = (
                await ac.post(
                    f"/canvas/sessions/{s['id']}/decision",
                    json={
                        "title": title,
                        "rationale": rationale,
                        "cited_artifact_ids": [],
                        "framework_kind": kind,
                    },
                )
            ).json()
            assert r.get("decision_id"), f"Failed to seed decision: {title}"
            seeded_ids.append(r["decision_id"])

        # Decision history returns all seeded entries with required fields
        history = (await ac.get(f"/decisions?product={PRODUCT_ID}&limit=20", headers=auth_headers)).json()
        decisions = history.get("decisions", [])
        assert len(decisions) >= 3
        seeded_titles = {s[0] for s in scenarios}
        returned_titles = {d["title"] for d in decisions}
        assert seeded_titles <= returned_titles, f"Missing: {seeded_titles - returned_titles}"
        for d in decisions[:3]:
            assert d.get("id") and d.get("title") and d.get("created_at") and d.get("decision_type")

        # Briefing endpoint returns valid structure (may be null if sentinel hasn't run)
        br = await ac.get(f"/briefings/latest?product={PRODUCT_ID}", headers=auth_headers)
        assert br.status_code in (200, 404)
        if br.status_code == 200:
            b = br.json()
            assert "content" in b and "created_at" in b

        # Recommendations endpoint returns valid structure
        rr = await ac.get(f"/recommendations?product={PRODUCT_ID}&limit=6", headers=auth_headers)
        assert rr.status_code in (200, 404)
        if rr.status_code == 200:
            for r in rr.json().get("recommendations", []):
                assert r.get("id") and r.get("title")
                assert r.get("severity") in ("high", "medium", "low")

        # Pulse endpoint returns counts and domain list
        pr = await ac.get(f"/portal/pulse?product={PRODUCT_ID}", headers=auth_headers)
        assert pr.status_code in (200, 404)
        if pr.status_code == 200:
            p = pr.json()
            assert "insights" in p and "domains" in p
            assert isinstance(p["domains"], list)

        # MapView "Explore →" — create a revisit session from the most recent decision
        past = decisions[0]
        revisit_title = f"Revisiting: {past['title'][:80]}"
        rv = (
            await ac.post(
                "/canvas/sessions",
                json={
                    "project_id": PRODUCT_ID,
                    "title": revisit_title,
                },
            )
        ).json()
        assert rv.get("id"), "revisit session not created"

        sess_list = (await ac.get(f"/canvas/sessions?project_id={PRODUCT_ID}&limit=10")).json()
        assert any(s.get("title") == revisit_title for s in sess_list), "revisit session missing from session list"


# ---------------------------------------------------------------------------
# JTBD-4: Close the loop — annotate a decision with its outcome
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_jtbd_close_the_loop(db_pool, auth_headers):
    """
    When time has passed and a decision's outcome is clear,
    I want to annotate the original record with what actually happened,
    so future decisions can learn from this one.

    Covers: decision capture, PATCH /decisions/:id (what_it_led_to), persistence.
    """
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        # Seed a decision
        sess = (
            await ac.post(
                "/canvas/sessions",
                json={
                    "project_id": PRODUCT_ID,
                    "title": "Auth extraction decision",
                },
            )
        ).json()
        dec_resp = (
            await ac.post(
                f"/canvas/sessions/{sess['id']}/decision",
                json={
                    "title": "Extract auth into standalone service",
                    "rationale": "Prerequisite for partner API — third-party integrations can't use internal session cookies.",
                    "cited_artifact_ids": [],
                    "framework_kind": "architecture",
                },
            )
        ).json()
        decision_id = dec_resp["decision_id"]
        assert decision_id

        # Now close the loop: annotate with outcome
        outcome_text = (
            "Shipped in sprint 12. Partner API launched on schedule. "
            "Latency increased ~4ms per auth check — acceptable. "
            "Unexpected win: enabled SSO integration 3 months later."
        )
        patch_resp = await ac.patch(
            f"/canvas/decisions/{decision_id}",
            json={"what_it_led_to": outcome_text},
        )
        assert patch_resp.status_code == 200
        patched = patch_resp.json()
        assert patched.get("what_it_led_to") == outcome_text, (
            f"Outcome not persisted. Got: {patched.get('what_it_led_to')}"
        )


# ---------------------------------------------------------------------------
# JTBD-5: Map code architecture before a risky change
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_jtbd_map_code_architecture(db_pool, auth_headers):
    """
    When I'm about to refactor a core module and need to quantify blast radius,
    I want a code architecture artifact with risk rating and affected file count,
    so I can plan review and rollback before touching anything.

    Covers: code_architecture framework kind, blast_radius fields (score, affected_files,
            risk), node/edge graph structure, session list filtering by project_id.
    """
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        sess = (
            await ac.post(
                "/canvas/sessions",
                json={
                    "project_id": PRODUCT_ID,
                    "title": "Canvas pipeline refactor — blast radius assessment",
                },
            )
        ).json()
        sid = sess["id"]

        with _mock_render(CODE_ARCH_ARTIFACT):
            fw = await ac.post(
                f"/canvas/sessions/{sid}/framework",
                json={
                    "framework_kind": "code_architecture",
                    "prompt": "Map dependencies of engine/canvas/orchestrated_renderer.py before refactor",
                    "cited_artifact_ids": [],
                },
            )
        assert fw.status_code == 200

        detail = (await ac.get(f"/canvas/sessions/{sid}")).json()
        fw_art = next((a for a in detail["artifacts"] if a["shape_kind"] == "framework_artifact"), None)
        assert fw_art is not None
        pl = fw_art["payload"]

        assert pl["framework_kind"] == "code_architecture"
        assert len(pl.get("nodes", [])) >= 2, "must have ≥2 nodes"
        assert len(pl.get("edges", [])) >= 1, "must have ≥1 edge"

        br = pl.get("blast_radius", {})
        assert 0.0 <= br.get("score", -1) <= 1.0, "blast_radius.score must be 0–1"
        assert isinstance(br.get("affected_files"), int), "affected_files must be int"
        assert br.get("risk") in ("low", "medium", "high"), "risk must be low|medium|high"
        assert pl.get("recommendation"), "recommendation must be non-empty"

        # Every edge references valid node IDs
        node_ids = {n["id"] for n in pl["nodes"]}
        for edge in pl["edges"]:
            assert edge["from"] in node_ids, f"edge.from '{edge['from']}' not in nodes"
            assert edge["to"] in node_ids, f"edge.to '{edge['to']}' not in nodes"

        # Session appears in project-filtered list
        sess_list = (await ac.get(f"/canvas/sessions?project_id={PRODUCT_ID}&limit=20")).json()
        ids = [s["id"] for s in sess_list]
        assert sid in ids, "session missing from project-filtered list"
