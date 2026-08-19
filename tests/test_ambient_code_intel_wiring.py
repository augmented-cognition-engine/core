"""Stage 3 of the A0 ambient trigger: wire gate + surface to the repo and the ACE HTTP client.

The end-to-end orchestrator (`ambient_context_for_turn`) is what a terminal hook calls; the journey
caller and repo-scope detection are the two adapters that make code intelligence "baked in but
gated" — active where there is a repo, dormant where there is not.
"""

from __future__ import annotations

import pytest

from ace_mcp_client.ambient import (
    ambient_context_for_turn,
    journey_via_client,
    repo_graph_in_scope,
)

pytestmark = pytest.mark.unit

_TARGET = "core/engine/scanner.py"


def _lens_response():
    return {
        "index_snapshot_id": "idx_abc",
        "index_generation": 1,
        "limitations": [],
        "lens": {
            "target_path": _TARGET,
            "nodes": [{"node_id": "graph_file::scanner"}],
            "edges": [],
            "evidence": [{"anchor_id": "a1"}],
            "omissions": [],
            "degraded_reasons": [],
        },
    }


def test_repo_graph_in_scope_true_for_git_dir(tmp_path):
    (tmp_path / ".git").mkdir()
    assert repo_graph_in_scope(str(tmp_path)) is True


def test_repo_graph_in_scope_true_for_git_file_worktree(tmp_path):
    # A linked worktree/submodule has `.git` as a file, not a directory — still in scope.
    (tmp_path / ".git").write_text("gitdir: /somewhere/.git/worktrees/wt\n")
    assert repo_graph_in_scope(str(tmp_path)) is True


def test_repo_graph_in_scope_false_without_git(tmp_path):
    # A personal-notes folder with no repo: code intelligence stays dormant.
    assert repo_graph_in_scope(str(tmp_path)) is False


class _FakeClient:
    def __init__(self, response):
        self.response = response
        self.calls: list[tuple[str, dict]] = []

    async def post(self, path, json=None):
        self.calls.append((path, json))
        return self.response


@pytest.mark.asyncio
async def test_journey_via_client_posts_expected_shape():
    client = _FakeClient(_lens_response())
    journey = journey_via_client(client)

    await journey("why is this built this way?" + "x" * 1000, "/repo")

    assert len(client.calls) == 1
    path, body = client.calls[0]
    assert path == "/v1/code-intelligence/journey"
    assert body["target_path"] == "/repo"
    assert body["receiver_ref"] == "coding-agent:provider-neutral"
    assert len(body["query"]) <= 500  # bounded to the request's length limit


@pytest.mark.asyncio
async def test_orchestrator_stays_dormant_without_a_repo():
    called = False

    async def journey(query, target):
        nonlocal called
        called = True
        return _lens_response()

    result = await ambient_context_for_turn(
        "why is scanner.py built this way?", _TARGET, journey=journey, graph_in_scope=False
    )

    assert result.answered is False
    assert called is False  # no repo → never even queries the engine


@pytest.mark.asyncio
async def test_orchestrator_surfaces_cited_context_with_a_repo():
    async def journey(query, target):
        return _lens_response()

    result = await ambient_context_for_turn(
        "why is scanner.py built this way?", _TARGET, journey=journey, graph_in_scope=True
    )

    assert result.answered is True
    assert "idx_abc" in result.provenance
