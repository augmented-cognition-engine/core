from __future__ import annotations

import copy
import json
import subprocess
import sys
from contextlib import asynccontextmanager
from pathlib import Path

import pytest

from core.engine.product.living_graph import (
    MAX_RECORDS_PER_SOURCE,
    PROJECTION_VERSION,
    SNAPSHOT_SCHEMA_VERSION,
    LivingProductGraphRecords,
    LivingProductGraphService,
    SourceState,
    project_product_snapshot,
    serialize_product_snapshot,
)
from core.engine.product.living_graph_store import SurrealLivingProductGraphStore

pytestmark = pytest.mark.unit

FIXTURE = Path(__file__).parents[1] / "evaluations" / "fixtures" / "g1_living_product_graph_v1.json"


def _records() -> LivingProductGraphRecords:
    payload = json.loads(FIXTURE.read_text())
    states = [SourceState(source="product", record_count=1, required=True)]
    states.extend(
        SourceState(
            source=family,
            record_count=len(rows),
            required=family in {"capabilities", "decisions", "assertions", "operational_relationships"},
        )
        for family, rows in payload["records"].items()
    )
    return LivingProductGraphRecords(
        product=payload["product"],
        records=payload["records"],
        source_states=states,
    )


def _issue_codes(snapshot: dict) -> set[str]:
    return {issue["code"] for issue in snapshot["issues"]}


def test_complete_product_snapshot_is_versioned_provenance_bearing_and_read_only():
    snapshot = project_product_snapshot("product:alpha", _records())

    assert snapshot["schema_version"] == SNAPSHOT_SCHEMA_VERSION
    assert snapshot["projection_version"] == PROJECTION_VERSION
    assert snapshot["snapshot_id"].startswith("product_snapshot:")
    assert snapshot["projection_state"] == {
        "status": "complete",
        "assertion_states": {"accepted": 1, "contested": 2, "provisional": 1, "rejected": 1},
        "issue_count": 0,
    }
    assert snapshot["authority"] == {
        "mode": "read_only",
        "operational_roadmap": "ROADMAP.md",
        "writes_permitted": False,
        "autonomous_dispatch": False,
        "operational_truth": "relationships.operational",
        "assertions_are_operational_only_when": "accepted_and_projection_eligible",
        "model_proposals_define_truth": False,
    }
    assert snapshot["product"]["id"] == "product:alpha"
    assert snapshot["product"]["state"] == "observed"
    assert snapshot["product"]["object_type"] == "product"
    assert snapshot["capabilities"]["items"][0]["lifecycle_state"] == "built"
    assert "settings" not in snapshot["product"]
    assert [row["id"] for row in snapshot["capabilities"]["items"]] == [
        "capability:billing",
        "capability:checkout",
    ]
    assert snapshot["relationships"]["operational"] == [
        {
            "assertion_id": "relationship_assertion:checkout_depends_billing",
            "id": "operational_relationship:checkout_depends_billing",
            "object": "capability:billing",
            "ontology_version": "ace.relationships.v1",
            "predicate": "depends_on",
            "projection_version": "ace.assertion-resolver.v1",
            "provenance": {
                "evidence_refs": ["observation:retry_correction"],
                "record_refs": [
                    "operational_relationship:checkout_depends_billing",
                    "relationship_assertion:checkout_depends_billing",
                ],
                "source_family": "operational_relationship",
            },
            "relationship_kind": "accepted_semantic",
            "authority": "canonical_operational_truth",
            "resolver_version": "ace.assertion-resolver.v1",
            "subject": "capability:checkout",
        }
    ]
    assert snapshot["work"]["authority"] == "runtime_records_only_not_living_roadmap"
    assert snapshot["decisions"][0]["provenance"]["record_refs"] == ["decision:idempotency"]
    assert len(snapshot["history"]["assertion_events"]) == 3


def test_sparse_product_has_explicit_unknowns_without_fabricated_fields():
    source = LivingProductGraphRecords(
        product={"id": "product:sparse", "name": "Sparse"},
        source_states=[SourceState(source="product", record_count=1, required=True)],
    )

    snapshot = project_product_snapshot("product:sparse", source)

    assert snapshot["product"]["name"] == "Sparse"
    assert snapshot["intent"] == {"directions": [], "visions": []}
    assert snapshot["relationships"] == {"operational": [], "assertions": [], "structural": []}
    assert snapshot["projection_state"]["status"] == "partial"
    assert "product_intent_missing" in _issue_codes(snapshot)
    assert snapshot["product"]["provenance"]["record_refs"] == ["product:sparse"]


