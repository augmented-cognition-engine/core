"""Fjord Operations product extension registered only through ACE's public facade."""

from __future__ import annotations

from typing import TYPE_CHECKING

from fjord_operations_extension.adapter import FjordOperationsAdapter

if TYPE_CHECKING:
    from core.engine.extensions import Registry


class FjordOperationsExtension:
    """A bounded product State Engine assembled without forking ACE Core."""

    name = "fjord-operations"
    version = "0.1.0"

    def register(self, reg: "Registry") -> None:
        from fjord_operations_extension.actions import (
            EVIDENCE_QUERY_OUTCOME_CONTRACT,
            PROMOTION_OUTCOME_CONTRACT,
            prepare_evidence_query,
            prepare_promotion_review,
            project_evidence_query,
            project_promotion_review,
        )

        reg.register_grounded_state_adapter("public-fixture", FjordOperationsAdapter())
        reg.register_task_action(
            "evidence-query",
            prepare_evidence_query,
            project_outcome=project_evidence_query,
            output_contract=EVIDENCE_QUERY_OUTCOME_CONTRACT,
            description="Resolve bounded Fjord Operations evidence into untrusted reasoning context.",
            lifecycle_operations=["submit", "retrieve", "history", "retry", "cancel"],
            cancellation_supported=True,
            resolver_capabilities=["ace.grounded-state.evidence-query/v1"],
            feature_flags=["state-engine-tp6"],
        )
        reg.register_task_action(
            "promotion-review",
            prepare_promotion_review,
            project_outcome=project_promotion_review,
            output_contract=PROMOTION_OUTCOME_CONTRACT,
            description="Apply an authenticated disposition to exact Fjord Operations promotion material.",
            lifecycle_operations=["submit", "retrieve", "history", "retry"],
            cancellation_supported=False,
            resolver_capabilities=["ace.grounded-state.promotion-resolver/v1"],
            required_authority=["state-engine-promotion-review"],
            feature_flags=["state-engine-tp7"],
        )
