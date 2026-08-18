"""ClaimBoundCorrectionService — J8: bind a correction, never mutate a Brief."""

from __future__ import annotations

from datetime import datetime

from ace.application.intelligence_resource_feedback import (
    IntelligenceResourceFeedbackService,
    IntelligenceResourceFeedbackTargetPort,
)
from ace.intelligence.contracts.claim_correction import ClaimCorrectionAdmissionV1Alpha1, ClaimCorrectionRequestV1Alpha1
from ace.intelligence.contracts.resource_feedback import IntelligenceResourceFeedbackRequestV1Alpha1
from ace.intelligence.contracts.resources import BriefV1Alpha1


class ClaimBoundCorrectionError(RuntimeError):
    """A claim-bound correction failed closed before proposing an unbound change."""


class ClaimBoundCorrectionNotFound(ClaimBoundCorrectionError):
    """The exact claim or citation identity is not present on the target Brief."""


def _exact_request(value: ClaimCorrectionRequestV1Alpha1) -> ClaimCorrectionRequestV1Alpha1:
    try:
        return ClaimCorrectionRequestV1Alpha1.model_validate(value.model_dump(mode="python"))
    except (AttributeError, TypeError, ValueError) as exc:
        raise ClaimBoundCorrectionError("claim correction request failed exact revalidation") from exc


class ClaimBoundCorrectionService:
    """Verify a correction targets an exact claim/citation, then propose it, never mutate it."""

    def __init__(
        self,
        *,
        targets: IntelligenceResourceFeedbackTargetPort,
        feedback: IntelligenceResourceFeedbackService,
    ) -> None:
        self.targets = targets
        self.feedback = feedback

    async def correct(
        self,
        value: ClaimCorrectionRequestV1Alpha1,
        *,
        evaluated_at: datetime,
    ) -> ClaimCorrectionAdmissionV1Alpha1:
        request = _exact_request(value)
        try:
            record = await self.targets.load_exact(request.target, evaluated_at=evaluated_at)
        except Exception as exc:
            raise ClaimBoundCorrectionError("target Brief exact load failed closed") from exc
        if record is None or record.reference != request.target or record.payload is None:
            raise ClaimBoundCorrectionError("target Brief exact revision is unavailable")
        try:
            brief = BriefV1Alpha1.model_validate_json(record.payload.value_json)
        except (TypeError, ValueError) as exc:
            raise ClaimBoundCorrectionError("target Brief payload failed exact replay") from exc

        claim = next((item for item in brief.claims if item.claim_id == request.claim_id), None)
        if claim is None:
            raise ClaimBoundCorrectionNotFound("claim_id is not present on the exact target Brief")
        if request.citation_id not in claim.citation_ids:
            raise ClaimBoundCorrectionNotFound("citation_id is not bound to the exact target claim")
        if not any(item.citation_id == request.citation_id for item in brief.citations):
            raise ClaimBoundCorrectionNotFound("citation_id does not resolve on the exact target Brief")

        feedback_request = IntelligenceResourceFeedbackRequestV1Alpha1(
            authenticated_context=request.authenticated_context,
            product_id=request.product_id,
            authority_grant_ref=request.authority_grant_ref,
            request_key=request.request_key,
            target=request.target,
            correction_intent=request.correction_intent,
            note=request.feedback_note,
            evidence=request.evidence,
            requested_at=request.requested_at,
        )
        admission = await self.feedback.submit(feedback_request, evaluated_at=evaluated_at)
        return ClaimCorrectionAdmissionV1Alpha1(request=request, feedback=admission)


__all__ = [
    "ClaimBoundCorrectionError",
    "ClaimBoundCorrectionNotFound",
    "ClaimBoundCorrectionService",
]
