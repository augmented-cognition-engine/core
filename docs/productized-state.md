# Build Productized State through an extension

Status: **0.3.x candidate public contract; not part of the published ace-core 0.3.0 artifact**

Productized State gives a builder one supported path from extension-owned context to inspectable,
durable reasoning without adding domain logic to Core or adding a twelfth MCP tool:

```text
install extension → inspect capabilities → ingest product context → reason and decide
→ inspect receipts → correct → restart → materially use the correction → inspect again
```

The fictional Fjord Operations package is the reproducible public example. Its data is CC0,
provider-free, and intentionally bounded. The example proves system behavior, not real-world causal
accuracy, hosted-model quality, or beneficial product impact.

## Builder commands

Install ACE and a compatible extension, configure the ordinary local runtime, and authenticate:

```bash
python -m pip install ace-core
python -m pip install --no-deps ./examples/ace_ext_fjord_operations
ace setup
ace doctor
```

Inspect the installed extension boundary before supplying product data:

```bash
ace state capabilities
```

The response binds the extension and adapter versions, registered task actions, and authority
boundary. Source mapping belongs to the extension. Authenticated product scope, stable identity,
validation, persistence, replay, and receipts belong to Core. Source text and models receive no
review, promotion, product-scope, or tool authority.

Create an ingestion envelope using contract `ace.product-state.ingestion/v1`. It contains no
product identifier because Core derives product scope only from the authenticated token:

```json
{
  "contract_version": "ace.product-state.ingestion/v1",
  "extension_id": "fjord-operations",
  "extension_version": "0.1.0",
  "adapter_name": "public-fixture",
  "manifest_external_id": "fjord-operations-public-corpus-v1",
  "extraction_run_id": "fjord-operations-extraction-v1",
  "submitted_at": "2026-06-05T00:00:00Z",
  "records": [
    {"input_key": "extension-owned-input", "record": {"...": "extension contract"}}
  ]
}
```

The complete public-safe records are in the extension's
[`public_corpus_v1.json`](../examples/ace_ext_fjord_operations/fjord_operations_extension/fixtures/public_corpus_v1.json).
Submit the envelope, invoke an extension-owned reasoning action, and inspect the integrated state:

```bash
ace state ingest /path/to/ingestion.json
ace state invoke /path/to/extension-invocation.json
ace state inspect
```

`ace state inspect` is a focused projection of the same authenticated, deterministic, read-only
Living Product Graph returned by `ace landscape`. It connects:

- ingestion receipts and exact replay identity;
- as-of belief projections and reviewed transition revisions;
- bounded task evidence and consequence rollouts;
- I1 decision/correction receipts, I2 deliberation attribution, and I3 material-use receipts;
- outcome reconciliation and promotion/correction lineage; and
- explicit unavailable, partial, degraded, contested, stale, and superseded states.

Capture a human correction through the existing observation lifecycle:

```bash
ace state correct \
  --domain operations \
  --correction-id FJORD-MONITORING-CORRECTION-V1 \
  "Monitor both active and standby cooling circuits."
```

Capturing a correction does not grant it promotion authority. Products that use the experimental
promotion-review action must still submit and inspect an authenticated review receipt. After an
intentional runtime restart, invoke the later task from a fresh process and require the exact
correction or promotion identity to materially change the decision. Retrieval or quotation alone
does not pass I3.

## Reproduce the frozen public journey

From a complete source checkout with Python 3.12, `uv`, and SurrealDB installed:

```bash
uv run python scripts/run_state_engine_product_journey.py \
  --config evaluations/fixtures/productized_state_journey_v1.json \
  freeze-check

uv run python scripts/run_state_engine_product_journey.py \
  --config evaluations/fixtures/productized_state_journey_v1.json \
  run \
  --work-dir /tmp/ace-productized-state \
  --output evaluations/results/productized_state_journey_v1.json \
  --markdown-output evaluations/results/productized_state_journey_v1.md
```

The runner builds and clean-installs the extension wheel, migrates schema zero to v171, upgrades a
v168 database to v171, uses `POST /product-state/ingestions` for exact ingestion/replay, and executes
the full passed K1–K3 decision, restart, correction, and material-use journey. It fails unless the
integrated read snapshot exposes every required receipt family and the MCP tool list remains exactly
eleven.

## Failure and authority boundaries

| Condition | Supported behavior |
|---|---|
| Adapter absent | `404 product_state_adapter_not_registered`; install/restart and inspect capabilities |
| Extension version mismatch | `409 product_state_extension_version_mismatch`; never substitute silently |
| Malformed or oversized input | request validation or `422 product_state_ingestion_rejected`; no partial authority |
| Caller supplies product scope | rejected; authenticated Core scope is authoritative |
| Exact replay | returns the same immutable batch receipt and identities |
| Foreign-product read | empty or `404`; no cross-product disclosure |
| Missing evidence | explicit empty/degraded coverage; no invented replacement |
| Stale transition | visible and rollout-ineligible |
| Simulation | always labeled simulation, never observation or belief |
| Correction | append-only; never rewrites the original task, rollout, or receipt |
| Interrupted task | predecessor degrades; an explicit retry creates an immutable successor |

The accepted evidence is bounded to one database, one API/worker deployment, synchronous adapter
clients, trusted installed Python extensions executing in process, and fictional data. It does not
claim hostile-code sandboxing, distributed ordering, multi-writer or multi-region operation,
autonomous learning, a general world model, real-world causal correctness, or beneficial impact.
