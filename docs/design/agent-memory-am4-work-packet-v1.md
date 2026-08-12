# ACE 0.7F Agent Memory AM4 work packet v1

## Exact dependency and scope

AM4 starts at exact cumulative integration head
`f761a682164d10e2ff81ba38cd2d0c987b4f8efd` on
`codex/v0.7-cumulative-integration-acceptance`. The cumulative review-only PR #122 and every
upstream AM0-AM3 branch remain unchanged. AM4 is implemented only on
`codex/v0.7-agent-memory-am4` and must be reviewed as a stacked draft against the cumulative
integration branch.

AM4 adds lifecycle, retention, canonical scoped export/import, and dependency-complete live-store
erasure. It does not add AM5 evolution, AM6 policy learning, AM7 adapters, AM8 UI, AM9 backend
portability, public task fields, package identity changes, an MCP tool, a database, or a second
authority, query, export, persistence, or receipt system.

## Ownership and reuse

- Core retains authenticated product/principal/session/source scope, exact ledger coordinates,
  lifecycle meaning, authority receipt references, immutable-record transaction ownership, and
  content-free lifecycle/erasure/export/import receipts.
- Intelligence retains AM2 assertions/graph and AM3 recall/Context Manifest/use-lineage meaning.
  AM4 reads those exact identities only to enumerate dependencies and filter current recall.
- Application services authorize before scans, reads, export, import, retention, or erasure and
  compose the existing Core store. They mint no reusable authority.
- `ImmutableRecordStore` and `SurrealImmutableRecordStore` remain the durable owners. AM4 adds
  product-fenced scanning, exact-material atomic delete-plus-proof, and cross-record-space atomic
  administrative import. It adds no schema or migration.
- Exact external content bodies enter only through `ExternalMemoryBodyStore`. A hard erasure or
  redaction requiring an external body fails closed when the owning store is absent or cannot
  prepare a rollback-capable mutation.

Historical activation, composition, delivery/export, and effect coordinates remain lineage with
`live_authority=false`; AM4 never treats them as present authority and never deletes another
bounded context's authoritative record merely because memory references it.

## Lifecycle meanings

| Meaning | Current recall | Historical ledger | Content body | Derivatives |
| --- | --- | --- | --- | --- |
| Supersession | old target ineligible; exact successor required | preserved | preserved | preserved with lineage |
| Expiry | ineligible after policy coordinate | preserved | preserved subject to later policy | preserved but not current-eligible |
| Archival | ineligible from active recall | preserved and inspectable by authorized lifecycle use | preserved or externally archived by policy | preserved |
| Redaction | ineligible | lifecycle history preserved | exact source bodies removed | non-body history/derivatives retained with redacted lifecycle |
| Soft forget | ineligible for the requesting scope | preserved | preserved | preserved |
| Hard erasure | ineligible and absent | content-free request/confirmation proof only | every supported live copy removed | every enumerated supported derivative removed |

None of supersession, expiry, archival, redaction, or soft forget rewrites an AM1-AM3 canonical
record. AM3 applies the current AM4 lifecycle overlay before ranking and context assembly. Graph
staleness is still evaluated against the canonical AM2 snapshot, then lifecycle narrows current
eligibility. Hard erasure removes canonical and derived live-store records, so a graph rebuild has
no source from which to recreate the erased item.

## Frozen contracts

`ace.core.agent_memory_lifecycle` freezes provider-neutral `v1alpha1` contracts for:

- category/scope/source/policy retention and exact lifecycle requests;
- typed dependency entries and complete snapshots;
- dry-run impact, lifecycle mutation, and erasure receipts;
- product/session/principal export request, canonical entries/artifact, and content-free receipt;
- import request, disposition, and receipt; and
- body availability and explicit omissions.

Every request binds authenticated scope, exact authority receipt, policy/version, and the AM0
ledger-through/prior coordinate. Hard erasure additionally binds the exact dependency snapshot and
digest, every removed reference, one removal-evidence digest per reference, and a post-removal probe
digest. Receipt grammar has no body, statement, summary, vector, prompt, or private-payload field.

## Dependency completeness

