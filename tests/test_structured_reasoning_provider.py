from __future__ import annotations

from datetime import UTC, datetime

import pytest

from ace.core.contracts import canonical_json
from ace.core.reasoning import FrozenContextItemV1Alpha1, ProviderExecutionRequestV1Alpha1
from ace.core.runtime_use import CapabilityArtifactIdentityV1Alpha1
from core.engine.core.provider_runtime import complete_structured_provider_call
from core.engine.core.structured_reasoning_provider import (
    SelectedLLMReasoningProvider,
    SelectedLLMReasoningProviderError,
)
from core.engine.core.tokens import get_accumulator

pytestmark = pytest.mark.unit

NOW = datetime(2026, 8, 14, 12, tzinfo=UTC)
CONFIGURATION_DIGEST = "sha256:" + "c" * 64
ARTIFACT = CapabilityArtifactIdentityV1Alpha1(
    capability="structured_reasoning",
    contract="ace.core.reasoning-provider/v1alpha1",
    implementation_id="selected_llm_adapter",
    implementation_version="1.0.0",
    artifact_digest="sha256:" + "a" * 64,
)


def _request() -> ProviderExecutionRequestV1Alpha1:
    context = FrozenContextItemV1Alpha1(
        product_id="product:personal",
        record_space="prepared_intelligence",
        record_kind="observation",
        record_key="observation:one",
        storage_id="immutable_record:one",
        material_digest="sha256:" + "b" * 64,
        payload_contract="ace.intelligence.observation/v1alpha1",
        as_of=NOW,
        available_at=NOW,
        content_json=canonical_json({"status": "changed"}),
    )
    return ProviderExecutionRequestV1Alpha1(
        product_id="product:personal",
        request_id="reasoning_request:one",
        request_digest="sha256:" + "d" * 64,
        attempt_key="reasoning_attempt:one",
        instruction_json=canonical_json({"output_contract": "fixture.brief/v1"}),
        context_items=(context,),
        cutoff_at=NOW,
        started_at=NOW,
    )


class _MeasuredProvider:
    async def complete_json(self, prompt, *, model, max_tokens):
        assert "trusted_instructions" in prompt
        assert max_tokens == 2048
        accumulator = get_accumulator()
        assert accumulator is not None
        accumulator.record(
            "complete_json",
            input_tokens=17,
            output_tokens=9,
            provider="fixture_provider",
            model=model,
        )
        accumulator.record_llm_call(
            {
                "provider": "fixture_provider",
                "requested_model": model,
                "resolved_model": "fixture-model-2026-08",
                "wall_ms": 3,
                "status": "completed",
            }
        )
        context_id = _request().context_items[0].context_id
        return {
            "referenced_context_ids": [context_id],
            "structured_result": {"summary": "The status changed."},
        }


class _UnknownUsageProvider:
    async def complete_json(self, _prompt, *, model, max_tokens):
        return {
            "referenced_context_ids": [_request().context_items[0].context_id],
            "structured_result": {"summary": "Unknown usage."},
        }


class _FailingProvider:
    async def complete_json(self, _prompt, *, model, max_tokens):
        raise RuntimeError("secret provider detail")


@pytest.mark.asyncio
async def test_selected_provider_adapts_actual_route_usage_and_context() -> None:
    provider = SelectedLLMReasoningProvider(
        provider=_MeasuredProvider(),
        artifact_identity=ARTIFACT,
        configuration_digest=CONFIGURATION_DIGEST,
        model="fixture-requested-model",
        model_version="2026-08",
        max_tokens=2048,
    )
    result = await provider.execute(_request())

    assert provider.artifact_identity == ARTIFACT
    assert result.route.provider_id == "fixture_provider"
    assert result.route.model_id == "fixture-model-2026-08"
    assert result.route.model_version == "2026-08"
    assert result.route.configuration_digest == CONFIGURATION_DIGEST
    assert result.usage.input_units == 17
    assert result.usage.output_units == 9
    assert result.usage.total_units == 26
    assert result.usage.duration_ms >= 0
    assert result.structured_json == canonical_json({"summary": "The status changed."})
    assert result.referenced_context_ids == (_request().context_items[0].context_id,)


@pytest.mark.asyncio
async def test_unknown_usage_is_explicit_and_governed_adapter_fails_closed() -> None:
    call = await complete_structured_provider_call(
        _UnknownUsageProvider(),
        prompt="{}",
        model="fixture-model",
        configuration_digest=CONFIGURATION_DIGEST,
    )
    assert set(call.unavailable_fields) == {"provider_id", "model_id", "input_units", "output_units"}
    assert call.input_units is None
    assert call.output_units is None

    provider = SelectedLLMReasoningProvider(
        provider=_UnknownUsageProvider(),
        artifact_identity=ARTIFACT,
        configuration_digest=CONFIGURATION_DIGEST,
        model="fixture-model",
    )
    with pytest.raises(SelectedLLMReasoningProviderError, match="lacks required governed telemetry"):
        await provider.execute(_request())


@pytest.mark.asyncio
async def test_provider_failure_is_sanitized_and_never_becomes_output() -> None:
    provider = SelectedLLMReasoningProvider(
        provider=_FailingProvider(),
        artifact_identity=ARTIFACT,
        configuration_digest=CONFIGURATION_DIGEST,
        model="fixture-model",
    )
    with pytest.raises(SelectedLLMReasoningProviderError, match="selected structured provider call failed") as exc:
        await provider.execute(_request())
    assert "secret provider detail" not in str(exc.value)
