"""Real-database E1-C proposal/review/revision/head restart proof."""

from __future__ import annotations

import os
import shutil
import socket
import subprocess
from contextlib import asynccontextmanager
from pathlib import Path

import pytest
from surrealdb import AsyncSurreal

from core.engine.cognition.composer import CognitiveComposer
from core.engine.cognition.contracts import (
    RECIPE_BODY_VERSION,
    CognitionIdentityV1,
    CognitionOwnerV1,
    CognitionScopeV1,
    CognitionType,
    OwnerKind,
    ScopeKind,
    canonical_hash,
)
from core.engine.cognition.discovery import DurableCognitionDiscovery
from core.engine.cognition.governance import (
    ActorClass,
    CognitionProposalV1,
    ProposalSourceV1,
    ReviewActorV1,
    ReviewDisposition,
)
from core.engine.cognition.governance_persistence import (
    CognitionGovernanceStore,
    DurableCognitionGovernanceService,
)
from core.engine.cognition.lifecycle import CognitionLifecycleService, LifecycleAction

pytestmark = pytest.mark.e2e

ROOT = Path(__file__).parents[1]


def _port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


async def _wait_port(port: int, process: subprocess.Popen) -> None:
    import asyncio

    for _ in range(200):
        if process.poll() is not None:
            raise RuntimeError("disposable SurrealDB exited before accepting connections")
        try:
            _, writer = await asyncio.open_connection("127.0.0.1", port)
            writer.close()
            await writer.wait_closed()
            return
        except OSError:
            await asyncio.sleep(0.05)
    raise RuntimeError("disposable SurrealDB did not accept connections")


class _Pool:
    def __init__(self, url: str) -> None:
        self.url = url

    @asynccontextmanager
    async def connection(self):
        db = AsyncSurreal(self.url)
        await db.connect()
        await db.signin({"username": "root", "password": "root"})
        await db.use("ace_cognition_restart", "ace_cognition_restart")
        try:
            yield db
        finally:
            await db.close()


async def _initialize(url: str) -> None:
    db = AsyncSurreal(url)
    await db.connect()
    await db.signin({"username": "root", "password": "root"})
    await db.use("ace_cognition_restart", "ace_cognition_restart")
    try:
        await db.query("DEFINE TABLE product SCHEMALESS; CREATE product:alpha SET name = 'Alpha'")
        for name in (
            "v169_governed_cognition_catalog.surql",
            "v170_governed_cognition_review.surql",
            "v171_governed_cognition_use.surql",
            "v176_governed_cognition_canonical_payload.surql",
        ):
            result = await db.query((ROOT / "core/schema" / name).read_text())
            assert not isinstance(result, str), result
    finally:
        await db.close()


def _proposal() -> CognitionProposalV1:
    identity = CognitionIdentityV1(
        cognition_type=CognitionType.RECIPE,
        owner=CognitionOwnerV1(
            kind=OwnerKind.PRODUCT,
            namespace="product:alpha",
            provenance="task:teach",
        ),
        stable_key="restart_recipe",
    )
    body = {
        "slug": "restart_recipe",
        "name": "Restart Recipe",
        "description": "Persist through a runtime restart.",
        "round_trip_probe": {"kept": "exact", "optional": None},
        "domain_intelligences": ["testing"],
        "activation_signals": ["implement", "test", "restart", "persistence"],
        "archetype_affinity": {"executor": 1.0},
        "mode_affinity": {"reactive": 1.0},
        "recipe": {
            "phases": [
                {
                    "cognitive_function": "frame",
                    "instruments": [{"fallback_slug": "first-principles"}],
                    "min_depth": 1,
                    "output_schema": "framed_problem",
                }
            ]
        },
    }
    return CognitionProposalV1(
        target_identity=identity,
        scope=CognitionScopeV1(kind=ScopeKind.PRODUCT, product_id="product:alpha"),
        intent="Preserve the accepted restart framing.",
        sources=(
            ProposalSourceV1(
                source_id="task:teach",
                source_kind="task",
                content_hash=canonical_hash({"task": "teach", "output": "accepted"}),
            ),
        ),
        body_schema_version=RECIPE_BODY_VERSION,
        draft_body=body,
        created_by=ReviewActorV1(actor_id="model:teacher", actor_class=ActorClass.MODEL),
    )


