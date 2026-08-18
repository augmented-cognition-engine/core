# Grounded Ask (J7) and Claim-Bound Correction (J8) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.
>
> This run executes inline in the same worker session that wrote the plan (no
> separate user is available to pick an execution mode for this isolated
> worktree), following superpowers:executing-plans task-by-task with TDD.

**Goal:** Add a server-side grounded Ask service that answers questions from a
principal's authorized Brief claims (citing exact, already-persisted
`GroundedClaimV1Alpha1`/`CitationV1Alpha1` material, or an honest no-answer),
and a claim-bound correction path that binds a correction to one exact
`claim_id`/`citation_id` pair and produces a proposal-only re-derivation
record — never a mutation.

**Architecture:** Both features are pure composition over existing governed
machinery, added as new files only:
- `GroundedAskService` wraps the existing `IntelligenceResourcePlaneService`
  (unchanged) to fetch authorized `BRIEF` resources, decodes each Brief's
  persisted `claims`/`citations` verbatim, lexically ranks `CITED` claims
  against the question, and returns the exact matched claim/citation objects
  (same `claim_id`/`citation_id` as originally synthesized) or an explicit
  no-answer. No LLM call, no new claim material — this is retrieval-and-select
  over already-grounded content, which is what makes "never fabricate
  coverage" trivially true.
- `ClaimBoundCorrectionService` wraps the existing
  `IntelligenceResourceFeedbackService` (unchanged): it loads the target
  Brief, verifies the exact `claim_id`/`citation_id` pair is actually present
  on it (fail closed if not), then submits the *existing*
  `IntelligenceResourceFeedbackRequestV1Alpha1` (target=Brief reference,
  note=`[claim:<id>][citation:<id>] <note>`) through the unchanged feedback
  service, which already guarantees `disposition="recorded_proposal_only"`
  and `changes_target/changes_ranking/triggers_recalculation=False`. A new
  wrapper contract (`ClaimCorrectionAdmissionV1Alpha1`) proves at the type
  level that the underlying feedback note was scoped to that exact pair.
- HTTP entry points only (`POST /v1/intelligence/ask`,
  `POST /v1/intelligence/ask/corrections`), wired the same way the sibling
  `/v1/intelligence/resources/{query,feedback}` endpoints are wired. No CLI
  surface (out of scope — HTTP alone satisfies "HTTP and/or CLI"). No MCP
  tool — the 11-tool surface in `ace_mcp_client/` is untouched.

**Tech Stack:** Python 3.14, Pydantic v2 frozen contracts, FastAPI, pytest
(`pytest.mark.unit`, `pytest.mark.asyncio`), ruff.

**Spec:** Task description under "Subject: implement ACE 1.2 Personal
Intelligence slice PI8 — Grounded Ask and correction" (this session's system
prompt); no separate spec file exists in-repo.

## Global Constraints

- No 12th public MCP tool — `ace_mcp_client/server.py`/`tools.py` are not
  touched.
- No changes to `ace/core` at all.
- Only *additive* new files under `ace/intelligence/contracts/` and
  `ace/application/` — no edits to existing contract classes in
  `resources.py`, `resource_plane.py`, `resource_feedback.py`, or existing
  service classes. The only edits to existing files are appending new
  `import`/`__all__` entries to the three package aggregators
  (`ace/intelligence/contracts/__init__.py`, `ace/intelligence/__init__.py`
  is fed automatically via `from ace.intelligence.contracts import *`,
  `ace/application/__init__.py`) and registering the new router in
  `core/engine/api/main.py`.
- Every new frozen contract uses the repo's `_StrictFrozenContract` pattern
  (`extra="forbid", frozen=True, strict=True, revalidate_instances="always",
  validate_default=True, allow_inf_nan=False`) copied per-file, matching
  `resources.py`/`resource_plane.py`/`resource_feedback.py` convention (they
  each define their own private copy rather than sharing one).
- Ask answers may only surface `ClaimGroundingKind.CITED` claims (never
  `INFERENCE`) — this is what makes "never emit a generic uncited answer"
  hold structurally.
- Test-first: every new module gets its test written and run-to-fail before
  the implementation is written.
- Focused verification command per task:
  `uv run pytest <changed test file(s)> -v`. Final gate:
  `uv run pytest tests/intelligence tests/test_api_intelligence_resources.py tests/api -m unit -v`
  plus `uv run ruff check .` and `uv run ruff format --check .` (full
  `make test` optionally, if time budget allows, but DB-backed `db-up` may
  not be available in this worktree — the unit-marked tests above do not
  need a live DB, they use `ace.testing.InMemoryImmutableRecordStore` and
  FastAPI dependency overrides, exactly like the sibling
  `tests/test_api_intelligence_resource_feedback.py`).

---

## Task 1: Grounded Ask contracts

**Files:**
- Create: `ace/intelligence/contracts/grounded_ask.py`
- Test: `tests/intelligence/test_grounded_ask_contracts.py`

**Interfaces:**
- Produces: `AskQuestionV1Alpha1(contract, authenticated_context, product_id,
  authority_grant_ref, question, subject_refs, as_of, available_at,
  max_claims)`; `AskAnswerV1Alpha1(contract, question, product_id, actor_ref,
  claims: tuple[GroundedClaimV1Alpha1, ...], citations:
  tuple[CitationV1Alpha1, ...], source_briefs:
  tuple[IntelligenceResourceReferenceV1Alpha1, ...], answered_at,
  authority_use: AuthorityUseReceiptV1Alpha1)`;
  `AskNoAnswerV1Alpha1(contract, question, product_id, actor_ref,
  missing_coverage: tuple[str, ...], considered_briefs:
  tuple[IntelligenceResourceReferenceV1Alpha1, ...], evaluated_at,
  authority_use: AuthorityUseReceiptV1Alpha1)`. These are consumed by Task 2
  (`GroundedAskService`) and Task 6 (HTTP wiring).

- [ ] **Step 1: Write the failing contract tests**

```python
# tests/intelligence/test_grounded_ask_contracts.py
from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from pydantic import ValidationError

from ace.core.runtime_use import AuthenticatedRuntimeContextV1Alpha1, AuthorityUseReceiptV1Alpha1
from ace.core.state import GovernedStateHeadPreconditionV1Alpha1
from ace.intelligence.contracts.grounded_ask import (
    AskAnswerV1Alpha1,
    AskNoAnswerV1Alpha1,
    AskQuestionV1Alpha1,
)
from ace.intelligence.contracts.resource_plane import (
    IntelligenceResourceKind,
    IntelligenceResourceReferenceV1Alpha1,
)
from ace.intelligence.contracts.resources import CitationV1Alpha1, ClaimGroundingKind, EvidenceAcquisitionMode, GroundedClaimV1Alpha1

pytestmark = pytest.mark.unit

PRODUCT = "product:grounded-ask"
ACTOR = "principal:asker"
GRANT = "authority_grant:grounded-ask"
NOW = datetime(2026, 8, 18, 12, 0, tzinfo=UTC)


def _context() -> AuthenticatedRuntimeContextV1Alpha1:
    return AuthenticatedRuntimeContextV1Alpha1(
        product_id=PRODUCT,
        actor_ref=ACTOR,
        authentication_receipt_ref="authentication_receipt:ask",
        authentication_receipt_digest="sha256:" + "a" * 64,
        authenticated_at=NOW - timedelta(minutes=5),
        expires_at=NOW + timedelta(hours=1),
    )


def _authority_use(subject: str, digest: str) -> AuthorityUseReceiptV1Alpha1:
    return AuthorityUseReceiptV1Alpha1(
        product_id=PRODUCT,
        actor_ref=ACTOR,
        authenticated_context=_context(),
        use_subject_ref=subject,
        use_subject_digest=digest,
        operation="query_intelligence_resources",
        authority="observe_read",
        grant_ref=GRANT,
        grant_hash="f" * 64,
        evaluated_at=NOW,
        expires_at=NOW + timedelta(hours=1),
        state_head_precondition=GovernedStateHeadPreconditionV1Alpha1(
            state_kind="authority_grant",
            product_id=PRODUCT,
            state_id=GRANT,
            sequence=1,
            revision_id="authority_revision:ask",
            commit_receipt_id="authority_receipt:ask",
        ),
    )


def _citation() -> CitationV1Alpha1:
    return CitationV1Alpha1(
        source_ref="evidence:public-snapshot",
        source_digest="sha256:" + "b" * 64,
        acquisition_mode=EvidenceAcquisitionMode.PREPARED_FIXTURE,
        acquisition_receipt_ref="receipt:public-snapshot-acquisition",
        acquisition_receipt_digest="sha256:" + "9" * 64,
        source_as_of=NOW - timedelta(days=1),
        retrieved_at=NOW - timedelta(days=1),
        locator="section:1",
        excerpt="Revenue grew year over year.",
    )


def _claim(citation: CitationV1Alpha1) -> GroundedClaimV1Alpha1:
    return GroundedClaimV1Alpha1(
        statement="Revenue grew year over year.",
        citation_ids=(citation.citation_id,),
        confidence=0.9,
    )


def _brief_reference() -> IntelligenceResourceReferenceV1Alpha1:
    return IntelligenceResourceReferenceV1Alpha1(
        product_id=PRODUCT,
        resource_kind=IntelligenceResourceKind.BRIEF,
        resource_id="brief:revenue",
        resource_digest="sha256:" + "c" * 64,
        resource_contract="ace.intelligence.brief/v1alpha1",
        revision=1,
        as_of=NOW - timedelta(hours=2),
        available_at=NOW - timedelta(hours=1),
    )


def test_ask_question_requires_matching_context_and_product_scope() -> None:
    with pytest.raises(ValidationError, match="crossed authenticated product scope"):
        AskQuestionV1Alpha1(
            authenticated_context=_context(),
            product_id="product:other",
            authority_grant_ref=GRANT,
            question="Did revenue grow?",
            as_of=NOW,
            available_at=NOW,
        )


def test_ask_answer_requires_every_claim_citation_to_resolve() -> None:
    citation = _citation()
    claim = _claim(citation)
    with pytest.raises(ValidationError, match="missing citations"):
        AskAnswerV1Alpha1(
            question="Did revenue grow?",
            product_id=PRODUCT,
            actor_ref=ACTOR,
            claims=(claim,),
            citations=(),
            source_briefs=(_brief_reference(),),
            answered_at=NOW,
            authority_use=_authority_use(claim.claim_id, claim.claim_digest),
        )


def test_ask_answer_rejects_unused_citations() -> None:
    citation = _citation()
    claim = _claim(citation)
    other = CitationV1Alpha1(
        source_ref="evidence:unused",
        source_digest="sha256:" + "d" * 64,
        acquisition_mode=EvidenceAcquisitionMode.PREPARED_FIXTURE,
        acquisition_receipt_ref="receipt:unused",
        acquisition_receipt_digest="sha256:" + "9" * 64,
        source_as_of=NOW - timedelta(days=1),
        retrieved_at=NOW - timedelta(days=1),
    )
    with pytest.raises(ValidationError, match="unused citations"):
        AskAnswerV1Alpha1(
            question="Did revenue grow?",
            product_id=PRODUCT,
            actor_ref=ACTOR,
            claims=(claim,),
            citations=(citation, other),
            source_briefs=(_brief_reference(),),
            answered_at=NOW,
            authority_use=_authority_use(claim.claim_id, claim.claim_digest),
        )


def test_ask_answer_rejects_inference_claims() -> None:
    basis_citation = _citation()
    inference = GroundedClaimV1Alpha1(
        statement="Revenue likely grew.",
        grounding_kind=ClaimGroundingKind.INFERENCE,
        inference_basis_refs=("observation:x",),
        confidence=0.4,
        uncertainty="Based on partial data.",
    )
    with pytest.raises(ValidationError, match="only surface cited claims"):
        AskAnswerV1Alpha1(
            question="Did revenue grow?",
            product_id=PRODUCT,
            actor_ref=ACTOR,
            claims=(inference,),
            citations=(basis_citation,),
            source_briefs=(_brief_reference(),),
            answered_at=NOW,
            authority_use=_authority_use(inference.claim_id, inference.claim_digest),
        )


def test_ask_answer_accepts_one_grounded_claim_and_its_citation() -> None:
    citation = _citation()
    claim = _claim(citation)
    answer = AskAnswerV1Alpha1(
        question="Did revenue grow?",
        product_id=PRODUCT,
        actor_ref=ACTOR,
        claims=(claim,),
        citations=(citation,),
        source_briefs=(_brief_reference(),),
        answered_at=NOW,
        authority_use=_authority_use(claim.claim_id, claim.claim_digest),
    )
    assert answer.claims == (claim,)
    assert answer.citations == (citation,)


def test_no_answer_requires_at_least_one_missing_coverage_reason() -> None:
    with pytest.raises(ValidationError):
        AskNoAnswerV1Alpha1(
            question="Did revenue grow?",
            product_id=PRODUCT,
            actor_ref=ACTOR,
            missing_coverage=(),
            evaluated_at=NOW,
            authority_use=_authority_use("ask:none", "sha256:" + "0" * 64),
        )


def test_no_answer_accepts_a_named_missing_coverage_reason() -> None:
    no_answer = AskNoAnswerV1Alpha1(
        question="Did revenue grow?",
        product_id=PRODUCT,
        actor_ref=ACTOR,
        missing_coverage=("missing_coverage:no_claims_matched_question_terms",),
        evaluated_at=NOW,
        authority_use=_authority_use("ask:none", "sha256:" + "0" * 64),
    )
    assert no_answer.missing_coverage == ("missing_coverage:no_claims_matched_question_terms",)
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest tests/intelligence/test_grounded_ask_contracts.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named
'ace.intelligence.contracts.grounded_ask'`.

