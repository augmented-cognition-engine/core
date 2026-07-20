# tests/test_generation_engine.py
"""Tests for E3 — Generation Engine.

Covers:
- run_ci_generator: target routing, coverage gate inclusion, LLM failure
- run_deploy_generator: target routing, service detection, LLM failure
- run_docs_generator: format routing, context loading, LLM failure
- run_changelog_generator: git log parsing, decision enrichment, LLM failure
- Stack detection helpers: _infer_stack_from_capabilities, _infer_services_from_stack
- MCP tools: ace_generate_ci, ace_generate_deploy, ace_generate_docs, ace_changelog
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ── Fixtures ─────────────────────────────────────────────────────────────────


@pytest.fixture
def mock_pool():
    mock_db = AsyncMock()
    mock_db.query = AsyncMock(return_value=[])
    mock_conn = MagicMock()
    mock_conn.__aenter__ = AsyncMock(return_value=mock_db)
    mock_conn.__aexit__ = AsyncMock(return_value=False)
    mock_p = MagicMock()
    mock_p.connection.return_value = mock_conn
    return mock_p, mock_db


@pytest.fixture
def mock_llm():
    llm = AsyncMock()
    llm.complete = AsyncMock(return_value="# generated content")
    return llm


# ── Stack detection ───────────────────────────────────────────────────────────


def test_infer_stack_detects_python():
    from core.engine.product.generation_engine import _infer_stack_from_capabilities

    caps = [{"slug": "api_auth", "title": "API Auth", "category": "security"}]
    # Default when no keywords found
    result = _infer_stack_from_capabilities(caps)
    assert result == ["python"]


def test_infer_stack_detects_fastapi_and_surrealdb():
    from core.engine.product.generation_engine import _infer_stack_from_capabilities

    caps = [
        {"slug": "fastapi_router", "title": "FastAPI Router", "category": "architecture"},
        {"slug": "surrealdb_store", "title": "SurrealDB Storage", "category": "data"},
    ]
    result = _infer_stack_from_capabilities(caps)
    assert "fastapi" in result
    assert "surrealdb" in result
    assert "python" in result


def test_infer_stack_detects_nextjs():
    from core.engine.product.generation_engine import _infer_stack_from_capabilities

    caps = [{"slug": "nextjs_router", "title": "Next.js App Router", "category": "frontend"}]
    result = _infer_stack_from_capabilities(caps)
    assert "nextjs" in result


def test_infer_services_includes_api_always():
    from core.engine.product.generation_engine import _infer_services_from_stack

    result = _infer_services_from_stack(["python", "fastapi"], [])
    assert "api" in result


def test_infer_services_adds_surrealdb_when_in_stack():
    from core.engine.product.generation_engine import _infer_services_from_stack

    result = _infer_services_from_stack(["python", "fastapi", "surrealdb", "redis"], [])
    assert "surrealdb" in result
    assert "redis" in result


# ── run_ci_generator ─────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_ci_generator_returns_content(mock_llm):
    from core.engine.product.generation_engine import run_ci_generator

    with (
        patch("core.engine.product.generation_engine.get_llm", return_value=mock_llm),
        patch(
            "core.engine.product.generation_engine._load_product_context",
            return_value={
                "capabilities": [{"slug": "api", "title": "API", "category": "architecture"}],
                "gap_profile": [{"dimension": "testing", "avg_score": 0.4, "gap_count": 3}],
                "top_decisions": [],
                "services": [],
                "stack": ["python"],
            },
        ),
    ):
        result = await run_ci_generator("product:platform", target="github_actions")

    assert result["target"] == "github_actions"
    assert result["content"] == "# generated content"
    assert result["suggested_path"] == ".github/workflows/ci.yml"
    assert "error" not in result


@pytest.mark.asyncio
async def test_ci_generator_unknown_target():
    from core.engine.product.generation_engine import run_ci_generator

    result = await run_ci_generator("product:platform", target="jenkins")

    assert "error" in result
    assert result["content"] == ""


@pytest.mark.asyncio
async def test_ci_generator_coverage_gates_from_gaps(mock_llm):
    from core.engine.product.generation_engine import run_ci_generator

    low_gap = {"dimension": "security", "avg_score": 0.3, "gap_count": 5}  # blocking
    med_gap = {"dimension": "testing", "avg_score": 0.6, "gap_count": 2}  # warning

    with (
        patch("core.engine.product.generation_engine.get_llm", return_value=mock_llm),
        patch(
            "core.engine.product.generation_engine._load_product_context",
            return_value={
                "capabilities": [],
                "gap_profile": [low_gap, med_gap],
                "top_decisions": [],
                "services": [],
                "stack": [],
            },
        ),
    ):
        result = await run_ci_generator("product:platform", target="github_actions")

    # security is below 0.5, so it's a blocking gate
    assert "security" in result["coverage_gates"]
    # testing is above 0.5 (warning), not in blocking gates
    assert "testing" not in result["coverage_gates"]


@pytest.mark.asyncio
async def test_ci_generator_llm_failure_returns_error(mock_llm):
    from core.engine.product.generation_engine import run_ci_generator

    mock_llm.complete = AsyncMock(side_effect=Exception("LLM timeout"))

    with (
        patch("core.engine.product.generation_engine.get_llm", return_value=mock_llm),
        patch(
            "core.engine.product.generation_engine._load_product_context",
            return_value={
                "capabilities": [],
                "gap_profile": [],
                "top_decisions": [],
                "services": [],
                "stack": [],
            },
        ),
    ):
        result = await run_ci_generator("product:platform", target="github_actions")

    assert "error" in result
    assert result["content"] == ""


@pytest.mark.asyncio
async def test_ci_generator_all_targets(mock_llm):
    from core.engine.product.generation_engine import CI_TARGETS, run_ci_generator

    for target in CI_TARGETS:
        with (
            patch("core.engine.product.generation_engine.get_llm", return_value=mock_llm),
            patch(
                "core.engine.product.generation_engine._load_product_context",
                return_value={
                    "capabilities": [],
                    "gap_profile": [],
                    "top_decisions": [],
                    "services": [],
                    "stack": [],
                },
            ),
        ):
            result = await run_ci_generator("product:platform", target=target)
        assert result["target"] == target
        assert "suggested_path" in result


# ── run_deploy_generator ──────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_deploy_generator_returns_content(mock_llm):
    from core.engine.product.generation_engine import run_deploy_generator

    with (
        patch("core.engine.product.generation_engine.get_llm", return_value=mock_llm),
        patch(
            "core.engine.product.generation_engine._load_product_context",
            return_value={
                "capabilities": [{"slug": "surrealdb_store", "title": "SurrealDB", "category": "data"}],
                "gap_profile": [],
                "top_decisions": [],
                "services": ["api", "surrealdb"],
                "stack": ["python", "surrealdb"],
            },
        ),
    ):
        result = await run_deploy_generator("product:platform", target="docker_compose")

    assert result["target"] == "docker_compose"
    assert result["content"] == "# generated content"
    assert result["suggested_path"] == "docker-compose.yml"
    assert "api" in result["services_detected"]


@pytest.mark.asyncio
async def test_deploy_generator_unknown_target():
    from core.engine.product.generation_engine import run_deploy_generator

    result = await run_deploy_generator("product:platform", target="heroku")

    assert "error" in result
    assert result["content"] == ""


@pytest.mark.asyncio
async def test_deploy_generator_all_targets(mock_llm):
    from core.engine.product.generation_engine import DEPLOY_TARGETS, run_deploy_generator

    for target in DEPLOY_TARGETS:
        with (
            patch("core.engine.product.generation_engine.get_llm", return_value=mock_llm),
            patch(
                "core.engine.product.generation_engine._load_product_context",
                return_value={
                    "capabilities": [],
                    "gap_profile": [],
                    "top_decisions": [],
                    "services": [],
                    "stack": [],
                },
            ),
        ):
            result = await run_deploy_generator("product:platform", target=target)
        assert result["target"] == target
        assert "suggested_path" in result


# ── run_docs_generator ────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_docs_generator_onboarding_guide(mock_llm):
    from core.engine.product.generation_engine import run_docs_generator

    with (
        patch("core.engine.product.generation_engine.get_llm", return_value=mock_llm),
        patch(
            "core.engine.product.generation_engine._load_product_context",
            return_value={
                "capabilities": [{"slug": "auth", "title": "Authentication", "category": "security"}],
                "gap_profile": [],
                "top_decisions": [{"title": "Use JWT", "rationale": "Stateless auth for API"}],
                "services": [],
                "stack": ["python"],
            },
        ),
    ):
        result = await run_docs_generator("product:platform", format="onboarding_guide")

    assert result["format"] == "onboarding_guide"
    assert result["title"] == "Developer Onboarding Guide"
    assert result["content"] == "# generated content"
    assert "error" not in result


@pytest.mark.asyncio
async def test_docs_generator_mermaid(mock_llm):
    from core.engine.product.generation_engine import run_docs_generator

    with (
        patch("core.engine.product.generation_engine.get_llm", return_value=mock_llm),
        patch(
            "core.engine.product.generation_engine._load_product_context",
            return_value={
                "capabilities": [],
                "gap_profile": [],
                "top_decisions": [],
                "services": [],
                "stack": [],
            },
        ),
    ):
        result = await run_docs_generator("product:platform", format="mermaid")

    assert result["format"] == "mermaid"
    assert result["title"] == "Architecture Diagram"


@pytest.mark.asyncio
async def test_docs_generator_api_reference(mock_llm):
    from core.engine.product.generation_engine import run_docs_generator

    with (
        patch("core.engine.product.generation_engine.get_llm", return_value=mock_llm),
        patch(
            "core.engine.product.generation_engine._load_product_context",
            return_value={
                "capabilities": [],
                "gap_profile": [],
                "top_decisions": [],
                "services": [],
                "stack": [],
            },
        ),
    ):
        result = await run_docs_generator("product:platform", format="api_reference")

    assert result["format"] == "api_reference"
    assert result["title"] == "API Reference"


@pytest.mark.asyncio
async def test_docs_generator_unknown_format():
    from core.engine.product.generation_engine import run_docs_generator

    result = await run_docs_generator("product:platform", format="pdf")

    assert "error" in result
    assert result["content"] == ""


@pytest.mark.asyncio
async def test_docs_generator_llm_failure(mock_llm):
    from core.engine.product.generation_engine import run_docs_generator

    mock_llm.complete = AsyncMock(side_effect=Exception("context too long"))

    with (
        patch("core.engine.product.generation_engine.get_llm", return_value=mock_llm),
        patch(
            "core.engine.product.generation_engine._load_product_context",
            return_value={
                "capabilities": [],
                "gap_profile": [],
                "top_decisions": [],
                "services": [],
                "stack": [],
            },
        ),
    ):
        result = await run_docs_generator("product:platform", format="mermaid")

    assert "error" in result
    assert result["content"] == ""


# ── run_changelog_generator ───────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_changelog_generator_returns_content(mock_llm):
    from core.engine.product.generation_engine import run_changelog_generator

    commits = [
        {"hash": "abc1234", "date": "2026-04-10", "message": "feat: add auth"},
        {"hash": "def5678", "date": "2026-04-09", "message": "fix: token expiry"},
    ]

    with (
        patch("core.engine.product.generation_engine.get_llm", return_value=mock_llm),
        patch("core.engine.product.generation_engine._fetch_git_commits", return_value=commits),
        patch(
            "core.engine.product.generation_engine._load_recent_decisions",
            return_value=[{"title": "JWT over session", "rationale": "Stateless", "discipline": "security"}],
        ),
    ):
        result = await run_changelog_generator("product:platform", since_tag="v1.0.0")

    assert result["changelog"] == "# generated content"
    assert result["commit_count"] == 2
    assert result["decisions_linked"] == 1
    assert "error" not in result


@pytest.mark.asyncio
async def test_changelog_generator_no_commits():
    from core.engine.product.generation_engine import run_changelog_generator

    with patch("core.engine.product.generation_engine._fetch_git_commits", return_value=[]):
        result = await run_changelog_generator("product:platform")

    assert result["changelog"] == ""
    assert result["commit_count"] == 0
    assert "error" in result


@pytest.mark.asyncio
async def test_changelog_generator_llm_failure(mock_llm):
    from core.engine.product.generation_engine import run_changelog_generator

    mock_llm.complete = AsyncMock(side_effect=Exception("timeout"))

    with (
        patch("core.engine.product.generation_engine.get_llm", return_value=mock_llm),
        patch(
            "core.engine.product.generation_engine._fetch_git_commits",
            return_value=[
                {"hash": "abc1234", "date": "2026-04-10", "message": "feat: add auth"},
            ],
        ),
        patch("core.engine.product.generation_engine._load_recent_decisions", return_value=[]),
    ):
        result = await run_changelog_generator("product:platform")

    assert "error" in result
    assert result["changelog"] == ""
    assert result["commit_count"] == 1


def test_fetch_git_commits_parses_log():
    """_fetch_git_commits handles clean git log output."""
    from core.engine.product.generation_engine import _fetch_git_commits

    fake_log = "abc1234|2026-04-10|feat: add authentication\ndef5678|2026-04-09|fix: token expiry bug"

    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0, stdout=fake_log)
        commits = _fetch_git_commits("/repo", None, 50)

    assert len(commits) == 2
    assert commits[0]["hash"] == "abc1234"
    assert commits[0]["message"] == "feat: add authentication"
    assert commits[1]["hash"] == "def5678"


def test_fetch_git_commits_returns_empty_on_error():
    """_fetch_git_commits returns [] on git failure."""
    from core.engine.product.generation_engine import _fetch_git_commits

    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=128, stdout="")
        commits = _fetch_git_commits("/repo", "v1.0.0", 50)

    assert commits == []


# ── MCP tool routing ──────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_ace_generate_ci_routes_to_engine(mock_llm):
    from core.engine.mcp import tools

    with patch("core.engine.product.generation_engine.get_llm", return_value=mock_llm):
        with patch(
            "core.engine.product.generation_engine._load_product_context",
            return_value={
                "capabilities": [],
                "gap_profile": [],
                "top_decisions": [],
                "services": [],
                "stack": [],
            },
        ):
            result = await tools.ace_generate_ci(target="github_actions", product_id="product:platform")

    assert result["target"] == "github_actions"
    assert "content" in result


@pytest.mark.asyncio
async def test_ace_generate_deploy_routes_to_engine(mock_llm):
    from core.engine.mcp import tools

    with patch("core.engine.product.generation_engine.get_llm", return_value=mock_llm):
        with patch(
            "core.engine.product.generation_engine._load_product_context",
            return_value={
                "capabilities": [],
                "gap_profile": [],
                "top_decisions": [],
                "services": [],
                "stack": [],
            },
        ):
            result = await tools.ace_generate_deploy(target="docker_compose", product_id="product:platform")

    assert result["target"] == "docker_compose"
    assert "content" in result


@pytest.mark.asyncio
async def test_ace_generate_docs_routes_to_engine(mock_llm):
    from core.engine.mcp import tools

    with patch("core.engine.product.generation_engine.get_llm", return_value=mock_llm):
        with patch(
            "core.engine.product.generation_engine._load_product_context",
            return_value={
                "capabilities": [],
                "gap_profile": [],
                "top_decisions": [],
                "services": [],
                "stack": [],
            },
        ):
            result = await tools.ace_generate_docs(format="mermaid", product_id="product:platform")

    assert result["format"] == "mermaid"
    assert "content" in result


@pytest.mark.asyncio
async def test_ace_changelog_routes_to_engine(mock_llm):
    from core.engine.mcp import tools

    with (
        patch("core.engine.product.generation_engine.get_llm", return_value=mock_llm),
        patch(
            "core.engine.product.generation_engine._fetch_git_commits",
            return_value=[
                {"hash": "abc1234", "date": "2026-04-10", "message": "feat: auth"},
            ],
        ),
        patch("core.engine.product.generation_engine._load_recent_decisions", return_value=[]),
    ):
        result = await tools.ace_changelog(since_tag="v1.0.0", product_id="product:platform")

    assert "changelog" in result
    assert result["commit_count"] == 1
