from __future__ import annotations

import copy
import json
import subprocess
import sys
from contextlib import asynccontextmanager
from pathlib import Path

import pytest

from core.engine.product.living_graph import (
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

FIXTURE = Path(__file__).parent / "fixtures" / "living_product_graph" / "complete.json"


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
        "assertion_states": {"accepted": 1, "contested": 1},
        "issue_count": 0,
    }
    assert snapshot["authority"] == {
        "mode": "read_only",
        "operational_roadmap": "docs/roadmap-status.md",
        "writes_permitted": False,
        "autonomous_dispatch": False,
    }
    assert snapshot["product"]["id"] == "product:alpha"
    assert snapshot["product"]["state"] == "observed"
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
            "resolver_version": "ace.assertion-resolver.v1",
            "subject": "capability:checkout",
        }
    ]
    assert snapshot["work"]["authority"] == "runtime_records_only_not_living_roadmap"
    assert snapshot["decisions"][0]["provenance"]["record_refs"] == ["decision:idempotency"]


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
    }
    assert [row["id"] for row in snapshot["relationships"]["operational"]] == [
        "operational_relationship:checkout_depends_billing"
    ]
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
    assert all(params["product"] == "product:alpha" for params in scoped_calls)


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


@pytest.mark.parametrize("product_id", ["alpha", "", "project:alpha"])
def test_noncanonical_product_identifiers_fail_closed(product_id: str):
    with pytest.raises(ValueError, match="product:<id>"):
        project_product_snapshot(product_id, LivingProductGraphRecords())
