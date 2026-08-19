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
    (tmp_path / "scanner.py").write_text("x = 1\n")

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


# --- repository-relative file targeting (1.1 journey interop) -----------------
# The shipped 1.1 journey endpoint accepts only a canonical repository-relative
# path to an EXISTING file — never an absolute path, a directory, or ".". The
# hook must therefore derive its target from the prompt and stay silent when no
# existing repository file is named (fail-closed, like every other gate here).


class _RecordingClient:
    def __init__(self, response):
        self.response = response
        self.requests: list[dict] = []

    async def post(self, path, json=None):
        self.requests.append({"path": path, "json": json})
        return self.response


@pytest.mark.asyncio
async def test_hook_sends_a_repository_relative_file_target_never_the_cwd(tmp_path):
    (tmp_path / ".git").mkdir()
    (tmp_path / "core").mkdir()
    (tmp_path / "core" / "scanner.py").write_text("x = 1\n")
    client = _RecordingClient(_lens_response())

    out = await run_hook(
        {"prompt": "why does core/scanner.py accumulate duplicate edges?", "cwd": str(tmp_path)},
        client=client,
    )

    assert out  # fired
    sent = client.requests[0]["json"]["target_path"]
    assert sent == "core/scanner.py"
    from pathlib import Path

    assert not Path(sent).is_absolute()


@pytest.mark.asyncio
async def test_hook_is_silent_when_the_prompt_names_no_existing_repository_file(tmp_path):
    (tmp_path / ".git").mkdir()
    client = _RecordingClient(_lens_response())

    out = await run_hook(
        {"prompt": "please refactor the activation machinery to be atomic", "cwd": str(tmp_path)},
        client=client,
    )

    assert out == ""
    assert client.requests == []  # fail-closed: no journey call without a valid file target


@pytest.mark.asyncio
async def test_hook_ignores_directories_dotfiles_noise_and_escapes(tmp_path):
    (tmp_path / ".git").mkdir()
    (tmp_path / "pkg").mkdir()
    (tmp_path / "pkg" / "real.py").write_text("x = 1\n")
    client = _RecordingClient(_lens_response())

    out = await run_hook(
        {
            "prompt": "look at pkg (a directory), ../escape.py, /etc/passwd, v1.2, and then pkg/real.py",
            "cwd": str(tmp_path),
        },
        client=client,
    )

    assert out
    assert client.requests[0]["json"]["target_path"] == "pkg/real.py"


def test_derive_repository_target_normalizes_leading_dot_slash(tmp_path):
    from ace_mcp_client.ambient import derive_repository_target

    (tmp_path / "a.py").write_text("x = 1\n")
    assert derive_repository_target("fix ./a.py please", str(tmp_path)) == "a.py"
    assert derive_repository_target("nothing here", str(tmp_path)) is None
