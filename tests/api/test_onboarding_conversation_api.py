"""API tests for /onboarding/conversation/* endpoints."""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient


@pytest.mark.asyncio
@pytest.mark.e2e
async def test_full_conversation_flow_via_api():
    from core.engine.api.main import app
    from core.engine.core.auth import get_current_user
    from core.engine.core.db import parse_record_id, pool

    await pool.init()
    app.dependency_overrides[get_current_user] = lambda: {"email": "api_test@example.com", "sub": "api_test"}

    product_id = None
    try:
        async with pool.connection() as db:
            await db.query("DELETE onboarding_conversation WHERE created_by = 'api_test@example.com'")

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            r = await client.post("/onboarding/conversation/start", json={"initial_prompt": "A habit tracker"})
            assert r.status_code == 200, r.text
            data = r.json()
            cid = data["conversation_id"]
            assert "opening" in data
            assert data["question"]["index"] == 2  # initial_prompt consumed Q1, so next is Q2

            r = await client.post(
                f"/onboarding/conversation/{cid}/answer", json={"question_index": 2, "answer": "ADHD adults"}
            )
            assert r.status_code == 200
            assert r.json()["next_question"]["index"] == 3

            r = await client.post(
                f"/onboarding/conversation/{cid}/answer",
                json={"question_index": 3, "answer": "MVP with 5 paying users"},
            )
            assert r.status_code == 200

            r = await client.post(
                f"/onboarding/conversation/{cid}/answer", json={"question_index": 4, "answer": "Onboarding friction"}
            )
            assert r.status_code == 200
            assert r.json().get("next_question") is None  # last answer

            r = await client.post(f"/onboarding/conversation/{cid}/complete")
            assert r.status_code == 200
            result = r.json()
            assert result["product_id"]
            assert result["voice_thread_id"]
            product_id = result["product_id"]
    finally:
        app.dependency_overrides.clear()
        async with pool.connection() as db:
            if product_id:
                pid = parse_record_id(product_id)
                await db.query("DELETE voice_thread WHERE product = $pid", {"pid": pid})
                await db.query("DELETE product_vision WHERE product = $pid", {"pid": pid})
                await db.query("DELETE $pid", {"pid": pid})
            await db.query("DELETE onboarding_conversation WHERE created_by = 'api_test@example.com'")


@pytest.mark.asyncio
@pytest.mark.e2e
async def test_get_conversation_returns_state():
    from core.engine.api.main import app
    from core.engine.core.auth import get_current_user
    from core.engine.core.db import pool

    await pool.init()
    app.dependency_overrides[get_current_user] = lambda: {"email": "get_test@example.com", "sub": "get_test"}

    try:
        async with pool.connection() as db:
            await db.query("DELETE onboarding_conversation WHERE created_by = 'get_test@example.com'")

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            start_r = await client.post("/onboarding/conversation/start", json={"initial_prompt": None})
            cid = start_r.json()["conversation_id"]
            await client.post(
                f"/onboarding/conversation/{cid}/answer", json={"question_index": 1, "answer": "thing one"}
            )

            r = await client.get(f"/onboarding/conversation/{cid}")
            assert r.status_code == 200
            data = r.json()
            assert len(data["answers"]) == 1
            assert data["next_question_index"] == 2
    finally:
        app.dependency_overrides.clear()
        async with pool.connection() as db:
            await db.query("DELETE onboarding_conversation WHERE created_by = 'get_test@example.com'")


@pytest.mark.asyncio
@pytest.mark.e2e
async def test_get_conversation_other_user_returns_404():
    """Tenant boundary: a different user must NOT be able to GET someone else's conversation.
    Returns 404 (not 403) to avoid existence-leakage."""
    from core.engine.api.main import app
    from core.engine.core.auth import get_current_user
    from core.engine.core.db import pool

    await pool.init()

    try:
        async with pool.connection() as db:
            await db.query("DELETE onboarding_conversation WHERE created_by = 'owner@example.com'")

        # Owner creates a conversation
        app.dependency_overrides[get_current_user] = lambda: {"email": "owner@example.com", "sub": "owner"}
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            start_r = await client.post("/onboarding/conversation/start", json={"initial_prompt": "owned by me"})
            cid = start_r.json()["conversation_id"]

        # Stranger tries to GET it — must be 404
        app.dependency_overrides[get_current_user] = lambda: {"email": "stranger@example.com", "sub": "stranger"}
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            r = await client.get(f"/onboarding/conversation/{cid}")
            assert r.status_code == 404, f"expected 404 for cross-tenant read, got {r.status_code}: {r.text}"
            assert r.json()["detail"] == "conversation_not_found"
    finally:
        app.dependency_overrides.clear()
        async with pool.connection() as db:
            await db.query("DELETE onboarding_conversation WHERE created_by = 'owner@example.com'")


