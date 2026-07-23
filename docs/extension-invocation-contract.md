# Experimental extension-invocation contract

Date: 2026-07-22

Outcome: **experimental contract verified; E1 remains not ready**

## Frozen boundary

ACE extensions can register a domain-owned task action that resolves structured references into
the existing durable task runtime and optionally projects a bounded domain outcome. Core owns the
authenticated invocation, product access scope, product/user-scoped idempotency, task identity,
provider execution, attempt lineage, persistence, and public receipt. The extension owns domain
reference resolution, task preparation, and outcome meaning.

This is an experimental HTTP execution surface. It is not part of the supported 0.1.x contract,
does not add a public MCP tool, and does not promote E1. The thin MCP surface remains exactly
eleven tools.

## Versioned contracts

`extension-invocation-v1` accepts:

- an extension ID, optional exact extension version, and registered action;
- authenticated workspace and actor scope supplied by Core;
- a bounded question and parameters object;
- at most 60 typed references with optional versions and digests;
- correlation and idempotency identities; and
- an optional wait bound of zero to two seconds.

The extension returns an `ExtensionTaskPlan`. Every input reference must appear exactly once in
`context_resolution` with one of:

- `resolved` — record content was retrieved within the authenticated scope;
- `declared` — the identifier influenced preparation without a retrieval claim;
- `missing` — the extension could not resolve it; or
- `rejected` — the extension deliberately refused it.

Missing, duplicate, or unknown resolution entries fail preparation. `missing` and `rejected`
entries remain visible and keep receipt coverage degraded.

A `resolved` entry must carry a record version, content hash, product scope, and one matching
bounded context record. Core appends those records to the private task description under an
explicit untrusted-data delimiter. Record content is neither persisted in the invocation metadata
nor returned in the public receipt, and instructions embedded in a record are not granted authority.
`missing` and `rejected` entries require a bounded failure reason.

`extension-invocation-receipt-v1` records:

- invocation, correlation, capability, and contract identity;
- immutable attempt number plus predecessor/successor task links;
- bounded input reference and resolution evidence;
- extension outcome, immutable created-artifact references with producer provenance, and ordinary
  task/provider provenance;
- I1, I2, and I3 receipt links when present;
- explicit missing/degraded coverage and bounded failures; and
- the existing task retrieval endpoint and the linked-attempt resume endpoint.

Stored future envelope or receipt versions fail closed to an empty degraded v1 projection. They
are not reinterpreted. Unknown fields are recanonicalized away; public strings and nested outcome
data are size-bounded and credential-redacted.

Version negotiation is deliberately narrow:

| Case | Behavior |
|---|---|
| Current v1 envelope and exact registered extension version | accepted |
| Current v1 envelope with extension version omitted | resolves the currently registered action |
| Current v1 envelope with a different extension version | generic 409 |
| Input contract not listed by the action | generic 409 before preparation |
| Persisted future envelope or receipt | empty degraded v1 projection; artifacts are not reinterpreted |

This is compatibility evidence for the in-tree v1/reference combination, not a multi-package
version-skew matrix and not a stable 0.1.x promise.

## Supported implementation path

```text
POST /extension-invocations
  → authenticate actor
  → resolve a registered extension action
  → validate exact per-reference accounting
  → persist the ordinary task receipt before provider work
  → run ordinary ACE orchestration
  → project a bounded extension outcome
  → GET /tasks/{task_id}
```

`POST /extension-invocations/{task_id}/resume` returns pending, running, and completed attempts
unchanged. For a failed or restart-degraded attempt it creates one idempotent successor task,
records `retry_of_task_id` on the successor, and records `resumed_by_task_id` on the predecessor.
This is attempt-level recovery; it does not claim continuation of a lost provider stream,
distributed task claiming, or exactly-once external side effects.

The capability manifest is available at authenticated
`GET /extension-invocations/capabilities`. It exposes contract metadata, never resolver or
projector callables. Authenticated `GET /extension-invocations/schemas` publishes the bounded
machine-readable v1 shapes, while `GET /extension-invocations` lists only the caller's
product-and-user-scoped public receipts (optionally filtered by an authorized workspace).
`GET /extension-invocations/{task_id}/history` returns the caller-scoped attempt lineage grouped
by the immutable root task link, not by a caller-chosen correlation label.
`POST /extension-invocations/{task_id}/cancel` delegates to Core's durable task cancellation only
when the registered capability explicitly advertises `cancel`; unsupported cancellation is
recorded as unavailable and rejected.