- [ ] **Step 3: Write `ace/intelligence/contracts/grounded_ask.py`**

```python
"""Server-side grounded Ask (J7) — answers are exact, already-grounded claims.

An Ask answer never manufactures new claim or citation material: it only
selects and returns ``GroundedClaimV1Alpha1``/``CitationV1Alpha1`` objects
that already exist, verbatim, on governed ``BriefV1Alpha1`` resources the
asking principal is authorized to read. If nothing citable matches the
question, the honest response is ``AskNoAnswerV1Alpha1`` naming what
coverage is missing, never an uncited ``AskAnswerV1Alpha1``.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Literal, Self

from pydantic import ConfigDict, Field, field_validator, model_validator

from ace.core.contracts import FrozenContract
from ace.core.runtime_use import AuthenticatedRuntimeContextV1Alpha1, AuthorityUseReceiptV1Alpha1
from ace.intelligence.contracts.common import validate_product_id, validate_reference
from ace.intelligence.contracts.resource_plane import IntelligenceResourceReferenceV1Alpha1
from ace.intelligence.contracts.resources import CitationV1Alpha1, ClaimGroundingKind, GroundedClaimV1Alpha1

ASK_QUESTION_VERSION = "ace.intelligence.ask-question/v1alpha1"
ASK_ANSWER_VERSION = "ace.intelligence.ask-answer/v1alpha1"
ASK_NO_ANSWER_VERSION = "ace.intelligence.ask-no-answer/v1alpha1"

MAX_ASK_CLAIMS = 20
MAX_ASK_QUESTION_CHARS = 2_000
MAX_ASK_SUBJECT_REFS = 256
MAX_ASK_MISSING_COVERAGE = 32
MAX_ASK_SOURCE_BRIEFS = MAX_ASK_CLAIMS
MAX_ASK_CITATIONS = MAX_ASK_CLAIMS * 4


class _StrictFrozenContract(FrozenContract):
    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        strict=True,
        revalidate_instances="always",
        validate_default=True,
        allow_inf_nan=False,
    )


def _aware(value: datetime, *, name: str) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{name} must include a timezone")
    return value.astimezone(UTC)


def _unique_sorted_refs(value: tuple[IntelligenceResourceReferenceV1Alpha1, ...]) -> tuple[IntelligenceResourceReferenceV1Alpha1, ...]:
    keys = [(item.resource_kind.value, item.resource_id, item.revision) for item in value]
    if len(keys) != len(set(keys)):
        raise ValueError("resource references must be unique")
    return tuple(sorted(value, key=lambda item: (item.resource_kind.value, item.resource_id, item.revision)))


class AskQuestionV1Alpha1(_StrictFrozenContract):
    """One authenticated, product-scoped question over authorized Brief claims."""

    contract: Literal["ace.intelligence.ask-question/v1alpha1"] = ASK_QUESTION_VERSION
    authenticated_context: AuthenticatedRuntimeContextV1Alpha1
    product_id: str
    authority_grant_ref: str
    question: str = Field(min_length=1, max_length=MAX_ASK_QUESTION_CHARS)
    subject_refs: tuple[str, ...] = Field(default_factory=tuple, max_length=MAX_ASK_SUBJECT_REFS)
    as_of: datetime
    available_at: datetime
    max_claims: int = Field(default=5, ge=1, le=MAX_ASK_CLAIMS)

    @field_validator("product_id")
    @classmethod
    def validate_scope(cls, value: str) -> str:
        return validate_product_id(value)

    @field_validator("authority_grant_ref")
    @classmethod
    def validate_grant(cls, value: str) -> str:
        return validate_reference(value, name="authority_grant_ref")

    @field_validator("question")
    @classmethod
    def validate_question(cls, value: str) -> str:
        if value != value.strip():
            raise ValueError("question must be trimmed")
        return value

    @field_validator("subject_refs")
    @classmethod
    def normalize_subjects(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        normalized = tuple(sorted(validate_reference(item, name="subject_refs") for item in value))
        if len(normalized) != len(set(normalized)):
            raise ValueError("subject_refs must be unique")
        return normalized

    @field_validator("as_of", "available_at")
    @classmethod
    def normalize_times(cls, value: datetime, info) -> datetime:
        return _aware(value, name=info.field_name)

    @model_validator(mode="after")
    def validate_scope_and_time(self) -> Self:
        if self.authenticated_context.product_id != self.product_id:
            raise ValueError("ask question crossed authenticated product scope")
        if self.available_at < self.as_of:
            raise ValueError("ask available_at cannot precede as_of")
        return self


class AskAnswerV1Alpha1(_StrictFrozenContract):
    """A grounded answer: exact cited claims plus their exact citations."""

    contract: Literal["ace.intelligence.ask-answer/v1alpha1"] = ASK_ANSWER_VERSION
    question: str = Field(min_length=1, max_length=MAX_ASK_QUESTION_CHARS)
    product_id: str
    actor_ref: str
    claims: tuple[GroundedClaimV1Alpha1, ...] = Field(min_length=1, max_length=MAX_ASK_CLAIMS)
    citations: tuple[CitationV1Alpha1, ...] = Field(min_length=1, max_length=MAX_ASK_CITATIONS)
    source_briefs: tuple[IntelligenceResourceReferenceV1Alpha1, ...] = Field(min_length=1, max_length=MAX_ASK_SOURCE_BRIEFS)
    answered_at: datetime
    authority_use: AuthorityUseReceiptV1Alpha1

    @field_validator("product_id")
    @classmethod
    def validate_scope(cls, value: str) -> str:
        return validate_product_id(value)

    @field_validator("claims")
    @classmethod
    def validate_unique_claims(cls, value: tuple[GroundedClaimV1Alpha1, ...]) -> tuple[GroundedClaimV1Alpha1, ...]:
        ids = [item.claim_id for item in value]
        if len(ids) != len(set(ids)):
            raise ValueError("answer claims must use unique content identities")
        return value

    @field_validator("citations")
    @classmethod
    def normalize_citations(cls, value: tuple[CitationV1Alpha1, ...]) -> tuple[CitationV1Alpha1, ...]:
        ids = [item.citation_id for item in value]
        if len(ids) != len(set(ids)):
            raise ValueError("answer citations must use unique content identities")
        return tuple(sorted(value, key=lambda item: item.citation_id or ""))

    @field_validator("source_briefs")
    @classmethod
    def normalize_source_briefs(cls, value):
        return _unique_sorted_refs(value)

    @field_validator("answered_at")
    @classmethod
    def normalize_answered_at(cls, value: datetime) -> datetime:
        return _aware(value, name="answered_at")

    @model_validator(mode="after")
    def validate_grounding(self) -> Self:
        if any(claim.grounding_kind is not ClaimGroundingKind.CITED for claim in self.claims):
            raise ValueError("a grounded Ask answer may only surface cited claims")
        citation_ids = {item.citation_id for item in self.citations}
        used = {citation_id for claim in self.claims for citation_id in claim.citation_ids}
        missing = used - citation_ids
        if missing:
            raise ValueError(f"answer claims reference missing citations: {sorted(missing)}")
        unused = citation_ids - used
        if unused:
            raise ValueError(f"answer contains unused citations: {sorted(unused)}")
        if any(ref.product_id != self.product_id for ref in self.source_briefs):
            raise ValueError("answer source Briefs crossed product scope")
        if self.authority_use.product_id != self.product_id or self.authority_use.actor_ref != self.actor_ref:
            raise ValueError("answer authority receipt does not match its exact principal")
        return self


class AskNoAnswerV1Alpha1(_StrictFrozenContract):
    """An honest refusal naming exactly what coverage is missing."""

    contract: Literal["ace.intelligence.ask-no-answer/v1alpha1"] = ASK_NO_ANSWER_VERSION
    question: str = Field(min_length=1, max_length=MAX_ASK_QUESTION_CHARS)
    product_id: str
    actor_ref: str
    missing_coverage: tuple[str, ...] = Field(min_length=1, max_length=MAX_ASK_MISSING_COVERAGE)
    considered_briefs: tuple[IntelligenceResourceReferenceV1Alpha1, ...] = Field(default_factory=tuple, max_length=MAX_ASK_SOURCE_BRIEFS)
    evaluated_at: datetime
    authority_use: AuthorityUseReceiptV1Alpha1

    @field_validator("product_id")
    @classmethod
    def validate_scope(cls, value: str) -> str:
        return validate_product_id(value)

    @field_validator("missing_coverage")
    @classmethod
    def normalize_missing_coverage(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        normalized = tuple(sorted(validate_reference(item, name="missing_coverage") for item in value))
        if len(normalized) != len(set(normalized)):
            raise ValueError("missing_coverage reasons must be unique")
        return normalized

    @field_validator("considered_briefs")
    @classmethod
    def normalize_considered_briefs(cls, value):
        return _unique_sorted_refs(value)

    @field_validator("evaluated_at")
    @classmethod
    def normalize_evaluated_at(cls, value: datetime) -> datetime:
        return _aware(value, name="evaluated_at")

    @model_validator(mode="after")
    def validate_scope(self) -> Self:
        if any(ref.product_id != self.product_id for ref in self.considered_briefs):
            raise ValueError("no-answer considered Briefs crossed product scope")
        if self.authority_use.product_id != self.product_id or self.authority_use.actor_ref != self.actor_ref:
            raise ValueError("no-answer authority receipt does not match its exact principal")
        return self


__all__ = [
    "ASK_ANSWER_VERSION",
    "ASK_NO_ANSWER_VERSION",
    "ASK_QUESTION_VERSION",
    "MAX_ASK_CLAIMS",
    "AskAnswerV1Alpha1",
    "AskNoAnswerV1Alpha1",
    "AskQuestionV1Alpha1",
]
```