@pytest.mark.asyncio
@pytest.mark.e2e
async def test_answer_invalid_returns_400():
    """Validation boundary: bad question_index and short answer must return 400, not 500."""
    from core.engine.api.main import app
    from core.engine.core.auth import get_current_user
    from core.engine.core.db import pool

    await pool.init()
    app.dependency_overrides[get_current_user] = lambda: {"email": "v_test@example.com", "sub": "v_test"}

    try:
        async with pool.connection() as db:
            await db.query("DELETE onboarding_conversation WHERE created_by = 'v_test@example.com'")

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            start_r = await client.post("/onboarding/conversation/start", json={"initial_prompt": None})
            cid = start_r.json()["conversation_id"]

            # Out-of-order index → 400
            r = await client.post(
                f"/onboarding/conversation/{cid}/answer",
                json={"question_index": 3, "answer": "skipped ahead"},
            )
            assert r.status_code == 400

            # Short answer → 400
            r = await client.post(
                f"/onboarding/conversation/{cid}/answer",
                json={"question_index": 1, "answer": "x"},
            )
            assert r.status_code == 400
    finally:
        app.dependency_overrides.clear()
        async with pool.connection() as db:
            await db.query("DELETE onboarding_conversation WHERE created_by = 'v_test@example.com'")


@pytest.mark.asyncio
@pytest.mark.e2e
async def test_answer_and_complete_cross_user_returns_404():
    """Tenant boundary: a different user must NOT be able to POST /answer or /complete
    on someone else's conversation. Returns 404 to avoid existence-leakage."""
    from core.engine.api.main import app
    from core.engine.core.auth import get_current_user
    from core.engine.core.db import pool

    await pool.init()

    try:
        async with pool.connection() as db:
            await db.query("DELETE onboarding_conversation WHERE created_by = 'owner2@example.com'")

        # Owner creates and partially answers a conversation
        app.dependency_overrides[get_current_user] = lambda: {"email": "owner2@example.com", "sub": "owner2"}
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            start_r = await client.post("/onboarding/conversation/start", json={"initial_prompt": "owned by me"})
            cid = start_r.json()["conversation_id"]

        # Stranger tries POST /answer — must be 404
        app.dependency_overrides[get_current_user] = lambda: {"email": "stranger2@example.com", "sub": "stranger2"}
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            r = await client.post(
                f"/onboarding/conversation/{cid}/answer",
                json={"question_index": 2, "answer": "trying to hijack"},
            )
            assert r.status_code == 404, f"expected 404 cross-user /answer, got {r.status_code}: {r.text}"
            assert r.json()["detail"] == "conversation_not_found"

            # Stranger tries POST /complete — must be 404
            r = await client.post(f"/onboarding/conversation/{cid}/complete")
            assert r.status_code == 404, f"expected 404 cross-user /complete, got {r.status_code}: {r.text}"
            assert r.json()["detail"] == "conversation_not_found"
    finally:
        app.dependency_overrides.clear()
        async with pool.connection() as db:
            await db.query("DELETE onboarding_conversation WHERE created_by = 'owner2@example.com'")


@pytest.mark.asyncio
@pytest.mark.e2e
async def test_complete_returns_product_name():
    """I3 contract: /complete MUST return `name` so the client can set the active
    product without a follow-up GET /products/{id} round-trip."""
    from core.engine.api.main import app
    from core.engine.core.auth import get_current_user
    from core.engine.core.db import parse_record_id, pool

    await pool.init()
    app.dependency_overrides[get_current_user] = lambda: {"email": "name_test@example.com", "sub": "name_test"}

    product_id = None
    try:
        async with pool.connection() as db:
            await db.query("DELETE onboarding_conversation WHERE created_by = 'name_test@example.com'")

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            r = await client.post(
                "/onboarding/conversation/start",
                json={"initial_prompt": "Habit tracker for ADHD adults"},
            )
            cid = r.json()["conversation_id"]
            for idx, ans in [(2, "ADHD adults"), (3, "MVP with 5 paying users"), (4, "Onboarding friction")]:
                r = await client.post(
                    f"/onboarding/conversation/{cid}/answer",
                    json={"question_index": idx, "answer": ans},
                )
                assert r.status_code == 200

            r = await client.post(f"/onboarding/conversation/{cid}/complete")
            assert r.status_code == 200, r.text
            result = r.json()
            assert result.get("product_id"), "missing product_id"
            assert result.get("voice_thread_id"), "missing voice_thread_id"
            assert result.get("name"), "missing `name` on /complete response (I3 sentinel)"
            assert "Habit tracker" in result["name"]
            product_id = result["product_id"]
    finally:
        app.dependency_overrides.clear()
        async with pool.connection() as db:
            if product_id:
                pid = parse_record_id(product_id)
                await db.query("DELETE voice_thread WHERE product = $pid", {"pid": pid})
                await db.query("DELETE product_vision WHERE product = $pid", {"pid": pid})
                await db.query("DELETE $pid", {"pid": pid})
            await db.query("DELETE onboarding_conversation WHERE created_by = 'name_test@example.com'")


@pytest.mark.asyncio
@pytest.mark.e2e
async def test_get_nonexistent_returns_404():
    """Not-found boundary: GET on a missing conversation_id returns 404."""
    from core.engine.api.main import app
    from core.engine.core.auth import get_current_user

    app.dependency_overrides[get_current_user] = lambda: {"email": "nf_test@example.com", "sub": "nf_test"}

    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            r = await client.get("/onboarding/conversation/onboarding_conversation:does_not_exist_999")
            assert r.status_code == 404
            assert r.json()["detail"] == "conversation_not_found"
    finally:
        app.dependency_overrides.clear()