The in-tree reference extension registers `product:product-check`, which declares reference
identities without pretending to retrieve records it cannot access. The provider-free
`run_task_action_conformance` helper checks manifest shape, input-version negotiation, exact
reference accounting, outcome validation, receipt schema and bounds, private-plan and resolver
content exclusion, projection-failure preservation, and credential redaction. It does not replace
runtime, persistence, isolation, cancellation, or version-skew tests.

The reusable helper and Core runtime suite divide conformance evidence as follows:

| Conformance case | Evidence owner |
|---|---|
| Registration, deterministic discovery, negotiation, valid preparation, completed receipt | `run_task_action_conformance` plus `tests/extensions/test_task_actions.py` |
| Idempotent replay and duplicate-key conflict | Core durable-task contract in `tests/test_task_public_contract.py` |
| Projection failure, missing resolver accounting, bounded/redacted output | Provider-free helper and extension contract/fixture tests |
| Extension unavailable after restart, foreign-product access | `tests/test_extension_invocations_api.py` |
| Runtime restart | Real SurrealKV two-process test in `tests/test_i1_restart_persistence.py` |
| Concurrent resume and attempt N+1 | `tests/test_extension_invocations_api.py` |
| Cancellation states | Extension API and Core task public-contract tests |
| Unknown contract versions and malicious stored payloads | Compatibility fixtures in `tests/fixtures/extension_invocations` |

An extension can run the provider-free helper for its own action implementation. Runtime-wide
claims remain Core-owned and must use the Core API/persistence suite; an extension callback alone
cannot prove database isolation, restart recovery, or concurrency.

## Authority and isolation

- Both manifest and invocation endpoints require ordinary ACE authentication.
- Task reads, history, and resume operations enforce product and user ownership; explicit
  workspace claims are also enforced when present in the authenticated token.
- Registered authority and feature requirements fail closed before extension preparation.
- The private persisted envelope, question, parameters, actor coordinates, and extension resolver
  state are removed from public task projections.
- Only an extension-scoped `Registry(extension_id=..., extension_version=...)` can register a task
  action; bare registries cannot claim an extension identity.
- The extension is trusted in-process code and remains responsible for enforcing product scope in
  its own data sources. Core cannot make an unsafe extension resolver safe.
- This packet adds authenticated experimental HTTP execution authority. It adds no CLI command,
  MCP tool, unattended scheduler, permission escalation, or release.

## Failure matrix

| Case | Public behavior |
|---|---|
| Unknown action | Generic 404 code without reflecting caller identifiers |
| Extension version mismatch | Generic 409 code without reflecting version strings |
| Preparation exception | Bounded credential-redacted 422 |
| Duplicate/missing/unknown resolution | Preparation fails closed |
| Missing or rejected reference | Invocation may run; receipt remains degraded |
| Outcome projection failure | Task result remains available; receipt names projection failure |
| Provider/task failure | Failed attempt and bounded failure remain resumable |
| Runtime restart while running | Prior attempt becomes degraded and explicitly resumable |
| Runtime restart during pending cancellation | Degraded stopped-process cancellation state is retained distinctly |
| Concurrent resume retry | Deterministic successor idempotency key reuses the same attempt |
| Foreign product, user, or claimed workspace | Ownership check returns not found |
| Required authority absent | Generic 403 before extension preparation |
| Required feature absent | Generic 404 before extension preparation |
| Unsupported cancellation | Durable unavailable state plus generic 409 |
| Supported cancellation | Core acknowledges cancellation or reports a degraded stopped-process state |
| Future envelope/receipt | Empty degraded v1 projection; no artifact reinterpretation |
| Credentials in errors/outcomes/notes or sensitive-keyed fields | Keys and values are redacted before public projection |
| Zero extensions | Kernel, Canvas, and eleven-tool MCP boundary remain operable |

## Restart evidence

`tests/test_i1_restart_persistence.py` starts a disposable SurrealKV database and production API,
creates a deterministic registered extension invocation, seeds an attempt owned by a prior runtime,
stops the API, starts a fresh API against the same store, and resumes through a fresh client.
Production startup replays schema zero through v157.