async def test_governed_cognition_chain_survives_fresh_database_connection(tmp_path) -> None:
    surreal = os.environ.get("ACE_I1_SURREAL_BIN") or shutil.which("surreal")
    if not surreal:
        for candidate in (Path("/opt/homebrew/bin/surreal"), Path.home() / ".surrealdb/surreal"):
            if candidate.exists():
                surreal = str(candidate)
                break
    if not surreal:
        pytest.skip("surreal binary is unavailable")
    port = _port()
    log = (tmp_path / "surreal.log").open("wb")
    process = subprocess.Popen(
        [
            surreal,
            "start",
            "--no-banner",
            "--username",
            "root",
            "--password",
            "root",
            "--bind",
            f"127.0.0.1:{port}",
            f"surrealkv://{tmp_path / 'store'}",
        ],
        cwd=ROOT,
        stdout=log,
        stderr=subprocess.STDOUT,
    )
    url = f"ws://127.0.0.1:{port}"
    try:
        await _wait_port(port, process)
        await _initialize(url)
        first_store = CognitionGovernanceStore(_Pool(url))
        service = DurableCognitionGovernanceService(first_store)
        proposal = await service.propose(_proposal())
        receipt = await service.review(
            proposal_id=str(proposal.proposal_id),
            product_id="product:alpha",
            review_request_id="review-request:restart",
            actor=ReviewActorV1(
                actor_id="user:reviewer",
                actor_class=ActorClass.HUMAN,
                authorities=("cognition-review",),
            ),
            disposition=ReviewDisposition.APPROVE,
            rationale="Exact material and provenance reviewed.",
            expected_head_generation=0,
        )

        retry_service = DurableCognitionGovernanceService(CognitionGovernanceStore(_Pool(url)))
        replay = await retry_service.review(
            proposal_id=str(proposal.proposal_id),
            product_id="product:alpha",
            review_request_id="review-request:restart",
            actor=ReviewActorV1(
                actor_id="user:reviewer",
                actor_class=ActorClass.HUMAN,
                authorities=("cognition-review",),
            ),
            disposition=ReviewDisposition.APPROVE,
            rationale="Exact material and provenance reviewed.",
            expected_head_generation=0,
        )
        assert replay == receipt

        second_store = CognitionGovernanceStore(_Pool(url))
        restored_proposal = await second_store.load_proposal(str(proposal.proposal_id), product_id="product:alpha")
        restored_review = await second_store.load_review(str(receipt.receipt_id), product_id="product:alpha")
        restored_revision = await second_store.load_revision(str(receipt.result_revision_id))
        restored_head = await second_store.load_head(str(receipt.result_head_id))
        assert restored_proposal == proposal
        assert restored_proposal.draft_body["round_trip_probe"] == {
            "kept": "exact",
            "optional": None,
        }
        assert restored_review == receipt
        assert restored_revision is not None
        assert restored_revision.approval_receipt_id == receipt.receipt_id
        assert restored_head is not None
        assert restored_head.active_revision_id == restored_revision.revision_id
        assert restored_head.generation == 1

        # A fresh composer/database client selects and materially uses the
        # newly approved revision, then another client retrieves both receipts.
        discovery = DurableCognitionDiscovery(_Pool(url))
        composer = CognitiveComposer(discovery=discovery)

        async def resolve_instrument(*, spec, **_kwargs):
            return spec.slug or spec.fallback_slug

        async def resolve_tool(*, spec, **_kwargs):
            return spec.slug or spec.fallback_slug

        composer._classifier.resolve_instrument = resolve_instrument
        composer._tool_classifier.resolve_tool = resolve_tool
        composition = await composer.compose(
            {
                "description": "Implement and test the restart persistence service.",
                "discipline": "testing",
                "task_type": "implement",
                "mode": "reactive",
                "complexity": "moderate",
                "archetype": "executor",
                "cognition_request_id": "task:fresh-cognition-use",
                "requested_cognition_slug": "restart_recipe",
            },
            "product:alpha",
        )
        assert composition.cognition_selection_receipt is not None
        assert restored_revision.revision_id in composition.cognition_selection_receipt.selected_revision_ids
        assert composition.cognition_use_receipt is not None
        assert any(
            item.revision_id == restored_revision.revision_id for item in composition.cognition_use_receipt.phase_uses
        )

        third_client = DurableCognitionDiscovery(_Pool(url))
        selection = await third_client.load_selection(
            str(composition.cognition_selection_receipt.selection_receipt_id),
            product_id="product:alpha",
        )
        use = await third_client.load_use(
            str(composition.cognition_use_receipt.use_receipt_id),
            product_id="product:alpha",
        )
        assert selection == composition.cognition_selection_receipt
        assert use == composition.cognition_use_receipt

        changed_body = dict(proposal.draft_body)
        changed_body["description"] = "Use the revised framing before rollback."
        changed_recipe = dict(changed_body["recipe"])
        changed_phases = [dict(item) for item in changed_recipe["phases"]]
        changed_phases[0]["output_schema"] = "revised_framed_problem"
        changed_recipe["phases"] = changed_phases
        changed_body["recipe"] = changed_recipe
        second_proposal = CognitionProposalV1(
            target_identity=proposal.target_identity,
            scope=proposal.scope,
            intent="Revise the accepted framing output.",
            sources=(
                ProposalSourceV1(
                    source_id="task:teach-second",
                    source_kind="task",
                    content_hash=canonical_hash({"task": "teach-second", "output": "accepted"}),
                ),
            ),
            base_revision_id=str(restored_revision.revision_id),
            body_schema_version=proposal.body_schema_version,
            draft_body=changed_body,
            dependencies=proposal.dependencies,
            created_by=proposal.created_by,
        )
        second_service = DurableCognitionGovernanceService(CognitionGovernanceStore(_Pool(url)))
        await second_service.propose(second_proposal)
        second_review = await second_service.review(
            proposal_id=str(second_proposal.proposal_id),
            product_id="product:alpha",
            review_request_id="review-request:second",
            actor=ReviewActorV1(
                actor_id="user:reviewer",
                actor_class=ActorClass.HUMAN,
                authorities=("cognition-review",),
            ),
            disposition=ReviewDisposition.APPROVE,
            rationale="Approve the exact revised output schema.",
            expected_head_generation=1,
        )
        second_revision = await first_store.load_revision(str(second_review.result_revision_id))
        second_head = await first_store.load_head(str(second_review.result_head_id))
        assert second_revision is not None
        assert second_head is not None
        assert second_head.generation == 2
        assert second_head.active_revision_id == second_revision.revision_id

        lifecycle = CognitionLifecycleService(_Pool(url))
        rollback = await lifecycle.transition(
            head_id=str(second_head.head_id),
            product_id="product:alpha",
            review_request_id="review-request:rollback",
            actor=ReviewActorV1(
                actor_id="user:reviewer",
                actor_class=ActorClass.HUMAN,
                authorities=("cognition-review",),
            ),
            action=LifecycleAction.ROLLBACK,
            rationale="Restore the prior verified output contract.",
            expected_generation=2,
            target_revision_id=str(restored_revision.revision_id),
        )
        rolled_back_head = await CognitionGovernanceStore(_Pool(url)).load_head(str(second_head.head_id))
        assert rollback.result_generation == 3
        assert rolled_back_head is not None
        assert rolled_back_head.generation == 3
        assert rolled_back_head.active_revision_id == restored_revision.revision_id
        assert await CognitionGovernanceStore(_Pool(url)).load_revision(str(second_revision.revision_id)) == (
            second_revision
        )

        after_rollback = CognitiveComposer(discovery=DurableCognitionDiscovery(_Pool(url)))
        after_rollback._classifier.resolve_instrument = resolve_instrument
        after_rollback._tool_classifier.resolve_tool = resolve_tool
        rollback_composition = await after_rollback.compose(
            {
                "description": "Implement and test the restart persistence service.",
                "discipline": "testing",
                "task_type": "implement",
                "mode": "reactive",
                "complexity": "moderate",
                "archetype": "executor",
                "cognition_request_id": "task:after-rollback",
                "requested_cognition_slug": "restart_recipe",
            },
            "product:alpha",
        )
        assert restored_revision.revision_id in rollback_composition.cognition_revision_ids.values()
        assert second_revision.revision_id not in rollback_composition.cognition_revision_ids.values()
    finally:
        process.terminate()
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=10)
        log.close()
