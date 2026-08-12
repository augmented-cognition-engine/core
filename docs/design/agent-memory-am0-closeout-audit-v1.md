# Agent Memory AM0 closeout audit v1

**Status:** final integrated migration candidate verified; draft PR authorized, merge and release unauthorized
**Date:** 2026-08-11
**Base:** `10bbed620291ac5f552c3313dd37580938a5b9d7` (draft PR #105)
**Verification branch:** `codex/agent-memory-am0-final-verification`

## Outcome

The AM0-A through AM0-F contract, conformance, migration, and integrated verification gates are
candidate complete. This does not dispatch AM1 or authorize staging, commit, push, pull request,
merge, release, or publication. The Context Manifest runtime implementation remains owned outside
AM0; this packet retains only its exact historical contract identity and creates no competing use
receipt.

No result in this audit changes Core 0.6.0, capability maturity, package metadata, public MCP
semantics, or a public Agent Memory support claim.

## Slice disposition

| Slice | Local state | Evidence | Remaining gate |
|---|---|---|---|
| AM0-A vocabulary and value contracts | Implemented | Strict provider-neutral Core and Intelligence contracts; deterministic identity; round-trip and unknown-version tests | Shared architecture/release reconciliation before closeout |
| AM0-B time, spans, scope, lifecycle | Implemented | Three independent selectors; every locator variant; explicit unavailable forms; host-owned scope; append-only lifecycle requiring the exact prior ledger coordinate; erasure proof bound to the exact erase-pending request | Runtime enforcement belongs to AM1-AM4 |
| AM0-C ports and transaction semantics | Implemented at contract/conformance level | Core ledger/dependency ports; Intelligence reconciliation/query/projection/composition ports; replay, atomic failure, exact-coordinate conflict, indeterminate receipt recovery, dependency-complete erasure, lifecycle-before-delivery filtering, projection rebuild, typed failure, and product-fence tests | SurrealDB runtime conformance begins in AM2; second backend remains AM9 |
| AM0-D existing-capability bridges | Partially implemented by design | Canonical Core source snapshot → provenance bridge; Core authority/approval bindings; reference-only Candidate Receipt → Context Manifest → I3 lineage | Grounded/legacy runtime adapters remain AM1-AM3; Context Manifest implementation is absent from this baseline and must land through its owner |
| AM0-E threat model | Contract-level gate implemented | [`agent-memory-am0-threat-model-v1.md`](agent-memory-am0-threat-model-v1.md) maps controls to executable tests and names residual runtime owners | AM1-AM9 must prove runtime controls; AM0 makes no production-security claim |
| AM0-F architecture and closeout conformance | Integrated candidate verified | Provider/host/import boundaries, naked-kernel checks, exact eleven-tool inventory, PR #104 linked-worktree regression, installed wheel, lock/diff/lint, and supported full gate | Separate landing/publication decision |

## Reconciliation findings

| Authoritative surface | Current baseline finding | AM0 action |
|---|---|---|
| `ROADMAP.md` | Correctly records public Core 0.6.0 Measured Intelligence as passed; contains no Agent Memory milestone claim | Preserve unchanged until a separately authorized roadmap update |
| `docs/capability-maturity.md` | Correctly describes public 0.6.0; contains no Agent Memory support claim | Preserve unchanged; AM0 remains proposed/local |
| Shared product and architecture language | Integrated 0.7D/0.7E base carries the owning Intelligence Builder stack | Preserved unchanged; AM0 adds no competing narrative or fourth layer |
| Context Manifest | Historical evidence documents `ace.context.manifest/v1`; its runtime implementation is not part of the integrated base | Preserve the exact contract identity as a reference-only link and verify its owning implementation when supplied; do not invent a competing receipt |
| I3 intelligence-use receipt | `intelligence-use-receipt-v1` exists in current main | Reference it exactly; decision lineage without its receipt fails validation |
| Package/release identity | `pyproject.toml`, `ace.__version__`, engine version, roadmap, maturity page, and release evidence agree on 0.6.0 | No version or release change in AM0 |
| Public MCP | Thin server remains exactly eleven tools | No additions or semantic widening |

## AM1 entry decision

The AM0-A through AM0-C handoff condition is satisfied on the integrated candidate: a later,
explicitly dispatched AM1 can use the frozen identity,
scope, exact/unavailable source-coordinate, three-clock, session/turn, lifecycle, and ledger-port
contracts without redefining them. This report is not permission to begin AM1, publish AM0, import
files from the preserved dirty checkout, or begin production onboarding-agent work.

The bounded handoff is now specified in
[`agent-memory-am1-work-packet-v1.md`](agent-memory-am1-work-packet-v1.md). Its frozen fixture is a
specification only: AM1 runtime work has not started, and exact derived identities remain an AM1-A
acceptance output.

## Closeout blockers

AM0 may be landed or declared publicly closed only after all of the following occur through
separately authorized work:

1. review and accept this exact migrated AM0 diff and its integrated verification record;
2. preserve the Context Manifest as an exact reference-only external identity until its owner
   supplies a landed implementation; that future integration must not create a competing receipt;
3. separately authorize any public roadmap, capability maturity, architecture index, evidence index, or issue
   ledger without changing the already closed 0.6.0 claim;
4. explicitly authorize staging and commit; and
5. separately authorize push, pull request, merge, release, or publication.

## Active-stack coordination boundary

The active control-tower and ACE 0.7 tasks currently own:

- PR #100: stable 0.7A Domain Pack/compiler/conformance foundation;
- PR #102: 0.7B Intelligence Builder Connect plus canonical public narrative; and
- the new 0.7C stack: Map/Ontology Agent proposals, immutable edits, explicit approval, and restart
  continuity.

AM0/AM1 must not implement or redefine those source-profile, ontology-agent, concept-model,
activation, or public onboarding surfaces. Agent Memory may later retain exact references to their
approved artifacts and preserve continuity across sessions, but it cannot own their semantics or
authority. Until the stack lands, AM0 remains isolated on current `origin/main` and unpublished.

## 0.7D, 0.7E, and 0.7G contract coordination

The control tower has frozen these cross-lane seams. They are handoff constraints, not permission
to expand AM0 or begin AM1 runtime integration:

- **0.7D Watch + Brief:** branch `codex/v0.7-intelligence-builder-watch-brief` is in progress from
  exact stack base `e1f6492db2417cbeccee14c04c5803ba1502afa6`. Immutable approved Watch
  proposals and inert cited Brief previews have restart-stable identities. Agent Memory may later
  retain those identities as source/derivation lineage only. They are not canonical memory,
  Monitors, Subscriptions, Shifts, or canonical Brief resources.
- **0.7E Activation + Domain Conformance:** a sibling activation-plan-bound admission path will
  preserve exact plan/spec/effect/approval and resulting activation revision/receipt coordinates.
  Its accepted historical seam is
  `ace.application.domain-activation-commit-reference/v1alpha2`. Memory may optionally retain an
  exact full-material-digest reference to that committed tuple through the provider-neutral Core
  historical-lineage envelope. Both contracts are permanently `authority_stage=historical_reference`
  and `live_authority=false`. Memory cannot grant
  activation, infer current authority from an earlier approval, or imply rollback, upgrade,
  suspension, or reactivation; each later operation requires its own exact authorized plan and
  receipt.
- **0.7G Agent Composition:** task composition plans and stage-run manifests are task-time control
  records, not Domain Activation Plans and not durable memory. Future composition may consume an
  authorized Candidate Receipt and exact Context Manifest/I3 lineage. Composition cannot produce,
  approve, activate, reconcile, rank, or erase memory.

AM0 needs no new 0.7D, 0.7E, or 0.7G type. Its existing provider-neutral stable-reference and
`derived_from` seams can carry the future identities after their owning contracts are published.
Integration must fail closed until the exact owning contract version and immutable identity are
available.

## Future lifecycle, export, erasure, and evaluation coordinates

Export and memory/no-memory evaluation are deliberately not added to AM0: export/import is AM4,
and matched-control materiality is AM3/AM6. Their future contracts must preserve these coordinates:

- export request authority, authenticated scope, exact ledger-through coordinate, lifecycle
  snapshot, canonical record/source/span identities, provenance, export policy/version, omissions,
  artifact digest, and a content-free immutable receipt;
- any retained activation lineage as historical coordinates only, never as evidence of current
  activation or present authority;
- erasure request lifecycle event, exact prior ledger coordinate, dependency-index snapshot, every
  primary and derived dependency, removal evidence, authority receipt, and content-free proof;
- memory treatment invocation, no-memory control invocation, exact matched-condition receipt,
  preregistered outcome criterion, Candidate Receipt, Context Manifest items, I3 material-use
  receipt, and restart coordinate, without predeclaring benefit.

The AM0 erasure proof now binds the exact erase-pending request event, and every non-initial
lifecycle event requires the exact prior ledger coordinate. AM4 still owns export/import runtime,
external-body deletion, backup/recovery limitations, and proof that erased material cannot return
after restart.

## Exact AM1 entry conditions

AM1 Core ledger implementation may begin only when all of the following are true:

1. the reviewed AM0 contract set is available from an authorized landed commit, or a separately
   approved isolated AM1 worktree records the exact AM0 file hashes as an explicit dependency;
2. AM0's final rebase passes focused contracts, boundary checks, naked-kernel startup, and the
   exact eleven-tool MCP inventory with no ownership drift;
3. the target branch/worktree is clean, isolated, and contains no preserved dirty-checkout or
   unrelated 0.7 lane material; and
4. AM1 receives an explicit implementation authorization naming its base and migration set.

AM1 may not integrate Watch/Brief or activation lineage until the control tower additionally
supplies the exact completed 0.7D commit/PR and the exact landed 0.7E activation-plan,
revision/receipt, rollback, and reactivation contract versions. 0.7G is not an AM1 ingestion
dependency; its exact task-composition and run-manifest identities become a later AM3/I3 lineage
coordination input.
