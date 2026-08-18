from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from ace.application.intelligence_resource_plane import IntelligenceResourceProjectionBatch
from ace.core.contracts import canonical_hash, canonical_json
from ace.core.runtime_use import AuthorityUseReceiptV1Alpha1
from ace.core.state import GovernedStateHeadPreconditionV1Alpha1, GovernedStateHeadV1
from ace.intelligence.contracts.resource_plane import (
    IntelligenceResourceAvailability,
    IntelligenceResourceKind,
    IntelligenceResourceRecordV1Alpha1,
    IntelligenceResourceReferenceV1Alpha1,
)
from ace.intelligence.contracts.resources import (
    ActivationRevisionReferenceV1Alpha1,
    BriefV1Alpha1,
    CanonicalJsonValueV1Alpha1,
    CitationV1Alpha1,
    EvidenceAcquisitionMode,
    GroundedClaimV1Alpha1,
    IntelligenceResourceMode,
)
from ace.testing import InMemoryImmutableRecordStore
from core.engine.api.grounded_ask import router
from core.engine.core.auth import get_current_user
from core.engine.core.claim_bound_correction import (
    ClaimCorrectionHttpRuntime,
    claim_bound_correction_runtime,
)
from core.engine.core.grounded_ask import AskGroundedQuestionHttpRuntime, ask_grounded_question_runtime

pytestmark = pytest.mark.unit

PRODUCT = "product:http-grounded-ask"
ACTOR = "principal:http-asker"
GRANT = "authority_grant:http-grounded-ask"
NOW = datetime.now(UTC)


def _activation() -> ActivationRevisionReferenceV1Alpha1:
    return ActivationRevisionReferenceV1Alpha1(
        product_id=PRODUCT,
        activation_key="generic_intelligence",
        activation_id=f"domain_activation:{canonical_hash([PRODUCT, 'generic_intelligence'])[:32]}",
        revision=1,
        revision_id="activation_revision:" + "a" * 32,
        revision_digest="sha256:" + "a" * 64,
    )


def _brief() -> BriefV1Alpha1:
    citation = CitationV1Alpha1(
        source_ref="evidence:filing",
        source_digest="sha256:" + "b" * 64,
        acquisition_mode=EvidenceAcquisitionMode.PREPARED_FIXTURE,
        acquisition_receipt_ref="receipt:filing",
        acquisition_receipt_digest="sha256:" + "9" * 64,
        source_as_of=NOW - timedelta(days=2),
        retrieved_at=NOW - timedelta(days=2),
    )
    claim = GroundedClaimV1Alpha1(
        statement="Revenue grew year over year.", citation_ids=(citation.citation_id,), confidence=0.9
    )
    return BriefV1Alpha1(
        product_id=PRODUCT,
        mode=IntelligenceResourceMode.PREPARED,
        activation_revision=_activation(),
        as_of=NOW - timedelta(hours=2),
        brief_type_ref="briefing:revenue",
        title="Revenue briefing",
        executive_summary="Revenue grew year over year.",
        body_markdown="# Revenue\n\n- Revenue grew year over year.",
        generated_at=NOW - timedelta(hours=1, minutes=30),
        citations=(citation,),
        claims=(claim,),
    )


def _brief_reference(brief: BriefV1Alpha1) -> IntelligenceResourceReferenceV1Alpha1:
    return IntelligenceResourceReferenceV1Alpha1(
        product_id=PRODUCT,
        resource_kind=IntelligenceResourceKind.BRIEF,
        resource_id="brief:revenue",
        resource_digest=str(brief.resource_digest),
        resource_contract=brief.contract,
        revision=1,
        as_of=brief.as_of,
        available_at=NOW - timedelta(hours=1),
    )


def _brief_record(brief: BriefV1Alpha1) -> IntelligenceResourceRecordV1Alpha1:
    return IntelligenceResourceRecordV1Alpha1(
        reference=_brief_reference(brief),
        availability=IntelligenceResourceAvailability.AVAILABLE,
        title=brief.title,
        payload=CanonicalJsonValueV1Alpha1(value_json=canonical_json(brief.model_dump(mode="json"))),
    )


class _Reader:
    def __init__(self, *records: IntelligenceResourceRecordV1Alpha1) -> None:
        self.records = records

    async def read(self, **kwargs) -> IntelligenceResourceProjectionBatch:
        return IntelligenceResourceProjectionBatch(records=self.records)


