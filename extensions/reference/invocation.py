"""Minimal generic task action shipped with the reference extension."""

from __future__ import annotations

from core.engine.extensions import (
    ContextResolution,
    ExtensionActorContext,
    ExtensionInvocationEnvelope,
    ExtensionOutcome,
    ExtensionTaskPlan,
)

OUTCOME_CONTRACT = "product.product-check-outcome-v1"


def prepare_product_check(
    envelope: ExtensionInvocationEnvelope,
    actor: ExtensionActorContext,
) -> ExtensionTaskPlan:
    """Demonstrate the contract without claiming a repository the example lacks."""
    return ExtensionTaskPlan(
        description=(
            "Evaluate the product question. Separate facts, assumptions, reversible tests, "
            f"and a recommendation.\nQuestion: {envelope.question.strip()}"
        ),
        context_resolution=[
            ContextResolution(
                reference=reference,
                status="declared",
                resolver="product.reference_identity",
                product_scope=actor.product_id,
                note="The reference identity was declared; the reference extension has no repository adapter.",
            )
            for reference in envelope.references
        ],
        outcome_contract=OUTCOME_CONTRACT,
    )


def project_product_check(output: str | None, execution: dict) -> ExtensionOutcome:
    return ExtensionOutcome(
        contract_version=OUTCOME_CONTRACT,
        data={
            "recommendation_content": output,
            "execution_state": execution.get("state"),
            "projection": "bounded_content_container",
        },
        warnings=[] if output else ["No usable recommendation content was returned."],
    )