def test_tp6_rollouts_are_read_only_simulations_not_observations_or_beliefs():
    source = _records()
    source.records["consequence_rollouts"] = [
        {
            "id": "grounded_consequence_rollout:one",
            "product": "product:alpha",
            "stable_id": "grounded_rollout_revision:one",
            "material_hash": "a" * 64,
            "contract_version": "ace.grounded-state.consequence-rollout/v1",
            "task_id": "task:one",
            "invocation_id": "invocation:one",
            "rollout_id": "consequence_rollout:one",
            "revision": 1,
            "projection_id": "grounded_belief_projection:one",
            "disposition": "eligible",
            "transition_revision_ids": ["grounded_transition_revision:one"],
        }
    ]
    source.records["rollout_reconciliations"] = [
        {
            "id": "grounded_rollout_reconciliation:one",
            "product": "product:alpha",
            "stable_id": "grounded_rollout_reconciliation:one",
            "material_hash": "b" * 64,
            "contract_version": "ace.grounded-state.rollout-reconciliation/v1",
            "rollout_revision_id": "grounded_rollout_revision:one",
            "predicted_outcome_id": "rollout_predicted_outcome:one",
            "observation_id": "grounded_rollout_outcome:one",
            "branch_id": "branch:action",
            "disposition": "matched",
        }
    ]

    snapshot = project_product_snapshot("product:alpha", source)

    rollout = snapshot["state_engine"]["consequence_rollouts"][0]
    reconciliation = snapshot["state_engine"]["rollout_reconciliations"][0]
    assert rollout["authority"] == "read_only_simulation_projection"
    assert rollout["record_meaning"] == "simulated_consequence_not_observation"
    assert reconciliation["record_meaning"] == "observed_outcome_reconciliation_not_simulated_fact"
    assert rollout not in snapshot["intelligence"]["observations"]
    assert rollout not in snapshot["intelligence"]["insights"]
    assert "payload" not in rollout


def test_productized_state_receipts_are_additive_inspectable_and_never_source_truth():
    source = _records()
    source.records["state_ingestions"] = [
        {
            "id": "grounded_batch_ingestion_receipt:one",
            "product": "product:alpha",
            "receipt_id": "batch_ingestion_receipt:one",
            "manifest_id": "batch_manifest:one",
            "manifest_hash": "a" * 64,
            "adapter_id": "example-adapter",
            "extraction_run_id": "run:one",
            "contract_version": "ace.grounded-state.batch-ingestion-receipt/v1",
            "payload": {"private": "not projected"},
        }
    ]
    source.records["belief_projections"] = [
        {
            "id": "grounded_belief_projection:one",
            "product": "product:alpha",
            "stable_id": "belief_projection:one",
            "material_hash": "b" * 64,
            "contract_version": "ace.grounded-state.belief-projection/v1",
            "as_of": "2030-01-01T00:00:00Z",
            "revision": 1,
            "evidence_pack_id": "grounded_evidence_pack:one",
            "assertion_refs": ["grounded_epistemic_assertion_revision:one"],
        }
    ]
    source.records["transition_revisions"] = [
        {
            "id": "grounded_transition_revision:one",
            "product": "product:alpha",
            "stable_id": "transition_revision:one",
            "material_hash": "c" * 64,
            "contract_version": "ace.grounded-state.transition-revision/v1",
            "hypothesis_id": "transition_hypothesis:one",
            "revision": 1,
            "review_state": "provisional",
            "rollout_eligible": True,
        }
    ]
    source.records["reasoning_evidence_packs"] = [
        {
            "id": "grounded_reasoning_evidence_pack:one",
            "product": "product:alpha",
            "stable_id": "reasoning_pack:one",
            "material_hash": "d" * 64,
            "contract_version": "ace.grounded-state.reasoning-evidence-pack/v1",
            "task_id": "task:one",
            "invocation_id": "invocation:one",
            "query_id": "evidence_query:one",
            "evidence_pack_id": "grounded_evidence_pack:one",
            "evidence_refs": ["grounded_source_claim:one"],
        }
    ]
    source.records["rollout_reasoning_use"] = [
        {
            "id": "grounded_rollout_reasoning_use:one",
            "product": "product:alpha",
            "stable_id": "reasoning_use:one",
            "material_hash": "e" * 64,
            "contract_version": "ace.grounded-state.rollout-reasoning-use/v1",
            "task_id": "task:one",
            "invocation_id": "invocation:one",
            "rollout_revision_id": "grounded_consequence_rollout:one",
            "comparison_state": "material",
        }
    ]

    snapshot = project_product_snapshot("product:alpha", source)
    state_engine = snapshot["state_engine"]

    assert state_engine["ingestions"][0]["authority"] == "read_only_ingestion_receipt"
    assert state_engine["belief_projections"][0]["record_meaning"].endswith("not_source_observation")
    assert state_engine["transition_revisions"][0]["record_meaning"].endswith("not_causal_fact")
    assert state_engine["reasoning_evidence_packs"][0]["task_id"] == "task:one"
    assert state_engine["reasoning_use_receipts"][0]["record_meaning"].endswith("not_beneficial_impact")
    assert "private" not in serialize_product_snapshot(snapshot).decode()


