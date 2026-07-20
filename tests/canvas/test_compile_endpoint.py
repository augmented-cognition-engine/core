"""Tests for POST /canvas/sessions/{id}/compile."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


@pytest.mark.asyncio
async def test_compile_endpoint_calls_spec_generator_with_session_context():
    """compile endpoint must pass canvas context to SpecGenerator.from_request."""
    fake_spec = {
        "id": "spec:abc",
        "title": "Canvas decisions spec",
        "content": "# Implementation Plan\n...",
    }

    fake_session = MagicMock()
    fake_session.project_id = "product:test"
    fake_session.title = "Bootstrap vs Series A"

    fake_artifacts = [
        MagicMock(shape_kind=MagicMock(value="sticky"), payload={"text": "We need $2M runway"}),
        MagicMock(
            shape_kind=MagicMock(value="framework_artifact"),
            payload={
                "framework_kind": "trade_off_matrix",
                "recommendation": "Series A for capital access",
            },
        ),
    ]

    captured_requests = []

    class FakeSpecGen:
        async def from_request(self, request: str, product_id: str) -> dict:
            captured_requests.append({"request": request, "product_id": product_id})
            return fake_spec

    with (
        patch("core.engine.api.canvas.persistence.get_session", AsyncMock(return_value=fake_session)),
        patch("core.engine.api.canvas.persistence.list_artifacts", AsyncMock(return_value=fake_artifacts)),
        patch("core.engine.api.canvas.SpecGenerator", return_value=FakeSpecGen()),
    ):
        from core.engine.api.canvas import compile_session

        result = await compile_session("canvas_session:test")

    assert result == fake_spec
    assert len(captured_requests) == 1
    req_text = captured_requests[0]["request"]
    assert "Bootstrap vs Series A" in req_text
    assert "Series A for capital access" in req_text
    assert captured_requests[0]["product_id"] == "product:test"


@pytest.mark.asyncio
async def test_compile_includes_sticky_text():
    """Sticky text must appear in the spec request."""
    fake_session = MagicMock()
    fake_session.project_id = "product:x"
    fake_session.title = "Tech choice"

    sticky = MagicMock(shape_kind=MagicMock(value="sticky"), payload={"text": "We must support multi-tenancy"})
    framework = MagicMock(
        shape_kind=MagicMock(value="framework_artifact"),
        payload={
            "recommendation": "Go with Postgres RLS",
        },
    )

    captured = []

    class FakeGen:
        async def from_request(self, request: str, product_id: str) -> dict:
            captured.append(request)
            return {}

    with (
        patch("core.engine.api.canvas.persistence.get_session", AsyncMock(return_value=fake_session)),
        patch("core.engine.api.canvas.persistence.list_artifacts", AsyncMock(return_value=[sticky, framework])),
        patch("core.engine.api.canvas.SpecGenerator", return_value=FakeGen()),
    ):
        from core.engine.api.canvas import compile_session

        await compile_session("canvas_session:x")

    assert len(captured) == 1
    assert "We must support multi-tenancy" in captured[0]
    assert "Postgres RLS" in captured[0]
