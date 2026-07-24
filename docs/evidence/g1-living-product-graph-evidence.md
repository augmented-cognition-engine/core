# G1 — assertion-backed, read-only Living Product Graph evidence

**Outcome:** G1 passed; IA-R1 is ready but not started

**Evidence date:** 2026-07-21

**Supported journey:** `ace landscape` → optional `ace assertion <stable-id>`
**Contract:** [`living-product-graph.md`](../living-product-graph.md)

## As-built audit

The audit began from current `origin/main` and did not find a prior G1 branch, standalone evidence
package, or task artifact. The projection and F0 assertion implementation were already present in
the initial public snapshot (`4cb3f2f`) and were reused. Brief-named
`docs/product-roadmap.md`, `docs/project-identity.md`, and `docs/partnership-thesis.md` are not in
the public repository; their public equivalents are `ROADMAP.md`, `README.md`, architecture,
governance, capability-maturity, and roadmap-status documents. No private replacement was assumed.

| Capability | Implementation location | Public access before G1 | Maturity before G1 | Existing evidence | Missing acceptance evidence | Compatibility risk | Failure before remediation | Required/remediated change |
|---|---|---|---|---|---|---|---|---|
| Relational proposals/assertions | `graph/assertions.py`, `graph/ontology.py`, v142 schema | Assertion CLI for one known ID | Implemented, internally callable | Resolver unit tests, disposable F0 persistence verifier | Product-facing composition | Low; versions already explicit | Individual assertion only | Reused unchanged |
| Deterministic semantic resolution | `resolve_proposals`, `persist_resolution` | Indirect | Reproducibly evidenced in F0 | Order, alias/inverse, duplicate, provider, conflict, human-confirmation tests | Connect result to supported landscape | Low | Not visible as a whole product | Reused unchanged |
| Canonical operational projection | `rebuild_projection`, `operational_relationship` | Indirect | Implemented and F0-evidenced | Accepted-only rebuild, concurrent arrival, fresh/upgrade/restart parity | Supported read response | Low | Internal table only | Reused unchanged |
| Product snapshot projection | `product/living_graph.py` | None | Implemented, internal, unit-evidenced | Whitelist, product scope, deterministic bytes, restart fixture | Contract, journey, failures, history | Medium; shape was unpublished | Internal Python call only | Frozen v1 contract; history, authority, object/lifecycle, issues added |
| Persistence read adapter | `product/living_graph_store.py` | None | Implemented, internal | Scoped fake-store and unavailable-DB tests | Explicit bounds and truncation | Medium; unbounded product tables | Possible oversized response | Stable ordering, 256-family bound, independent source receipts |
| Evidence/provenance | Assertion refs plus observation/outcome records | Assertion CLI only | Implemented | F0 and projection fixture | Missing/dangling behavior | Medium | Missing refs were silent | Explicit unresolved-evidence/history issues |
| Contestation/dissent | Assertion status, contradiction refs, reviews | Assertion CLI only | Implemented | Conflict and critic tests | Whole-product visibility | High if collapsed | Not composed publicly | Both sides visible; neither operational |
| Decision/correction/outcome linkage | Existing decision, observation, insight, prediction/outcome, structural records | Multiple unrelated CLI/MCP reads | Implemented, experimental composition | Component tests | One coherent read | Low | Users assembled internals manually | Included with stable provenance in snapshot |
| History/version behavior | Assertion events, resolver/ontology versions | Assertion CLI | Partial | F0 restart and assertion inspection | Snapshot history and compatibility policy | Medium | Snapshot omitted history | Assertion-event read family and version pin |
| Stable identity/serialization | Source IDs, canonical JSON, snapshot hash | None | Unit-evidenced only | Repeat/permutation/process tests | Public guarantee | Medium | Undocumented | 0.1.x policy and structural replay receipt |
| Public journey | CLI and exactly eleven thin MCP tools | No landscape journey | Missing | CLI and MCP boundary tests | Entire G1 user outcome | Low if CLI-only | No supported entry point | Added `ace landscape`; MCP remains eleven |
| Authority boundary | Pure projector, injected store, kernel boundary test | None | Internally evidenced | No transport/extension import test | Crafted input and method proof | High | No public endpoint to assess | Auth-token scope, GET-only route, SELECT-only adapter tests |
| Failure/degraded behavior | Source receipts and issue list | None | Partial | Sparse/unavailable/malformed tests | Version, bounds, leakage, recovery | Medium | Some omissions and raw host failures possible | Structured recovery, sanitization, 409/422, truncation |
| Atrium/extension boundary | Kernel boundary and reference extension API | Not applicable | Protected | Zero-extension and import guards | Prove G1 does not widen it | High if coupled | No G1 adapter | No Atrium change; no extension import or invocation |

The audit therefore distinguished four states: F0 resolution was implemented and reproducibly
evidenced; the snapshot was implemented and internally callable; no product-wide public access was
supported; and no standalone G1 replay or compatibility evidence existed.

## Frozen read contract and journey

The complete field, absence, identifier, ordering, bound, redaction, degraded-state, and
compatibility rules are frozen in [`living-product-graph.md`](../living-product-graph.md). The public
journey uses the existing supported CLI host:

```bash
uv run ace landscape
uv run ace assertion relationship_assertion:<id>  # optional deeper trail
```

The landscape includes the focal product, direct stored relationships, accepted/provisional/
contested/rejected assertion states, evidence/provenance, uncertainty, decisions, corrections,
expected and observed outcomes, history, explicit gaps, and projection metadata. It does not add a
twelfth MCP tool or make broad engine/Atrium details part of the contract.