def test_tp7_promotion_lifecycle_is_read_only_metadata_not_source_evidence():
    source = _records()
    source.records["promotion_proposals"] = [
        {
            "id": "grounded_promotion_proposal:one",
            "product": "product:alpha",
            "stable_id": "grounded_promotion_proposal:one",
            "material_hash": "a" * 64,
            "contract_version": "ace.grounded-state.promotion-proposal/v1",
            "task_id": "task:one",
            "target_kind": "durable_conclusion",
            "content_hash": "b" * 64,
            "evidence_pack_id": "grounded_evidence_pack:one",
            "rollout_revision_id": "grounded_rollout_revision:one",
            "payload": {"content": "must not leak"},
        }
    ]
    source.records["promotion_receipts"] = [
        {
            "id": "grounded_promotion_receipt:one",
            "product": "product:alpha",
            "stable_id": "grounded_promotion_receipt:one",
            "material_hash": "c" * 64,
            "contract_version": "ace.grounded-state.promotion-receipt/v1",
            "proposal_id": "grounded_promotion_proposal:one",
            "review_id": "grounded_promotion_review:one",
            "disposition": "accepted",
            "memory_id": "insight:promotion_one",
        }
    ]
    source.records["promotion_memory_lineage"] = [
        {
            "id": "grounded_promotion_memory_lineage:one",
            "product": "product:alpha",
            "stable_id": "grounded_promotion_memory_lineage:one",
            "material_hash": "d" * 64,
            "contract_version": "ace.grounded-state.promotion-memory-lineage/v1",
            "memory_id": "insight:promotion_one",
            "proposal_id": "grounded_promotion_proposal:one",
            "receipt_id": "grounded_promotion_receipt:one",
            "task_id": "task:one",
            "evidence_pack_id": "grounded_evidence_pack:one",
            "rollout_revision_id": "grounded_rollout_revision:one",
        }
    ]

    snapshot = project_product_snapshot("product:alpha", source)

    promotion = snapshot["state_engine"]["promotion"]
    assert promotion["proposals"][0]["authority"] == "read_only_promotion_lifecycle"
    assert promotion["receipts"][0]["disposition"] == "accepted"
    assert promotion["memory_lineage"][0]["memory_id"] == "insight:promotion_one"
    assert "payload" not in promotion["proposals"][0]
    assert "must not leak" not in serialize_product_snapshot(snapshot).decode()
    assert promotion["proposals"][0] not in snapshot["intelligence"]["observations"]
    assert promotion["proposals"][0] not in snapshot["intelligence"]["insights"]


def test_contested_assertion_remains_inspectable_but_cannot_become_operational_truth():
    source = _records()
    source.records["operational_relationships"].append(
        {
            "id": "operational_relationship:invalid_contested",
            "in": "decision:idempotency",
            "out": "capability:checkout",
            "predicate": "improves",
            "assertion_id": "relationship_assertion:idempotency_improves_checkout",
        }
    )

    snapshot = project_product_snapshot("product:alpha", source)

    assert {row["status"] for row in snapshot["relationships"]["assertions"]} == {
        "accepted",
        "contested",
        "provisional",
        "rejected",
    }
    assert [row["id"] for row in snapshot["relationships"]["operational"]] == [
        "operational_relationship:checkout_depends_billing"
    ]
    assert "ineligible_operational_relationship_excluded" in _issue_codes(snapshot)


