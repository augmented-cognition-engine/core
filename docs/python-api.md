# Public Python API

ACE 1.0 freezes the documented `ace.core`, `ace.intelligence`, `ace.application`, and `ace.testing` contract families for the 1.0 compatibility line. Everything demonstrated here runs without a database, network, or model provider.

## The public Python surface

Everything below uses only public `ace.*` APIs and runs with no database, no network, and no model
provider.

### Compile a Domain Pack

```python
import hashlib
import json

from ace.intelligence.packs.compiler import compile_pack_document


def resource(payload: dict) -> bytes:
    return json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")


def digest(payload: bytes) -> str:
    return "sha256:" + hashlib.sha256(payload).hexdigest()


ontology = resource(
    {
        "contract": "ace.intelligence.ontology/v1alpha1",
        "module_id": "domain_ontology",
        "entity_types": [
            {
                "entity_type_id": "watched_subject",
                "attributes": [
                    {"attribute_id": "name", "value_type": "string", "required": True},
                    {"attribute_id": "tracked_value", "value_type": "number"},
                ],
            }
        ],
    }
)

manifest = resource(
    {
        "contract": "ace.intelligence.domain-pack-manifest/v1alpha1",
        "metadata": {
            "pack_id": "example_domain",
            "version": "0.1.0",
            "display_name": "Example Domain",
        },
        "resources": [
            {
                "resource_id": "ontology",
                "path": "modules/ontology.json",
                "digest": digest(ontology),
            }
        ],
        "modules": [
            {
                "module_id": "domain_ontology",
                "contract": "ace.intelligence.ontology/v1alpha1",
                "resource_id": "ontology",
            }
        ],
    }
)

pack = compile_pack_document(manifest, {"modules/ontology.json": ontology})

print(pack.metadata.pack_id)          # example_domain
print(pack.pack_digest)               # sha256:...  stable across key order and whitespace
print([m.module_id for m in pack.modules])
```

Compilation is fail-closed. Tamper with a byte and you get a `PackCompilationError` carrying a
`digest_mismatch` diagnostic with the exact path — not a silently different pack.

### Append immutable records and replay them

```python
import asyncio
from datetime import UTC, datetime

from ace.core import AppendOnlyTransactionRequestV1, ImmutableRecordV1
from ace.testing import InMemoryImmutableRecordStore

observed_at = datetime(2026, 8, 7, 12, 0, tzinfo=UTC)

record = ImmutableRecordV1(
    product_id="product:demo",
    record_space="live",
    record_kind="observation",
    record_key="watched_subject:acme@2026-08-07",
    payload_contract="ace.intelligence.observation/v1alpha1",
    payload={"tracked_value": 42.0},
    as_of=observed_at,
    available_at=observed_at,
    processing_order=0,
)

request = AppendOnlyTransactionRequestV1(
    product_id="product:demo",
    record_space="live",
    transaction_key="admit:watched_subject:acme@2026-08-07",
    records=(record,),
    submitted_at=observed_at,
)


async def main() -> None:
    store = InMemoryImmutableRecordStore()
    receipt = await store.append(request)
    replayed = await store.append(request)      # exact replay, not a second write
    assert receipt == replayed

    print(record.storage_id)                    # immutable_record:<stable digest>
    print(record.material_hash)                 # sha256:<canonical material>


asyncio.run(main())
```

Storage identity and material hash are **derived, never supplied**. Passing a `storage_id` that does
not match the record's scope and key is a validation error, so a caller cannot forge identity or
retroactively edit material behind a stable ID. `InMemoryImmutableRecordStore` is a reference port
for conformance and fault tests — production hosts supply Core's database-backed adapter.

### Other public entry points

| Import | What it gives you |
|---|---|
| `ace.core` | `GovernedStateStore`, `ImmutableRecordStore`, `CoreAuthorityResolver`, `GovernedReasoningService`, `DecisionV1Alpha1`, `OutcomeV1Alpha1`, `canonical_json`, `canonical_hash`, `stable_id` |
| `ace.intelligence` | `detect_numeric_shift` / `detect_live_numeric_shift`, `detect_categorical_shift`, `route_shift_as_signal`, `eligible_signal_routes`, `assemble_canonical_brief`, `derive_claim_epistemic_statuses`, `project_supersession_impact`, `interpret_prepared_source_mapping` |
| `ace.intelligence.packs.runtime` | `bind_prepared_activation`, `resolve_detector_rule`, `resolve_brief_synthesis_policy`, `resolve_epistemic_status_policy`, `resolve_feedback_policy` |
| `ace.application` | `LiveSourceIngressService`, `LiveIntelligenceBridgeService`, `LiveBriefSynthesisService`, `BriefSynthesisService`, `PreparedDecisionFeedbackService`, `DomainActivationAdmissionService` |
| `ace.testing` | `InMemoryImmutableRecordStore`, `exercise_live_source_ingress_restart`, `exercise_prepared_ledger_restart`, `exercise_prepared_source_mapping` |

Public contract names remain `v1alpha1` / `v1alpha2`, but those exact contracts are frozen for the
1.0 compatibility line. Incompatible changes require a new contract string plus a documented
migration and deprecation path.

---
