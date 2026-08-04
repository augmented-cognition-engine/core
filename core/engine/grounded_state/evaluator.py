"""Deterministic, provider-free evaluation for TP0 temporal reference corpora."""

from __future__ import annotations

import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Literal, Mapping

from pydantic import Field, ValidationError

from core.engine.grounded_state.contracts import FrozenContract
from core.engine.grounded_state.corpus import (
    REQUIRED_MAINTAINER_REVIEW_CASE_KEYS,
    REQUIRED_REFERENCE_CATEGORIES,
    TEMPORAL_REFERENCE_CORPUS_VERSION,
    CorpusMaturity,
    ReferenceCategory,
    RelationshipClassification,
    RelationshipEndpointKind,
    ReviewDecision,
    ReviewRequirement,
    ReviewStatus,
    TemporalReferenceCaseV1,
    TemporalReferenceCorpusV1,
)

TEMPORAL_REFERENCE_EVALUATION_VERSION = "ace.grounded-state.temporal-reference-evaluation/v1"


class ContractValidationFailureV1(FrozenContract):
    location: str = Field(min_length=1, max_length=1_000)
    message: str = Field(min_length=1, max_length=2_000)


class EvidenceIdentityOccurrenceV1(FrozenContract):
    case_key: str = Field(min_length=1, max_length=120)
    input_key: str = Field(min_length=1, max_length=80)


class DuplicateEvidenceIdentityV1(FrozenContract):
    evidence_id: str = Field(min_length=1, max_length=240)
    occurrences: tuple[EvidenceIdentityOccurrenceV1, ...] = Field(min_length=2, max_length=200)
    matches_declared_expectation: bool


class TemporalReferenceEvaluationV1(FrozenContract):
    contract_version: Literal["ace.grounded-state.temporal-reference-evaluation/v1"] = (
        TEMPORAL_REFERENCE_EVALUATION_VERSION
    )
    corpus_contract_version: str | None = None
    maturity: CorpusMaturity | None = None
    total_cases: int = Field(ge=0)
    validated_cases: int = Field(ge=0)
    category_counts: dict[str, int]
    contract_validation_failures: tuple[ContractValidationFailureV1, ...]
    duplicate_case_identities: tuple[str, ...]
    duplicate_evidence_identities: tuple[DuplicateEvidenceIdentityV1, ...]
    missing_required_categories: tuple[ReferenceCategory, ...]
    unreviewed_subjective_expectations: tuple[str, ...]
    unaccepted_subjective_expectations: tuple[str, ...]
    corpus_hash: str | None = None
    contract_valid: bool
    candidate_complete: bool
    frozen_acceptance_ready: bool


def _validation_failures(exc: ValidationError) -> tuple[ContractValidationFailureV1, ...]:
    failures = []
    for error in exc.errors(include_url=False):
        location = ".".join(str(item) for item in error["loc"]) or "corpus"
        failures.append(ContractValidationFailureV1(location=location, message=error["msg"]))
    return tuple(failures)


