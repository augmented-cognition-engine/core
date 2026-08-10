from __future__ import annotations

import ast
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from ace_reference_workspace_action import (
    ACTION_TYPE,
    ReferenceWorkspaceActionAdapter,
    ReferenceWorkspaceActionError,
)

from ace.core import (
    ActionDisposition,
    ActionEffectState,
    ActionIntentV1Alpha1,
    AuthenticatedRuntimeContextV1Alpha1,
    GovernedActionAuthorizationProjection,
    GovernedStateHeadPreconditionV1Alpha1,
    ImmutableRecordV1,
    ReceiptReferenceV1Alpha1,
    canonical_json,
)

NOW = datetime.now(UTC).replace(microsecond=0)
PRODUCT = "product:reference-action"


def _precondition(kind: str, sequence: int) -> GovernedStateHeadPreconditionV1Alpha1:
    return GovernedStateHeadPreconditionV1Alpha1(
        state_kind=kind,
        product_id=PRODUCT,
        state_id=f"{kind}:reference",
        sequence=sequence,
        revision_id=f"revision:{kind}:{sequence}",
        commit_receipt_id=f"governed_state_commit:{kind}:{sequence}",
    )


def _intent(*, relative_path: str = "exports/brief.md", content: str = "# Governed brief\n"):
    context = AuthenticatedRuntimeContextV1Alpha1(
        product_id=PRODUCT,
        actor_ref="principal:operator",
        authentication_receipt_ref="authentication:reference",
        authentication_receipt_digest="sha256:" + "a" * 64,
        authenticated_at=NOW - timedelta(minutes=1),
        expires_at=NOW + timedelta(minutes=10),
    )
    decision = ImmutableRecordV1(
        product_id=PRODUCT,
        record_space="prepared",
        record_kind="decision",
        record_key="decision:reference",
        payload_contract="ace.core.decision/v1alpha1",
        payload={},
        as_of=NOW - timedelta(minutes=1),
        available_at=NOW,
        processing_order=0,
    ).reference()
    return ActionIntentV1Alpha1(
        action_key="action:reference:1",
        product_id=PRODUCT,
        authenticated_context=context,
        decision=decision,
        action_type=ACTION_TYPE,
        parameters_json=canonical_json({"content": content, "relative_path": relative_path}),
        requested_at=NOW,
    )


def _authorization() -> GovernedActionAuthorizationProjection:
    return GovernedActionAuthorizationProjection(
        authorization_ref=ReceiptReferenceV1Alpha1(
            receipt_id="authorization:reference",
            receipt_digest="sha256:" + "b" * 64,
        ),
        authorized_at=NOW + timedelta(seconds=1),
        state_preconditions=(
            _precondition("authority_grant", 1),
            _precondition("capability_state", 1),
        ),
    )


@pytest.mark.asyncio
async def test_prepare_is_effect_free_and_execute_creates_one_exact_file(tmp_path: Path) -> None:
    (tmp_path / "exports").mkdir()
    adapter = ReferenceWorkspaceActionAdapter(workspace_root=tmp_path)
    intent = _intent()

    plan = await adapter.prepare(intent)
    assert not (tmp_path / "exports" / "brief.md").exists()
    assert plan.target_ref == "workspace:exports/brief.md"
    assert plan.declared_side_effects == ("create_file",)

    result = await adapter.execute(plan, _authorization())
    assert result.disposition is ActionDisposition.SUCCEEDED
    assert result.effect_state is ActionEffectState.CONFIRMED
    assert (tmp_path / "exports" / "brief.md").read_text() == "# Governed brief\n"
    assert result.after_evidence[0].target_ref == plan.target_ref


@pytest.mark.asyncio
async def test_target_created_after_prepare_fails_with_no_effect(tmp_path: Path) -> None:
    (tmp_path / "exports").mkdir()
    adapter = ReferenceWorkspaceActionAdapter(workspace_root=tmp_path)
    plan = await adapter.prepare(_intent())
    target = tmp_path / "exports" / "brief.md"
    target.write_text("winner")

    result = await adapter.execute(plan, _authorization())
    assert result.disposition is ActionDisposition.FAILED
    assert result.effect_state is ActionEffectState.NONE
    assert result.failure_code == "target_changed"
    assert target.read_text() == "winner"


@pytest.mark.asyncio
async def test_parent_replaced_by_symlink_after_prepare_fails_closed(tmp_path: Path) -> None:
    approved_parent = tmp_path / "exports"
    approved_parent.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    adapter = ReferenceWorkspaceActionAdapter(workspace_root=tmp_path)
    plan = await adapter.prepare(_intent())
    approved_parent.rmdir()
    approved_parent.symlink_to(outside, target_is_directory=True)

    result = await adapter.execute(plan, _authorization())
    assert result.disposition is ActionDisposition.FAILED
    assert result.effect_state is ActionEffectState.NONE
    assert result.failure_code == "target_changed"
    assert not (outside / "brief.md").exists()


@pytest.mark.asyncio
@pytest.mark.parametrize("path", ["../brief.md", "/tmp/brief.md", "exports/../brief.md", "missing/brief.md"])
async def test_path_escape_and_missing_parent_fail_closed(tmp_path: Path, path: str) -> None:
    (tmp_path / "exports").mkdir()
    adapter = ReferenceWorkspaceActionAdapter(workspace_root=tmp_path)
    with pytest.raises(ReferenceWorkspaceActionError):
        await adapter.prepare(_intent(relative_path=path))


def test_distribution_imports_only_public_ace_contracts() -> None:
    source = Path(__file__).resolve().parents[1] / "src/ace_reference_workspace_action/adapter.py"
    imports = {
        node.module
        for node in ast.walk(ast.parse(source.read_text(), filename=str(source)))
        if isinstance(node, ast.ImportFrom) and node.module
    }
    assert "ace.core" in imports
    assert not any(name == "core" or name.startswith("core.") for name in imports)
    assert not any(name == "ace.intelligence" or name.startswith("ace.intelligence.") for name in imports)
