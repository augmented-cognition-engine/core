"""CI/CD workflow generator.

Strategy: deterministic templates parameterized by:
- Detected stack (from graph_file.language)
- Gap profile (from capability_quality)
- Available tools (shutil.which checks at generation time)

Never ask LLM to generate YAML — hallucination risk is too high.
LLM is used only for prose sections (job descriptions, README snippets).
"""

from __future__ import annotations

import logging
import os
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

import jinja2

from core.engine.core.db import parse_rows, pool

logger = logging.getLogger(__name__)

Target = Literal["github_actions", "gitlab_ci", "circleci"]

_TEMPLATES_DIR = Path(__file__).parent / "templates"
_TEMPLATE_FILES = {
    "github_actions": "github_actions.yml.j2",
    "gitlab_ci": "gitlab_ci.yml.j2",
    "circleci": "circleci.yml.j2",
}
_DEFAULT_OUTPUT = {
    "github_actions": ".github/workflows/ace-ci.yml",
    "gitlab_ci": ".gitlab-ci.yml",
    "circleci": ".circleci/config.yml",
}


@dataclass
class CIConfig:
    """Parameterized CI configuration."""

    target: str
    stack: list[str] = field(default_factory=list)
    python_version: str = "3.12"
    node_version: str = "20"
    test_command: str = "pytest -m 'not e2e'"
    coverage_threshold: int = 60
    run_security: bool = True
    run_deps: bool = False
    run_quality: bool = False
    run_lighthouse: bool = False
    has_docker: bool = False
    has_iac: bool = False
    extra_steps: list[dict] = field(default_factory=list)


async def generate_ci(
    target: str,
    product_id: str = "product:platform",
    output_path: str | None = None,
) -> dict:
    """Generate CI/CD workflow file for the target platform.

    Steps:
    1. Detect stack from graph_file DB
    2. Load gap profile from capability_quality
    3. Detect available tools (semgrep, ruff, pip-audit)
    4. Build CIConfig
    5. Render Jinja2 template
    6. Write to output_path if provided

    Returns: {target, output_path, content, coverage_threshold, tools_included, warnings}
    """
    warnings: list[str] = []

    # 1. Stack detection
    stack = await _detect_stack(product_id)
    if not stack:
        stack = ["python"]
        warnings.append("Stack not detected from DB — defaulting to Python. Run ace_scan_repo first.")

    # 2. Gap profile for coverage threshold
    testing_score = await _get_testing_score(product_id)
    coverage_threshold = _coverage_threshold_from_score(testing_score)

    # 3. Tool availability
    tools = _detect_available_tools()

    # 4. Infrastructure detection
    has_docker = os.path.exists("Dockerfile") or os.path.exists("dockerfile")
    has_iac = any(Path(".").rglob("*.tf"))

    config = CIConfig(
        target=target,
        stack=stack,
        coverage_threshold=coverage_threshold,
        run_security=tools["semgrep"],
        run_deps=tools["pip_audit"] and "python" in stack,
        run_quality=tools["ruff"] and "python" in stack,
        has_docker=has_docker,
        has_iac=has_iac,
    )

    # 5. Render template
    content, render_warnings = _render_template(target, config)
    warnings.extend(render_warnings)

    tools_included = [t for t, available in tools.items() if available]

    # 6. Write if path provided
    out_path = output_path or _DEFAULT_OUTPUT.get(target, "ci.yml")
    if output_path and content:
        os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
        with open(output_path, "w") as f:
            f.write(content)

    return {
        "target": target,
        "output_path": out_path,
        "content": content,
        "coverage_threshold": coverage_threshold,
        "tools_included": tools_included,
        "stack": stack,
        "warnings": warnings,
    }


def _render_template(target: str, config: CIConfig) -> tuple[str, list[str]]:
    """Render the Jinja2 template for the given target and config.

    Returns: (rendered_content, warnings)
    """
    warnings: list[str] = []
    template_file = _TEMPLATE_FILES.get(target)
    if not template_file:
        return "", [f"No template for target {target!r}"]

    template_path = _TEMPLATES_DIR / template_file
    if not template_path.exists():
        return "", [f"Template file missing: {template_path}"]

    try:
        env = jinja2.Environment(
            loader=jinja2.FileSystemLoader(str(_TEMPLATES_DIR)),
            undefined=jinja2.StrictUndefined,
            trim_blocks=True,
            lstrip_blocks=True,
        )
        tmpl = env.get_template(template_file)
        rendered = tmpl.render(
            target=config.target,
            stack=config.stack,
            python_version=config.python_version,
            node_version=config.node_version,
            test_command=config.test_command,
            coverage_threshold=config.coverage_threshold,
            run_security=config.run_security,
            run_deps=config.run_deps,
            run_quality=config.run_quality,
            run_lighthouse=config.run_lighthouse,
            has_docker=config.has_docker,
            has_iac=config.has_iac,
            extra_steps=config.extra_steps,
        )
        return rendered, warnings
    except jinja2.TemplateError as exc:
        return "", [f"Template render error: {exc}"]


async def _detect_stack(product_id: str) -> list[str]:
    """Detect stack from graph_file.language in DB."""
    try:
        async with pool.connection() as db:
            rows = parse_rows(
                await db.query(
                    "SELECT language, count() AS n FROM graph_file "
                    "WHERE graph_id = 'default' GROUP BY language ORDER BY n DESC"
                )
            )
        return [r["language"] for r in rows if r.get("language") and int(r.get("n", 0)) > 2]
    except Exception as exc:
        logger.debug("Stack detection from DB failed: %s", exc)
        return []


async def _get_testing_score(product_id: str) -> float:
    """Get current testing discipline score from capability_quality."""
    try:
        async with pool.connection() as db:
            rows = parse_rows(
                await db.query(
                    "SELECT score FROM capability_quality "
                    "WHERE product = <record>$product AND discipline = 'testing' "
                    "ORDER BY assessed_at DESC LIMIT 1",
                    {"product": product_id},
                )
            )
        if rows:
            return float(rows[0].get("score") or 0.0)
    except Exception:
        pass
    return 0.6  # sane default when no data


def _coverage_threshold_from_score(testing_score: float) -> int:
    """Set coverage gate at ~90% of current score — avoids immediate failures.

    Ratchets up automatically on next generate as testing score improves.
    """
    if testing_score >= 0.8:
        return 80
    if testing_score >= 0.6:
        return 60
    if testing_score >= 0.4:
        return 40
    return 20


def _detect_available_tools() -> dict[str, bool]:
    """Check which analysis tools are installed on this machine."""
    return {
        "semgrep": bool(shutil.which("semgrep")),
        "ruff": bool(shutil.which("ruff")),
        "pip_audit": bool(shutil.which("pip-audit")),
        "bandit": bool(shutil.which("bandit")),
        "trufflehog": bool(shutil.which("trufflehog")),
    }