@pytest.mark.parametrize("status", ["provisional", "rejected", "superseded", "stale"])
def test_nonaccepted_assertions_remain_inspectable_but_never_operational(status: str):
    source = _records()
    assertion = next(
        row for row in source.records["assertions"] if row["id"] == "relationship_assertion:checkout_depends_billing"
    )
    assertion["status"] = status
    assertion["projection_eligible"] = status == "accepted"

    snapshot = project_product_snapshot("product:alpha", source)

    assert snapshot["relationships"]["operational"] == []
    projected = next(
        row
        for row in snapshot["relationships"]["assertions"]
        if row["id"] == "relationship_assertion:checkout_depends_billing"
    )
    assert projected["status"] == status
    assert "ineligible_operational_relationship_excluded" in _issue_codes(snapshot)


def test_corrected_or_invalidated_assertion_is_removed_from_operational_projection():
    source = _records()
    assertion = next(
        row for row in source.records["assertions"] if row["id"] == "relationship_assertion:checkout_depends_billing"
    )
    assertion["status"] = "stale"
    assertion["projection_eligible"] = False
    assertion["degraded_reason"] = "evidence_invalidated"

    snapshot = project_product_snapshot("product:alpha", source)

    assert snapshot["relationships"]["operational"] == []
    stale = next(
        row
        for row in snapshot["relationships"]["assertions"]
        if row["id"] == "relationship_assertion:checkout_depends_billing"
    )
    assert stale["status"] == "stale"
    assert stale["degraded_reason"] == "evidence_invalidated"


def test_cross_product_records_and_relationships_are_excluded():
    source = _records()
    source.records["capabilities"].append(
        {
            "id": "capability:beta_secret",
            "product": "product:beta",
            "slug": "secret",
            "name": "Beta Secret",
        }
    )
    source.records["capability_dependencies"].append(
        {
            "id": "capability_dep:cross_product",
            "in": "capability:checkout",
            "out": "capability:beta_secret",
            "dep_type": "requires",
        }
    )

    snapshot = project_product_snapshot("product:alpha", source)
    encoded = serialize_product_snapshot(snapshot)

    assert b"Beta Secret" not in encoded
    assert b"beta_secret" not in encoded
    assert "cross_product_record_excluded" in _issue_codes(snapshot)
    assert "relationship_endpoint_outside_product" in _issue_codes(snapshot)


def test_missing_evidence_and_dangling_history_are_explicit_without_fabrication():
    source = _records()
    source.records["assertions"][0]["evidence_refs"].append("observation:missing")
    source.records["assertion_events"].append(
        {
            "id": "assertion_event:dangling",
            "assertion_id": "relationship_assertion:missing",
            "event_type": "resolution",
        }
    )

    snapshot = project_product_snapshot("product:alpha", source)

    assert "evidence_reference_unresolved" in _issue_codes(snapshot)
    assert "assertion_event_missing_assertion" in _issue_codes(snapshot)
    assert "observation:missing" not in {row["id"] for row in snapshot["intelligence"]["observations"]}
    assert all(issue["recovery"] for issue in snapshot["issues"])


def test_cyclic_relationships_are_preserved_once_and_projection_terminates():
    source = _records()
    source.records["capability_dependencies"].append(
        {
            "id": "capability_dep:billing_checkout",
            "in": "capability:billing",
            "out": "capability:checkout",
            "dep_type": "requires",
        }
    )

    snapshot = project_product_snapshot("product:alpha", source)

    dependencies = [row for row in snapshot["relationships"]["structural"] if row["id"].startswith("capability_dep:")]
    assert [row["id"] for row in dependencies] == [
        "capability_dep:billing_checkout",
        "capability_dep:checkout_billing",
    ]


def test_repeated_projection_and_permuted_loader_order_are_byte_identical():
    first = _records()
    second = copy.deepcopy(first)
    second.source_states.reverse()
    for rows in second.records.values():
        rows.reverse()

    left = project_product_snapshot("product:alpha", first)
    right = project_product_snapshot("product:alpha", second)

    assert left == right
    assert serialize_product_snapshot(left) == serialize_product_snapshot(right)


