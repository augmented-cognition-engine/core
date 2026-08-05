"""E1-D progressive discovery, budget, and exact-use receipt gates."""

from __future__ import annotations

import pytest

from core.engine.cognition.catalog import CatalogRecipeView, build_default_catalog
from core.engine.cognition.contracts import (
    CognitionDependencyV1,
    CognitionHeadV1,
    CognitionIdentityV1,
    CognitionOwnerV1,
    CognitionRevisionV1,
    CognitionScopeV1,
    CognitionSourceV1,
    CognitionType,
    OwnerKind,
    ScopeKind,
    canonical_hash,
)
from core.engine.cognition.discovery import (
    CandidateDisposition,
    CognitionDiscoveryBudgetV1,
    CognitionPhaseUseV1,
    CognitionUseReceiptV1,
    DiscoveredRecipe,
    normalize_selection_receipt,
    normalize_use_receipt,
    select_recipes,
)
from core.engine.cognition.legacy_adapters import meta_skill_from_body


def _package_candidates() -> tuple[DiscoveredRecipe, ...]:
    catalog = build_default_catalog()
    heads = {item.cognition_id: item for item in catalog.store.heads()}
    return tuple(
        DiscoveredRecipe(view=view, head=heads[str(view.revision.identity.cognition_id)])
        for view in catalog.recipe_views()
    )


def _available(_dependency: CognitionDependencyV1) -> bool:
    return True


def test_frozen_depth_budget_defaults_and_larger_override_authority() -> None:
    assert CognitionDiscoveryBudgetV1.for_depth(1).model_dump(mode="json") == {
        "contract_version": "cognition-discovery-budget-v1",
        "depth": 1,
        "level0_candidate_limit": 64,
        "selected_revision_limit": 4,
        "level0_serialized_bytes": 24_576,
        "level1_cognition_tokens": 256,
        "level2_resource_tokens": 0,
        "level2_artifact_fetches": 0,
        "selection_provider_calls": 0,
        "selection_provider_cost_usd": 0.0,
        "remaining_task_model_calls": None,
        "remaining_task_tokens": None,
        "remaining_task_cost_usd": None,
    }
    assert CognitionDiscoveryBudgetV1.for_depth(4).selected_revision_limit == 8
    with pytest.raises(ValueError, match="policy_authority_required"):
        CognitionDiscoveryBudgetV1.for_depth(1, selected_revision_limit=5)


def test_selection_is_deterministic_bounded_and_provider_free() -> None:
    candidates = _package_candidates()
    scores = {
        "coding_intelligence": 0.9,
        "verification_intelligence": 0.8,
        "domain_specific_intelligence": 0.7,
    }
    kwargs = {
        "product_id": "product:test",
        "request_id": "task:test",
        "budget": CognitionDiscoveryBudgetV1.for_depth(2, selected_revision_limit=2),
        "score": lambda recipe: scores.get(recipe.slug, 0.1),
        "dependency_available": _available,
    }
    first = select_recipes(candidates, **kwargs)
    second = select_recipes(tuple(reversed(candidates)), **kwargs)
    assert first.receipt == second.receipt
    assert first.receipt.selection_provider_calls == 0
    assert first.receipt.selection_provider_cost_usd == 0
    assert first.receipt.selected_revision_ids == second.receipt.selected_revision_ids
    assert len(first.selected) == 2
    assert any(
        item.disposition is CandidateDisposition.OMITTED and item.reason == "selected_revision_limit"
        for item in first.receipt.candidates
    )


def test_candidate_and_level1_token_budget_omit_whole_revisions() -> None:
    result = select_recipes(
        _package_candidates(),
        product_id="product:test",
        request_id="task:small-budget",
        budget=CognitionDiscoveryBudgetV1.for_depth(
            1,
            level0_candidate_limit=1,
            selected_revision_limit=1,
            level1_cognition_tokens=0,
        ),
        score=lambda _recipe: 1.0,
        dependency_available=_available,
    )
    assert not result.selected
    reasons = {item.reason for item in result.receipt.candidates}
    assert "level0_candidate_limit" in reasons
    assert "level1_token_budget" in reasons
    assert all(item.loaded_level == 0 for item in result.receipt.candidates)


