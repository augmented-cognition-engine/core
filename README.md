<div align="center">

# ACE — Augmented Cognition Engine

**The open-source foundation for governed intelligence.**

ACE turns changing evidence into entities, shifts, signals, briefs, and decisions—with provenance,
authority, and feedback built in. Self-hosted and provider-neutral, it commits every observation,
derivation, brief, decision, and outcome as an immutable, product-scoped record under explicit
authority.

![version 0.4.2](https://img.shields.io/badge/version-0.4.2-blue)
![Python 3.12](https://img.shields.io/badge/python-3.12-blue)
![License Apache-2.0](https://img.shields.io/badge/license-Apache--2.0-green)
![status: developer preview](https://img.shields.io/badge/status-developer%20preview-orange)

[Quickstart](#quickstart) ·
[What ACE does](#what-ace-does) ·
[Architecture](#architecture-one-install-two-bounded-contexts) ·
[Domain Packs](#domain-packs-add-a-vertical-without-touching-the-kernel) ·
[Python surface](#the-public-python-surface) ·
[Limitations](#maturity-and-limitations) ·
[Roadmap](https://github.com/augmented-cognition-engine/core/blob/main/ROADMAP.md)

</div>

---

## What ACE does

ACE is the **Augmented Cognition Engine**: a self-hosted runtime for building systems that must
reason over changing evidence without losing provenance, authority, or institutional memory. The
configured model supplies inference inside the loop; ACE owns the loop around it.

- **Understand.** Admit evidence with source identity and time, resolve it into a temporal entity
  graph, and preserve the difference between observations, claims, inference, and unknowns.
- **Reason.** Classify a problem, dynamically compose useful perspectives and methods, orchestrate
  deliberation, and synthesize an inspectable recommendation grounded in the admitted context.
- **Decide.** Record the recommendation, human disposition, decision, rationale, and evidence as
  durable, attributable state rather than leaving them in a chat transcript.
- **Observe and improve.** Reconcile decisions and forecasts with later outcomes, preserve
  corrections, and make governed feedback available to later reasoning. ACE does not silently
  rewrite history or grant itself new authority.

### Two connected loops

ACE supports deliberate reasoning over a problem and continuous intelligence over changing
sources. They converge on the same governed decision and outcome model.

```mermaid
flowchart LR
    subgraph REASON["Decision reasoning"]
        PROBLEM["problem or decision"] --> CLASSIFY["classify + compose"]
        CLASSIFY --> DELIB["multi-perspective deliberation"]
        DELIB --> REC["grounded recommendation"]
    end

    subgraph INTEL["Continuous intelligence"]
        SRC["authorized sources"] --> OBS["observations + entity graph"]
        OBS --> CHANGE["shifts + signals"]
        CHANGE --> BRIEF["grounded brief"]
    end

    REC --> DEC["governed decision"]
    BRIEF --> DEC
    DEC --> OUT["observed outcome"]
    OUT -.->|"correction + material use"| CLASSIFY
    OUT -.->|"governed feedback"| CHANGE

    CORE["Core<br/>authority · state · provenance · receipts"] -.->|governs| REC
    CORE -.->|governs| BRIEF
    CORE -.->|commits| DEC
    CORE -.->|commits| OUT
```

The **decision-reasoning loop** begins when a person or product brings a problem. ACE selects and
coordinates a problem-fit reasoning approach, records how the result was produced, and keeps the
decision available for inspection and correction.

The **continuous-intelligence loop** begins with an authorized source. ACE admits an Observation,
updates entity state, detects a Shift against a baseline, routes a meaningful Signal, and assembles
a cited Brief for a subscriber or decision context.

The same application can use both: an intelligence Brief can trigger deeper deliberation, and the
resulting decision and outcome can change what the intelligence system watches next.

### What you can build

- **Domain intelligence applications** such as World Intelligence for public-issue sensemaking or
  Market Intelligence for competitors, products, narratives, customers, and go-to-market change.
- **Decision systems** for product, strategy, research, operations, and other work where the
  reasoning and its evidence must survive beyond one model response.
- **Governed AI backends** that need provider-neutral inference, scoped authority, append-only
  state, replay, human disposition, and attributable outcome feedback.

ACE is infrastructure, not a finished vertical application. Domain-specific products ship
separately and consume the same public Core + Intelligence contracts.

---

## How ACE is structured

Most AI systems treat state as a side effect: a chat log, a vector index, or a cache. ACE treats
governed state as part of the product and makes the reasoning replayable.

- **One install, one repository.** `ace-core` ships **Core** and **Intelligence** together. There is
  no second service to run to get the reasoning and intelligence contracts.
- **Core owns cognition and control.** Authority, temporal and immutable state, reasoning,
  receipts, decisions, and outcomes. Nothing durable is written except through Core.
- **Intelligence owns sensing and orientation.** The Observation → Entity Snapshot → Shift → Signal
  → Brief pipeline, monitors, routing, and pack conformance are domain-neutral.
- **Domain Packs supply vocabulary and policy.** Ontology, source mappings, shift definitions,
  personas, synthesis templates, and policy ship as independently versioned, **inert declarative
  data** — compiled and content-addressed, never imported or executed.

Adding a vertical means supplying a pack and registered connectors, not modifying the kernel.

### How continuous intelligence runs

Each hop from Observation through Brief is a typed contract, not a convention. Every resource
carries lineage to its exact inputs, including content digests and availability time, so a Brief
can be walked back to the admitted source material that produced it.

The pipeline runs in two clearly separated modes:

| Mode | What it means | What it can touch |
|---|---|---|
| **PREPARED** | Analysis over supplied material. Pure functions over contract values. | No network, no clock authority, no side effects. |
| **LIVE** | Governed effects against an authorized real source. | One exact resolved source definition, through an activation-bound, authority-checked adapter. |

Interpretation functions are mode-typed and refuse to cross: `detect_numeric_shift` accepts only
PREPARED snapshots, `detect_live_numeric_shift` only LIVE ones. **No pure Intelligence function
grants LIVE authority** — the application bridge must independently prove a committed activation
and authorize persistence through Core.

### The architecture is the feature

ACE wraps a **lean coordinating** Core around specialized reasoning and Intelligence capabilities;
the octopus is useful inspiration for that shape, **not a literal ratio** of code or intelligence.
The existing cognitive runtime remains visible inside this architecture: **Human ↔ ACE ↔ LLM**,
**A nine-layer cognitive pipeline**, and **Dynamic composition** describe how ACE assembles and
governs reasoning. Core + Intelligence + Domain Packs describe how the same machinery becomes a
reusable intelligence engine without putting domain nouns or executable behavior in the kernel.

ACE provides graph-grounded, calibrated foresight. It projects conditional consequences of
decisions, exposes the mechanisms and uncertainty behind them, observes what actually happens, and
uses resolved forecasts to improve later reasoning.

---

## Architecture: one install, two bounded contexts

```mermaid
flowchart TB
    subgraph PKG["ace-core — one install"]
        direction TB
        subgraph APP["ace.application — governed services"]
            A1["LIVE source ingress"]
            A2["LIVE Intelligence bridge"]
            A3["Brief / case-brief synthesis"]
            A4["decision feedback · supersession impact"]
        end
        subgraph INT["ace.intelligence — invariant machinery"]
            I1["pack compiler + conformance"]
            I2["detection · routing · synthesis"]
            I3["epistemic status · derivation families"]
            I4["monitors · personas · subscriptions"]
        end
        subgraph CORE["ace.core — governed cognition"]
            C1["authority + activation"]
            C2["immutable records · append-only transactions"]
            C3["governed-state heads · preconditions"]
            C4["reasoning receipts · decisions · outcomes"]
        end
    end

    PACK[["Domain Pack<br/>independently versioned<br/>inert JSON"]] -.->|compiled + digested| INT
    CONN[["source connector<br/>registered by the host"]] -.->|bounded registry| APP
    APP --> INT
    APP --> CORE
    INT --> CORE
    HOST["host adapter<br/>(private: core.engine)"] --> APP
```

The dependency direction is enforced, not just described: `ace.application` depends on `ace.core`
and `ace.intelligence`; `ace.intelligence` depends on `ace.core`; **nothing under `ace/` imports the
host.** Architecture gates in the test suite assert this.

### What each layer owns

| Layer | Owns | Explicitly does not own |
|---|---|---|
| **`ace.core`** | Authority resolution and authority-use receipts; capability-use receipts; immutable records and atomic append-only transactions; governed-state heads with rechecked preconditions; canonical source snapshots and URI/IP validation; governed reasoning requests, bindings, and terminal receipts; decisions and outcomes. | Domain vocabulary. Core never learns what a "competitor" or a "port call" is. |
| **`ace.intelligence`** | The Domain Pack compiler and its fail-closed diagnostics; the Observation → Entity Snapshot → Shift → Signal → Brief resource contracts; numeric-delta and categorical-transition detection; signal routing; brief synthesis and canonical rendering; epistemic status and derivation families; supersession impact; monitors, persona bindings, subscriptions. | Persistence, authority, network access, or a clock. Importing `ace.intelligence` performs no discovery, I/O, compilation, activation, or host composition. |
| **`ace.application`** | Services that compose the two: LIVE source ingress, the LIVE Intelligence bridge, Brief and case-brief synthesis, prepared intelligence ledger, decision feedback, supersession-impact admission, domain-activation admission. | Connector implementations, transport, or scheduling — those are the host's. |
| **Domain Pack** (separate artifact) | Ontology, source mappings, detection rules, personas and routing rules, synthesis templates, epistemic-status vocabularies, feedback policy, capability requirements, authority requests, overlay slots. | Code. A pack is data all the way down. |

---

## Domain Packs: add a vertical without touching the kernel

A Domain Pack is a manifest plus JSON module resources. The compiler
(`ace.intelligence.packs.compiler.compile_pack_document`) is a **pure, deterministic function**: it
performs no discovery, import, I/O, clock read, model call, secret lookup, registry mutation, or
persistence operation.

What that buys you:

- **Content addressing.** Every resource is digest-checked; every module is canonicalized and
  hashed; the pack gets a `pack_digest`. Semantically identical packs with different key order or
  indentation compile to byte-identical IR. One changed attribute changes the digest.
- **No executable surface.** The compiler rejects any key named `regex`, `template`, `expression`,
  `predicate`, `handler`, `script`, `eval`, `exec`, `jsonpath`, and friends — and rejects mappings
  that try to select or override host-owned envelope fields such as `source_digest`,
  `activation_id`, or `product_id`. A pack cannot smuggle in behavior.
- **Fail-closed diagnostics.** Errors arrive as stable `(severity, code, path, message)` records:
  `unknown_target_entity_type`, `missing_required_outputs`, `module_cycle`, `digest_mismatch`.
- **Independent versioning.** Packs carry their own `pack_id` and semantic `version`, and declare
  the compiler and runtime contracts they target. They ship on their own schedule.
- **Independent verification.** A pack that declares no epistemic-status module for a template
  simply does not get status-aware synthesis — it does not silently get a permissive default.

### A generic pack, end to end

Domain Packs are **JSON** (`media_type` is fixed to `application/json`); the compiler parses with a
strict reader that rejects duplicate object keys, non-finite numbers, and lone surrogates. Nothing
below is vertical-specific — swap `watched_subject` for `vessel`, `competitor`, `service`, or
`counterparty` and the kernel is unchanged.

`modules/ontology.json` — what exists in your world:

```json
{
  "contract": "ace.intelligence.ontology/v1alpha1",
  "module_id": "domain_ontology",
  "entity_types": [
    {
      "entity_type_id": "watched_subject",
      "display_name": "Watched Subject",
      "attributes": [
        { "attribute_id": "name", "value_type": "string", "required": true },
        { "attribute_id": "tracked_value", "value_type": "number" },
        { "attribute_id": "status", "value_type": "string" }
      ]
    }
  ],
  "relation_types": []
}
```

`modules/detection.json` — what counts as a material change:

```json
{
  "contract": "ace.intelligence.detection/v1alpha2",
  "module_id": "domain_detection",
  "numeric_delta_rules": [
    {
      "detector_id": "tracked_value_moved",
      "entity_type_id": "watched_subject",
      "attribute_id": "tracked_value",
      "metric": "percent_change",
      "threshold": 10.0,
      "direction": "any",
      "shift_type": "tracked_value_shift",
      "signal_type": "tracked_value_signal"
    }
  ],
  "categorical_transition_rules": [
    {
      "detector_id": "status_changed",
      "entity_type_id": "watched_subject",
      "attribute_id": "status",
      "transitions": [{ "from_value": "nominal", "to_value": "degraded" }],
      "shift_type": "status_shift",
      "signal_type": "status_signal"
    }
  ]
}
```

`pack.json` — the manifest that binds them, with declared capabilities, authority requests, and
operator-tunable overlay slots:

```json
{
  "contract": "ace.intelligence.domain-pack-manifest/v1alpha1",
  "metadata": {
    "pack_id": "example_domain",
    "version": "0.1.0",
    "display_name": "Example Domain",
    "description": "A domain-neutral illustration of the pack contract."
  },
  "resources": [
    { "resource_id": "ontology",  "path": "modules/ontology.json",  "digest": "sha256:<64 hex>" },
    { "resource_id": "detection", "path": "modules/detection.json", "digest": "sha256:<64 hex>" }
  ],
  "modules": [
    {
      "module_id": "domain_ontology",
      "contract": "ace.intelligence.ontology/v1alpha1",
      "resource_id": "ontology"
    },
    {
      "module_id": "domain_detection",
      "contract": "ace.intelligence.detection/v1alpha2",
      "resource_id": "detection",
      "depends_on": ["domain_ontology"]
    }
  ],
  "capability_requirements": [
    {
      "requirement_id": "public_snapshot",
      "capability": "source_snapshot",
      "contract": "ace.source.snapshot/v1alpha1"
    }
  ],
  "authority_requests": [
    { "request_id": "read_public_source", "authority": "source_read" }
  ],
  "overlay_slots": [
    { "slot_id": "watched_subjects", "value_kind": "string_list", "required": true }
  ]
}
```

Additional module contracts a pack may declare, all compiled by the same function:
`ace.intelligence.source-mapping/v1alpha1` (source field → ontology attribute, with bounded
transforms only), `ace.intelligence.personas/v1alpha1` (personas plus signal-routing rules),
`ace.intelligence.synthesis/v1alpha1` and `/v1alpha2` (brief templates),
`ace.intelligence.epistemic-status/v1alpha1` and `/v1alpha2`, and
`ace.intelligence.decision-outcomes/v1alpha1` (feedback policy).

---

## What 0.4.0 adds

0.4.0 is the **Governed Cognition** release. It closes the gap between "ACE can analyze material you
hand it" and "ACE can go get material under authority and stay governed the whole way."

- **Governed LIVE source ingress** as a packaged public application service. One exact resolved
  source definition is captured through an activation-bound, authority-checked adapter and admitted
  atomically as five durable records — acquisition receipt, canonical source snapshot, Observation,
  Entity Snapshot, admission receipt — under four rechecked governed-state heads.
- **The governed LIVE Intelligence bridge and LIVE Brief synthesis.** Admitted snapshots derive
  Shift → Signal → attention dispositions, and route-triggered Briefs run through Core governed
  reasoning, with exact idempotent replay and restart reopening of every admission.
- **Bounded connector composition.** LIVE cognition is composed into the host exclusively through a
  private adapter. Connectors register in a constructor-supplied registry keyed by exact artifact
  identity: **no dynamic entry-point loading, no embedded code in domain packs, and no persistence
  path outside Core's immutable-record port.**
- **Fail-closed acquisition.** Source acquisition fails closed on scope, URI, redirect, DNS/IP
  rebinding, payload size, digest, replay, timing, and authority violations. Authority-use receipts
  are single-use and non-reusable across admissions.
- **Packaged conformance seams** (`ace.testing`) so an external package can exercise the public
  service contracts — including restart and replay — without importing the host.
- **Unchanged public surface.** Exactly eleven MCP tools. Extension-disabled (naked-kernel) startup
  still works and composes no LIVE service. Schema head stays at **v175**, with additive,
  append-only governed-state and immutable-record migrations.

The 0.4.0 milestone also carries a teaching-experience track (propose → inspect → approve → use →
measure → revise or retire). The governed-LIVE slice above is what shipped; see the
[roadmap](https://github.com/augmented-cognition-engine/core/blob/main/ROADMAP.md) for the rest.

Full detail: [CHANGELOG](https://github.com/augmented-cognition-engine/core/blob/main/CHANGELOG.md).

---

## Quickstart

### Fastest verified path — no database, no provider, no keys

The Core and Intelligence contracts are pure. You can compile a pack and exercise the full
derivation machinery on a laptop in seconds:

```bash
git clone https://github.com/augmented-cognition-engine/core ace
cd ace
uv sync
uv run pytest tests/intelligence -q
```

That runs the Domain Pack compiler, detection, routing, synthesis, epistemic status, source
mapping, ledger, activation, and governed-reasoning suites against no external service.

### Full self-hosted runtime

Running the reasoning service adds a database and a model provider.

**Prerequisites:** macOS or Linux · Git · Python 3.12 ·
[`uv`](https://docs.astral.sh/uv/) · Docker Engine with Compose v2 · credentials for one
[supported provider](https://github.com/augmented-cognition-engine/core/blob/main/docs/providers.md).

```bash
uv run ace setup
```

`ace setup` asks which model route to use, generates local credentials, writes `.env` with mode
`0600` without replacing existing secrets, starts SurrealDB through Docker Compose, applies every
migration, starts the ACE API as a local background process, and logs in the CLI and thin MCP
client. It is safe to rerun; if it is interrupted, run the same command again.

```bash
uv run ace doctor          # configuration, database, schema, auth, provider routing, API, MCP
uv run ace service status
uv run ace service logs --lines 80
uv run ace service stop    # preserves the SurrealDB volume
```

`ace doctor` verifies operational readiness only. It does not certify the correctness of data
already in the graph, and by default it spends no model tokens — add `--live-provider` for one
explicitly requested minimal call.

Manual control, for CI or development:

```bash
cp .env.example .env
docker compose -f infra/docker-compose.yml up -d surrealdb
uv run python scripts/schema_apply.py
uv run uvicorn core.engine.api.main:app --host 127.0.0.1 --port 3000
uv run ace login --api-key '<the API_KEY from .env>'
```

### Package-only install

The distribution is `ace-core`; it provides the `ace` import package, the `ace` CLI, and the
`ace-mcp-client` command.

```bash
python -m pip install ace-core
python -c "import ace; print(ace.__version__)"
ace --help
```

The self-hosted runtime path above uses the source checkout because it carries the pinned Compose
stack and the release-maintained local service scripts.

### Test gates

```bash
make test-fast          # the fast suite (pytest -m "not e2e")
make test-naked-kernel  # the kernel with NO extensions loaded, plus the boundary guard
make lint               # ruff check + format --check
```

---

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

Public contracts are `v1alpha1` / `v1alpha2`. They are versioned in the name so a change is visible,
but they are alpha and may change on a preview minor release.

---

## MCP: still exactly eleven tools

The thin, pure-HTTP MCP client exposes the same eleven tools it did in 0.2 and 0.3. **0.4.0 adds
none.**

| Tool | Purpose |
|---|---|
| `ace_start` | Establish product and session context |
| `ace_load` | Load relevant accumulated intelligence |
| `ace_capture` | Persist an observation or correction |
| `ace_task` | Submit orchestration with a durable receipt |
| `ace_status` | Retrieve task or system status |
| `ace_capture_idea` | Preserve an emerging idea |
| `ace_search` | Search accumulated intelligence |
| `ace_briefing` | Retrieve a return briefing |
| `ace_impact` | Inspect likely code impact |
| `ace_history` | Inspect file or symbol history |
| `ace_related` | Find related code and knowledge |

To connect a client, register the command `uv run ace-mcp-client` with its working directory set to
the clone. It reuses the token written by `ace login`. Call `ace_start` first, then `ace_load(...)`
before domain work.

`ace_task` uses a durable asynchronous receipt contract: it returns within a bounded submission
window with either a completed result or a `pending`/`running` task ID, and long reasoning continues
after the MCP call ends. Retrieve it with `ace_status(filter="task:…")`. `completed`, `failed`, and
`degraded` are distinct terminal states — a polling timeout is not a task failure.

Setup and provider details:
[`docs/providers.md`](https://github.com/augmented-cognition-engine/core/blob/main/docs/providers.md)
·
[`docs/capability-maturity.md`](https://github.com/augmented-cognition-engine/core/blob/main/docs/capability-maturity.md)
·
[`docs/governed-cognition-builder.md`](https://github.com/augmented-cognition-engine/core/blob/main/docs/governed-cognition-builder.md)
·
[`docs/governed-cognition-operations.md`](https://github.com/augmented-cognition-engine/core/blob/main/docs/governed-cognition-operations.md)

---

## Security and governance invariants

These are enforced by contract validation and architecture tests, not by convention.

**Authority**
- Every LIVE effect requires a resolved authority grant and a committed domain activation. Prepared
  analysis grants no authority under any circumstance.
- Authority-use receipts are single-use and cannot be reused across admissions.
- Capability use is bound to exact artifact identity, so a capability granted for one artifact does
  not carry to another.
- Models may propose. Models cannot approve, activate, roll back, expire, supersede, retire, or
  grant execution authority.

**State**
- All durable writes go through Core's immutable-record port as atomic append-only transactions.
  There is no persistence path around it.
- Governed-state heads carry preconditions that are **rechecked inside the commit**; a stale head
  fails the transaction rather than racing it.
- Identity and material hashes are derived from canonical JSON. Supplying a mismatched
  `storage_id`, `material_hash`, or `request_hash` is a validation error.
- Replay is exact: the same transaction key with the same material returns the same receipt; the
  same key with different material raises a replay conflict.

**Acquisition**
- Source acquisition fails closed on scope, URI, redirect, DNS/IP-rebinding, payload-size, digest,
  replay, timing, and authority violations. HTTPS URIs are validated exactly and IP literals are
  checked against non-public ranges.
- **ACE does not browse.** There is no automatic or arbitrary web access. A connector may fetch only
  one exact resolved source definition, and only through the bounded registry the host constructed.

**Packs and connectors**
- Domain Packs are inert data. The compiler rejects executable-shaped fields and refuses mappings
  that touch host-owned envelope fields.
- Connectors register in a constructor-supplied registry keyed by exact artifact identity. There is
  no dynamic entry-point loading for LIVE source connectors.
- The naked kernel (`ACE_DISABLE_EXTENSIONS=1`) boots and composes no LIVE service. `make
  test-naked-kernel` is that boundary in CI form.

Report vulnerabilities per
[SECURITY.md](https://github.com/augmented-cognition-engine/core/blob/main/SECURITY.md).

---

## Repository map

```
.
├── ace/                      ← the public package (this is the product surface)
│   ├── core/                 ← authority, immutable records, governed state, reasoning, decisions
│   ├── intelligence/
│   │   ├── contracts/        ← pack, resources, detection, synthesis, epistemic, ledger, monitors…
│   │   ├── packs/            ← compiler, runtime binding, activation, diagnostics
│   │   └── detection/        ← numeric delta, categorical transition
│   ├── application/          ← LIVE ingress, LIVE bridge, brief synthesis, decision feedback
│   └── testing/              ← packaged conformance seams for external packages
├── core/
│   ├── engine/               ← the host runtime (private): API, CLI, orchestration, adapters
│   ├── schema/               ← SurrealDB migrations (head: v176)
│   └── ui/canvas/            ← Atrium, an experimental React research canvas (repository beta)
├── ace_mcp_client/           ← thin pure-HTTP MCP client (the eleven tools)
├── extensions/reference/     ← the worked extension example the kernel actually loads
├── examples/                 ← independent example packages
├── docs/                     ← architecture, providers, maturity, operations, evidence
├── evaluations/              ← frozen fixtures and acceptance results
├── infra/                    ← docker-compose for SurrealDB + API
├── scripts/                  ← schema apply, journeys, verification, scaffolding
└── tests/                    ← including tests/intelligence, the no-service contract suite
```

`ace/` is the public boundary. `core/engine/` is the host and is private — public `ace` contracts
stay host-free, and host adapters are the only `core.engine` edge into the public package.

---

## Maturity and limitations

**0.4.0 is a developer preview and a single-node governed-cognition release.** Read this section
before you build on it.

What is bounded:

- **Single node.** One ACE API/worker deployment and one SurrealDB/SurrealKV database. Distributed
  ordering, multi-writer consistency, multi-region failover, and exactly-once delivery across
  independent databases are **not** claimed.
- **Trusted extensions only.** In-process Python extensions must be explicitly trusted. There is no
  hostile-code isolation.
- **Alpha contracts.** The `v1alpha1` / `v1alpha2` public contracts may change on a preview minor
  release. Changes are visible in the contract string.
- **Domain Packs and connectors are independently versioned** and are **not** part of this release's
  compatibility promise. There is no domain-pack marketplace, registry, or distribution channel —
  packs are artifacts you build and supply.
- **Python 3.12 only.**

What ACE does not claim:

- No hosted SaaS. ACE is self-hosted; you run the database and bring your own model credentials.
- No supported graphical UI. Atrium is experimental repository-beta source, not part of the Python
  artifact, the supported runtime, or the golden path.
- No automatic or arbitrary web access.
- No real-world causal accuracy, calibrated forecasting, autonomous learning, general model of
  reality,
  or demonstrated beneficial impact outside the frozen, bounded evaluation scopes recorded in
  [`docs/evidence/`](https://github.com/augmented-cognition-engine/core/blob/main/docs/evidence/README.md).
- Security review to date is an independent **AI** review, not a human penetration test,
  professional audit, or certification. That limitation travels with the evidence.

Current supported/experimental/internal boundaries:
[`docs/capability-maturity.md`](https://github.com/augmented-cognition-engine/core/blob/main/docs/capability-maturity.md).
Point-in-time acceptance receipts:
[`docs/evidence/`](https://github.com/augmented-cognition-engine/core/blob/main/docs/evidence/README.md).

---

## Roadmap and contributing

The north-star loop is:

```text
understand → reason → decide → act with authority → observe outcomes → improve future reasoning
```

0.4.0 delivers the governed-cognition span of that loop. 0.5.0 (*Reasoning into Action*) carries an
approved decision into bounded, attributable action; 0.6.0 (*Measured Intelligence*) promotes or
retires reasoning revisions because of measured outcomes.

- [Public roadmap](https://github.com/augmented-cognition-engine/core/blob/main/ROADMAP.md) — outcome
  state, sequencing, and declared boundaries
- [Roadmap project board](https://github.com/orgs/augmented-cognition-engine/projects/1) — live Now /
  Next / Later
- [Architecture](https://github.com/augmented-cognition-engine/core/blob/main/docs/architecture.md) —
  as-built boundaries
- [Contributing](https://github.com/augmented-cognition-engine/core/blob/main/CONTRIBUTING.md) ·
  [Code of conduct](https://github.com/augmented-cognition-engine/core/blob/main/CODE_OF_CONDUCT.md) ·
  [Security policy](https://github.com/augmented-cognition-engine/core/blob/main/SECURITY.md)
- [Issues](https://github.com/augmented-cognition-engine/core/issues) — the best first contribution is
  a Domain Pack for a vertical we have not tried, plus the diagnostic it made you wish existed

Good contributions to start with: a new detector family, a synthesis template contract, a source
connector against a public API, or a conformance seam that makes an external package easier to test.

---

## License

Apache-2.0 — see
[`LICENSE`](https://github.com/augmented-cognition-engine/core/blob/main/LICENSE) and
[`NOTICE`](https://github.com/augmented-cognition-engine/core/blob/main/NOTICE).

Existing ACE code is copyright Edwin Amirian; contributors retain copyright in their contributions
and license them under Apache-2.0. QueryLabs LLC is the founding sponsor. Separately distributed
extensions and Domain Packs state their own licenses. The default stack runs SurrealDB separately;
the SurrealDB server is source-available under BSL 1.1 rather than OSI open source.

<div align="center">

---

**Bring the domain. ACE keeps the receipts.**

[Quickstart](#quickstart) ·
[Domain Packs](#domain-packs-add-a-vertical-without-touching-the-kernel) ·
[Limitations](#maturity-and-limitations)

</div>