The built-in dependency walk begins only after authorization and scans the exact product fence.
It follows stable identities transitively across all current AM1-AM3 record spaces and recognizes:

- primary episodic metadata and private source bodies;
- AM2 assertions, decisions, graph projections, and edge references;
- AM3 rank candidates/receipts, Context Manifests, planner results, injection/reflection,
  decision-material and I3 lineage;
- optional embedding/vector records when present;
- summaries and caches when present; and
- external content bodies through an exact owner reference.

Completeness uncertainty, a missing root, a stale dependency, or an unavailable required external
owner refuses mutation. Dry-run returns identifiers, kinds, counts, digests, omissions, and exact
external actions only; it returns no erased body.

## Export and import

Export is canonical JSON over exact immutable record identities and includes:

- product/session/principal selector and authenticated scope;
- ledger-through coordinate;
- lifecycle state and provenance references;
- body availability and exact omissions;
- record/payload contract identities, original as-of/availability/order coordinates;
- per-entry material digest, policy/version, and artifact digest; and
- a separate content-free durable export receipt.

Import exact-revalidates the artifact digest, authenticated scope, policy/version, body
availability, record identity/material digest, and current governed head before one atomic
cross-record-space restore. Exact replay returns the prior result. Divergent identity/material,
missing bodies, foreign scope, future/stale coordinate, or incompatible policy refuses all
mutation.

## Fail-closed and restart rules

- Authorization occurs before product scan, record lookup, external-body lookup, mutation, or
  receipt write. Missing and inaccessible resources use the same non-disclosing denial.
- Every mutation requires a present-tense governed-state head precondition.
- A stale AM0 prior coordinate or dependency snapshot refuses mutation.
- Live-store erasure deletes exact material and appends content-free request/confirmation/snapshot
  proof in one transaction. Injected failure leaves every dependency intact.
- Exact replay after restart reopens the content-free receipt without needing erased material.
- Fresh-process Surreal restart plus AM2 graph rebuild must not recreate the erased identity.

## Backup, restore, and compliance limitation

AM4 proves deletion only for the configured supported live immutable-record store and exact
external-body owners participating in the transaction protocol. It does **not** claim that offline
filesystem snapshots, database backups, replicas outside the configured owner, provider-retained
copies, logs, or operator-created exports are synchronously destroyed.

Operators must declare a backup retention and recovery window. During that window an erased body
may remain encrypted and inaccessible in an offline backup. Any restore must reapply the retained
content-free erasure request/receipt ledger before the restored service becomes readable, then run
the dependency and non-reappearance probes again. AM9 owns automated backup inventory,
multi-instance recovery, tenant deletion/restore, disaster recovery, and portability proof. Until
that work lands, ACE must not claim instantaneous physical deletion from every backup medium or a
complete regulatory compliance posture.

## Verification matrix

- frozen provider-free positive/fail-closed fixture;
- all six lifecycle meanings and current recall behavior;
- dependency enumeration across primary, body, assertion, graph, AM3 manifest/rank/use,
  embedding, summary, and cache records;
- content-free tamper-evident erasure proof;
- atomic failure, stale refusal, denial-before-scan, and cross-scope non-disclosure;
- product/session/principal export validation and export/import round trip;
- exact replay, collision, missing-body, incompatible-policy, and scope refusal;
- real Surreal restart/reopen, fresh process, graph rebuild, and non-reappearance;
- focused AM0-AM4 plus relevant Core/Intelligence/privacy/time/graph/package/schema tests;
- supported full non-E2E/non-extension gate and exactly eleven thin MCP tools; and
- two checkout-free installed-wheel reproductions.

## AM5, AM8, and AM9 handoff

- AM5 may consume immutable lifecycle events as constraints, but cannot reverse erasure, reactivate
  expired/forgotten material, widen scope, or treat deletion/use history as rank or trust evidence.
- AM8 may preview/confirm these exact requests and render their receipts, but cannot invent
  completeness, authority, successful deletion, or body availability.
- AM9 must add declared backup inventories/recovery windows, restore-time re-erasure automation,
  multi-instance coordination, tenant administration, and a second-backend reproduction without
  changing these identities or semantics.