The prior attempt becomes degraded and resumable. The fresh successor completes with attempt
number 2, links back to the prior task, updates the predecessor's successor link, retains
provider/model provenance, and preserves the existing I1/I2/I3 receipts in the same restart
journey. Observed result: **1 passed in 27.11 seconds**.

## Verification record

| Gate | Result |
|---|---|
| Focused invocation/task/kernel/migration contracts | **78 passed** |
| Broader extension/kernel/MCP contracts | **98 passed** |
| Real schema-zero-to-v157 database/API restart | **1 passed** |
| Canvas resume helper | **30 passed** |
| Naked Canvas build and extension-leakage boundary | **9 passed; build passed** |
| Core-only Canvas suite and production build | **290 passed; build passed** |
| Wired Marketing Canvas fixture | **452 passed; build passed** |
| Full non-E2E suite with extensions | **6,636 passed, 46 skipped, 235 deselected** |
| Full non-E2E naked-kernel suite | **6,628 passed, 47 skipped, 242 deselected** |
| Reference/scaffold/fixture contract | **39 passed** |
| Repository Ruff and format | **passed; 1,819 files formatted** |
| actionlint | **passed** |
| Wheel and sdist build/inventory from commit archive | **passed; v157, API, contracts, reference action, and evidence present; tests/UI/private files absent** |

The two full-suite totals include nine passing tests from the merged L1 preregistration packet.
The wired Marketing Canvas figure is the fixture-backed result for the same merged runtime and
Marketing integration; the current Core worktree has no adjacent Marketing UI fixture, so the
current-turn rerun is the 290-test Core-only row.

Commands executed from the repository root:

```bash
uv run pytest tests/extensions/test_task_actions.py tests/test_extension_invocations_api.py \
  tests/test_task_public_contract.py tests/test_kernel_boundary.py tests/test_schema_migration_lint.py \
  tests/test_schema_migration_errors.py tests/test_migration_safety.py -q --tb=short
uv run pytest tests/extensions tests/test_extension_invocations_api.py \
  tests/test_extension_registry.py tests/test_kernel_boundary.py tests/test_mcp_specs.py \
  tests/test_mcp_tools.py tests/voice/test_proactive_line_extension.py -q --tb=short
uv run pytest tests/test_i1_restart_persistence.py -q --tb=short
uv run pytest -m "not e2e" -q --tb=short
ACE_DISABLE_EXTENSIONS=1 uv run pytest -m "not e2e and not requires_extensions" -q --tb=short
uv run ruff check .
uv run ruff format --check .
actionlint
(cd core/ui/canvas && npm test -- src/app/journey/useOrchestrationSession.test.ts)
(cd core/ui/canvas && npm run build:naked)
(cd core/ui/canvas && npm test && npm run build)
git archive HEAD | tar -x -C <temporary-source>
uv build --out-dir <temporary-source>/dist <temporary-source>
```

The local repository-wide reruns used explicit `--ignore` arguments for unrelated untracked
workspace directories while they existed; those directories were not staged and are absent from
the clean package/CI scope. The first naked-kernel run exposed an attributable mutable-dictionary
alias in cancellation persistence: the stored `requested` snapshot appeared to change when the
later stopped-process state was assembled. Core now persists a copy, the two-state focused
regression passes, and the complete naked-kernel rerun is green. An intermediate rerun also hit a
pytest import-name collision inside an unrelated untracked extension checkout; no product code was
changed for it.

## Explicit limitations and E1 gap

- A complete receipt proves bounded contract coverage and execution completion, not correctness,
  benefit, safety, or faithful domain interpretation.
- An extension may be buggy, harmful, or incorrectly scoped; it runs as trusted in-process code.
- Attempt-level resume may repeat provider calls or extension preparation. It is not transaction
  replay or exactly-once execution.
- Outcome projection is generated/extension-defined data, not proof of causality or quality.
- Cancellation is process-local and cooperative; distributed recovery, external-side-effect
  cancellation, resource guarantees, and portable task claiming remain T1.
- E1 still requires at least one packaged non-reference example, a published conformance matrix,
  compatibility/version-skew evidence, and preservation of the eleven-tool boundary across those
  packages. This contract is a prerequisite, not that evidence.