Note: Pydantic forbids two `model_validator` methods with the same name
(`validate_scope`) across `AskNoAnswerV1Alpha1` in the same class — that's
fine here since each is defined on a *different* class, but double check
there isn't a name clash with the `field_validator` also called
`validate_scope` on the same class (`AskAnswerV1Alpha1`/`AskNoAnswerV1Alpha1`
each only have one method literally named `validate_scope`, the
field-level one is named `validate_scope` too in both classes — rename the
field validator to `validate_product_scope` in each class to avoid the
Python-level duplicate-method-name collision before running the tests.

- [ ] **Step 4: Run to verify pass**

Run: `uv run pytest tests/intelligence/test_grounded_ask_contracts.py -v`
Expected: PASS (7 tests).

- [ ] **Step 5: Lint**

Run: `uv run ruff check ace/intelligence/contracts/grounded_ask.py tests/intelligence/test_grounded_ask_contracts.py --fix && uv run ruff format ace/intelligence/contracts/grounded_ask.py tests/intelligence/test_grounded_ask_contracts.py`

---

## Task 2: `GroundedAskService`

**Files:**
- Create: `ace/application/grounded_ask.py`
- Test: `tests/intelligence/test_grounded_ask_service.py`

**Interfaces:**
- Consumes: `IntelligenceResourcePlaneService` (unchanged, from Task's
  research — `ace/application/intelligence_resource_plane.py`), the Task 1
  contracts.
- Produces: `GroundedAskService(resource_plane=...).ask(request:
  AskQuestionV1Alpha1, *, evaluated_at: datetime) -> AskAnswerV1Alpha1 |
  AskNoAnswerV1Alpha1`; `GroundedAskError`; `ASK_MAX_CANDIDATE_BRIEFS = 50`.
  Consumed by Task 6 (HTTP wiring).

- [ ] **Step 1: Write the failing service tests**

Reuse the exact `_Reader`/`_Authority` double pattern from
`tests/intelligence/test_intelligence_resource_plane.py` (already in the
repo) so the service is tested at the same layer the resource-plane service
itself is tested at — feed the reader real `BriefV1Alpha1` JSON as each
record's `payload`.

```python
# tests/intelligence/test_grounded_ask_service.py
from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from ace.application.grounded_ask import ASK_MAX_CANDIDATE_BRIEFS, GroundedAskError, GroundedAskService
from ace.application.intelligence_resource_plane import IntelligenceResourcePlaneService, IntelligenceResourceProjectionBatch
from ace.core.contracts import canonical_json
from ace.core.runtime_use import AuthenticatedRuntimeContextV1Alpha1, AuthorityUseReceiptV1Alpha1
from ace.core.state import GovernedStateHeadPreconditionV1Alpha1
from ace.intelligence.contracts.grounded_ask import AskAnswerV1Alpha1, AskNoAnswerV1Alpha1, AskQuestionV1Alpha1
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
    ClaimGroundingKind,
    EvidenceAcquisitionMode,
    GroundedClaimV1Alpha1,
    IntelligenceResourceMode,
)

pytestmark = pytest.mark.unit

PRODUCT = "product:grounded-ask-service"
ACTOR = "principal:asker"
GRANT = "authority_grant:grounded-ask-service"
NOW = datetime(2026, 8, 18, 12, 0, tzinfo=UTC)


def _context() -> AuthenticatedRuntimeContextV1Alpha1:
    return AuthenticatedRuntimeContextV1Alpha1(
        product_id=PRODUCT,
        actor_ref=ACTOR,
        authentication_receipt_ref="authentication_receipt:ask-service",
        authentication_receipt_digest="sha256:" + "a" * 64,
        authenticated_at=NOW - timedelta(minutes=5),
        expires_at=NOW + timedelta(hours=1),
    )


def _activation() -> ActivationRevisionReferenceV1Alpha1:
    return ActivationRevisionReferenceV1Alpha1(
        product_id=PRODUCT,
        activation_key="generic_intelligence",
        activation_id="domain_activation:" + "a" * 32,
        revision=1,
        revision_id="activation_revision:" + "a" * 32,
        revision_digest="sha256:" + "a" * 64,
    )


def _citation(suffix: str, *, excerpt: str) -> CitationV1Alpha1:
    return CitationV1Alpha1(
        source_ref=f"evidence:{suffix}",
        source_digest="sha256:" + "b" * 64,
        acquisition_mode=EvidenceAcquisitionMode.PREPARED_FIXTURE,
        acquisition_receipt_ref=f"receipt:{suffix}",
        acquisition_receipt_digest="sha256:" + "9" * 64,
        source_as_of=NOW - timedelta(days=2),
        retrieved_at=NOW - timedelta(days=2),
        locator="section:1",
        excerpt=excerpt,
    )


def _brief(*, resource_id_hex: str, statement: str, excerpt: str, confidence: float = 0.9) -> BriefV1Alpha1:
    citation = _citation(resource_id_hex, excerpt=excerpt)
    claim = GroundedClaimV1Alpha1(statement=statement, citation_ids=(citation.citation_id,), confidence=confidence)
    return BriefV1Alpha1(
        product_id=PRODUCT,
        mode=IntelligenceResourceMode.PREPARED,
        activation_revision=_activation(),
        as_of=NOW - timedelta(hours=2),
        brief_type_ref="briefing:revenue",
        title="Revenue briefing",
        executive_summary=statement,
        body_markdown=f"# Revenue\n\n- {statement}",
        generated_at=NOW - timedelta(hours=1, minutes=30),
        citations=(citation,),
        claims=(claim,),
    )


def _brief_record(brief: BriefV1Alpha1, *, resource_id: str, available_at: datetime = NOW - timedelta(hours=1)) -> IntelligenceResourceRecordV1Alpha1:
    return IntelligenceResourceRecordV1Alpha1(
        reference=IntelligenceResourceReferenceV1Alpha1(
            product_id=PRODUCT,
            resource_kind=IntelligenceResourceKind.BRIEF,
            resource_id=resource_id,
            resource_digest=str(brief.resource_digest),
            resource_contract=brief.contract,
            revision=1,
            as_of=brief.as_of,
            available_at=available_at,
        ),
        availability=IntelligenceResourceAvailability.AVAILABLE,
        title=brief.title,
        summary=brief.executive_summary,
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
            grant_ref=kwargs["grant_ref"],
            grant_hash="f" * 64,
            evaluated_at=kwargs["evaluated_at"],
            expires_at=NOW + timedelta(hours=1),
            state_head_precondition=GovernedStateHeadPreconditionV1Alpha1(
                state_kind="authority_grant",
                product_id=PRODUCT,
                state_id=GRANT,
                sequence=1,
                revision_id="authority_revision:ask-service",
                commit_receipt_id="authority_receipt:ask-service",
            ),
        )


class _DenyingAuthority:
    async def resolve_authority_use(self, **kwargs):
        raise RuntimeError("denied")


def _question(*, question: str = "Did revenue grow?", max_claims: int = 5) -> AskQuestionV1Alpha1:
    return AskQuestionV1Alpha1(
        authenticated_context=_context(),
        product_id=PRODUCT,
        authority_grant_ref=GRANT,
        question=question,
        as_of=NOW,
        available_at=NOW,
        max_claims=max_claims,
    )


@pytest.mark.asyncio
async def test_answers_with_the_exact_persisted_claim_and_citation() -> None:
    brief = _brief(resource_id_hex="a", statement="Revenue grew year over year.", excerpt="Revenue rose 12%.")
    service = GroundedAskService(
        resource_plane=IntelligenceResourcePlaneService(
            reader=_Reader(_brief_record(brief, resource_id="brief:revenue")),
            authority=_Authority(),
        )
    )

    result = await service.ask(_question(), evaluated_at=NOW)

    assert isinstance(result, AskAnswerV1Alpha1)
    assert result.claims == brief.claims
    assert result.citations == brief.citations
    assert result.source_briefs[0].resource_id == "brief:revenue"


@pytest.mark.asyncio
async def test_refuses_honestly_when_no_claim_matches_the_question() -> None:
    brief = _brief(resource_id_hex="a", statement="Headcount stayed flat.", excerpt="No hiring this quarter.")
    service = GroundedAskService(
        resource_plane=IntelligenceResourcePlaneService(
            reader=_Reader(_brief_record(brief, resource_id="brief:headcount")),
            authority=_Authority(),
        )
    )

    result = await service.ask(_question(question="Did revenue grow?"), evaluated_at=NOW)

    assert isinstance(result, AskNoAnswerV1Alpha1)
    assert result.missing_coverage == ("missing_coverage:no_claims_matched_question_terms",)
    assert result.considered_briefs[0].resource_id == "brief:headcount"


@pytest.mark.asyncio
async def test_refuses_honestly_when_no_brief_resources_are_visible() -> None:
    service = GroundedAskService(
        resource_plane=IntelligenceResourcePlaneService(reader=_Reader(), authority=_Authority())
    )

    result = await service.ask(_question(), evaluated_at=NOW)

    assert isinstance(result, AskNoAnswerV1Alpha1)
    assert result.missing_coverage == ("missing_coverage:no_authorized_brief_resources_available",)
    assert result.considered_briefs == ()


@pytest.mark.asyncio
async def test_fails_closed_when_authorization_is_denied() -> None:
    brief = _brief(resource_id_hex="a", statement="Revenue grew year over year.", excerpt="Revenue rose 12%.")
    service = GroundedAskService(
        resource_plane=IntelligenceResourcePlaneService(
            reader=_Reader(_brief_record(brief, resource_id="brief:revenue")),
            authority=_DenyingAuthority(),
        )
    )

    with pytest.raises(GroundedAskError):
        await service.ask(_question(), evaluated_at=NOW)


@pytest.mark.asyncio
async def test_bounds_candidate_briefs_by_the_ordinary_budget() -> None:
    brief = _brief(resource_id_hex="a", statement="Revenue grew year over year.", excerpt="Revenue rose 12%.")
    captured: dict = {}

    class _CapturingReader(_Reader):
        async def read(self, **kwargs):
            captured.update(kwargs)
            return await super().read(**kwargs)

    service = GroundedAskService(
        resource_plane=IntelligenceResourcePlaneService(
            reader=_CapturingReader(_brief_record(brief, resource_id="brief:revenue")),
            authority=_Authority(),
        )
    )
    await service.ask(_question(), evaluated_at=NOW)

    assert captured["query"].page_size == ASK_MAX_CANDIDATE_BRIEFS
    assert captured["query"].resource_kinds == (IntelligenceResourceKind.BRIEF,)
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest tests/intelligence/test_grounded_ask_service.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'ace.application.grounded_ask'`.

- [ ] **Step 3: Write `ace/application/grounded_ask.py`**

```python
"""GroundedAskService — J7: answer questions only from authorized Brief claims."""

from __future__ import annotations

import re
from datetime import datetime

from ace.application.intelligence_resource_plane import (
    IntelligenceResourcePlaneError,
    IntelligenceResourcePlaneService,
)
from ace.intelligence.contracts.grounded_ask import AskAnswerV1Alpha1, AskNoAnswerV1Alpha1, AskQuestionV1Alpha1
from ace.intelligence.contracts.resource_plane import (
    IntelligenceResourceAvailability,
    IntelligenceResourceKind,
    IntelligenceResourceQueryV1Alpha1,
    IntelligenceResourceReferenceV1Alpha1,
)
from ace.intelligence.contracts.resources import BriefV1Alpha1, ClaimGroundingKind, GroundedClaimV1Alpha1

ASK_MAX_CANDIDATE_BRIEFS = 50

_WORD = re.compile(r"[a-z0-9]+")


class GroundedAskError(RuntimeError):
    """A grounded Ask failed closed before exposing an unauthorized or uncited answer."""


def _exact_question(value: AskQuestionV1Alpha1) -> AskQuestionV1Alpha1:
    try:
        return AskQuestionV1Alpha1.model_validate(value.model_dump(mode="python"))
    except (AttributeError, TypeError, ValueError) as exc:
        raise GroundedAskError("ask question failed exact revalidation") from exc


def _terms(text: str) -> set[str]:
    return set(_WORD.findall(text.lower()))


class GroundedAskService:
    """Answer one question from a principal's authorized Brief claims, or refuse honestly."""

    def __init__(self, *, resource_plane: IntelligenceResourcePlaneService) -> None:
        self.resource_plane = resource_plane

    async def ask(
        self,
        value: AskQuestionV1Alpha1,
        *,
        evaluated_at: datetime,
    ) -> AskAnswerV1Alpha1 | AskNoAnswerV1Alpha1:
        request = _exact_question(value)
        question_terms = _terms(request.question)

        query = IntelligenceResourceQueryV1Alpha1(
            authenticated_context=request.authenticated_context,
            product_id=request.product_id,
            authority_grant_ref=request.authority_grant_ref,
            resource_kinds=(IntelligenceResourceKind.BRIEF,),
            subject_refs=request.subject_refs,
            as_of=request.as_of,
            available_at=request.available_at,
            page_size=ASK_MAX_CANDIDATE_BRIEFS,
        )
        try:
            page = await self.resource_plane.query(query, evaluated_at=evaluated_at)
        except IntelligenceResourcePlaneError as exc:
            raise GroundedAskError("authorized Brief retrieval failed closed") from exc

        considered: list[IntelligenceResourceReferenceV1Alpha1] = []
        scored: list[tuple[int, GroundedClaimV1Alpha1, BriefV1Alpha1, IntelligenceResourceReferenceV1Alpha1]] = []
        for item in page.items:
            if item.availability is not IntelligenceResourceAvailability.AVAILABLE or item.payload is None:
                continue
            considered.append(item.reference)
            try:
                brief = BriefV1Alpha1.model_validate_json(item.payload.value_json)
            except (TypeError, ValueError):
                continue
            for claim in brief.claims:
                if claim.grounding_kind is not ClaimGroundingKind.CITED:
                    continue
                score = len(question_terms & _terms(claim.statement))
                if score > 0:
                    scored.append((score, claim, brief, item.reference))

        scored.sort(key=lambda entry: (-entry[0], -entry[1].confidence, str(entry[1].claim_id)))
        selected = scored[: request.max_claims]

        if not selected:
            missing_coverage = (
                ("missing_coverage:no_authorized_brief_resources_available",)
                if not considered
                else ("missing_coverage:no_claims_matched_question_terms",)
            )
            return AskNoAnswerV1Alpha1(
                question=request.question,
                product_id=request.product_id,
                actor_ref=request.authenticated_context.actor_ref,
                missing_coverage=missing_coverage,
                considered_briefs=tuple(considered),
                evaluated_at=evaluated_at,
                authority_use=page.authority_use,
            )

        selected_claims = tuple(entry[1] for entry in selected)
        citations_by_id = {
            citation.citation_id: citation for _, _, brief, _ in selected for citation in brief.citations
        }
        used_citation_ids = {citation_id for claim in selected_claims for citation_id in claim.citation_ids}
        selected_citations = tuple(
            citations_by_id[citation_id] for citation_id in used_citation_ids if citation_id in citations_by_id
        )
        if len(selected_citations) != len(used_citation_ids):
            raise GroundedAskError("selected claim citations could not be resolved on their source Brief")
        source_briefs = tuple({entry[3] for entry in selected})

        return AskAnswerV1Alpha1(
            question=request.question,
            product_id=request.product_id,
            actor_ref=request.authenticated_context.actor_ref,
            claims=selected_claims,
            citations=selected_citations,
            source_briefs=source_briefs,
            answered_at=evaluated_at,
            authority_use=page.authority_use,
        )


__all__ = [
    "ASK_MAX_CANDIDATE_BRIEFS",
    "GroundedAskError",
    "GroundedAskService",
]
```

- [ ] **Step 4: Run to verify pass**

Run: `uv run pytest tests/intelligence/test_grounded_ask_service.py -v`
Expected: PASS (5 tests).

- [ ] **Step 5: Lint**

Run: `uv run ruff check ace/application/grounded_ask.py tests/intelligence/test_grounded_ask_service.py --fix && uv run ruff format ace/application/grounded_ask.py tests/intelligence/test_grounded_ask_service.py`

---

## Task 3: Claim-bound correction contracts

**Files:**
- Create: `ace/intelligence/contracts/claim_correction.py`
- Test: `tests/intelligence/test_claim_correction_contracts.py`

**Interfaces:**
- Consumes: `IntelligenceResourceCorrectionIntent`,
  `IntelligenceResourceFeedbackAdmissionV1Alpha1`,
  `IntelligenceResourceFeedbackRequestV1Alpha1` (all unchanged, from
  `ace/intelligence/contracts/resource_feedback.py`).
- Produces: `ClaimCorrectionRequestV1Alpha1(contract, authenticated_context,
  product_id, authority_grant_ref, request_key, target:
  IntelligenceResourceReferenceV1Alpha1, claim_id, citation_id,
  correction_intent, note, evidence, requested_at, correction_id,
  correction_digest)` with a `.feedback_note` property; and
  `ClaimCorrectionAdmissionV1Alpha1(contract, request:
  ClaimCorrectionRequestV1Alpha1, feedback:
  IntelligenceResourceFeedbackAdmissionV1Alpha1)`. Consumed by Task 4
  (`ClaimBoundCorrectionService`) and Task 6 (HTTP wiring).

- [ ] **Step 1: Write the failing contract tests**

```python
# tests/intelligence/test_claim_correction_contracts.py
from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from pydantic import ValidationError

from ace.core.runtime_use import AuthenticatedRuntimeContextV1Alpha1, AuthorityUseReceiptV1Alpha1
from ace.core.state import GovernedStateHeadPreconditionV1Alpha1
from ace.intelligence.contracts.claim_correction import ClaimCorrectionAdmissionV1Alpha1, ClaimCorrectionRequestV1Alpha1
from ace.intelligence.contracts.resource_feedback import (
    IntelligenceResourceCorrectionIntent,
    IntelligenceResourceFeedbackAdmissionV1Alpha1,
    IntelligenceResourceFeedbackReceiptV1Alpha1,
    IntelligenceResourceFeedbackRequestV1Alpha1,
)
from ace.intelligence.contracts.resource_plane import IntelligenceResourceKind, IntelligenceResourceReferenceV1Alpha1
from ace.core.records import AppendOnlyTransactionReceiptV1, ImmutableRecordReferenceV1

pytestmark = pytest.mark.unit

PRODUCT = "product:claim-correction"
ACTOR = "principal:corrector"
GRANT = "authority_grant:claim-correction"
NOW = datetime(2026, 8, 18, 12, 0, tzinfo=UTC)


def _context() -> AuthenticatedRuntimeContextV1Alpha1:
    return AuthenticatedRuntimeContextV1Alpha1(
        product_id=PRODUCT,
        actor_ref=ACTOR,
        authentication_receipt_ref="authentication_receipt:correction",
        authentication_receipt_digest="sha256:" + "a" * 64,
        authenticated_at=NOW - timedelta(minutes=5),
        expires_at=NOW + timedelta(hours=1),
    )


def _target() -> IntelligenceResourceReferenceV1Alpha1:
    return IntelligenceResourceReferenceV1Alpha1(
        product_id=PRODUCT,
        resource_kind=IntelligenceResourceKind.BRIEF,
        resource_id="brief:revenue",
        resource_digest="sha256:" + "c" * 64,
        resource_contract="ace.intelligence.brief/v1alpha1",
        revision=1,
        as_of=NOW - timedelta(hours=2),
        available_at=NOW - timedelta(hours=1),
    )


def _request(**overrides) -> ClaimCorrectionRequestV1Alpha1:
    fields = {
        "authenticated_context": _context(),
        "product_id": PRODUCT,
        "authority_grant_ref": GRANT,
        "request_key": "claim-correction:stable-1",
        "target": _target(),
        "claim_id": "grounded_claim:" + "1" * 32,
        "citation_id": "citation:" + "2" * 32,
        "correction_intent": IntelligenceResourceCorrectionIntent.OUTDATED,
        "note": "The cited filing was later restated.",
        "requested_at": NOW,
    }
    fields.update(overrides)
    return ClaimCorrectionRequestV1Alpha1(**fields)


def test_rejects_a_target_that_is_not_a_brief() -> None:
    non_brief = IntelligenceResourceReferenceV1Alpha1(
        product_id=PRODUCT,
        resource_kind=IntelligenceResourceKind.SIGNAL,
        resource_id="signal:x",
        resource_digest="sha256:" + "d" * 64,
        resource_contract="ace.intelligence.signal/v1alpha1",
        revision=1,
        as_of=NOW - timedelta(hours=2),
        available_at=NOW - timedelta(hours=1),
    )
    with pytest.raises(ValidationError, match="only a Brief"):
        _request(target=non_brief)


def test_feedback_note_embeds_the_exact_claim_and_citation_identity() -> None:
    request = _request()
    assert request.feedback_note == (
        f"[claim:{request.claim_id}][citation:{request.citation_id}] {request.note}"
    )


def test_admission_rejects_a_feedback_record_scoped_to_a_different_claim() -> None:
    request = _request()
    underlying = IntelligenceResourceFeedbackRequestV1Alpha1(
        authenticated_context=request.authenticated_context,
        product_id=request.product_id,
        authority_grant_ref=request.authority_grant_ref,
        request_key=request.request_key,
        target=request.target,
        correction_intent=request.correction_intent,
        note="Some other unbound note.",
        requested_at=request.requested_at,
    )
    authority_use = AuthorityUseReceiptV1Alpha1(
        product_id=PRODUCT,
        actor_ref=ACTOR,
        authenticated_context=request.authenticated_context,
        use_subject_ref=underlying.feedback_id,
        use_subject_digest=underlying.feedback_digest,
        operation="submit_intelligence_resource_feedback",
        authority="derive_propose",
        grant_ref=GRANT,
        grant_hash="f" * 64,
        evaluated_at=NOW,
        expires_at=NOW + timedelta(hours=1),
        state_head_precondition=GovernedStateHeadPreconditionV1Alpha1(
            state_kind="authority_grant",
            product_id=PRODUCT,
            state_id=GRANT,
            sequence=1,
            revision_id="authority_revision:claim-correction",
            commit_receipt_id="authority_receipt:claim-correction",
        ),
    )
    feedback = IntelligenceResourceFeedbackReceiptV1Alpha1(
        request=underlying,
        authority_use=authority_use,
        recorded_at=NOW,
    )
    record = ImmutableRecordReferenceV1(
        product_id=PRODUCT,
        record_space="feedback",
        record_kind="resource_feedback",
        record_key=str(underlying.feedback_id),
        payload_contract=feedback.contract,
        storage_id="storage:1",
    )
    transaction = AppendOnlyTransactionReceiptV1(
        product_id=PRODUCT,
        record_space="feedback",
        transaction_key=f"resource_feedback:{underlying.feedback_id}",
        records=(record,),
        submitted_at=NOW,
        governed_state_preconditions=(authority_use.state_head_precondition,),
    )
    admission = IntelligenceResourceFeedbackAdmissionV1Alpha1(feedback=feedback, record=record, transaction=transaction)

    with pytest.raises(ValidationError, match="exact claim/citation-bound proposal"):
        ClaimCorrectionAdmissionV1Alpha1(request=request, feedback=admission)
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest tests/intelligence/test_claim_correction_contracts.py -v`
Expected: FAIL — `ModuleNotFoundError`. (If `ImmutableRecordReferenceV1` or
`AppendOnlyTransactionReceiptV1` field names differ slightly from the guess
above, adjust to match `ace/core/records.py` — check it if this step's
import or construction fails for a reason other than the missing module.)

- [ ] **Step 3: Write `ace/intelligence/contracts/claim_correction.py`**

```python
"""Claim-bound correction (J8) — proposal-only, never a silent mutation.

Binds a correction to the exact ``claim_id``/``citation_id`` pair of a
grounded Ask answer, then reuses the existing proposal-only feedback
machinery (``IntelligenceResourceFeedbackRequestV1Alpha1`` /
``IntelligenceResourceFeedbackService``) verbatim to record it. This module
adds no new durable write path — it only proves, at the type level, that the
underlying feedback record was scoped to one exact claim and citation before
it was written.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Literal, Self

from pydantic import ConfigDict, Field, field_validator, model_validator

from ace.core.contracts import FrozenContract, canonical_hash
from ace.core.runtime_use import AuthenticatedRuntimeContextV1Alpha1
from ace.intelligence.contracts.common import validate_product_id, validate_reference
from ace.intelligence.contracts.resource_feedback import (
    IntelligenceResourceCorrectionIntent,
    IntelligenceResourceFeedbackAdmissionV1Alpha1,
)
from ace.intelligence.contracts.resource_plane import IntelligenceResourceKind, IntelligenceResourceReferenceV1Alpha1

CLAIM_CORRECTION_REQUEST_VERSION = "ace.intelligence.claim-correction-request/v1alpha1"
CLAIM_CORRECTION_ADMISSION_VERSION = "ace.intelligence.claim-correction-admission/v1alpha1"

MAX_CLAIM_CORRECTION_EVIDENCE = 32
MAX_CLAIM_CORRECTION_NOTE_CHARS = 3_800


class _StrictFrozenContract(FrozenContract):
    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        strict=True,
        revalidate_instances="always",
        validate_default=True,
        allow_inf_nan=False,
    )


def _aware(value: datetime, *, name: str) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{name} must include a timezone")
    return value.astimezone(UTC)


class ClaimCorrectionRequestV1Alpha1(_StrictFrozenContract):
    """One idempotent actor request correcting one exact claim/citation pair."""

    contract: Literal["ace.intelligence.claim-correction-request/v1alpha1"] = CLAIM_CORRECTION_REQUEST_VERSION
    authenticated_context: AuthenticatedRuntimeContextV1Alpha1
    product_id: str
    authority_grant_ref: str
    request_key: str
    target: IntelligenceResourceReferenceV1Alpha1
    claim_id: str
    citation_id: str
    correction_intent: IntelligenceResourceCorrectionIntent
    note: str = Field(min_length=1, max_length=MAX_CLAIM_CORRECTION_NOTE_CHARS)
    evidence: tuple[IntelligenceResourceReferenceV1Alpha1, ...] = Field(
        default_factory=tuple, max_length=MAX_CLAIM_CORRECTION_EVIDENCE
    )
    requested_at: datetime
    correction_id: str | None = None
    correction_digest: str | None = None

    @field_validator("product_id")
    @classmethod
    def validate_scope(cls, value: str) -> str:
        return validate_product_id(value)

    @field_validator("authority_grant_ref", "request_key", "claim_id", "citation_id")
    @classmethod
    def validate_refs(cls, value: str, info) -> str:
        return validate_reference(value, name=info.field_name)

    @field_validator("note")
    @classmethod
    def validate_note(cls, value: str) -> str:
        if value != value.strip():
            raise ValueError("note must be trimmed")
        return value

    @field_validator("requested_at")
    @classmethod
    def normalize_requested_at(cls, value: datetime) -> datetime:
        return _aware(value, name="requested_at")

    @field_validator("evidence")
    @classmethod
    def normalize_evidence(cls, value):
        keys = [(item.resource_kind.value, item.resource_id, item.revision, item.resource_digest) for item in value]
        if len(keys) != len(set(keys)):
            raise ValueError("evidence references must be unique")
        return tuple(sorted(value, key=lambda item: (item.resource_kind.value, item.resource_id, item.revision)))

    @model_validator(mode="after")
    def validate_exact_scope_and_identity(self) -> Self:
        context = self.authenticated_context
        if context.product_id != self.product_id or self.target.product_id != self.product_id:
            raise ValueError("claim correction request crossed authenticated product scope")
        if not (context.authenticated_at <= self.requested_at < context.expires_at):
            raise ValueError("claim correction request fell outside its authentication window")
        if self.target.resource_kind is not IntelligenceResourceKind.BRIEF:
            raise ValueError("a claim-bound correction may only target a Brief resource")
        if any(item.product_id != self.product_id for item in self.evidence):
            raise ValueError("claim correction evidence crossed product scope")

        identity_material = {
            "product_id": self.product_id,
            "actor_ref": context.actor_ref,
            "request_key": self.request_key,
            "claim_id": self.claim_id,
            "citation_id": self.citation_id,
        }
        content_material = {
            **identity_material,
            "authority_grant_ref": self.authority_grant_ref,
            "target": self.target.model_dump(mode="json"),
            "correction_intent": self.correction_intent.value,
            "note": self.note,
            "evidence": [item.model_dump(mode="json") for item in self.evidence],
        }
        identity_hash = canonical_hash(identity_material)
        content_hash = canonical_hash(content_material)
        expected_id = f"claim_correction:{identity_hash[:32]}"
        expected_digest = f"sha256:{content_hash}"
        if self.correction_id is not None and self.correction_id != expected_id:
            raise ValueError("correction_id does not match actor-scoped request identity")
        if self.correction_digest is not None and self.correction_digest != expected_digest:
            raise ValueError("correction_digest does not match exact correction material")
        object.__setattr__(self, "correction_id", expected_id)
        object.__setattr__(self, "correction_digest", expected_digest)
        return self

    @property
    def feedback_note(self) -> str:
        return f"[claim:{self.claim_id}][citation:{self.citation_id}] {self.note}"


class ClaimCorrectionAdmissionV1Alpha1(_StrictFrozenContract):
    """Proof that the recorded proposal-only feedback was bound to this exact claim/citation."""

    contract: Literal["ace.intelligence.claim-correction-admission/v1alpha1"] = CLAIM_CORRECTION_ADMISSION_VERSION
    request: ClaimCorrectionRequestV1Alpha1
    feedback: IntelligenceResourceFeedbackAdmissionV1Alpha1

    @model_validator(mode="after")
    def validate_binding(self) -> Self:
        underlying = self.feedback.feedback.request
        if (
            underlying.product_id != self.request.product_id
            or underlying.target != self.request.target
            or underlying.correction_intent != self.request.correction_intent
            or underlying.evidence != self.request.evidence
            or underlying.authenticated_context.actor_ref != self.request.authenticated_context.actor_ref
            or underlying.note != self.request.feedback_note
        ):
            raise ValueError("claim correction admission does not prove the exact claim/citation-bound proposal")
        return self


__all__ = [
    "CLAIM_CORRECTION_ADMISSION_VERSION",
    "CLAIM_CORRECTION_REQUEST_VERSION",
    "ClaimCorrectionAdmissionV1Alpha1",
    "ClaimCorrectionRequestV1Alpha1",
]
```

- [ ] **Step 4: Run to verify pass**

Run: `uv run pytest tests/intelligence/test_claim_correction_contracts.py -v`
Expected: PASS (3 tests).

- [ ] **Step 5: Lint**

Run: `uv run ruff check ace/intelligence/contracts/claim_correction.py tests/intelligence/test_claim_correction_contracts.py --fix && uv run ruff format ace/intelligence/contracts/claim_correction.py tests/intelligence/test_claim_correction_contracts.py`

---

## Task 4: `ClaimBoundCorrectionService`

**Files:**
- Create: `ace/application/claim_bound_correction.py`
- Test: `tests/intelligence/test_claim_bound_correction_service.py`

**Interfaces:**
- Consumes: `IntelligenceResourceFeedbackService`,
  `IntelligenceResourceFeedbackTargetPort` (unchanged, from
  `ace/application/intelligence_resource_feedback.py`), Task 3 contracts.
- Produces: `ClaimBoundCorrectionService(targets=..., feedback=...).correct(
  request: ClaimCorrectionRequestV1Alpha1, *, evaluated_at: datetime) ->
  ClaimCorrectionAdmissionV1Alpha1`; `ClaimBoundCorrectionError`;
  `ClaimBoundCorrectionNotFound`. Consumed by Task 6 (HTTP wiring).

- [ ] **Step 1: Write the failing service tests**

Mirror `tests/intelligence/test_intelligence_resource_feedback.py`'s
`_Targets`/`_Authority`/`_store()` doubles exactly (same file already in the
repo), but seed `_Targets` with an `IntelligenceResourceRecordV1Alpha1`
whose `payload` is a real `BriefV1Alpha1`.

```python
# tests/intelligence/test_claim_bound_correction_service.py
from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from ace.application.claim_bound_correction import (
    ClaimBoundCorrectionError,
    ClaimBoundCorrectionNotFound,
    ClaimBoundCorrectionService,
)
from ace.application.intelligence_resource_feedback import IntelligenceResourceFeedbackService
from ace.core.contracts import canonical_json
from ace.core.runtime_use import AuthenticatedRuntimeContextV1Alpha1, AuthorityUseReceiptV1Alpha1
from ace.core.state import GovernedStateHeadPreconditionV1Alpha1, GovernedStateHeadV1
from ace.intelligence.contracts.claim_correction import ClaimCorrectionRequestV1Alpha1
from ace.intelligence.contracts.resource_feedback import IntelligenceResourceCorrectionIntent
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

pytestmark = pytest.mark.unit

PRODUCT = "product:claim-bound-correction"
ACTOR = "principal:corrector"
GRANT = "authority_grant:claim-bound-correction"
NOW = datetime(2026, 8, 18, 12, 0, tzinfo=UTC)


def _store() -> InMemoryImmutableRecordStore:
    return InMemoryImmutableRecordStore(
        governed_state_heads={
            ("authority_grant", PRODUCT, GRANT): GovernedStateHeadV1(
                state_kind="authority_grant",
                product_id=PRODUCT,
                state_id=GRANT,
                sequence=1,
                revision_id="authority_revision:claim-bound-correction",
                commit_receipt_id="authority_receipt:claim-bound-correction",
                updated_at=NOW - timedelta(minutes=10),
            )
        }
    )


def _context() -> AuthenticatedRuntimeContextV1Alpha1:
    return AuthenticatedRuntimeContextV1Alpha1(
        product_id=PRODUCT,
        actor_ref=ACTOR,
        authentication_receipt_ref="authentication_receipt:claim-bound-correction",
        authentication_receipt_digest="sha256:" + "a" * 64,
        authenticated_at=NOW - timedelta(minutes=5),
        expires_at=NOW + timedelta(hours=1),
    )


def _activation() -> ActivationRevisionReferenceV1Alpha1:
    return ActivationRevisionReferenceV1Alpha1(
        product_id=PRODUCT,
        activation_key="generic_intelligence",
        activation_id="domain_activation:" + "a" * 32,
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


def _target_reference(brief: BriefV1Alpha1) -> IntelligenceResourceReferenceV1Alpha1:
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


def _target_record(brief: BriefV1Alpha1) -> IntelligenceResourceRecordV1Alpha1:
    return IntelligenceResourceRecordV1Alpha1(
        reference=_target_reference(brief),
        availability=IntelligenceResourceAvailability.AVAILABLE,
        title=brief.title,
        payload=CanonicalJsonValueV1Alpha1(value_json=canonical_json(brief.model_dump(mode="json"))),
    )


class _Targets:
    def __init__(self, *records: IntelligenceResourceRecordV1Alpha1) -> None:
        self.records = {item.reference: item for item in records}

    async def load_exact(self, reference, *, evaluated_at):
        return self.records.get(reference)


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
            grant_ref=kwargs["grant_ref"],
            grant_hash="f" * 64,
            evaluated_at=kwargs["evaluated_at"],
            expires_at=NOW + timedelta(hours=1),
            state_head_precondition=GovernedStateHeadPreconditionV1Alpha1(
                state_kind="authority_grant",
                product_id=PRODUCT,
                state_id=GRANT,
                sequence=1,
                revision_id="authority_revision:claim-bound-correction",
                commit_receipt_id="authority_receipt:claim-bound-correction",
            ),
        )


def _request(brief: BriefV1Alpha1, **overrides) -> ClaimCorrectionRequestV1Alpha1:
    claim = brief.claims[0]
    fields = {
        "authenticated_context": _context(),
        "product_id": PRODUCT,
        "authority_grant_ref": GRANT,
        "request_key": "claim-correction:stable-1",
        "target": _target_reference(brief),
        "claim_id": str(claim.claim_id),
        "citation_id": str(claim.citation_ids[0]),
        "correction_intent": IntelligenceResourceCorrectionIntent.OUTDATED,
        "note": "The cited filing was later restated.",
        "requested_at": NOW,
    }
    fields.update(overrides)
    return ClaimCorrectionRequestV1Alpha1(**fields)


def _service(*records: IntelligenceResourceRecordV1Alpha1) -> ClaimBoundCorrectionService:
    targets = _Targets(*records)
    return ClaimBoundCorrectionService(
        targets=targets,
        feedback=IntelligenceResourceFeedbackService(records=_store(), targets=targets, authority=_Authority()),
    )


@pytest.mark.asyncio
async def test_binds_a_correction_to_the_exact_claim_and_citation() -> None:
    brief = _brief()
    admission = await _service(_target_record(brief)).correct(_request(brief), evaluated_at=NOW)

    assert admission.request.claim_id == str(brief.claims[0].claim_id)
    assert admission.feedback.feedback.request.note.startswith(f"[claim:{brief.claims[0].claim_id}]")
    assert admission.feedback.feedback.disposition == "recorded_proposal_only"
    assert admission.feedback.feedback.changes_target is False


@pytest.mark.asyncio
async def test_fails_closed_when_claim_id_is_not_on_the_target_brief() -> None:
    brief = _brief()
    with pytest.raises(ClaimBoundCorrectionNotFound, match="claim_id is not present"):
        await _service(_target_record(brief)).correct(
            _request(brief, claim_id="grounded_claim:" + "9" * 32), evaluated_at=NOW
        )


@pytest.mark.asyncio
async def test_fails_closed_when_citation_id_is_not_bound_to_the_claim() -> None:
    brief = _brief()
    with pytest.raises(ClaimBoundCorrectionNotFound, match="citation_id is not bound"):
        await _service(_target_record(brief)).correct(
            _request(brief, citation_id="citation:" + "9" * 32), evaluated_at=NOW
        )


@pytest.mark.asyncio
async def test_fails_closed_when_target_brief_is_unavailable() -> None:
    brief = _brief()
    with pytest.raises(ClaimBoundCorrectionError, match="unavailable"):
        await _service().correct(_request(brief), evaluated_at=NOW)


@pytest.mark.asyncio
async def test_never_mutates_the_target_and_stays_proposal_only() -> None:
    brief = _brief()
    admission = await _service(_target_record(brief)).correct(_request(brief), evaluated_at=NOW)

    assert admission.feedback.feedback.changes_source_trust is False
    assert admission.feedback.feedback.changes_ranking is False
    assert admission.feedback.feedback.triggers_recalculation is False
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest tests/intelligence/test_claim_bound_correction_service.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'ace.application.claim_bound_correction'`.

- [ ] **Step 3: Write `ace/application/claim_bound_correction.py`**

```python
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
```

- [ ] **Step 4: Run to verify pass**

Run: `uv run pytest tests/intelligence/test_claim_bound_correction_service.py -v`
Expected: PASS (5 tests).

- [ ] **Step 5: Lint**

Run: `uv run ruff check ace/application/claim_bound_correction.py tests/intelligence/test_claim_bound_correction_service.py --fix && uv run ruff format ace/application/claim_bound_correction.py tests/intelligence/test_claim_bound_correction_service.py`

---

## Task 5: Wire package exports

**Files:**
- Modify: `ace/intelligence/contracts/__init__.py` (add two import blocks +
  `__all__` entries, alphabetically near `agent_memory_recall`/
  `composition_policy` for `claim_correction`, and near
  `feedback`/`impact` for `grounded_ask`)
- Modify: `ace/application/__init__.py` (add two import blocks + `__all__`
  entries, alphabetically near `case_brief_synthesis`/
  `composition_policy_admission` for `claim_bound_correction`, and near
  `installed_pack_artifacts`/`intelligence_agent` for `grounded_ask`)

**Interfaces:**
- Consumes: Tasks 1-4 public symbols.
- Produces: `AskAnswerV1Alpha1`, `AskNoAnswerV1Alpha1`, `AskQuestionV1Alpha1`,
  `ClaimCorrectionAdmissionV1Alpha1`, `ClaimCorrectionRequestV1Alpha1`
  importable from `ace.intelligence`; `GroundedAskService`,
  `GroundedAskError`, `ClaimBoundCorrectionService`,
  `ClaimBoundCorrectionError`, `ClaimBoundCorrectionNotFound` importable
  from `ace.application`. Consumed by Task 6 (HTTP wiring, which imports
  from `ace.application` the same way `intelligence_resource_plane.py`'s
  Core host does).

- [ ] **Step 1: Write the failing import test**

```python
# tests/intelligence/test_grounded_ask_and_correction_exports.py
from __future__ import annotations

import pytest

pytestmark = pytest.mark.unit


def test_ask_contracts_are_exported_from_ace_intelligence() -> None:
    from ace.intelligence import AskAnswerV1Alpha1, AskNoAnswerV1Alpha1, AskQuestionV1Alpha1  # noqa: F401


def test_correction_contracts_are_exported_from_ace_intelligence() -> None:
    from ace.intelligence import ClaimCorrectionAdmissionV1Alpha1, ClaimCorrectionRequestV1Alpha1  # noqa: F401


def test_ask_and_correction_services_are_exported_from_ace_application() -> None:
    from ace.application import (  # noqa: F401
        ClaimBoundCorrectionError,
        ClaimBoundCorrectionNotFound,
        ClaimBoundCorrectionService,
        GroundedAskError,
        GroundedAskService,
    )
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest tests/intelligence/test_grounded_ask_and_correction_exports.py -v`
Expected: FAIL — `ImportError`.

- [ ] **Step 3: Add the import/`__all__` blocks**

In `ace/intelligence/contracts/__init__.py`, add (matching the existing
per-module block style exactly):

```python
from ace.intelligence.contracts.claim_correction import (
    CLAIM_CORRECTION_ADMISSION_VERSION,
    CLAIM_CORRECTION_REQUEST_VERSION,
    ClaimCorrectionAdmissionV1Alpha1,
    ClaimCorrectionRequestV1Alpha1,
)
```
and
```python
from ace.intelligence.contracts.grounded_ask import (
    ASK_ANSWER_VERSION,
    ASK_NO_ANSWER_VERSION,
    ASK_QUESTION_VERSION,
    MAX_ASK_CLAIMS,
    AskAnswerV1Alpha1,
    AskNoAnswerV1Alpha1,
    AskQuestionV1Alpha1,
)
```
placed alphabetically (ruff's isort will fix exact placement — run
`ruff check --fix` after adding), plus append the corresponding string
literals to the `__all__` list at the bottom of the file.

In `ace/application/__init__.py`, add:

```python
from ace.application.claim_bound_correction import (
    ClaimBoundCorrectionError,
    ClaimBoundCorrectionNotFound,
    ClaimBoundCorrectionService,
)
```
and
```python
from ace.application.grounded_ask import ASK_MAX_CANDIDATE_BRIEFS, GroundedAskError, GroundedAskService
```
plus the corresponding `__all__` entries, and also re-export the Task 1/3
contract symbols the Core host will need
(`AskQuestionV1Alpha1`, `AskAnswerV1Alpha1`, `AskNoAnswerV1Alpha1`,
`ClaimCorrectionRequestV1Alpha1`, `ClaimCorrectionAdmissionV1Alpha1`,
`IntelligenceResourceCorrectionIntent` if not already exported) by importing
them from `ace.intelligence.contracts.grounded_ask` /
`ace.intelligence.contracts.claim_correction` the same way line 629
(`from ace.intelligence.contracts.resource_feedback import (...)`) already
re-exports feedback contracts for `ace.application` consumers — check that
block first; if `IntelligenceResourceCorrectionIntent` is already
re-exported there, don't duplicate it.

- [ ] **Step 4: Run to verify pass**

Run: `uv run pytest tests/intelligence/test_grounded_ask_and_correction_exports.py -v`
Expected: PASS (3 tests).

- [ ] **Step 5: Lint (this step matters most here — isort ordering)**

Run: `uv run ruff check ace/intelligence/contracts/__init__.py ace/application/__init__.py --fix && uv run ruff format ace/intelligence/contracts/__init__.py ace/application/__init__.py`

---

## Task 6: HTTP wiring and router registration

**Files:**
- Create: `core/engine/core/grounded_ask.py`
- Create: `core/engine/core/claim_bound_correction.py`
- Create: `core/engine/api/grounded_ask.py`
- Modify: `core/engine/api/main.py` (import + `app.include_router(...)`,
  next to the existing `intelligence_resources_router` registration)
- Test: `tests/test_api_grounded_ask.py`

**Interfaces:**
- Consumes: Task 2 (`GroundedAskService`), Task 4
  (`ClaimBoundCorrectionService`), and the existing
  `core/engine/core/intelligence_resource_plane.py`
  (`intelligence_resource_projection_reader`, `IntelligenceResourceHttpRuntime`-style
  runtime dataclass pattern) and
  `core/engine/core/intelligence_resource_feedback.py`
  (`CoreIntelligenceResourceFeedbackTargets`, `_verified_claims` pattern) —
  both unchanged, imported directly.
- Produces: `POST /v1/intelligence/ask` (200, `AskAnswerV1Alpha1 |
  AskNoAnswerV1Alpha1`), `POST /v1/intelligence/ask/corrections` (201,
  `ClaimCorrectionAdmissionV1Alpha1`).

- [ ] **Step 1: Write the failing HTTP tests**

Mirror `tests/test_api_intelligence_resource_feedback.py`'s exact
`monkeypatch`/`dependency_overrides`/`ASGITransport` pattern.

```python
# tests/test_api_grounded_ask.py
from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from ace.application.intelligence_resource_plane import IntelligenceResourceProjectionBatch
from ace.core.contracts import canonical_json
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
        activation_id="domain_activation:" + "a" * 32,
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
    def __init__(self, *records) -> None:
        self.records = records

    async def read(self, **kwargs):
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
    monkeypatch.setattr("core.engine.core.grounded_ask.intelligence_resource_projection_reader", lambda store: _Reader(_brief_record(_brief())))
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_current_user] = lambda: claims
    app.dependency_overrides[ask_grounded_question_runtime] = lambda: AskGroundedQuestionHttpRuntime(records=records, authority=_Authority())
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
    app.dependency_overrides[claim_bound_correction_runtime] = lambda: ClaimCorrectionHttpRuntime(records=records, authority=_Authority())
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
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest tests/test_api_grounded_ask.py -v`
Expected: FAIL — `ModuleNotFoundError`.

- [ ] **Step 3: Write `core/engine/core/grounded_ask.py`**

Mirror `core/engine/core/intelligence_resource_plane.py`'s
`IntelligenceResourceHttpQueryV1`/`intelligence_resource_runtime`/
`_verified_claims`/`query_intelligence_resource_page` shape exactly, but
call `GroundedAskService` instead of `IntelligenceResourcePlaneService`
directly:

```python
"""Supported Core host for the governed grounded Ask (J7) surface."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from pydantic import BaseModel, ConfigDict, Field

from ace.application import (
    RESOURCE_QUERY_AUTHORITY,
    AskAnswerV1Alpha1,
    AskNoAnswerV1Alpha1,
    AskQuestionV1Alpha1,
    GroundedAskError,
    GroundedAskService,
    IntelligenceResourcePlaneAuthorizationPort,
    IntelligenceResourcePlaneService,
)
from ace.core import ImmutableRecordPersistenceError, ImmutableRecordStore
from core.engine.core.agent_composition_runtime import (
    GovernedCompositionAuthorityError,
    GovernedStateRuntimeUseResolver,
    persist_task_authentication_receipt,
)
from core.engine.core.db import pool
from core.engine.core.governed_state import SurrealGovernedStateStore
from core.engine.core.immutable_records import SurrealImmutableRecordStore
from core.engine.core.intelligence_resource_plane import intelligence_resource_projection_reader


class AskGroundedQuestionHttpRequestV1(BaseModel):
    """User material only; actor, product, and time come from the verified host."""

    model_config = ConfigDict(extra="forbid")

    authority_grant_ref: str = Field(min_length=1, max_length=240)
    question: str = Field(min_length=1, max_length=2_000)
    subject_refs: tuple[str, ...] = Field(default_factory=tuple, max_length=256)
    as_of: datetime
    available_at: datetime
    max_claims: int = Field(default=5, ge=1, le=20)


@dataclass(frozen=True, slots=True)
class AskGroundedQuestionHttpRuntime:
    records: ImmutableRecordStore
    authority: IntelligenceResourcePlaneAuthorizationPort


class AskGroundedQuestionHttpUnauthenticated(RuntimeError):
    pass


class AskGroundedQuestionHttpDenied(RuntimeError):
    pass


class AskGroundedQuestionHttpConflict(RuntimeError):
    pass


class AskGroundedQuestionHttpUnavailable(RuntimeError):
    pass


def ask_grounded_question_runtime() -> AskGroundedQuestionHttpRuntime:
    records = SurrealImmutableRecordStore(pool)
    return AskGroundedQuestionHttpRuntime(
        records=records,
        authority=GovernedStateRuntimeUseResolver(governed_state=SurrealGovernedStateStore(pool)),
    )


def _verified_claims(user: dict) -> tuple[str, str]:
    actor_ref = user.get("sub")
    product_id = user.get("product")
    authorities = user.get("authorities")
    if not isinstance(actor_ref, str) or not actor_ref or not isinstance(product_id, str) or not product_id:
        raise AskGroundedQuestionHttpUnauthenticated("verified token lacks product scope")
    if not isinstance(authorities, list) or RESOURCE_QUERY_AUTHORITY not in authorities:
        raise AskGroundedQuestionHttpDenied("intelligence read authority is required")
    return actor_ref, product_id


async def ask_grounded_question(
    *,
    selector: AskGroundedQuestionHttpRequestV1,
    user: dict,
    runtime: AskGroundedQuestionHttpRuntime,
) -> AskAnswerV1Alpha1 | AskNoAnswerV1Alpha1:
    actor_ref, product_id = _verified_claims(user)
    now = datetime.now(UTC)
    try:
        authentication = await persist_task_authentication_receipt(
            claims={**user, "sub": actor_ref, "product": product_id},
            verified_at=now,
            store=runtime.records,
            verification_policy_ref="jwt_verification_policy:v1",
        )
        request = AskQuestionV1Alpha1(
            authenticated_context=authentication.runtime_context(),
            product_id=product_id,
            authority_grant_ref=selector.authority_grant_ref,
            question=selector.question,
            subject_refs=selector.subject_refs,
            as_of=selector.as_of,
            available_at=selector.available_at,
            max_claims=selector.max_claims,
        )
        resource_plane = IntelligenceResourcePlaneService(
            reader=intelligence_resource_projection_reader(runtime.records),
            authority=runtime.authority,
        )
        return await GroundedAskService(resource_plane=resource_plane).ask(request, evaluated_at=now)
    except GovernedCompositionAuthorityError as exc:
        raise AskGroundedQuestionHttpDenied("current Core grant denied the question") from exc
    except ImmutableRecordPersistenceError as exc:
        raise AskGroundedQuestionHttpUnavailable("authentication evidence is unavailable") from exc
    except (GroundedAskError, TypeError, ValueError) as exc:
        raise AskGroundedQuestionHttpConflict("ask request could not preserve its exact contract") from exc


__all__ = [
    "AskGroundedQuestionHttpConflict",
    "AskGroundedQuestionHttpDenied",
    "AskGroundedQuestionHttpRequestV1",
    "AskGroundedQuestionHttpRuntime",
    "AskGroundedQuestionHttpUnauthenticated",
    "AskGroundedQuestionHttpUnavailable",
    "ask_grounded_question",
    "ask_grounded_question_runtime",
]
```

- [ ] **Step 4: Write `core/engine/core/claim_bound_correction.py`**

Mirror `core/engine/core/intelligence_resource_feedback.py` exactly, reusing
its `CoreIntelligenceResourceFeedbackTargets` directly (it only reads
`.authenticated_context`/`.product_id`/`.authority_grant_ref` off the
`request` it's given, which `ClaimCorrectionRequestV1Alpha1` also provides):

```python
"""Supported Core host for the governed claim-bound correction (J8) surface."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from pydantic import BaseModel, ConfigDict, Field

from ace.application import (
    RESOURCE_FEEDBACK_AUTHORITY,
    ClaimBoundCorrectionError,
    ClaimBoundCorrectionNotFound,
    ClaimBoundCorrectionService,
    ClaimCorrectionAdmissionV1Alpha1,
    ClaimCorrectionRequestV1Alpha1,
    IntelligenceResourceCorrectionIntent,
    IntelligenceResourceFeedbackDenied,
    IntelligenceResourceFeedbackError,
    IntelligenceResourceFeedbackService,
    IntelligenceResourceFeedbackUnavailable,
    IntelligenceResourceKind,
)
from ace.core import ImmutableRecordPersistenceError, ImmutableRecordStore
from core.engine.core.agent_composition_runtime import (
    GovernedCompositionAuthorityError,
    GovernedStateRuntimeUseResolver,
    persist_task_authentication_receipt,
)
from core.engine.core.db import pool
from core.engine.core.governed_state import SurrealGovernedStateStore
from core.engine.core.immutable_records import SurrealImmutableRecordStore
from core.engine.core.intelligence_resource_feedback import CoreIntelligenceResourceFeedbackTargets
from core.engine.core.intelligence_resource_plane import intelligence_resource_projection_reader


class ClaimCorrectionHttpReferenceV1(BaseModel):
    model_config = ConfigDict(extra="forbid")

    contract: str
    product_id: str
    resource_kind: IntelligenceResourceKind
    resource_id: str
    resource_digest: str
    resource_contract: str
    revision: int
    as_of: datetime
    available_at: datetime


class ClaimCorrectionHttpRequestV1(BaseModel):
    model_config = ConfigDict(extra="forbid")

    authority_grant_ref: str = Field(min_length=1, max_length=240)
    request_key: str = Field(min_length=1, max_length=240)
    target: ClaimCorrectionHttpReferenceV1
    claim_id: str = Field(min_length=1, max_length=240)
    citation_id: str = Field(min_length=1, max_length=240)
    correction_intent: IntelligenceResourceCorrectionIntent
    note: str = Field(min_length=1, max_length=3_800)
    evidence: tuple[ClaimCorrectionHttpReferenceV1, ...] = Field(default_factory=tuple, max_length=32)


@dataclass(frozen=True, slots=True)
class ClaimCorrectionHttpRuntime:
    records: ImmutableRecordStore
    authority: GovernedStateRuntimeUseResolver


class ClaimCorrectionHttpUnauthenticated(RuntimeError):
    pass


class ClaimCorrectionHttpDenied(RuntimeError):
    pass


class ClaimCorrectionHttpConflict(RuntimeError):
    pass


class ClaimCorrectionHttpUnavailable(RuntimeError):
    pass


def claim_bound_correction_runtime() -> ClaimCorrectionHttpRuntime:
    records = SurrealImmutableRecordStore(pool)
    return ClaimCorrectionHttpRuntime(
        records=records,
        authority=GovernedStateRuntimeUseResolver(governed_state=SurrealGovernedStateStore(pool)),
    )


def _verified_claims(user: dict) -> tuple[str, str]:
    actor_ref = user.get("sub")
    product_id = user.get("product")
    authorities = user.get("authorities")
    if not isinstance(actor_ref, str) or not actor_ref or not isinstance(product_id, str) or not product_id:
        raise ClaimCorrectionHttpUnauthenticated("verified token lacks product scope")
    if not isinstance(authorities, list) or RESOURCE_FEEDBACK_AUTHORITY not in authorities:
        raise ClaimCorrectionHttpDenied("intelligence feedback authority is required")
    return actor_ref, product_id


async def correct_claim_bound_ask_answer(
    *,
    selector: ClaimCorrectionHttpRequestV1,
    user: dict,
    runtime: ClaimCorrectionHttpRuntime,
) -> ClaimCorrectionAdmissionV1Alpha1:
    actor_ref, product_id = _verified_claims(user)
    now = datetime.now(UTC)
    try:
        authentication = await persist_task_authentication_receipt(
            claims={**user, "sub": actor_ref, "product": product_id},
            verified_at=now,
            store=runtime.records,
            verification_policy_ref="jwt_verification_policy:v1",
        )
        request = ClaimCorrectionRequestV1Alpha1(
            authenticated_context=authentication.runtime_context(),
            product_id=product_id,
            authority_grant_ref=selector.authority_grant_ref,
            request_key=selector.request_key,
            target=selector.target.model_dump(mode="python"),
            claim_id=selector.claim_id,
            citation_id=selector.citation_id,
            correction_intent=selector.correction_intent,
            note=selector.note,
            evidence=tuple(item.model_dump(mode="python") for item in selector.evidence),
            requested_at=now,
        )
        targets = CoreIntelligenceResourceFeedbackTargets(
            reader=intelligence_resource_projection_reader(runtime.records),
            request=request,
        )
        service = ClaimBoundCorrectionService(
            targets=targets,
            feedback=IntelligenceResourceFeedbackService(
                records=runtime.records, targets=targets, authority=runtime.authority
            ),
        )
        return await service.correct(request, evaluated_at=now)
    except ClaimBoundCorrectionNotFound as exc:
        raise ClaimCorrectionHttpConflict(str(exc)) from exc
    except IntelligenceResourceFeedbackDenied as exc:
        raise ClaimCorrectionHttpDenied("current Core grant denied the correction") from exc
    except GovernedCompositionAuthorityError as exc:
        raise ClaimCorrectionHttpDenied("current Core grant denied the correction") from exc
    except ImmutableRecordPersistenceError as exc:
        raise ClaimCorrectionHttpUnavailable("correction evidence storage is unavailable") from exc
    except IntelligenceResourceFeedbackUnavailable as exc:
        raise ClaimCorrectionHttpUnavailable("correction evidence storage is unavailable") from exc
    except (ClaimBoundCorrectionError, IntelligenceResourceFeedbackError, TypeError, ValueError) as exc:
        raise ClaimCorrectionHttpConflict(str(exc)) from exc


__all__ = [
    "ClaimCorrectionHttpConflict",
    "ClaimCorrectionHttpDenied",
    "ClaimCorrectionHttpReferenceV1",
    "ClaimCorrectionHttpRequestV1",
    "ClaimCorrectionHttpRuntime",
    "ClaimCorrectionHttpUnauthenticated",
    "ClaimCorrectionHttpUnavailable",
    "claim_bound_correction_runtime",
    "correct_claim_bound_ask_answer",
]
```

- [ ] **Step 5: Write `core/engine/api/grounded_ask.py`**

```python
"""HTTP transport for the governed grounded Ask and claim-bound correction surface."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status

from core.engine.core.auth import get_current_user
from core.engine.core.claim_bound_correction import (
    ClaimCorrectionAdmissionV1Alpha1,
    ClaimCorrectionHttpConflict,
    ClaimCorrectionHttpDenied,
    ClaimCorrectionHttpRequestV1,
    ClaimCorrectionHttpRuntime,
    ClaimCorrectionHttpUnauthenticated,
    ClaimCorrectionHttpUnavailable,
    claim_bound_correction_runtime,
    correct_claim_bound_ask_answer,
)
from core.engine.core.grounded_ask import (
    AskGroundedQuestionHttpConflict,
    AskGroundedQuestionHttpDenied,
    AskGroundedQuestionHttpRequestV1,
    AskGroundedQuestionHttpRuntime,
    AskGroundedQuestionHttpUnauthenticated,
    AskGroundedQuestionHttpUnavailable,
    ask_grounded_question,
    ask_grounded_question_runtime,
)
from ace.application import AskAnswerV1Alpha1, AskNoAnswerV1Alpha1

router = APIRouter(prefix="/v1/intelligence/ask", tags=["intelligence-ask"])


@router.post("", response_model=AskAnswerV1Alpha1 | AskNoAnswerV1Alpha1)
async def ask_intelligence_question(
    selector: AskGroundedQuestionHttpRequestV1,
    user: dict = Depends(get_current_user),
    runtime: AskGroundedQuestionHttpRuntime = Depends(ask_grounded_question_runtime),
) -> AskAnswerV1Alpha1 | AskNoAnswerV1Alpha1:
    """Answer one question from authorized Brief claims, or refuse honestly."""

    try:
        return await ask_grounded_question(selector=selector, user=user, runtime=runtime)
    except AskGroundedQuestionHttpUnauthenticated as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc)) from exc
    except AskGroundedQuestionHttpDenied as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Intelligence ask denied") from exc
    except AskGroundedQuestionHttpUnavailable as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Intelligence ask evidence is unavailable",
        ) from exc
    except AskGroundedQuestionHttpConflict as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Intelligence ask could not preserve its exact contract",
        ) from exc


@router.post(
    "/corrections",
    response_model=ClaimCorrectionAdmissionV1Alpha1,
    status_code=status.HTTP_201_CREATED,
)
async def create_claim_bound_correction(
    selector: ClaimCorrectionHttpRequestV1,
    user: dict = Depends(get_current_user),
    runtime: ClaimCorrectionHttpRuntime = Depends(claim_bound_correction_runtime),
) -> ClaimCorrectionAdmissionV1Alpha1:
    """Bind a correction to one exact claim/citation and record it as a proposal only."""

    try:
        return await correct_claim_bound_ask_answer(selector=selector, user=user, runtime=runtime)
    except ClaimCorrectionHttpUnauthenticated as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc)) from exc
    except ClaimCorrectionHttpDenied as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Intelligence correction denied") from exc
    except ClaimCorrectionHttpUnavailable as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Intelligence correction storage is unavailable",
        ) from exc
    except ClaimCorrectionHttpConflict as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc


__all__ = ["router"]
```

- [ ] **Step 6: Register the router in `core/engine/api/main.py`**

Add, next to the existing `intelligence_resources_router` import/include
(around line 668/682):

```python
from core.engine.api.grounded_ask import router as grounded_ask_router
```
and
```python
app.include_router(grounded_ask_router)
```

- [ ] **Step 7: Run to verify pass**

Run: `uv run pytest tests/test_api_grounded_ask.py -v`
Expected: PASS (3 tests). If `CoreIntelligenceResourceFeedbackTargets`
duck-typing on `ClaimCorrectionRequestV1Alpha1` fails because that class
checks `isinstance` anywhere (it shouldn't, based on the research read of
`core/engine/core/intelligence_resource_feedback.py:87-126` — it only
attribute-accesses), fall back to constructing a small local
`_ClaimCorrectionFeedbackTargets` adapter in
`core/engine/core/claim_bound_correction.py` with the same body instead of
importing the Core class.

- [ ] **Step 8: Lint**

Run: `uv run ruff check core/engine/core/grounded_ask.py core/engine/core/claim_bound_correction.py core/engine/api/grounded_ask.py core/engine/api/main.py tests/test_api_grounded_ask.py --fix && uv run ruff format core/engine/core/grounded_ask.py core/engine/core/claim_bound_correction.py core/engine/api/grounded_ask.py core/engine/api/main.py tests/test_api_grounded_ask.py`

---

## Task 7: Full verification and commit

- [ ] **Step 1: Run the full focused test slice**

Run:
```
uv run pytest tests/intelligence/test_grounded_ask_contracts.py \
  tests/intelligence/test_grounded_ask_service.py \
  tests/intelligence/test_claim_correction_contracts.py \
  tests/intelligence/test_claim_bound_correction_service.py \
  tests/intelligence/test_grounded_ask_and_correction_exports.py \
  tests/test_api_grounded_ask.py -v
```
Expected: all PASS.

- [ ] **Step 2: Run the broader regression slice for touched shared files**

Run:
```
uv run pytest tests/intelligence tests/test_api_intelligence_resources.py \
  tests/test_api_intelligence_resource_feedback.py -m unit -v
```
Expected: all PASS (proves the additive `__init__.py`/router changes did not
break the sibling resource-plane/feedback surfaces).

- [ ] **Step 3: Lint the whole diff**

Run: `uv run ruff check . && uv run ruff format --check .`
Expected: clean. Fix any remaining issues with `--fix`/`ruff format .` and
re-run Steps 1-2 if any fix touches behavior (not just formatting).

- [ ] **Step 4: Confirm MCP surface and ace/core are untouched**

Run: `git diff --stat -- ace_mcp_client ace/core`
Expected: empty output.

- [ ] **Step 5: Review the full diff**

Run: `git status && git diff --stat`

- [ ] **Step 6: Commit**

```bash
git add ace/intelligence/contracts/grounded_ask.py ace/intelligence/contracts/claim_correction.py \
  ace/application/grounded_ask.py ace/application/claim_bound_correction.py \
  ace/intelligence/contracts/__init__.py ace/application/__init__.py \
  core/engine/core/grounded_ask.py core/engine/core/claim_bound_correction.py \
  core/engine/api/grounded_ask.py core/engine/api/main.py \
  tests/intelligence/test_grounded_ask_contracts.py tests/intelligence/test_grounded_ask_service.py \
  tests/intelligence/test_claim_correction_contracts.py tests/intelligence/test_claim_bound_correction_service.py \
  tests/intelligence/test_grounded_ask_and_correction_exports.py tests/test_api_grounded_ask.py \
  docs/superpowers/plans/2026-08-18-grounded-ask-and-correction.md
git commit -m "PI8: add server-side grounded Ask and claim-bound correction"
```
