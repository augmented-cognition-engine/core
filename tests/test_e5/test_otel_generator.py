"""Tests for otel_generator: file output, template rendering, exporter variants."""

import os
import tempfile
from unittest.mock import patch

import pytest

from core.engine.generation.otel_generator import generate_otel_config

_STACK_PATCH = patch("core.engine.scanner.hardening._detect_stack_filesystem", return_value=["python"])


async def _gen(tmp, **kwargs):
    with _STACK_PATCH:
        return await generate_otel_config(stack=["python"], output_dir=tmp, **kwargs)


# ── generate_otel_config ───────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_generate_otel_config_writes_two_files():
    with tempfile.TemporaryDirectory() as tmp:
        result = await _gen(tmp)
    assert len(result["files_written"]) == 2


@pytest.mark.asyncio
async def test_generate_otel_config_writes_otel_setup_py():
    with tempfile.TemporaryDirectory() as tmp:
        result = await _gen(tmp)
    paths = [f["path"] for f in result["files_written"]]
    assert any("otel_setup.py" in p for p in paths)


@pytest.mark.asyncio
async def test_generate_otel_config_writes_logging_config_py():
    with tempfile.TemporaryDirectory() as tmp:
        result = await _gen(tmp)
    paths = [f["path"] for f in result["files_written"]]
    assert any("logging_config.py" in p for p in paths)


@pytest.mark.asyncio
async def test_generate_otel_config_files_exist_on_disk():
    with tempfile.TemporaryDirectory() as tmp:
        result = await _gen(tmp)
        for f in result["files_written"]:
            assert os.path.exists(f["path"])


@pytest.mark.asyncio
async def test_generate_otel_config_no_unrendered_placeholders():
    with tempfile.TemporaryDirectory() as tmp:
        result = await _gen(tmp)
        for f in result["files_written"]:
            content = open(f["path"]).read()
            assert "{exporter_import}" not in content
            assert "{exporter_class}" not in content
            assert "{service_name}" not in content
            assert "{default_endpoint}" not in content


@pytest.mark.asyncio
async def test_generate_otel_config_jaeger_exporter():
    with tempfile.TemporaryDirectory() as tmp:
        result = await _gen(tmp, exporter="jaeger")
        otel_path = next(f["path"] for f in result["files_written"] if "otel_setup" in f["path"])
        content = open(otel_path).read()
    assert result["exporter"] == "jaeger"
    assert "grpc" in content or "4317" in content


@pytest.mark.asyncio
async def test_generate_otel_config_stdout_exporter():
    with tempfile.TemporaryDirectory() as tmp:
        result = await _gen(tmp, exporter="stdout")
        otel_path = next(f["path"] for f in result["files_written"] if "otel_setup" in f["path"])
        content = open(otel_path).read()
    assert result["exporter"] == "stdout"
    assert "ConsoleSpanExporter" in content


@pytest.mark.asyncio
async def test_generate_otel_config_honeycomb_exporter():
    with tempfile.TemporaryDirectory() as tmp:
        result = await _gen(tmp, exporter="honeycomb")
        otel_path = next(f["path"] for f in result["files_written"] if "otel_setup" in f["path"])
        content = open(otel_path).read()
    assert result["exporter"] == "honeycomb"
    assert "honeycomb.io" in content


@pytest.mark.asyncio
async def test_generate_otel_config_unknown_exporter_defaults_to_jaeger():
    with tempfile.TemporaryDirectory() as tmp:
        result = await _gen(tmp, exporter="unknown_backend")
    assert result["exporter"] == "jaeger"


@pytest.mark.asyncio
async def test_generate_otel_config_returns_missing_packages():
    with tempfile.TemporaryDirectory() as tmp:
        result = await _gen(tmp)
    assert isinstance(result["missing_packages"], list)
    assert len(result["missing_packages"]) > 0


@pytest.mark.asyncio
async def test_generate_otel_config_service_name_from_product_id():
    with tempfile.TemporaryDirectory() as tmp:
        with _STACK_PATCH:
            result = await generate_otel_config(stack=["python"], product_id="product:my_service", output_dir=tmp)
        otel_path = next(f["path"] for f in result["files_written"] if "otel_setup" in f["path"])
        content = open(otel_path).read()
    assert "my-service" in content


@pytest.mark.asyncio
async def test_generate_otel_config_otel_setup_has_setup_function():
    with tempfile.TemporaryDirectory() as tmp:
        result = await _gen(tmp)
        otel_path = next(f["path"] for f in result["files_written"] if "otel_setup" in f["path"])
        content = open(otel_path).read()
    assert "def setup_otel" in content


@pytest.mark.asyncio
async def test_generate_otel_config_logging_config_has_formatter():
    with tempfile.TemporaryDirectory() as tmp:
        result = await _gen(tmp)
        log_path = next(f["path"] for f in result["files_written"] if "logging_config" in f["path"])
        content = open(log_path).read()
    assert "OTelFormatter" in content


@pytest.mark.asyncio
async def test_generate_otel_config_stack_auto_detected_when_none():
    with tempfile.TemporaryDirectory() as tmp:
        with patch("core.engine.scanner.hardening._detect_stack_filesystem", return_value=["python", "fastapi"]):
            result = await generate_otel_config(stack=None, output_dir=tmp)
    assert "python" in result["stack"] or "fastapi" in result["stack"]
