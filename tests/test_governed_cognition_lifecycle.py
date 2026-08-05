"""E1-E rollback, expiry, retirement, and authority gates."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from core.engine.cognition.catalog import CatalogRecipeView, build_default_catalog
from core.engine.cognition.contracts import CognitionHeadV1, CognitionScopeV1, ScopeKind
from core.engine.cognition.discovery import (
    CandidateDisposition,
    CognitionDiscoveryBudgetV1,
    DiscoveredRecipe,
    select_recipes,
)
from core.engine.cognition.governance import ActorClass, ReviewActorV1
from core.engine.cognition.lifecycle import LifecycleAction, build_lifecycle_transition


def _fixture():
    catalog = build_default_catalog()
    revision = catalog.recipe_revision("coding_intelligence")
    assert revision is not None
    head = next(item for item in catalog.store.heads() if item.cognition_id == revision.identity.cognition_id)
    return revision, head


def _human() -> ReviewActorV1:
    return ReviewActorV1(
        actor_id="user:reviewer",
        actor_class=ActorClass.HUMAN,
        authorities=("cognition-review",),
    )


def _product_head(revision, *, generation: int = 1) -> CognitionHeadV1:
    return CognitionHeadV1(
        cognition_id=str(revision.identity.cognition_id),
        scope=CognitionScopeV1(kind=ScopeKind.PRODUCT, product_id="product:test"),
        active_revision_id=str(revision.revision_id),
        generation=generation,
        authority_receipt_id="cognition_review:test",
    )


def test_model_cannot_disable_active_cognition() -> None:
    revision, _ = _fixture()
    head = _product_head(revision)
    with pytest.raises(PermissionError, match="human_authority_required"):
        build_lifecycle_transition(
            head=head,
            current_revision=revision,
            target_revision=None,
            product_id="product:test",
            review_request_id="review:disable",
            actor=ReviewActorV1(actor_id="model:test", actor_class=ActorClass.MODEL),
            action=LifecycleAction.DISABLE,
            rationale="No authority.",
            expected_generation=1,
        )


def test_retirement_moves_head_without_mutating_revision() -> None:
    revision, _ = _fixture()
    head = _product_head(revision)
    receipt, retired = build_lifecycle_transition(
        head=head,
        current_revision=revision,
        target_revision=None,
        product_id="product:test",
        review_request_id="review:retire",
        actor=_human(),
        action=LifecycleAction.RETIRE,
        rationale="Retire after human review.",
        expected_generation=1,
    )
    assert retired.head_id == head.head_id
    assert retired.active_revision_id == revision.revision_id
    assert retired.generation == 2
    assert retired.lifecycle == "retired"
    assert retired.authority_receipt_id == receipt.receipt_id
    assert revision.material_hash == build_default_catalog().recipe_revision("coding_intelligence").material_hash


def test_expired_active_head_is_filtered_before_scoring() -> None:
    revision, _ = _fixture()
    expired = CognitionHeadV1(
        cognition_id=str(revision.identity.cognition_id),
        scope=CognitionScopeV1(kind=ScopeKind.PRODUCT, product_id="product:test"),
        active_revision_id=str(revision.revision_id),
        generation=2,
        authority_receipt_id="cognition_lifecycle:expired",
        expires_at=datetime.now(timezone.utc) - timedelta(seconds=1),
    )
    result = select_recipes(
        (
            DiscoveredRecipe(
                view=CatalogRecipeView(
                    slug="coding_intelligence",
                    revision=revision,
                    runtime_view=build_default_catalog().recipe("coding_intelligence"),
                    disciplines=(),
                    task_types=(),
                ),
                head=expired,
            ),
        ),
        product_id="product:test",
        request_id="task:expired",
        budget=CognitionDiscoveryBudgetV1.for_depth(1),
        score=lambda _recipe: 1.0,
        dependency_available=lambda _dependency: True,
    )
    assert not result.selected
    assert result.receipt.candidates[0].disposition is CandidateDisposition.FILTERED
    assert result.receipt.candidates[0].reason == "head_expired"


def test_rollback_requires_distinct_revision_of_same_identity() -> None:
    revision, _ = _fixture()
    head = _product_head(revision)
    with pytest.raises(RuntimeError, match="distinct prior revision"):
        build_lifecycle_transition(
            head=head,
            current_revision=revision,
            target_revision=revision,
            product_id="product:test",
            review_request_id="review:rollback",
            actor=_human(),
            action=LifecycleAction.ROLLBACK,
            rationale="No-op rollback is invalid.",
            expected_generation=1,
        )