class _Authority:
    async def resolve_authority_use(self, **kwargs) -> AuthorityUseReceiptV1Alpha1:
        return AuthorityUseReceiptV1Alpha1(
            product_id=kwargs["context"].product_id,
            actor_ref=kwargs["context"].actor_ref,
            authenticated_context=kwargs["context"],
            use_subject_ref=kwargs["use_subject_ref"],
            use_subject_digest=kwargs["use_subject_digest"],
            operation=kwargs["operation"],
            authority=kwargs["authority"],
            grant_ref=GRANT,
            grant_hash="c" * 64,
            evaluated_at=kwargs["evaluated_at"],
            expires_at=NOW + timedelta(hours=1),
            state_head_precondition=GovernedStateHeadPreconditionV1Alpha1(
                state_kind="authority_grant",
                product_id=PRODUCT,
                state_id=GRANT,
                sequence=1,
                revision_id="authority_revision:http-ask",
                commit_receipt_id="authority_receipt:http-ask",
            ),
        )


def _records() -> InMemoryImmutableRecordStore:
    return InMemoryImmutableRecordStore(
        governed_state_heads={
            ("authority_grant", PRODUCT, GRANT): GovernedStateHeadV1(
                state_kind="authority_grant",
                product_id=PRODUCT,
                state_id=GRANT,
                sequence=1,
                revision_id="authority_revision:http-ask",
                commit_receipt_id="authority_receipt:http-ask",
                updated_at=NOW - timedelta(minutes=10),
            )
        }
    )


def _claims(*, authorities):
    return {"sub": ACTOR, "product": PRODUCT, "authorities": authorities, "exp": (NOW + timedelta(hours=1)).timestamp()}


async def _ask(monkeypatch, records, *, claims, body):
    monkeypatch.setattr(
        "core.engine.core.grounded_ask.intelligence_resource_projection_reader",
        lambda store: _Reader(_brief_record(_brief())),
    )
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_current_user] = lambda: claims
    app.dependency_overrides[ask_grounded_question_runtime] = lambda: AskGroundedQuestionHttpRuntime(
        records=records, authority=_Authority()
    )
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        return await client.post("/v1/intelligence/ask", json=body)


@pytest.mark.asyncio
async def test_http_ask_returns_a_grounded_answer(monkeypatch) -> None:
    response = await _ask(
        monkeypatch,
        _records(),
        claims=_claims(authorities=["observe_read"]),
        body={
            "authority_grant_ref": GRANT,
            "question": "Did revenue grow?",
            "as_of": NOW.isoformat(),
            "available_at": NOW.isoformat(),
        },
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["contract"] == "ace.intelligence.ask-answer/v1alpha1"
    assert body["claims"][0]["statement"] == "Revenue grew year over year."


@pytest.mark.asyncio
async def test_http_ask_requires_read_authority(monkeypatch) -> None:
    response = await _ask(
        monkeypatch,
        _records(),
        claims=_claims(authorities=[]),
        body={
            "authority_grant_ref": GRANT,
            "question": "Did revenue grow?",
            "as_of": NOW.isoformat(),
            "available_at": NOW.isoformat(),
        },
    )
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_http_correction_binds_to_the_exact_claim_returned_by_ask(monkeypatch) -> None:
    brief = _brief()
    claim = brief.claims[0]
    monkeypatch.setattr(
        "core.engine.core.claim_bound_correction.intelligence_resource_projection_reader",
        lambda store: _Reader(_brief_record(brief)),
    )
    app = FastAPI()
    app.include_router(router)
    records = _records()
    app.dependency_overrides[get_current_user] = lambda: _claims(authorities=["derive_propose"])
    app.dependency_overrides[claim_bound_correction_runtime] = lambda: ClaimCorrectionHttpRuntime(
        records=records, authority=_Authority()
    )
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/v1/intelligence/ask/corrections",
            json={
                "authority_grant_ref": GRANT,
                "request_key": "claim-correction:http-1",
                "target": _brief_reference(brief).model_dump(mode="json"),
                "claim_id": str(claim.claim_id),
                "citation_id": str(claim.citation_ids[0]),
                "correction_intent": "outdated",
                "note": "The cited filing was later restated.",
                "evidence": [],
            },
        )
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["feedback"]["feedback"]["disposition"] == "recorded_proposal_only"
    assert body["feedback"]["feedback"]["request"]["note"].startswith(f"[claim:{claim.claim_id}]")
