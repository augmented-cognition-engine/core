from __future__ import annotations

import json
from datetime import UTC, datetime

import pytest
from click.testing import CliRunner
from fastapi import HTTPException

from core.engine.api import product_state as api
from core.engine.cli.main import cli
from core.engine.product_state.contracts import ProductStateIngestionEnvelopeV1

pytestmark = pytest.mark.unit


class _Adapter:
    adapter_id = "example-public"
    adapter_version = "v1"
    primary_model_calls = 0

    def __init__(self) -> None:
        self.product_id: str | None = None

    def build_manifest(self, *, product_id: str, **kwargs):
        self.product_id = product_id
        return {"product_id": product_id, **kwargs}


class _Receipt:
    def model_dump(self, *, mode: str):
        assert mode == "json"
        return {
            "receipt_id": "batch_ingestion_receipt:one",
            "product_id": "product:alpha",
            "item_counts": {"accepted": 1, "failed": 0, "rejected": 0},
        }


class _IngestionService:
    def __init__(self, pool) -> None:
        assert pool is api.pool

    async def ingest(self, manifest):
        assert manifest["product_id"] == "product:alpha"
        return _Receipt()


def _envelope(**updates) -> ProductStateIngestionEnvelopeV1:
    payload = {
        "contract_version": "ace.product-state.ingestion/v1",
        "extension_id": "example",
        "extension_version": "1.0.0",
        "adapter_name": "public",
        "manifest_external_id": "manifest-v1",
        "extraction_run_id": "run-v1",
        "submitted_at": datetime(2030, 1, 1, tzinfo=UTC),
        "records": [{"input_key": "one", "record": {"kind": "event"}}],
    }
    payload.update(updates)
    return ProductStateIngestionEnvelopeV1.model_validate(payload)


def test_ingestion_contract_rejects_caller_product_scope() -> None:
    with pytest.raises(ValueError, match="authenticated product scope"):
        _envelope(records=[{"product_id": "product:foreign"}])


@pytest.mark.asyncio
async def test_ingestion_uses_installed_adapter_and_authenticated_product(monkeypatch) -> None:
    adapter = _Adapter()
    monkeypatch.setattr(api, "registered_grounded_state_adapter", lambda extension_id, name: adapter)
    monkeypatch.setattr(
        api,
        "registered_grounded_state_adapter_manifests",
        lambda: [
            {
                "extension_id": "example",
                "extension_version": "1.0.0",
                "adapter_name": "public",
                "adapter_id": "example-public",
                "adapter_version": "v1",
                "primary_model_calls": 0,
            }
        ],
    )
    monkeypatch.setattr(api, "GroundedStateIngestionService", _IngestionService)

    result = await api.ingest_product_state(_envelope(), {"product": "product:alpha"})

    assert adapter.product_id == "product:alpha"
    assert result["receipt"]["receipt_id"] == "batch_ingestion_receipt:one"
    assert result["authority"]["product_scope"] == "authenticated_token_only"
    assert result["authority"]["model_review_or_promotion_authority"] is False


@pytest.mark.asyncio
async def test_ingestion_fails_closed_on_missing_or_mismatched_extension(monkeypatch) -> None:
    monkeypatch.setattr(api, "registered_grounded_state_adapter", lambda extension_id, name: None)
    with pytest.raises(HTTPException) as missing:
        await api.ingest_product_state(_envelope(), {"product": "product:alpha"})
    assert missing.value.status_code == 404

    monkeypatch.setattr(api, "registered_grounded_state_adapter", lambda extension_id, name: _Adapter())
    monkeypatch.setattr(
        api,
        "registered_grounded_state_adapter_manifests",
        lambda: [{"extension_id": "example", "extension_version": "2.0.0", "adapter_name": "public"}],
    )
    with pytest.raises(HTTPException) as mismatch:
        await api.ingest_product_state(_envelope(), {"product": "product:alpha"})
    assert mismatch.value.status_code == 409


def test_state_cli_exposes_the_builder_journey(monkeypatch, tmp_path) -> None:
    input_path = tmp_path / "ingestion.json"
    input_path.write_text(json.dumps(_envelope().model_dump(mode="json")), encoding="utf-8")

    class _Response:
        status_code = 200

        @staticmethod
        def json():
            return {"contract_version": "ace.product-state.ingestion/v1", "receipt": {"receipt_id": "one"}}

    calls = []

    def request(method, url, **kwargs):
        calls.append((method, url, kwargs))
        return _Response()

    monkeypatch.setattr("core.engine.cli.commands.product_state.httpx.request", request)
    monkeypatch.setattr("core.engine.cli.commands.product_state.get_headers", lambda: {"Authorization": "test"})

    result = CliRunner().invoke(cli, ["--url", "http://ace.test", "state", "ingest", str(input_path)])

    assert result.exit_code == 0, result.output
    assert "ace.product-state.ingestion/v1" in result.output
    assert calls[0][0:2] == ("POST", "http://ace.test/product-state/ingestions")
    assert calls[0][2]["json"]["extension_id"] == "example"