def test_fresh_process_replay_is_byte_identical():
    code = f"""
import json
from pathlib import Path
from core.engine.product.living_graph import LivingProductGraphRecords, project_product_snapshot, serialize_product_snapshot

payload = json.loads(Path({str(FIXTURE)!r}).read_text())
source = LivingProductGraphRecords(product=payload["product"], records=payload["records"])
print(serialize_product_snapshot(project_product_snapshot("product:alpha", source)).decode())
"""
    outputs = []
    for _ in range(2):
        result = subprocess.run(
            [sys.executable, "-c", code],
            cwd=Path(__file__).parents[1],
            capture_output=True,
            text=True,
            check=False,
        )
        assert result.returncode == 0, result.stderr
        outputs.append(result.stdout)
    assert outputs[0] == outputs[1]


def test_unknown_and_legacy_records_are_explicit_and_do_not_gain_identity_or_scope():
    source = _records()
    source.records["tasks"].extend(
        [
            {"id": "task:legacy_unscoped", "description": "Unknown owner"},
            {"product": "product:alpha", "description": "Missing identity"},
        ]
    )

    snapshot = project_product_snapshot("product:alpha", source)

    task_ids = {row["id"] for row in snapshot["work"]["tasks"]}
    assert "task:legacy_unscoped" not in task_ids
    assert "unscoped_legacy_record_excluded" in _issue_codes(snapshot)
    assert "record_missing_stable_id" in _issue_codes(snapshot)


def test_unavailable_optional_store_is_visible_without_erasing_supported_data():
    source = _records()
    source.records["outcome_observations"] = []
    source.source_states = [state for state in source.source_states if state.source != "outcome_observations"]
    source.source_states.append(
        SourceState(
            source="outcome_observations",
            status="unavailable",
            reason="query_TableUnavailable",
        )
    )

    snapshot = project_product_snapshot("product:alpha", source)

    assert snapshot["product"]["state"] == "observed"
    assert len(snapshot["decisions"]) == 1
    assert snapshot["foresight"]["outcome_observations"] == []
    assert snapshot["projection_state"]["status"] == "degraded"
    assert "source_unavailable" in _issue_codes(snapshot)


def test_truncated_source_is_bounded_and_explicitly_degraded():
    source = _records()
    source.source_states = [state for state in source.source_states if state.source != "observations"]
    source.source_states.append(
        SourceState(
            source="observations",
            status="truncated",
            record_count=MAX_RECORDS_PER_SOURCE,
            reason="record_limit",
            limit=MAX_RECORDS_PER_SOURCE,
        )
    )

    snapshot = project_product_snapshot("product:alpha", source)

    assert snapshot["projection_state"]["status"] == "degraded"
    receipt = next(row for row in snapshot["source_states"] if row["source"] == "observations")
    assert receipt["limit"] == MAX_RECORDS_PER_SOURCE
    assert "source_degraded" in _issue_codes(snapshot)


class _ReplayStore:
    def __init__(self, records: LivingProductGraphRecords):
        self._records = records

    async def load_product_graph(self, product_id: str) -> LivingProductGraphRecords:
        assert product_id == "product:alpha"
        return copy.deepcopy(self._records)


@pytest.mark.asyncio
async def test_fresh_service_instance_replays_same_snapshot():
    persisted_fixture = _records()
    before_restart = await LivingProductGraphService(_ReplayStore(persisted_fixture)).snapshot("product:alpha")
    after_restart = await LivingProductGraphService(_ReplayStore(persisted_fixture)).snapshot("product:alpha")

    assert serialize_product_snapshot(before_restart) == serialize_product_snapshot(after_restart)


