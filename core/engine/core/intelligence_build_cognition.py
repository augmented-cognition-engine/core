"""Production, domain-neutral governed cognition resolution for Intelligence builds.

ACE 1.2 PI13 WS3c: resolve the current governed reasoning-execution and
append-operation bindings for one authorized Intelligence build, adapt the
already-selected local structured reasoning provider, and return the exact
``IntelligenceBuildFirstBriefCognition`` the host composes into first-Brief
synthesis. Every missing configuration head, capability state, or authority
grant fails closed with a specific production error; nothing here mints,
widens, or commits governed state -- only current heads are read.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Callable, Literal

from pydantic import ConfigDict

from ace.application.intelligence_build_execution import AuthorizedIntelligenceBuild
from ace.application.intelligence_build_first_brief import IntelligenceBuildFirstBriefCognition
from ace.core.agent_composition import AuthorityClass
from ace.core.contracts import FrozenContract, canonical_hash
from ace.core.delegated_cognition import GRANT_PAYLOAD_CONTRACT, CompositionAuthorityGrantMaterial
from ace.core.reasoning import (
    GOVERNED_OPERATION_CONFIGURATION_STATE_KIND,
    REASONING_CONFIGURATION_STATE_KIND,
    GovernedOperationBindingV1Alpha1,
    GovernedReasoningService,
    ReasoningExecutionBindingV1Alpha1,
)
from ace.core.records import ImmutableRecordStore
from ace.core.runtime_use import (
    AUTHORITY_GRANT_STATE_KIND,
    CAPABILITY_STATE_KIND,
    CapabilityArtifactIdentityV1Alpha1,
    capability_state_ref_for_artifact,
)
from ace.core.state import GovernedStateStore
from core.engine.core.agent_composition_runtime import (
    CAPABILITY_PAYLOAD_CONTRACT,
    CONFIGURATION_PAYLOAD_CONTRACT,
    CompositionCapabilityStateMaterial,
    GovernedCompositionAuthorityError,
    GovernedStateRuntimeUseResolver,
    ReasoningCompositionConfigurationMaterial,
)
from core.engine.core.llm import get_llm
from core.engine.core.structured_reasoning_provider import (
    SelectedLLMReasoningProvider,
    SelectedLLMReasoningProviderError,
)

FIRST_BRIEF_REASONING_CONFIGURATION_REF = "reasoning_configuration:intelligence-build-first-brief"
FIRST_BRIEF_APPEND_CONFIGURATION_REF = "governed_operation_configuration:intelligence-build-first-brief-append"
INTELLIGENCE_BUILD_APPEND_CONFIGURATION_PAYLOAD_CONTRACT = "ace.host.intelligence-build-append-configuration/v1alpha1"

REASONING_GRANT_OPERATION = "reason"
APPEND_RECORDS_OPERATION = "append_immutable_records"


def _artifact(
    *, capability: str, contract: str, implementation_id: str, implementation_version: str
) -> CapabilityArtifactIdentityV1Alpha1:
    material = {
        "capability": capability,
        "contract": contract,
        "implementation_id": implementation_id,
        "implementation_version": implementation_version,
    }
    return CapabilityArtifactIdentityV1Alpha1(
        capability=capability,
        contract=contract,
        implementation_id=implementation_id,
        implementation_version=implementation_version,
        artifact_digest=f"sha256:{canonical_hash(material)}",
    )


REASONING_ADAPTER_ARTIFACT = _artifact(
    capability="structured_reasoning",
    contract="ace.core.reasoning-provider/v1alpha1",
    implementation_id="core_selected_llm_reasoning_provider",
    implementation_version="1.0.0",
)

APPEND_ARTIFACT = _artifact(
    capability="immutable_record_append",
    contract="ace.core.immutable-record-append/v1alpha1",
    implementation_id="core_immutable_record_append",
    implementation_version="1.0.0",
)


class IntelligenceBuildAppendConfigurationMaterial(FrozenContract):
    """Durable host selection of one exact append artifact and authority."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True, revalidate_instances="always")

    contract: Literal["ace.host.intelligence-build-append-configuration/v1alpha1"] = (
        INTELLIGENCE_BUILD_APPEND_CONFIGURATION_PAYLOAD_CONTRACT
    )
    product_id: str
    configuration_ref: str
    artifact: CapabilityArtifactIdentityV1Alpha1
    authority: str
    grant_ref: str
    operation: Literal["append_immutable_records"]
    lifecycle: Literal["active", "suspended", "retired"]


