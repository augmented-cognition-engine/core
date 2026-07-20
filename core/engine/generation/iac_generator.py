"""Infrastructure-as-code generator.

Strategy: detect actual services from code graph, not generic templates.
- Scan graph_file.imports for service patterns (FastAPI, SurrealDB, Redis, etc.)
- Detect Dockerfile presence for build-able service
- Render graph-parameterized deployment manifest via Jinja2

LLM is used only for: health check paths, env var descriptions.
Template handles YAML structure.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

import jinja2

from core.engine.core.db import parse_rows, pool

logger = logging.getLogger(__name__)

Target = Literal["docker_compose", "railway", "coolify", "kamal"]

_TEMPLATES_DIR = Path(__file__).parent / "templates"
_DEFAULT_OUTPUT = {
    "docker_compose": "docker-compose.yml",
    "railway": "railway.toml",
    "coolify": "coolify.yml",
    "kamal": "config/deploy.yml",
}

_IMPORT_INDICATORS = {
    "fastapi": ("api", 8000, "http://localhost:{port}/health"),
    "flask": ("api", 5000, "http://localhost:{port}/health"),
    "django": ("api", 8000, "http://localhost:{port}/health"),
    "starlette": ("api", 8000, None),
    "surrealdb": ("surrealdb", 8000, "http://localhost:{port}/health"),
    "redis": ("redis", 6379, None),
    "sqlalchemy": ("postgres", 5432, None),
    "psycopg": ("postgres", 5432, None),
    "celery": ("worker", None, None),
    "dramatiq": ("worker", None, None),
}

_KNOWN_IMAGES = {
    "surrealdb": "surrealdb/surrealdb:latest",
    "redis": "redis:7-alpine",
    "postgres": "postgres:16-alpine",
}


@dataclass
class ServiceSpec:
    name: str
    image_or_build: str
    port: int | None = None
    environment: list[str] = field(default_factory=list)
    health_check: str | None = None
    depends_on: list[str] = field(default_factory=list)


async def generate_iac(
    target: str,
    product_id: str = "product:platform",
    output_path: str | None = None,
) -> dict:
    """Generate deployment manifest for the target platform.

    Returns: {target, output_path, content, services_detected, warnings}
    """
    warnings: list[str] = []

    services = await detect_services(".", product_id)
    if not services:
        warnings.append("No services detected from graph — run ace_scan_repo first.")
        services = [ServiceSpec(name="app", image_or_build=".", port=8000)]

    if target == "docker_compose":
        content, render_warnings = _render_docker_compose(services)
    elif target == "railway":
        content = _render_railway(services)
        render_warnings = []
    elif target in ("coolify", "kamal"):
        content = f"# {target} support coming in E3b v2\n"
        render_warnings = [f"{target} template not yet implemented."]
    else:
        return {"error": f"Unknown target {target!r}"}

    warnings.extend(render_warnings)

    out_path = output_path or _DEFAULT_OUTPUT.get(target, "deploy.yml")
    if output_path and content:
        os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
        with open(output_path, "w") as f:
            f.write(content)

    return {
        "target": target,
        "output_path": out_path,
        "content": content,
        "services_detected": [s.name for s in services],
        "warnings": warnings,
    }


async def detect_services(repo_path: str, product_id: str) -> list[ServiceSpec]:
    """Detect services from code graph imports and filesystem.

    Returns list of ServiceSpec derived from:
    - graph_file.imports → service type patterns
    - Dockerfile presence → buildable web service
    """
    detected_names: set[str] = set()
    services: list[ServiceSpec] = []

    # Detect from graph_file imports
    import_hits = await _detect_from_graph(product_id)

    for import_key, (svc_name, port, health_tmpl) in _IMPORT_INDICATORS.items():
        if import_key not in import_hits:
            continue
        if svc_name in detected_names:
            continue
        detected_names.add(svc_name)

        _is_infrastructure = svc_name in _KNOWN_IMAGES
        image_or_build = _KNOWN_IMAGES.get(svc_name, ".")

        health = health_tmpl.format(port=port) if health_tmpl and port else None

        env_vars: list[str] = []
        depends: list[str] = []

        if svc_name == "api":
            # Web service depends on detected infrastructure
            for dep_name in ("surrealdb", "redis", "postgres"):
                if dep_name in import_hits:
                    depends.append(dep_name)
                    if dep_name == "surrealdb":
                        env_vars.append("SURREAL_URL")
                    elif dep_name == "redis":
                        env_vars.append("REDIS_URL")
                    elif dep_name == "postgres":
                        env_vars.append("DATABASE_URL")
            env_vars.append("SECRET_KEY")

        services.append(
            ServiceSpec(
                name=svc_name,
                image_or_build=image_or_build,
                port=port,
                environment=env_vars,
                health_check=health,
                depends_on=depends,
            )
        )

    # If no API service but Dockerfile exists, add a generic app service
    if "api" not in detected_names and os.path.exists(os.path.join(repo_path, "Dockerfile")):
        services.insert(
            0,
            ServiceSpec(
                name="app",
                image_or_build=".",
                port=8000,
                environment=["SECRET_KEY"],
            ),
        )

    return services


async def _detect_from_graph(product_id: str) -> set[str]:
    """Query graph_file.imports to detect service indicators."""
    try:
        async with pool.connection() as db:
            rows = parse_rows(await db.query("SELECT imports FROM graph_file WHERE graph_id = 'default' LIMIT 500"))
        all_imports: set[str] = set()
        for r in rows:
            for imp in r.get("imports") or []:
                all_imports.add(str(imp).lower().split(".")[0])
        return all_imports & set(_IMPORT_INDICATORS.keys())
    except Exception as exc:
        logger.debug("_detect_from_graph failed: %s", exc)
        return set()


def _render_docker_compose(services: list[ServiceSpec]) -> tuple[str, list[str]]:
    warnings: list[str] = []
    detected_summary = ", ".join(s.name for s in services) or "no services"
    try:
        env = jinja2.Environment(
            loader=jinja2.FileSystemLoader(str(_TEMPLATES_DIR)),
            undefined=jinja2.Undefined,
            trim_blocks=True,
            lstrip_blocks=True,
        )
        tmpl = env.get_template("docker_compose.yml.j2")
        content = tmpl.render(services=services, detected_summary=detected_summary)
        return content, warnings
    except jinja2.TemplateError as exc:
        return "", [f"Template render error: {exc}"]


def _render_railway(services: list[ServiceSpec]) -> str:
    lines = ["# Generated by ace_generate_deploy — railway.toml", ""]
    for svc in services:
        lines.append("[[services]]")
        lines.append(f'name = "{svc.name}"')
        if svc.image_or_build == ".":
            lines.append('source = "."')
        else:
            lines.append(f'image = "{svc.image_or_build}"')
        if svc.port:
            lines.append(f"port = {svc.port}")
        lines.append("")
    return "\n".join(lines)