class _FixtureDatabase:
    _TABLES = {
        "project": "projects",
        "product_direction": "product_directions",
        "product_vision": "product_visions",
        "capability": "capabilities",
        "capability_quality": "capability_quality",
        "decision": "decisions",
        "decision_prediction": "predictions",
        "prediction_outcome": "prediction_outcomes",
        "outcome_observation": "outcome_observations",
        "action_outcome": "action_outcomes",
        "observation": "observations",
        "insight": "insights",
        "task": "tasks",
        "grounded_batch_ingestion_receipt": "state_ingestions",
        "grounded_belief_projection": "belief_projections",
        "grounded_transition_revision": "transition_revisions",
        "grounded_reasoning_evidence_pack": "reasoning_evidence_packs",
        "grounded_rollout_reasoning_use": "rollout_reasoning_use",
        "grounded_consequence_rollout": "consequence_rollouts",
        "grounded_rollout_reconciliation": "rollout_reconciliations",
        "grounded_promotion_proposal": "promotion_proposals",
        "grounded_promotion_review": "promotion_reviews",
        "grounded_promotion_receipt": "promotion_receipts",
        "grounded_promotion_memory_lineage": "promotion_memory_lineage",
        "initiative": "initiatives",
        "milestone": "milestones",
        "work_item": "work_items",
        "agent_spec": "agent_specs",
        "roadmap_phase": "roadmap_phases",
        "capability_dep": "capability_dependencies",
        "cross_project_dep": "cross_project_dependencies",
        "affected": "decision_affected",
        "supersedes": "decision_supersedes",
        "led_to": "decision_led_to",
        "derived_from": "insight_derived_from",
        "relationship_assertion": "assertions",
        "assertion_event": "assertion_events",
        "operational_relationship": "operational_relationships",
    }

    def __init__(self, payload: dict):
        self.payload = payload
        self.calls: list[tuple[str, dict]] = []

    async def query(self, query: str, params: dict):
        self.calls.append((query, params))
        if "FROM ONLY" in query:
            return self.payload["product"]
        table = query.split("FROM", 1)[1].strip().split()[0]
        if table in self._TABLES:
            return self.payload["records"].get(self._TABLES[table], [])
        raise AssertionError(f"unexpected query: {query}")


class _FixturePool:
    def __init__(self, db: _FixtureDatabase):
        self.db = db

    @asynccontextmanager
    async def connection(self):
        yield self.db


@pytest.mark.asyncio
async def test_surreal_store_adapter_loads_the_complete_scoped_fixture():
    payload = json.loads(FIXTURE.read_text())
    database = _FixtureDatabase(payload)
    service = LivingProductGraphService(SurrealLivingProductGraphStore(_FixturePool(database)))

    snapshot = await service.snapshot("product:alpha")

    assert snapshot["projection_state"]["status"] == "complete"
    assert len(snapshot["capabilities"]["items"]) == 2
    assert len(snapshot["relationships"]["operational"]) == 1
    scoped_calls = [params for query, params in database.calls if "WHERE product" in query]
    assert scoped_calls
    assert all(str(params["product"]) == "product:alpha" for params in scoped_calls)
    assert all(query.lstrip().upper().startswith("SELECT") for query, _params in database.calls)
    bounded_calls = [(query, params) for query, params in database.calls if "LIMIT $limit" in query]
    assert bounded_calls
    assert all(params["limit"] == MAX_RECORDS_PER_SOURCE + 1 for _query, params in bounded_calls)


@pytest.mark.asyncio
async def test_surreal_store_adapter_truncates_oversized_family_at_stable_bound():
    payload = json.loads(FIXTURE.read_text())
    payload["records"]["observations"] = [
        {
            "id": f"observation:bounded_{index:03d}",
            "product": "product:alpha",
            "content": f"Synthetic bounded observation {index}",
        }
        for index in range(MAX_RECORDS_PER_SOURCE + 1)
    ]
    database = _FixtureDatabase(payload)
    store = SurrealLivingProductGraphStore(_FixturePool(database))

    records = await store.load_product_graph("product:alpha")

    assert len(records.records["observations"]) == MAX_RECORDS_PER_SOURCE
    state = next(row for row in records.source_states if row.source == "observations")
    assert state.status == "truncated"
    assert state.reason == "record_limit"
    assert state.limit == MAX_RECORDS_PER_SOURCE


class _UnavailablePool:
    @asynccontextmanager
    async def connection(self):
        raise RuntimeError("database offline")
        yield


@pytest.mark.asyncio
async def test_database_unavailability_returns_a_deterministic_degraded_snapshot():
    store = SurrealLivingProductGraphStore(_UnavailablePool())

    first = await LivingProductGraphService(store).snapshot("product:offline")
    second = await LivingProductGraphService(store).snapshot("product:offline")

    assert first == second
    assert first["product"]["state"] == "unknown"
    assert first["projection_state"]["status"] == "unknown"
    assert "missing_product_record" in _issue_codes(first)
    assert "source_unavailable" in _issue_codes(first)
    assert all(state["status"] == "unavailable" for state in first["source_states"])


@pytest.mark.parametrize("product_id", ["alpha", "", "project:alpha", "product:../alpha", "product:a/b"])
def test_noncanonical_product_identifiers_fail_closed(product_id: str):
    with pytest.raises(ValueError, match="product:<id>"):
        project_product_snapshot(product_id, LivingProductGraphRecords())
