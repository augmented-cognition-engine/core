"""The terminal ambient hook emits cited context for repo turns and stays silent otherwise."""

from __future__ import annotations

import pytest

from ace_mcp_client.ambient_hook import run_hook

pytestmark = pytest.mark.unit


def _lens_response():
    return {
        "index_snapshot_id": "idx_abc",
        "index_generation": 1,
        "limitations": [],
        "lens": {
            "target_path": "scanner.py",
            "nodes": [{"node_id": "graph_file::scanner"}],
            "edges": [],
            "evidence": [{"anchor_id": "a1"}],
            "omissions": [],
            "degraded_reasons": [],
        },
    }


class _FakeClient:
    def __init__(self, response):
        self.response = response

    async def post(self, path, json=None):
        return self.response


@pytest.mark.asyncio
async def test_hook_emits_cited_context_for_a_repo_turn(tmp_path):
    (tmp_path / ".git").mkdir()

    out = await run_hook(
        {"prompt": "why is scanner.py built this way?", "cwd": str(tmp_path)},
        client=_FakeClient(_lens_response()),
    )

    assert "code intelligence" in out.lower()
    assert "idx_abc" in out  # provenance disclosed inline


@pytest.mark.asyncio
async def test_hook_is_silent_without_a_repo(tmp_path):
    out = await run_hook(
        {"prompt": "why is scanner.py built this way?", "cwd": str(tmp_path)},  # no .git
        client=_FakeClient(_lens_response()),
    )

    assert out == ""


@pytest.mark.asyncio
async def test_hook_is_silent_on_empty_prompt():
    out = await run_hook({"prompt": "", "cwd": "."}, client=None)

    assert out == ""
