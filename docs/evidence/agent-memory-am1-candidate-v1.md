# Agent Memory AM1 episodic experience ledger candidate evidence v1

- Date: 2026-08-12
- AC7 parent: `c7ff511a80ab3bdd3a13e7ca270567eaf6b3b1bf`
- AM0 parent: `48e1aea6ff848be63aab2d49adda1428231ca522` (draft PR #108 authority)
- Exact convergence: `a55edc2848c742dc98cfa01f6632bb75d5f31d81`
- Convergence branch: `codex/v0.7-agent-memory-composition-convergence`
- Candidate branch: `codex/v0.7-agent-memory-am1`
- Exact AM1 implementation artifact: pending immutable implementation commit
- Status: isolated publication candidate; not accepted, merged, released, or supported

## Candidate claim and limit

AM1 is intended to provide a provider-neutral episodic ledger for authorized sessions, ordered
turn and event experience, exact or explicitly unavailable source spans, bounded inspection,
content-private transcript reads, deterministic batch/stream normalization, import lifecycle, and
idempotent durable replay. Adapters only propose inert source events. Core retains canonical
identity, authenticated scope, authority, lifecycle, commit order, and content-free receipts.

This record does not claim typed semantic assertions, reconciliation, recall or relevance ranking,
Context Manifest injection, durable instruction policy, learning, memory benefit, composition
runtime behavior, or release readiness. System and tool content remains recorded experience and
never becomes instruction or authority merely because it appears in the ledger.

## Frozen topology and AM0 preservation

The convergence commit has exactly two parents, in order: AC7
`c7ff511a80ab3bdd3a13e7ca270567eaf6b3b1bf` and AM0
`48e1aea6ff848be63aab2d49adda1428231ca522`. Its common ancestor is exact 0.7E
`10bbed620291ac5f552c3313dd37580938a5b9d7`. PR #108 remains authoritative for its exact
21-file SHA-256 manifest. The convergence publication must preserve this merge without squash or
history rewrite; the AM1 publication must target the exact convergence ref.

## Ownership and persistence boundary

| Boundary | Candidate responsibility | Explicit non-ownership |
|---|---|---|
| Core contracts | Canonical scope, source/event/span/import identities, state and content-free receipt grammar | Provider schemas, semantic meaning, relevance, or authority inferred from content |
| Application services | Present-tense authorization, exact adapter selection, deterministic normalization, ingest/read orchestration, retry and repair projection | Foundational identity, database truth, model extraction, or unrestricted export |
| Fixture adapters | Parse two materially different provider-free inputs into inert proposals | Scope, canonical identity, authority, lifecycle, persistence, or fallback |
| Durable owner | Existing `ImmutableRecordStore` and `SurrealImmutableRecordStore` opaque append/receipt transaction machinery | A new schema, migration, database, vector store, parallel event ledger, or provider-specific repository |

No public MCP tool, TaskCreate field, Domain Pack contract, composition selection policy,
activation rule, delivery/export authority, effect authority, package identity, or naked-kernel
startup behavior may change.

## Conformance evidence

| Check | Result |
|---|---|
| Two-adapter canonical identity and source-span equality | Passed in provider-free AM1 conformance; exact IDs frozen in fixture |
| Deterministic out-of-order batch and stream normalization | Passed in focused AM1 conformance |
| Exact replay no-op and divergent replay conflict | Passed against both the in-memory Core-port seam and real SurrealDB, including a concurrent exact race |
| Duplicate handling and atomic injected failure | Passed; injected Surreal failure left zero records and no receipt |
| Present-tense authorization before ingest and every read | Passed in application service tests; authorization is rechecked before body lookup and commit |
| Cross-product, cross-principal, stale/revoked/expired/rotated denial | Cross-product, cross-principal, stale, denied, restricted, expired and quarantined paths passed with uniform authorization-before-lookup denial |
| Nonexistent-resource non-disclosure and content-free receipts | Passed in focused service and strict-contract tests |
| Tool/system non-authority | Passed in adapter and Core identity tests |
| Queued/ready/partial/failed/stale/retry/repair lifecycle | Contract matrix and predecessor-bound retry/repair service append passed |
| Fresh service/API/database restart and ordered replay | Passed using the existing Surreal owner: close/reopen in a fresh service plus a separate process with a fresh database client reproduced exact replay, ordered listing, private span read and divergent conflict |
| Focused AM0/AM1 and relevant Core/Intelligence/boundary tests | `198 passed, 1 skipped`; all `tests/agent_memory`: `104 passed`, including `57` AM1 tests and the real Surreal proof |
| Full supported non-E2E/non-extension lane | `7,570 passed, 244 skipped, 261 deselected`; four sandbox-only localhost denials all passed in a separate unsandboxed rerun (`4 passed`) |
| Package, naked-kernel, extension-disabled and exactly-eleven-MCP checks | `31 passed, 1` intentional naked-kernel skip; installed source and wheel expose exactly eleven tools |
| Ruff, format, lock, diff, schema, authority, privacy, domain, composition and secret scans | AM1 changed paths, lock, diff, schema tests, domain boundaries, AC6/AC7 provider-free checks and secret scan passed; whole-repository Ruff baseline remains red as disclosed below |
| Checkout-free installed-wheel reproduction | Passed in two clean target directories; checkpoint artifact SHA-256 recorded below and final immutable artifact rebuilt after commit |

AM1 changed paths pass Ruff lint and format, `uv lock --check`, and `git diff --check`. Schema
focused tests passed (`20 passed`); domain boundaries passed (`21 passed`); the secret scan found no
findings across all 18 AM1 paths; AC6 and AC7 provider-free verifiers passed. No schema or migration
file changed, and no World/Market domain vocabulary was introduced.

The whole-repository Ruff checks retain pre-existing/convergence baseline debt outside the AM1
change set: one import-order finding in the additive convergence initializer
`ace/intelligence/contracts/__init__.py`, plus 16 unrelated files that the formatter would change.
No AM1-changed file is implicated. The broad test lane's four initial failures were caused solely by
the filesystem sandbox denying localhost bind/connect; the exact four tests passed outside that
sandbox.

## Installed-wheel reproduction

The checkpoint candidate wheel was built without publishing it:

- artifact: `ace_core-0.6.0-py3-none-any.whl`;
- disposable build path:
  `/tmp/ace-am1-wheel-build.Q8tyu1/ace_core-0.6.0-py3-none-any.whl`;
- SHA-256: `fcbb1d5236ccd51f16760a5cf337fd21a938c2731b946834b210e88d29e16682`;
- clean checkout-free targets: `/tmp/ace-am1-wheel-target-one.623ya8` and
  `/tmp/ace-am1-wheel-target-two.OdGNIR`.

Both targets imported `ace.core.agent_memory_ingestion` and
`ace.application.agent_memory_ingestion` from the installed wheel, loaded the packaged frozen AM1
fixture, and reproduced the same two-adapter normalized digest
`sha256:d9b8bb1c89ca23a0f7bf58172a1bf61739742552ac6a5551d3b46556349969c8`, canonical session
`agent_memory_session:a5926f27a3fe0bb34b43e3fbfed2386e`, three event identities, and three
turn identities. An AST inspection of the installed `ace_mcp_client/server.py` found exactly the
eleven frozen public tools with no additions or duplicates.

The first isolated-build attempt could not resolve the exactly pinned `setuptools==83.0.0` because
sandbox DNS was unavailable. The existing repository environment already contained exact
setuptools 83.0.0, so the successful build used `python -m build --wheel --no-isolation`; no
dependency, lock, package-version, or source change was made. The wheel was not uploaded or
published. A checkout-free wheel will be rebuilt from the exact immutable implementation commit,
and that commit-specific artifact will supersede this checkpoint coordinate in the publication
record.

## Privacy, recovery, and receipt boundaries

Public receipts may expose only bounded identifiers, digests, spans, ordering and lifecycle state.
Transcript/event/span bodies remain behind a separately authorized body interface. Authorization
must occur before lookup so foreign scope and nonexistent resources have the same non-disclosing
failure. Exact replay returns the prior receipt; divergent material at one idempotency identity
conflicts. Indeterminate work requires receipt lookup before retry, and partial compatibility work
must reach a truthful terminal or repair-required state without rewriting committed history.

## Known limitations and AM2 gate

AM1 is bounded source-experience infrastructure. It performs no semantic extraction, truth
promotion, conflict reconciliation, ranked recall, context injection, learning, or benefit
evaluation. Provider-free fixtures are conformance inputs, not supported live connectors.

AM2 remains closed until the control tower accepts both the convergence-only and AM1-only draft
publication topology, records the exact final AM1 artifact coordinate and integrated base, and
accepts the completed restart, privacy, authority, schema/recovery, package, and test evidence.