## Read-only authority proof

The projector is pure and transport-independent. Its store is injected, contains SELECT statements
only, orders and bounds every multi-record query, and degrades independently by source. The API
derives scope from the signed product claim and accepts only a projection-version query parameter.
Tests show that extra product IDs, filters, serialized method payloads, POST requests, malformed
claims, unavailable databases, and unexpected internal exceptions cannot reach write or execution
authority or leak raw exception text.

The journey cannot create or modify graph records, change assertion state, resolve conflict, change
a decision, submit a task, authorize or dispatch action, invoke an extension, call a model, rewrite
provenance, or repair canonical state. Operational telemetry from the existing API host remains
outside product intelligence; the G1 service itself emits no telemetry or cache writes.

## Determinism and truth maintenance

The reused F0 evidence proves order-independent resolution across aliases/inverses, repeated and
duplicate proposals, provider/model labels, concurrent arrival, conflicts, legacy migration,
projection rebuild, and runtime/API restart. G1 adds byte-identical snapshot replay across input
order, repeated calls, and a fresh Python process. Assertions in accepted, provisional, contested,
rejected, stale, and superseded states are structurally checked.

The synthetic receipt records one accepted operational edge, one provisional causal assertion,
two mutually contested effect assertions, and one rejected undeclared predicate. Only the accepted,
eligible assertion becomes operational. Stale/superseded/rejected/provisional/contested assertions
remain inspectable but cannot become operational merely because historical rows exist.

## Reproducible evidence package

Input manifest: `evaluations/fixtures/g1_living_product_graph_manifest_v1.json`

Synthetic fixture: `evaluations/fixtures/g1_living_product_graph_v1.json`

Verifier: `scripts/verify_g1_living_product_graph.py`

Sanitized receipt:
`evaluations/results/g1_living_product_graph_v1.json`

Clean command:

```bash
uv sync --frozen
uv run python scripts/verify_g1_living_product_graph.py
```

Observed clean replay: 40.691 ms, 21,706 canonical bytes,
SHA-256 `3f1fa223369c36ac83c62d926ce60d1350bfa1d795d3d6a902515fd9efc2cee6`.
Repeated, reversed-input, and fresh-process results were byte-identical. The package required zero
LLM calls, zero domain writes, no database, no credential, and no private data.

## Failure evidence

Covered cases include unknown product, missing evidence, dangling assertion history, contested and
rejected-only relationships, unavailable or incomplete source tables, unsupported projection,
malformed identifiers, cycles, oversized families, database unavailability, partial history,
legacy unscoped data, absent authentication, crafted scope/filter/payload parameters, and
cross-product records. Results are bounded, deterministic, sanitized, non-mutating, and carry
recovery guidance. No test allows a read to invent or auto-repair a relationship.

## Verification

Local verification completed from the isolated G1 worktree:

| Gate | Result |
|---|---|
| Focused projection, API/CLI, F0, kernel, eleven-tool, and package compatibility suite | **80 passed** |
| Full non-E2E suite | **6,316 passed, 46 skipped, 234 deselected** |
| Zero-extension non-E2E suite | **6,308 passed, 47 skipped, 241 deselected** |
| Explicit zero-extension kernel boundary | **4 passed** |
| Disposable F0 persistence/restart/rebuild/API-restart verifier | **passed**, schema 142 and byte-identical fresh/upgrade/restart projections |
| G1 evidence replay | **passed**, repeated/reordered/fresh-process byte-identical |
| Ruff check and formatting check | **passed** |
| Dependency audit | **no known vulnerabilities** after raising the GitPython floor to the patched 3.1.51+ line |
| Changed-file secret scan and diff whitespace check | **passed** |
| Container build and live health check | **passed** against a disposable SurrealDB container |
| Wheel and sdist inventory | **passed**; G1 runtime/docs/evidence included, tests/UI/VCS/local paths excluded |

The initial sandboxed full-suite attempt had four loopback-socket failures caused by sandbox network
denial; the same complete command passed outside that restriction and is the result recorded above.
No shared Canvas adapter changed, so local Canvas validation was not applicable. The authoritative
[acceptance CI run](https://github.com/augmented-cognition-engine/core/actions/runs/29872552736)
passed Lint, fast tests, naked-kernel tests, Canvas typecheck/test/build, security audit, and the
dependent Docker build. Pull request #15's reconciliation commit is still required to pass a new
final-head run before merge; post-merge main CI is the final repository-state verification.

## Limitations

- Snapshot pagination is not supported in v1; each record family returns at most 256 stable rows
  and declares truncation.
- Stable product ownership is required. Unscoped legacy records are excluded until migrated.
- The snapshot reports stored evidence and assertion state; it does not assess truth with an LLM.
- The single snapshot is product-scoped, not a general arbitrary-depth graph query.
- Atrium rendering, graph editing, assertion disposition, and execution remain outside G1.
- The public fixture is synthetic. It proves contract behavior and determinism, not real-world data
  completeness or model quality.

## Reconciliation

The local acceptance matrix and complete branch CI passed, so the versioned roadmaps and
[public live roadmap issue](https://github.com/augmented-cognition-engine/core/issues/2) move G1 to
passed and IA-R1 to ready in pull request #15. That closeout commit must receive a completely green
final-head CI run before merge, and merged main must then receive green CI. Any failure reopens G1
rather than weakening or bypassing a gate. IA-R1 implementation is explicitly outside this work.
