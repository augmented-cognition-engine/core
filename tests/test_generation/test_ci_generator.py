"""Tests for CI generator: coverage threshold and template rendering."""

from core.engine.generation.ci_generator import (
    CIConfig,
    _coverage_threshold_from_score,
    _detect_available_tools,
    _render_template,
)

# ── _coverage_threshold_from_score ────────────────────────────────────────


def test_threshold_high_score_returns_80():
    assert _coverage_threshold_from_score(0.9) == 80
    assert _coverage_threshold_from_score(0.8) == 80


def test_threshold_medium_high_returns_60():
    assert _coverage_threshold_from_score(0.7) == 60
    assert _coverage_threshold_from_score(0.6) == 60


def test_threshold_medium_returns_40():
    assert _coverage_threshold_from_score(0.5) == 40
    assert _coverage_threshold_from_score(0.4) == 40


def test_threshold_low_score_returns_20():
    assert _coverage_threshold_from_score(0.0) == 20
    assert _coverage_threshold_from_score(0.39) == 20


# ── _detect_available_tools ───────────────────────────────────────────────


def test_detect_tools_returns_dict():
    tools = _detect_available_tools()
    assert isinstance(tools, dict)
    assert "semgrep" in tools
    assert "ruff" in tools
    assert "pip_audit" in tools
    assert all(isinstance(v, bool) for v in tools.values())


# ── _render_template ──────────────────────────────────────────────────────


def _python_config(target: str) -> CIConfig:
    return CIConfig(
        target=target,
        stack=["python"],
        python_version="3.12",
        test_command="pytest",
        coverage_threshold=60,
        run_security=True,
        run_quality=True,
        run_deps=False,
    )


def test_render_github_actions_has_name_and_jobs():
    content, warnings = _render_template("github_actions", _python_config("github_actions"))
    assert not warnings
    assert "name: ACE Quality Gate" in content
    assert "jobs:" in content


def test_render_github_actions_no_unrendered_jinja():
    content, _ = _render_template("github_actions", _python_config("github_actions"))
    assert "{{" not in content
    assert "{%" not in content


def test_render_github_actions_includes_coverage_threshold():
    config = _python_config("github_actions")
    config.coverage_threshold = 75
    content, _ = _render_template("github_actions", config)
    assert "75" in content


def test_render_github_actions_python_steps_present():
    content, _ = _render_template("github_actions", _python_config("github_actions"))
    assert "python" in content.lower()
    assert "pytest" in content


def test_render_github_actions_no_docker_step_when_false():
    config = _python_config("github_actions")
    config.has_docker = False
    content, _ = _render_template("github_actions", config)
    assert "docker build" not in content


def test_render_github_actions_docker_step_when_true():
    config = _python_config("github_actions")
    config.has_docker = True
    content, _ = _render_template("github_actions", config)
    assert "docker build" in content


def test_render_gitlab_ci_has_stages():
    content, warnings = _render_template("gitlab_ci", _python_config("gitlab_ci"))
    assert not warnings
    assert "stages:" in content
    assert "test" in content


def test_render_circleci_has_version():
    content, warnings = _render_template("circleci", _python_config("circleci"))
    assert not warnings
    assert "version: 2.1" in content


def test_render_unknown_target_returns_empty():
    content, warnings = _render_template("jenkins", _python_config("jenkins"))
    assert content == ""
    assert len(warnings) > 0


def test_render_node_stack_includes_node_setup():
    config = CIConfig(
        target="github_actions",
        stack=["node"],
        node_version="20",
        coverage_threshold=60,
    )
    content, _ = _render_template("github_actions", config)
    assert "node" in content.lower()