def evaluate_temporal_reference_corpus(payload: Mapping[str, Any]) -> TemporalReferenceEvaluationV1:
    """Validate and summarize a corpus without databases, network access, or model providers."""
    raw_cases = payload.get("cases")
    raw_cases = raw_cases if isinstance(raw_cases, list) else []
    total_cases = len(raw_cases)

    logical_keys = [item.get("case_key") for item in raw_cases if isinstance(item, dict)]
    duplicate_case_identities = {
        str(case_key) for case_key, count in Counter(logical_keys).items() if case_key is not None and count > 1
    }

    valid_cases: list[TemporalReferenceCaseV1] = []
    case_failures: list[ContractValidationFailureV1] = []
    for index, raw_case in enumerate(raw_cases):
        try:
            valid_cases.append(TemporalReferenceCaseV1.model_validate(raw_case))
        except ValidationError as exc:
            for failure in _validation_failures(exc):
                case_failures.append(
                    ContractValidationFailureV1(
                        location=f"cases.{index}.{failure.location}",
                        message=failure.message,
                    )
                )

    computed_ids = [case.case_id() for case in valid_cases]
    duplicate_case_identities.update(case_id for case_id, count in Counter(computed_ids).items() if count > 1)

    corpus: TemporalReferenceCorpusV1 | None = None
    corpus_failures: tuple[ContractValidationFailureV1, ...] = ()
    try:
        corpus = TemporalReferenceCorpusV1.model_validate(payload)
    except ValidationError as exc:
        corpus_failures = _validation_failures(exc)

    failures_by_identity = {
        (failure.location, failure.message): failure for failure in (*case_failures, *corpus_failures)
    }
    failures = tuple(sorted(failures_by_identity.values(), key=lambda failure: (failure.location, failure.message)))

    category_counts = {category.value: 0 for category in ReferenceCategory}
    for case in valid_cases:
        for category in case.categories:
            category_counts[category.value] += 1
    category_counts = {key: value for key, value in category_counts.items() if value}
    covered_categories = {category for case in valid_cases for category in case.categories}
    missing_required_categories = tuple(sorted(REQUIRED_REFERENCE_CATEGORIES - covered_categories, key=str))

    occurrences: dict[str, list[EvidenceIdentityOccurrenceV1]] = defaultdict(list)
    declared_duplicate_occurrences: dict[str, set[tuple[str, str]]] = defaultdict(set)
    for case in valid_cases:
        evidence_by_key = {item.input_key: item.record.evidence_id() for item in case.evidence}
        for item in case.evidence:
            evidence_id = item.record.evidence_id()
            occurrences[evidence_id].append(
                EvidenceIdentityOccurrenceV1(case_key=case.case_key, input_key=item.input_key)
            )
        for relationship in case.expected.relationships:
            if relationship.classification not in {
                RelationshipClassification.EXACT_REPLAY,
                RelationshipClassification.DUPLICATE_SOURCE,
            }:
                continue
            endpoints = (relationship.subject, relationship.object)
            keys = {
                endpoint.identity
                for endpoint in endpoints
                if endpoint is not None and endpoint.kind is RelationshipEndpointKind.EVIDENCE
            }
            identities = {evidence_by_key[key] for key in keys if key in evidence_by_key}
            if len(keys) >= 2 and len(identities) == 1:
                evidence_id = identities.pop()
                declared_duplicate_occurrences[evidence_id].update((case.case_key, key) for key in keys)
    duplicate_evidence = tuple(
        DuplicateEvidenceIdentityV1(
            evidence_id=evidence_id,
            occurrences=tuple(sorted(items, key=lambda item: (item.case_key, item.input_key))),
            matches_declared_expectation=(
                {(item.case_key, item.input_key) for item in items}
                == declared_duplicate_occurrences.get(evidence_id, set())
            ),
        )
        for evidence_id, items in sorted(occurrences.items())
        if len(items) > 1
    )

    valid_case_by_key = {case.case_key: case for case in valid_cases}
    required_review_keys = set(REQUIRED_MAINTAINER_REVIEW_CASE_KEYS)
    required_review_keys.update(
        case.case_key for case in valid_cases if case.review.requirement is ReviewRequirement.MAINTAINER_ADJUDICATION
    )
    unreviewed = tuple(
        sorted(
            case_key
            for case_key in required_review_keys
            if case_key not in valid_case_by_key
            or valid_case_by_key[case_key].review.status is not ReviewStatus.COMPLETED
        )
    )
    unaccepted = tuple(
        sorted(
            case_key
            for case_key in required_review_keys
            if case_key not in valid_case_by_key
            or valid_case_by_key[case_key].review.status is not ReviewStatus.COMPLETED
            or any(
                judgment.decision is not ReviewDecision.ACCEPTED
                for judgment in valid_case_by_key[case_key].review.judgments
            )
        )
    )
    maturity = corpus.maturity if corpus is not None else None
    contract_valid = corpus is not None and not failures and not duplicate_case_identities
    candidate_complete = (
        contract_valid
        and total_cases == 40
        and not missing_required_categories
        and all(item.matches_declared_expectation for item in duplicate_evidence)
    )
    frozen_acceptance_ready = candidate_complete and maturity is CorpusMaturity.FROZEN and not unaccepted

    return TemporalReferenceEvaluationV1(
        corpus_contract_version=(
            corpus.contract_version
            if corpus is not None
            else str(payload.get("contract_version") or TEMPORAL_REFERENCE_CORPUS_VERSION)
        ),
        maturity=maturity,
        total_cases=total_cases,
        validated_cases=len(valid_cases),
        category_counts=category_counts,
        contract_validation_failures=failures,
        duplicate_case_identities=tuple(sorted(duplicate_case_identities)),
        duplicate_evidence_identities=duplicate_evidence,
        missing_required_categories=missing_required_categories,
        unreviewed_subjective_expectations=unreviewed,
        unaccepted_subjective_expectations=unaccepted,
        corpus_hash=corpus.corpus_hash() if corpus is not None else None,
        contract_valid=contract_valid,
        candidate_complete=candidate_complete,
        frozen_acceptance_ready=frozen_acceptance_ready,
    )


def evaluate_temporal_reference_file(path: str | Path) -> TemporalReferenceEvaluationV1:
    """Load and evaluate one JSON corpus file."""
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("temporal reference corpus must be a JSON object")
    return evaluate_temporal_reference_corpus(payload)
