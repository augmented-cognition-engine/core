# tests/test_api_capture.py
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from core.engine.api.main import app
from core.engine.core.auth import get_current_user


@pytest.fixture
def client():
    mock_user = {"sub": "user:test", "product": "product:test"}
    app.dependency_overrides[get_current_user] = lambda: mock_user
    yield TestClient(app)
    app.dependency_overrides.clear()


def test_sessions_endpoint_accepts_transcript(client):
    """POST /sessions accepts a transcript with auth."""
    with patch("core.engine.api.capture.CapturePipeline") as mock_pipeline:
        from unittest.mock import AsyncMock

        mock_instance = AsyncMock()
        mock_pipeline.return_value = mock_instance
        mock_instance.run = AsyncMock()

        resp = client.post(
            "/sessions",
            json={
                "transcript": "I fixed the bug by changing the config.",
            },
        )
    assert resp.status_code == 202
    assert "session_id" in resp.json()
