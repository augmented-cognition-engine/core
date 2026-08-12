"""Provider-free reference implementation of the public external adapter ports.

This adapter records opaque digests in process memory and performs no network
I/O.  It exists to prove an independent implementation of the public adapter
contract; production hosts supply their own transport and private secret refs.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Callable

from ace.application.external_operations import AdministrativeExportAdapter, ExternalDestinationAdapter
from ace.core.external_operations import (
    AdministrativeExportManifestV1Alpha1,
    DeliveryState,
    DestinationAcknowledgmentV1Alpha1,
    DestinationDeliveryAttemptV1Alpha1,
    DestinationDeliveryIntentV1Alpha1,
    DestinationDeliveryLookupV1Alpha1,
    DestinationDeliveryResultV1Alpha1,
    EffectState,
    ExternalEffectAttemptV1Alpha1,
    ExternalEffectIntentV1Alpha1,
    ExternalEffectLookupV1Alpha1,
    ExternalEffectResultV1Alpha1,
    ExternalOperationAuthorityV1Alpha1,
    LookupDisposition,
    PortabilityReceiptV1Alpha1,
    exact_external_reference,
)
from ace.core.runtime_use import CapabilityArtifactIdentityV1Alpha1


def _aware(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("reference adapter clock must include a timezone")
    return value.astimezone(UTC)


class ReferenceExternalDestinationAdapter(ExternalDestinationAdapter, AdministrativeExportAdapter):
    """Deterministic digest mailbox with lookup and duplicate detection."""

    def __init__(
        self,
        *,
        clock: Callable[[], datetime],
        host_private_secret_ref: str = "host-secret-ref:not-used-by-provider-free-adapter",
    ) -> None:
        self.clock = clock
        self._host_private_secret_ref = host_private_secret_ref
        self.deliveries: dict[str, DestinationDeliveryResultV1Alpha1] = {}
        self.effects: dict[str, ExternalEffectResultV1Alpha1] = {}
        self.exports: dict[str, PortabilityReceiptV1Alpha1] = {}

    @property
    def artifact_identity(self) -> CapabilityArtifactIdentityV1Alpha1:
        return CapabilityArtifactIdentityV1Alpha1(
            capability="governed_external_operations",
            contract="ace.core.external-destination-adapter/v1alpha1",
            implementation_id="reference_digest_mailbox",
            implementation_version="1.0.0",
            artifact_digest="sha256:" + "5" * 64,
        )

    def _now(self) -> datetime:
        return _aware(self.clock())

    async def send_delivery(
        self,
        *,
        intent: DestinationDeliveryIntentV1Alpha1,
        attempt: DestinationDeliveryAttemptV1Alpha1,
    ) -> DestinationDeliveryResultV1Alpha1:
        prior = self.deliveries.get(intent.idempotency_key)
        if prior is not None:
            return DestinationDeliveryResultV1Alpha1(
                attempt=exact_external_reference(attempt),
                state=DeliveryState.DUPLICATE,
                completed_at=self._now(),
            )
        acknowledgment = DestinationAcknowledgmentV1Alpha1(
            delivery_attempt=exact_external_reference(attempt),
            destination_revision=intent.destination_revision,
            recipient_ref=intent.recipient_ref,
            idempotency_key=intent.idempotency_key,
            payload_digest=intent.payload_digest,
            acknowledgment_ref=f"reference_mailbox:{intent.idempotency_key}",
            acknowledged_at=self._now(),
        )
        result = DestinationDeliveryResultV1Alpha1(
            attempt=exact_external_reference(attempt),
            state=DeliveryState.ACKNOWLEDGED,
            acknowledgment=acknowledgment,
            completed_at=acknowledgment.acknowledged_at,
        )
        self.deliveries[intent.idempotency_key] = result
        return result

    async def lookup_delivery(
        self,
        *,
        intent: DestinationDeliveryIntentV1Alpha1,
        attempt: DestinationDeliveryAttemptV1Alpha1,
    ) -> DestinationDeliveryLookupV1Alpha1:
        prior = self.deliveries.get(intent.idempotency_key)
        if prior is None:
            return DestinationDeliveryLookupV1Alpha1(
                attempt=exact_external_reference(attempt),
                idempotency_key=intent.idempotency_key,
                disposition=LookupDisposition.NOT_FOUND,
                looked_up_at=self._now(),
                permits_retry=True,
            )
        acknowledgment = prior.acknowledgment
        result = DestinationDeliveryResultV1Alpha1(
            attempt=exact_external_reference(attempt),
            state=prior.state,
            acknowledgment=(
                DestinationAcknowledgmentV1Alpha1(
                    delivery_attempt=exact_external_reference(attempt),
                    destination_revision=acknowledgment.destination_revision,
                    recipient_ref=acknowledgment.recipient_ref,
                    idempotency_key=acknowledgment.idempotency_key,
                    payload_digest=acknowledgment.payload_digest,
                    acknowledgment_ref=acknowledgment.acknowledgment_ref,
                    acknowledged_at=self._now(),
                )
                if acknowledgment is not None
                else None
            ),
            failure_code=prior.failure_code,
            retry_after_lookup=prior.retry_after_lookup,
            completed_at=self._now(),
        )
        return DestinationDeliveryLookupV1Alpha1(
            attempt=exact_external_reference(attempt),
            idempotency_key=intent.idempotency_key,
            disposition=LookupDisposition.FOUND,
            resolved_result=result,
            looked_up_at=self._now(),
        )

    async def execute_effect(
        self,
        *,
        intent: ExternalEffectIntentV1Alpha1,
        attempt: ExternalEffectAttemptV1Alpha1,
    ) -> ExternalEffectResultV1Alpha1:
        if intent.idempotency_key in self.effects:
            return ExternalEffectResultV1Alpha1(
                attempt=exact_external_reference(attempt),
                state=EffectState.DUPLICATE,
                completed_at=self._now(),
            )
        result = ExternalEffectResultV1Alpha1(
            attempt=exact_external_reference(attempt),
            state=EffectState.SUCCEEDED,
            result_digest_value=intent.parameters_digest,
            completed_at=self._now(),
        )
        self.effects[intent.idempotency_key] = result
        return result

    async def lookup_effect(
        self,
        *,
        intent: ExternalEffectIntentV1Alpha1,
        attempt: ExternalEffectAttemptV1Alpha1,
    ) -> ExternalEffectLookupV1Alpha1:
        prior = self.effects.get(intent.idempotency_key)
        if prior is None:
            return ExternalEffectLookupV1Alpha1(
                attempt=exact_external_reference(attempt),
                idempotency_key=intent.idempotency_key,
                disposition=LookupDisposition.NOT_FOUND,
                looked_up_at=self._now(),
                permits_retry=True,
            )
        result = ExternalEffectResultV1Alpha1(
            attempt=exact_external_reference(attempt),
            state=prior.state,
            result_digest_value=prior.result_digest_value,
            failure_code=prior.failure_code,
            retry_after_lookup=prior.retry_after_lookup,
            completed_at=self._now(),
        )
        return ExternalEffectLookupV1Alpha1(
            attempt=exact_external_reference(attempt),
            idempotency_key=intent.idempotency_key,
            disposition=LookupDisposition.FOUND,
            resolved_result=result,
            looked_up_at=self._now(),
        )

    async def create_export(
        self,
        *,
        manifest: AdministrativeExportManifestV1Alpha1,
        authority: ExternalOperationAuthorityV1Alpha1,
    ) -> PortabilityReceiptV1Alpha1:
        prior = self.exports.get(str(manifest.manifest_id))
        if prior is not None:
            return prior
        receipt = PortabilityReceiptV1Alpha1(
            manifest=exact_external_reference(manifest),
            authority=authority,
            artifact_checksum=manifest.checksum,
            included_count=len(manifest.included),
            omitted_count=len(manifest.omitted_refs),
            redacted_count=len(manifest.redacted_refs),
            created_at=self._now(),
        )
        self.exports[str(manifest.manifest_id)] = receipt
        return receipt


__all__ = ["ReferenceExternalDestinationAdapter"]
