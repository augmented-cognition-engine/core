"""Supported TP1B worker supervision configuration sentinels."""

from pathlib import Path

import yaml

ROOT = Path(__file__).parents[1]


def test_compose_supervises_worker_with_migration_and_liveness_dependencies():
    compose = yaml.safe_load((ROOT / "infra/docker-compose.yml").read_text())
    worker = compose["services"]["ace-worker"]

    assert worker["command"] == "python core/engine/worker/start.py"
    assert worker["restart"] == "unless-stopped"
    assert worker["depends_on"]["surrealdb"]["condition"] == "service_healthy"
    assert worker["depends_on"]["migrate"]["condition"] == "service_completed_successfully"
    assert worker["environment"]["ACE_PRODUCT_ID"] == "${ACE_PRODUCT_ID:-product:platform}"
    assert worker["healthcheck"]["test"][:3] == ["CMD", "python", "-c"]
    assert "localhost:37778/health" in worker["healthcheck"]["test"][3]
