"""Tests for IaC generator: service detection from imports and template rendering."""

from core.engine.generation.iac_generator import ServiceSpec, _render_docker_compose, _render_railway

# ── _render_docker_compose ─────────────────────────────────────────────────


def _api_service() -> ServiceSpec:
    return ServiceSpec(
        name="api",
        image_or_build=".",
        port=8000,
        environment=["SECRET_KEY", "DATABASE_URL"],
        depends_on=["postgres"],
    )


def _db_service() -> ServiceSpec:
    return ServiceSpec(
        name="postgres",
        image_or_build="postgres:16-alpine",
        port=5432,
    )


def test_render_docker_compose_has_services_key():
    content, warnings = _render_docker_compose([_api_service()])
    assert "services:" in content
    assert not warnings


def test_render_docker_compose_includes_service_name():
    content, _ = _render_docker_compose([_api_service()])
    assert "api:" in content


def test_render_docker_compose_build_dot_for_local():
    content, _ = _render_docker_compose([_api_service()])
    assert "build: ." in content


def test_render_docker_compose_image_for_infrastructure():
    content, _ = _render_docker_compose([_db_service()])
    assert "postgres:16-alpine" in content


def test_render_docker_compose_port_present():
    content, _ = _render_docker_compose([_api_service()])
    assert "8000" in content


def test_render_docker_compose_multiple_services():
    content, _ = _render_docker_compose([_api_service(), _db_service()])
    assert "api:" in content
    assert "postgres:" in content


def test_render_docker_compose_no_unrendered_jinja():
    content, _ = _render_docker_compose([_api_service()])
    assert "{{" not in content or "${" in content  # only ${VAR} substitutions remain


# ── _render_railway ────────────────────────────────────────────────────────


def test_render_railway_has_services():
    content = _render_railway([_api_service()])
    assert "[[services]]" in content
    assert 'name = "api"' in content


def test_render_railway_port_present():
    content = _render_railway([_api_service()])
    assert "8000" in content


def test_render_railway_source_for_local_build():
    content = _render_railway([_api_service()])
    assert 'source = "."' in content


def test_render_railway_image_for_prebuilt():
    content = _render_railway([_db_service()])
    assert 'image = "postgres:16-alpine"' in content