class IntelligenceBuildCognitionUnavailable(RuntimeError):
    """Current governed cognition material is missing, inactive, or mismatched."""


def _utc_now() -> datetime:
    return datetime.now(UTC)


class ProductionIntelligenceBuildCognitionResolver:
    """Resolve current governed bindings and adapt the selected local provider.

    Reads only current governed-state heads for one authorized build; it mints
    no authority, commits no state, and installs no test or echo material.
    """

    def __init__(
        self,
        *,
        governed_state: GovernedStateStore,
        runtime_use: GovernedStateRuntimeUseResolver,
        records: ImmutableRecordStore,
        provider_factory: Callable[[], object] = get_llm,
        clock: Callable[[], datetime] = _utc_now,
    ) -> None:
        self.governed_state = governed_state
        self.runtime_use = runtime_use
        self.records = records
        self.provider_factory = provider_factory
        self.clock = clock

    async def _load_head(self, *, state_kind: str, product_id: str, state_id: str, dependency: str):
        try:
            return await self.runtime_use._load(state_kind=state_kind, product_id=product_id, state_id=state_id)
        except GovernedCompositionAuthorityError as exc:
            raise IntelligenceBuildCognitionUnavailable(
                f"intelligence-build cognition requires the current {dependency} governed head "
                f"'{state_id}' ({state_kind}): {exc}"
            ) from exc

    async def _validate_grant(
        self,
        *,
        build: AuthorizedIntelligenceBuild,
        grant_ref: str,
        authority: str,
        operation: str,
        dependency: str,
    ) -> None:
        material = await self._load_head(
            state_kind=AUTHORITY_GRANT_STATE_KIND,
            product_id=build.product_id,
            state_id=grant_ref,
            dependency=f"{dependency} authority-grant",
        )
        if material.revision.payload_contract != GRANT_PAYLOAD_CONTRACT:
            raise IntelligenceBuildCognitionUnavailable(f"{dependency} grant '{grant_ref}' has an unsupported payload")
        try:
            grant = CompositionAuthorityGrantMaterial.model_validate(material.revision.payload, strict=False)
        except ValueError as exc:
            raise IntelligenceBuildCognitionUnavailable(
                f"{dependency} grant '{grant_ref}' failed exact validation"
            ) from exc
        try:
            authority_class = AuthorityClass(authority)
        except ValueError as exc:
            raise IntelligenceBuildCognitionUnavailable(
                f"{dependency} authority '{authority}' is not recognized"
            ) from exc
        expected_grant_hash = canonical_hash(grant.model_dump(mode="json", exclude={"grant_hash"}))
        evaluated_at = build.authority_use.evaluated_at
        if (
            grant.grant_hash != expected_grant_hash
            or canonical_hash(grant.model_dump(mode="json")) != material.revision.material_hash
            or grant.grant_ref != grant_ref
            or grant.product_id != build.product_id
            or grant.actor_ref != build.actor_ref
            or grant.participant_principal_ref != build.actor_ref
            or grant.authority_class != authority_class
            or operation not in grant.operations
            or grant.scope_ref != build.product_id
            or grant.lifecycle != "active"
            or grant.effective_at > evaluated_at
            or (grant.expires_at is not None and grant.expires_at <= evaluated_at)
            or grant.revoked_at is not None
        ):
            raise IntelligenceBuildCognitionUnavailable(
                f"{dependency} grant '{grant_ref}' is inactive, expired, revoked, or crossed the authorized build scope"
            )
        matching = [item for item in material.receipt.authority_grants if item.grant_ref == grant_ref]
        if len(matching) != 1:
            raise IntelligenceBuildCognitionUnavailable(
                f"{dependency} grant '{grant_ref}' lacks one exact resolved receipt entry"
            )
        resolved = matching[0]
        if (
            resolved.product_id != grant.product_id
            or resolved.authority != grant.authority_class.value
            or resolved.grant_hash != grant.grant_hash
            or resolved.state != "active"
            or resolved.effective_at != grant.effective_at
            or resolved.expires_at != grant.expires_at
        ):
            raise IntelligenceBuildCognitionUnavailable(
                f"{dependency} grant '{grant_ref}' disagrees with its exact commit receipt"
            )

    async def _validate_capability(
        self,
        *,
        build: AuthorizedIntelligenceBuild,
        artifact: CapabilityArtifactIdentityV1Alpha1,
        configuration_ref: str,
        dependency: str,
    ) -> None:
        state_ref = capability_state_ref_for_artifact(artifact)
        material = await self._load_head(
            state_kind=CAPABILITY_STATE_KIND,
            product_id=build.product_id,
            state_id=state_ref,
            dependency=f"{dependency} capability-state",
        )
        if material.revision.payload_contract != CAPABILITY_PAYLOAD_CONTRACT:
            raise IntelligenceBuildCognitionUnavailable(
                f"{dependency} capability state '{state_ref}' has an unsupported payload"
            )
        try:
            state = CompositionCapabilityStateMaterial.model_validate(material.revision.payload, strict=False)
        except ValueError as exc:
            raise IntelligenceBuildCognitionUnavailable(
                f"{dependency} capability state '{state_ref}' failed exact validation"
            ) from exc
        if (
            canonical_hash(state.model_dump(mode="json")) != material.revision.material_hash
            or state.product_id != build.product_id
            or state.artifact != artifact
            or state.lifecycle != "active"
            or configuration_ref not in state.permitted_configuration_refs
        ):
            raise IntelligenceBuildCognitionUnavailable(
                f"{dependency} capability state '{state_ref}' is inactive, mismatched, or does not permit '{configuration_ref}'"
            )

    def _is_configured_store(self, records: ImmutableRecordStore, *, product_id: str) -> bool:
        """Accept the configured store, or the build's own product-scoped view of it.

        ``start_intelligence_build`` hands every host port a per-invocation
        ``ProductScopedImmutableRecordStore`` wrapping the configured store, so
        identity alone would reject the production composition. Unwrap exactly
        one such fence, and only when it is scoped to this build's own product;
        a wrapper over a different store, a different product, or any other
        object is still refused.
        """

        if records is self.records:
            return True
        inner = getattr(records, "_store", None)
        scoped_product = getattr(records, "product_id", None)
        return inner is self.records and scoped_product == product_id

    async def compose_first_brief_cognition(
        self,
        *,
        build: AuthorizedIntelligenceBuild,
        records: ImmutableRecordStore,
    ) -> IntelligenceBuildFirstBriefCognition:
        if not self._is_configured_store(records, product_id=build.product_id):
            raise IntelligenceBuildCognitionUnavailable(
                "intelligence-build cognition requires the exact configured immutable-record store"
            )

        reasoning_material = await self._load_head(
            state_kind=REASONING_CONFIGURATION_STATE_KIND,
            product_id=build.product_id,
            state_id=FIRST_BRIEF_REASONING_CONFIGURATION_REF,
            dependency="reasoning-configuration",
        )
        if reasoning_material.revision.payload_contract != CONFIGURATION_PAYLOAD_CONTRACT:
            raise IntelligenceBuildCognitionUnavailable("reasoning configuration has an unsupported payload contract")
        try:
            reasoning_configuration = ReasoningCompositionConfigurationMaterial.model_validate(
                reasoning_material.revision.payload, strict=False
            )
        except ValueError as exc:
            raise IntelligenceBuildCognitionUnavailable("reasoning configuration failed exact validation") from exc
        if (
            canonical_hash(reasoning_configuration.model_dump(mode="json")) != reasoning_material.revision.material_hash
            or reasoning_configuration.product_id != build.product_id
            or reasoning_configuration.configuration_ref != FIRST_BRIEF_REASONING_CONFIGURATION_REF
            or reasoning_configuration.artifact != REASONING_ADAPTER_ARTIFACT
            or reasoning_configuration.lifecycle != "active"
        ):
            raise IntelligenceBuildCognitionUnavailable(
                "reasoning configuration is inactive, mismatched, or crossed the authorized product scope"
            )
        await self._validate_grant(
            build=build,
            grant_ref=reasoning_configuration.grant_ref,
            authority=reasoning_configuration.authority.value,
            operation=REASONING_GRANT_OPERATION,
            dependency="reasoning",
        )
        await self._validate_capability(
            build=build,
            artifact=REASONING_ADAPTER_ARTIFACT,
            configuration_ref=FIRST_BRIEF_REASONING_CONFIGURATION_REF,
            dependency="reasoning",
        )
        try:
            execution_binding = ReasoningExecutionBindingV1Alpha1(
                product_id=build.product_id,
                artifact=REASONING_ADAPTER_ARTIFACT,
                configuration_ref=FIRST_BRIEF_REASONING_CONFIGURATION_REF,
                authority=reasoning_configuration.authority.value,
                grant_ref=reasoning_configuration.grant_ref,
                state_head_precondition=reasoning_material.head,
            )
        except ValueError as exc:
            raise IntelligenceBuildCognitionUnavailable(
                "current reasoning configuration head cannot form an exact reasoning execution binding"
            ) from exc

        append_material = await self._load_head(
            state_kind=GOVERNED_OPERATION_CONFIGURATION_STATE_KIND,
            product_id=build.product_id,
            state_id=FIRST_BRIEF_APPEND_CONFIGURATION_REF,
            dependency="append-configuration",
        )
        if append_material.revision.payload_contract != INTELLIGENCE_BUILD_APPEND_CONFIGURATION_PAYLOAD_CONTRACT:
            raise IntelligenceBuildCognitionUnavailable("append configuration has an unsupported payload contract")
        try:
            append_configuration = IntelligenceBuildAppendConfigurationMaterial.model_validate(
                append_material.revision.payload, strict=False
            )
        except ValueError as exc:
            raise IntelligenceBuildCognitionUnavailable("append configuration failed exact validation") from exc
        if (
            canonical_hash(append_configuration.model_dump(mode="json")) != append_material.revision.material_hash
            or append_configuration.product_id != build.product_id
            or append_configuration.configuration_ref != FIRST_BRIEF_APPEND_CONFIGURATION_REF
            or append_configuration.artifact != APPEND_ARTIFACT
            or append_configuration.operation != APPEND_RECORDS_OPERATION
            or append_configuration.lifecycle != "active"
        ):
            raise IntelligenceBuildCognitionUnavailable(
                "append configuration is inactive, mismatched, or crossed the authorized product scope"
            )
        await self._validate_grant(
            build=build,
            grant_ref=append_configuration.grant_ref,
            authority=append_configuration.authority,
            operation=append_configuration.operation,
            dependency="append",
        )
        await self._validate_capability(
            build=build,
            artifact=APPEND_ARTIFACT,
            configuration_ref=FIRST_BRIEF_APPEND_CONFIGURATION_REF,
            dependency="append",
        )
        try:
            append_binding = GovernedOperationBindingV1Alpha1(
                product_id=build.product_id,
                artifact=APPEND_ARTIFACT,
                configuration_ref=FIRST_BRIEF_APPEND_CONFIGURATION_REF,
                authority=append_configuration.authority,
                grant_ref=append_configuration.grant_ref,
                state_head_precondition=append_material.head,
            )
        except ValueError as exc:
            raise IntelligenceBuildCognitionUnavailable(
                "current append configuration head cannot form an exact governed operation binding"
            ) from exc

        try:
            provider = self.provider_factory()
        except Exception as exc:
            raise IntelligenceBuildCognitionUnavailable(
                "no eligible local structured reasoning provider is selected; configure an LLM provider"
            ) from exc
        if provider is None or not callable(getattr(provider, "complete_json", None)):
            raise IntelligenceBuildCognitionUnavailable(
                "the selected local provider does not support governed structured completion"
            )
        try:
            adapted = SelectedLLMReasoningProvider(
                provider=provider,
                artifact_identity=REASONING_ADAPTER_ARTIFACT,
                configuration_digest=f"sha256:{reasoning_material.revision.material_hash}",
                model=None,
            )
        except SelectedLLMReasoningProviderError as exc:
            raise IntelligenceBuildCognitionUnavailable(
                "the configured reasoning artifact is incompatible with the selected local provider"
            ) from exc

        reasoning = GovernedReasoningService(
            store=self.records,
            runtime_use=self.runtime_use,
            provider=adapted,
            clock=self.clock,
        )
        return IntelligenceBuildFirstBriefCognition(
            reasoning=reasoning,
            execution_binding=execution_binding,
            append_binding=append_binding,
        )


__all__ = [
    "APPEND_ARTIFACT",
    "APPEND_RECORDS_OPERATION",
    "FIRST_BRIEF_APPEND_CONFIGURATION_REF",
    "FIRST_BRIEF_REASONING_CONFIGURATION_REF",
    "INTELLIGENCE_BUILD_APPEND_CONFIGURATION_PAYLOAD_CONTRACT",
    "REASONING_ADAPTER_ARTIFACT",
    "REASONING_GRANT_OPERATION",
    "IntelligenceBuildAppendConfigurationMaterial",
    "IntelligenceBuildCognitionUnavailable",
    "ProductionIntelligenceBuildCognitionResolver",
]
