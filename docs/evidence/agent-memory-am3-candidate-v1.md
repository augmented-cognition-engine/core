# ACE 0.7F Agent Memory AM3 candidate evidence v1

## Candidate coordinates

- Frozen AM2 authority head: `0938a63d577f817a68c61cbd8b56841c50d770e2`
- Exact isolated repair base: `9cf4d56fa88dc8c75c69a730319f05af976d3240`
- Base branch: `codex/v0.7-agent-memory-am2-correction-kind-fix`
- Candidate branch: `codex/v0.7-agent-memory-am3`
- Exact AM3 implementation artifact: `52c3d9c4eee52dea61f364dab052f7e94697f2c4`
- Checkout-free wheel: `ace_core-0.6.0-py3-none-any.whl`
- Wheel SHA-256: `8fb891f81c4a16fd313b3b5b764cd0b941c3640389d795003f4693c5b8a95e3f`
- Status: isolated stacked draft candidate; not accepted, merged, released, or supported

AM2 PR #119 and its branch remain unchanged. The separately published repair ref is exactly one
commit ahead of AM2 and changes only the AM2 graph projector, its focused AM2 conformance test, and
a narrow evidence note/index. The AM3 implementation artifact is exactly one later commit whose
merge base and parent are the repair head; its effective diff contains no AM2 implementation or
test path.

GitHub's connected write integration returned `403 Resource not accessible by integration` when
creating the repair draft. The exact review URLs are the
[AM2 correction-kind repair comparison](https://github.com/augmented-cognition-engine/core/compare/codex/v0.7-agent-memory-am2...codex/v0.7-agent-memory-am2-correction-kind-fix?expand=1)
and the
[AM3 comparison](https://github.com/augmented-cognition-engine/core/compare/codex/v0.7-agent-memory-am2-correction-kind-fix...codex/v0.7-agent-memory-am3?expand=1).

## Bounded claim

AM3 supplies authorized recall and the smallest eligible context set to exact receiving task,
composition-plan, stage, participant, and run-manifest coordinates. Durable content-free evidence
distinguishes selection, omission, injection, reflection, and decision-material use. A provider-free
matched no-memory control establishes only a bounded output delta as material influence.
Correctness, benefit, and causality remain unknown.

## Contract and durable artifact identities

The implementation freezes content-addressed `v1alpha1` contracts for receiving coordinates,
authenticated recall, retrieval policy/snapshot, per-signal scores, candidate/omission evidence,
separate instruction resolution, Context Planner request/result, injection, reflection,
decision-material use, I3 lineage, condition assignment, materiality comparison, and query-aid
derivation. The canonical context artifact is `ace.context.manifest/v1`.

Durable record kinds remain inside the existing `agent_memory_recall_v1alpha1` immutable-record
space: recall, instruction resolution, manifest, planner result, injection, reflection,
decision-material, context-use, materiality comparison, and memory-context lineage. No schema or
migration was added. Public receipts and manifests retain bounded coordinates, hashes, scores,
omissions, and telemetry only; selected bodies stay behind authorized assembly.

## Retrieval and context journey

Supported resolution tiers are deterministic structured lookup, frozen fused retrieval, and
bounded AM2 graph expansion. No response-reuse or compact-synthesis claim is made because the base
has no eligible owner for either. The frozen fused policy uses existing lexical and vector ports
when present, plus exact entity, independent temporal eligibility, bounded graph distance, source
diversity, explicitly governed reliability, and correction/uncertainty/lifecycle priority.
Unavailable optional signals contribute zero under the full denominator and remain visible.

The manifest binds exact selected and omitted candidates, retrieval state, instruction resolution,
budget, degradation, receiver, and source coordinates. Composition consumes only the manifest and
selection receipt references after its own present-tense participant/authority/current-head check.
Selection, injection, reflection, and decision-material use each have distinct receipts and never
grant participant, policy, authority, tool, plan, or run-manifest control.

The provider-free matched case held task, prompt contract, provider, model, configuration, decision
schema, and toolset constant. The memory condition selected `bounded_alpha`; the no-memory condition
selected `bounded_beta`. The bounded changed field establishes material influence only. The durable
comparison and use receipts fix benefit to `unknown` and bind the exact I3 receipt reference.

## Verification ledger

| Gate | Result |
| --- | --- |
| Frozen PR #117/#118/#119 topology and exact AM2 head | Passed before implementation; remote AM2 remained `0938a63d577f817a68c61cbd8b56841c50d770e2` before repair push |
| Isolated correction-kind repair | 20 AM2 tests passed including real restart; effective diff is one commit and four non-AM3 paths |
| Focused AM0-AM3 and real restart/rebuild | 141 passed with local Surreal access |
| I3, AC1-AC7 composition, retrieval, vector, graph, context, privacy, package and boundary matrix | 262 passed |
| Full supported non-E2E/non-extension lane | 7,605 passed, 245 skipped, 261 marker-deselected; five localhost-only sandbox failures passed unchanged in the exact unsandboxed rerun |
| Package, naked kernel and exactly eleven MCP tools | 48 passed, 1 intentional skip; both installed targets independently reported exactly eleven tools |
| Current schema/package integrity | 31 passed, 1 intentional skip; no schema, migration, package identity, or lock change |
| Ruff, format, lock, diff and bounded scans | Whole-repository Ruff, AM3-path format, lock, diff, authority/privacy/domain/composition/public-surface/secret scans passed |
| Checkout-free installed wheel in two clean targets | Passed in `/tmp/ace-am3-wheel-target-one.GUxuEL` and `/tmp/ace-am3-wheel-target-two.gJ4KUf`; both imported AM3 application/contracts from the target, resolved `ace.context.manifest/v1` and the fused-policy contract, and exposed exactly eleven thin MCP tools |

The real restart test wrote canonical AM2 and AM3 records through
`SurrealImmutableRecordStore`, restarted the real database, opened the prior content-free manifest
from a fresh Python process, created an independent later receiving task, recorded matched
decision-material/I3 lineage, rebuilt the AM2 graph from canonical decisions, and refused the old
manifest against the new projection head.

## Environmental and baseline disclosure

The sandboxed full-lane run could not bind localhost for the AM3 Surreal restart, two Canvas proxy
tests, the loopback egress guard, or the closed-port startup probe. All five exact tests passed
unchanged with approved loopback access. The initial wheel-build attempt could not resolve the
pinned build backend because sandbox DNS was unavailable; the identical approved build succeeded.

Whole-repository format checking remains red on 16 unrelated pre-existing files. All AM3-owned
paths and the isolated repair paths are formatted, whole-repository Ruff passes, and AM3 changes no
dependency or lock material.

## Frozen boundaries and AM4 gate

- AM0-AM2 and AC1-AC7 authorities, identities, contracts, branches, and PRs are unchanged.
- No schema, migration, database, vector store, search engine, graph source of truth, provider
  credential, public TaskCreate field, MCP tool, package identity, export, erasure, retention,
  autonomous learning, delivery effect, or external repository change is included.
- Private query, source, instruction, and context bodies do not enter public receipts.
- AM4 remains closed until the control tower accepts the isolated repair draft topology and this
  AM3-only stacked candidate. No retention, export, erasure, or governed evolution work has begun.

The exact architecture, authorization order, ranking policy, Context Manifest and composition/I3
bridge, fail-closed matrix, materiality rule, and AM4 gate are frozen in
`docs/design/agent-memory-am3-work-packet-v1.md`.
