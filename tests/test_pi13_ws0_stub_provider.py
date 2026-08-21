"""The WS0 deterministic provider drives the production strategy ports and wire adapter."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta

import pytest
from httpx import ASGITransport, AsyncClient

from ace.application.intelligence_builder import IntelligenceBuilderSessionService
from ace.application.intelligence_builder_contracts import OnboardingStage
from ace.core.contracts import canonical_json
from ace.intelligence.contracts.synthesis import BriefSynthesisDraftV1Alpha1
from core.engine.core.llm import OpenAICompatProvider
from core.engine.core.local_owner_authority import LOCAL_OWNER_PRODUCT_ID
from core.engine.core.tokens import TokenAccumulator, clear_accumulator, set_accumulator
from scripts.pi13_ws0_stub_provider import (
    BRIEF_DRAFT_CONTRACT,
    STUB_MODEL_ID,
    StubProviderServer,
    attribute_id_for_field,
    extract_prompt,
    respond,
)
from tests.test_pi13_ws3_activation_composition import (
    _admit_activation_plan,
    _composition,
    _json,
    _post,
    _progress_to_first_briefing_ready,
    at,
)

pytestmark = pytest.mark.unit


def test_attribute_ids_are_slug_safe_and_deterministic() -> None:
    assert attribute_id_for_field("/0/anchor_value") == "field_0_anchor_value"
    assert attribute_id_for_field("/status") == "field_status"
    assert attribute_id_for_field("/") == "field_root"


def test_extract_prompt_recovers_the_canonical_json_before_the_format_instruction() -> None:
    prompt = canonical_json({"stage": "concept_model_proposal", "trusted_context": {}})
    messages = [{"role": "user", "content": f"{prompt}\n\nReturn valid JSON only. No markdown, no explanation."}]
    assert extract_prompt(messages) == json.loads(prompt)


def test_unknown_stage_is_refused() -> None:
    with pytest.raises(ValueError):
        respond({"stage": "something_else"})


@pytest.mark.asyncio
async def test_stub_drives_the_production_strategies_to_an_active_session(tmp_path) -> None:
    """The same composition the WS3 proof uses, with the WS0 stub answering every
    selected-provider stage over Markdown-shaped captures."""

    material = await _composition(tmp_path, respond=respond)
    base: datetime = material["base"]
    bound_json = _json(material["bound"])

    async with AsyncClient(transport=ASGITransport(app=material["app"]), base_url="http://test") as client:
        chain = await _progress_to_first_briefing_ready(client, material)
        await _admit_activation_plan(client, material, chain)
        activated = await _post(
            client,
            "/activation-plan/activate",
            {
                "bound_plan": bound_json,
                "activation_approval_receipt_ref": chain["activation_approval_receipt_ref"],
                "requested_at": at(base, 11),
            },
        )
    assert activated["replayed"] is False
    assert material["provider"].calls == 3

    sessions: IntelligenceBuilderSessionService = material["sessions"]
    current = await sessions.load_latest(
        product_id=LOCAL_OWNER_PRODUCT_ID,
        session_id=chain["briefing_ready_session"]["session_id"],
        available_at=base + timedelta(seconds=12),
    )
    assert current is not None and current.stage is OnboardingStage.ACTIVE


def test_brief_draft_envelope_satisfies_the_contract_and_uses_every_support() -> None:
    prompt = {
        "context_items": [
            {"context_id": "ctx:obs-a", "content": {}, "material_digest": "sha256:" + "a" * 64},
            {"context_id": "ctx:snap-a", "content": {}, "material_digest": "sha256:" + "b" * 64},
        ],
        "required_output_envelope": {"referenced_context_ids": ["ctx:obs-a", "ctx:snap-a"]},
        "trusted_instructions": {
            "brief_type": "personal_orientation",
            "corpus_boundary": {
                "observation_ids": ["observation:a", "observation:b"],
                "entity_snapshot_ids": ["entity_snapshot:a"],
            },
            "output_contract": BRIEF_DRAFT_CONTRACT,
            "personas": [{"persona_id": "personal_orientation_analyst"}],
            "required_sections": ["current_landscape", "what_matters_now", "open_questions"],
        },
    }
    envelope = respond(prompt)
    assert sorted(envelope["referenced_context_ids"]) == ["ctx:obs-a", "ctx:snap-a"]
    # Production parses the provider envelope from JSON (model_validate_json); mirror it.
    draft = BriefSynthesisDraftV1Alpha1.model_validate_json(json.dumps(envelope["structured_result"]))
    assert [section.section_id for section in draft.sections] == [
        "current_landscape",
        "what_matters_now",
        "open_questions",
    ]
    assert draft.persona_ids == ("personal_orientation_analyst",)
    used = {ref for section in draft.sections for claim in section.claims for ref in claim.support_refs}
    assert used == {"observation:a", "observation:b", "entity_snapshot:a"}
    for section in draft.sections:
        for claim in section.claims:
            if claim.grounding_kind.value == "cited":
                assert all(ref.startswith("observation:") for ref in claim.support_refs)
            else:
                assert claim.uncertainty


@pytest.mark.asyncio
async def test_loopback_server_serves_the_production_compat_adapter_with_usage() -> None:
    server = StubProviderServer().start()
    accumulator = TokenAccumulator()
    set_accumulator(accumulator)
    try:
        provider = OpenAICompatProvider(base_url=server.base_url, default_model="ignored-by-stub")
        prompt = canonical_json(
            {
                "stage": "concept_model_proposal",
                "trusted_context": {
                    "source_profile": {
                        "samples": [
                            {
                                "sample_id": "sample:one",
                                "fields": [{"field_path": "/0/text", "value_kind": "string"}],
                            }
                        ]
                    }
                },
            }
        )
        material = await provider.complete_json(prompt)
    finally:
        clear_accumulator()
        server.stop()

    assert material["entity_types"][0]["attributes"][0]["attribute_id"] == "field_0_text"
    assert material["citations"][0]["source_sample_id"] == "sample:one"
    calls = accumulator.calls_snapshot()
    assert len(calls) == 1
    assert calls[0]["provider"] == "OpenAICompatProvider"
    assert calls[0]["model"] == "ignored-by-stub"
    assert calls[0]["input_tokens"] >= 1 and calls[0]["output_tokens"] >= 1
    assert STUB_MODEL_ID  # the wire response names the stub model; the adapter keys usage by the requested model


@pytest.mark.asyncio
async def test_loopback_server_rejects_unknown_paths_and_bad_prompts() -> None:
    import httpx

    server = StubProviderServer().start()
    try:
        async with httpx.AsyncClient() as client:
            missing = await client.post(server.base_url + "/embeddings", json={})
            bad = await client.post(
                server.base_url + "/chat/completions", json={"messages": [{"role": "user", "content": "hello"}]}
            )
    finally:
        server.stop()
    assert missing.status_code == 404
    assert bad.status_code == 400
    assert "error" in bad.json()


def test_datetime_helper_is_timezone_aware() -> None:
    assert datetime.fromisoformat(at(datetime.now(UTC), 1)).tzinfo is not None