def _product_candidate(*, stable_key: str, dependency_owner: str) -> DiscoveredRecipe:
    body = {
        "slug": stable_key,
        "name": "Product Recipe",
        "description": "A product recipe.",
        "domain_intelligences": ["testing"],
        "recipe": {
            "phases": [
                {
                    "cognitive_function": "frame",
                    "instruments": [{"fallback_slug": "missing"}],
                    "min_depth": 1,
                    "output_schema": "frame",
                }
            ]
        },
    }
    identity = CognitionIdentityV1(
        cognition_type=CognitionType.RECIPE,
        owner=CognitionOwnerV1(
            kind=OwnerKind.PRODUCT,
            namespace="product:test",
            provenance="task:test",
        ),
        stable_key=stable_key,
    )
    revision = CognitionRevisionV1(
        identity=identity,
        body_schema_version="ace.cognition.recipe/v1",
        body=body,
        dependencies=(
            CognitionDependencyV1(
                cognition_type=CognitionType.INSTRUMENT,
                stable_key="missing",
                owner_namespace=dependency_owner,
            ),
        ),
        sources=(
            CognitionSourceV1(
                source_kind="task",
                locator="task:test",
                content_hash=canonical_hash({"task": "test"}),
            ),
        ),
        approval_receipt_id="cognition_review:test",
    )
    scope = CognitionScopeV1(kind=ScopeKind.PRODUCT, product_id="product:test")
    head = CognitionHeadV1(
        cognition_id=str(identity.cognition_id),
        scope=scope,
        active_revision_id=str(revision.revision_id),
        authority_receipt_id="cognition_review:test",
    )
    return DiscoveredRecipe(
        view=CatalogRecipeView(
            slug=stable_key,
            revision=revision,
            runtime_view=meta_skill_from_body(body),
            disciplines=(),
            task_types=(),
        ),
        head=head,
    )


def test_unavailable_required_dependency_fails_candidate_closed() -> None:
    result = select_recipes(
        (_product_candidate(stable_key="taught", dependency_owner="extension:gone"),),
        product_id="product:test",
        request_id="task:test",
        budget=CognitionDiscoveryBudgetV1.for_depth(1),
        score=lambda _recipe: 1.0,
        dependency_available=lambda _dependency: False,
        requested_slug="taught",
    )
    assert not result.selected
    candidate = result.receipt.candidates[0]
    assert candidate.disposition is CandidateDisposition.UNAVAILABLE
    assert candidate.reason == "required_dependency_unavailable"
    assert candidate.unavailable_dependencies == ("instrument:extension:gone:missing",)
    assert result.receipt.state == "degraded"


def test_same_slug_different_identity_is_ambiguous_not_fallback_selected() -> None:
    one = _product_candidate(stable_key="same", dependency_owner="core:ace")
    revision = one.view.revision
    other_identity = CognitionIdentityV1(
        cognition_type=CognitionType.RECIPE,
        owner=CognitionOwnerV1(
            kind=OwnerKind.GLOBAL,
            namespace="global:test",
            provenance="authority:test",
        ),
        stable_key="same",
    )
    other_revision = CognitionRevisionV1(
        identity=other_identity,
        body_schema_version=revision.body_schema_version,
        body=revision.body,
        dependencies=revision.dependencies,
        sources=revision.sources,
        approval_receipt_id="cognition_review:other",
    )
    other = DiscoveredRecipe(
        view=CatalogRecipeView(
            slug="same",
            revision=other_revision,
            runtime_view=one.view.runtime_view,
            disciplines=(),
            task_types=(),
        ),
        head=CognitionHeadV1(
            cognition_id=str(other_identity.cognition_id),
            scope=CognitionScopeV1(kind=ScopeKind.GLOBAL, global_authority="authority:test"),
            active_revision_id=str(other_revision.revision_id),
            authority_receipt_id="cognition_review:other",
        ),
    )
    result = select_recipes(
        (one, other),
        product_id="product:test",
        request_id="task:test",
        budget=CognitionDiscoveryBudgetV1.for_depth(1),
        score=lambda _recipe: 1.0,
        dependency_available=_available,
        requested_slug="same",
    )
    assert not result.selected
    assert {item.reason for item in result.receipt.candidates} == {"ambiguous_stable_key"}


def test_use_receipt_binds_exact_revision_and_material_phase_delta() -> None:
    selection = select_recipes(
        _package_candidates(),
        product_id="product:test",
        request_id="task:test",
        budget=CognitionDiscoveryBudgetV1.for_depth(1, selected_revision_limit=1),
        score=lambda recipe: 1.0 if recipe.slug == "coding_intelligence" else 0.0,
        dependency_available=_available,
        requested_slug="coding_intelligence",
    ).receipt
    revision_id = selection.selected_revision_ids[0]
    receipt = CognitionUseReceiptV1(
        request_id="task:test",
        product_id="product:test",
        selection_receipt_id=str(selection.selection_receipt_id),
        selected_revision_ids=(revision_id,),
        phase_uses=(
            CognitionPhaseUseV1(
                revision_id=revision_id,
                stable_key="coding_intelligence",
                phase_index=0,
                cognitive_function="frame",
                instruments=("first-principles",),
            ),
        ),
        state="used",
    )
    replay = CognitionUseReceiptV1.model_validate(receipt.model_dump(mode="json"))
    changed = receipt.model_copy(
        update={
            "use_receipt_id": None,
            "material_use_hash": None,
            "phase_uses": (receipt.phase_uses[0].model_copy(update={"cognitive_function": "validate"}),),
        }
    )
    assert replay == receipt
    assert changed.use_receipt_id != receipt.use_receipt_id
    assert changed.material_use_hash != receipt.material_use_hash
    assert normalize_selection_receipt(selection.model_dump(mode="json"), product_id="product:other") == {}
    assert normalize_use_receipt(receipt.model_dump(mode="json"), product_id="product:other") == {}
