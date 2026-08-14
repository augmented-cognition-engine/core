"""Adapter from ACE's selected LLM route to the governed reasoning port."""

from __future__ import annotations

import json

from ace.core.contracts import canonical_json
from ace.core.reasoning import (
    ProviderExecutionRequestV1Alpha1,
    ProviderRouteV1Alpha1,
    ProviderStructuredOutputV1Alpha1,
    ProviderUsageV1Alpha1,
)
from ace.core.runtime_use import CapabilityArtifactIdentityV1Alpha1
from core.engine.core.provider_runtime import complete_structured_provider_call


class SelectedLLMReasoningProviderError(RuntimeError):
    """The selected LLM could not satisfy the exact governed provider port."""


class SelectedLLMReasoningProvider:
    """Use the already selected LLM once, without introducing another route."""

    def __init__(
        self,
        *,
        provider: object,
        artifact_identity: CapabilityArtifactIdentityV1Alpha1,
        configuration_digest: str,
        model: str | None = None,
        model_version: str | None = None,
        max_tokens: int = 4096,
    ) -> None:
        exact = CapabilityArtifactIdentityV1Alpha1.model_validate(artifact_identity.model_dump(mode="python"))
        if exact.capability != "structured_reasoning" or exact.contract != "ace.core.reasoning-provider/v1alpha1":
            raise SelectedLLMReasoningProviderError("artifact does not implement the governed reasoning port")
        if not configuration_digest.startswith("sha256:") or len(configuration_digest) != 71:
            raise SelectedLLMReasoningProviderError("configuration digest must use exact sha256 syntax")
        if max_tokens < 1:
            raise SelectedLLMReasoningProviderError("max_tokens must be positive")
        self.provider = provider
        self._artifact_identity = exact
        self.configuration_digest = configuration_digest
        self.model = model
        self.model_version = model_version
        self.max_tokens = max_tokens

    @property
    def artifact_identity(self) -> CapabilityArtifactIdentityV1Alpha1:
        return self._artifact_identity

    @staticmethod
    def _prompt(request: ProviderExecutionRequestV1Alpha1) -> str:
        return canonical_json(
            {
                "context_items": [
                    {
                        "content": json.loads(item.content_json),
                        "context_id": item.context_id,
                        "material_digest": item.material_digest,
                    }
                    for item in request.context_items
                ],
                "required_output_envelope": {
                    "referenced_context_ids": [item.context_id for item in request.context_items],
                    "structured_result": "object matching trusted_instructions.output_contract",
                },
                "trusted_instructions": json.loads(request.instruction_json),
            }
        )

    async def execute(self, request: ProviderExecutionRequestV1Alpha1) -> ProviderStructuredOutputV1Alpha1:
        try:
            exact = ProviderExecutionRequestV1Alpha1.model_validate(request.model_dump(mode="python"))
            call = await complete_structured_provider_call(
                self.provider,
                prompt=self._prompt(exact),
                model=self.model,
                max_tokens=self.max_tokens,
                configuration_digest=self.configuration_digest,
            )
            material = json.loads(call.structured_json)
        except Exception as exc:
            raise SelectedLLMReasoningProviderError("selected structured provider call failed") from exc
        if set(material) != {"referenced_context_ids", "structured_result"}:
            raise SelectedLLMReasoningProviderError("provider output omitted the exact governed result envelope")
        expected_context = tuple(sorted(item.context_id for item in exact.context_items))
        referenced = material["referenced_context_ids"]
        structured = material["structured_result"]
        if not isinstance(referenced, list) or not all(isinstance(item, str) for item in referenced):
            raise SelectedLLMReasoningProviderError("provider output did not reference every exact context item")
        if (
            tuple(sorted(referenced)) != expected_context
            or len(referenced) != len(set(referenced))
            or not isinstance(structured, dict)
        ):
            raise SelectedLLMReasoningProviderError("provider output did not reference every exact context item")
        if call.unavailable_fields:
            raise SelectedLLMReasoningProviderError(
                "selected provider lacks required governed telemetry: " + ", ".join(call.unavailable_fields)
            )
        model_version = self.model_version or call.model_id
        if model_version is None:
            raise SelectedLLMReasoningProviderError("selected provider lacks a model version")
        return ProviderStructuredOutputV1Alpha1(
            route=ProviderRouteV1Alpha1(
                provider_id=str(call.provider_id),
                model_id=str(call.model_id),
                model_version=model_version,
                configuration_digest=str(call.configuration_digest),
            ),
            usage=ProviderUsageV1Alpha1(
                input_units=int(call.input_units),
                output_units=int(call.output_units),
                total_units=int(call.input_units) + int(call.output_units),
                duration_ms=call.duration_ms,
            ),
            structured_json=canonical_json(structured),
            referenced_context_ids=tuple(referenced),
        )


__all__ = ["SelectedLLMReasoningProvider", "SelectedLLMReasoningProviderError"]
