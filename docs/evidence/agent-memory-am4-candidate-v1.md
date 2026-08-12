# ACE 0.7F Agent Memory AM4 candidate evidence v1

## Candidate coordinates

- Exact cumulative integration base: `f761a682164d10e2ff81ba38cd2d0c987b4f8efd`
- Base branch: `codex/v0.7-cumulative-integration-acceptance`
- Cumulative review-only PR: #122
- Candidate branch: `codex/v0.7-agent-memory-am4`
- Exact implementation artifact: `769f5a89e6ab3fe39968cd0e493da67dc2dfc94b`
- Draft PR: publication blocked only by invalid local GitHub CLI credentials
- Status: isolated stacked draft candidate; not accepted, merged, released, or supported

## Bounded claim

AM4 adds distinct supersession, expiry, archival, redaction, soft-forget, and hard-erasure
semantics; retention dry runs; complete supported live-store dependency enumeration; content-free
tamper-evident erasure proof; canonical scoped export/import; and restart/rebuild non-reappearance.

It preserves Core ownership of scope, authority, ledger coordinates, governed heads, immutable
records, and receipts. AM2 remains the assertion/graph owner and AM3 remains the authorized recall,
Context Manifest, and use-lineage owner. No public task field, MCP tool, package identity, schema,
provider, vector store, database, external repository, or AM5+ behavior is added.

## Verification ledger

| Gate | Result |
| --- | --- |
| Exact base/branch/ancestry and clean entry | Passed before implementation |
| Frozen AM4 provider-free fixture and contracts | Passed in the 18-test AM4 unit/conformance matrix |
| All six lifecycle meanings and current AM3 recall filtering | Passed; expiry/forget narrows current eligibility without rewriting the canonical AM2 snapshot |
| Dependency-complete primary/AM2/AM3/embedding/summary/cache closure | Passed, including exact external-body enumeration and rollback |
| Atomic hard erasure and content-free proof | Passed in memory and real Surreal injected-failure/restart tests |
| Export/import round trip, replay/collision/missing-body/policy/erased-artifact refusal | Passed in memory and real Surreal; no second receipt table was added |
| Real Surreal restart, fresh process, graph rebuild, non-reappearance | Passed; the same journey also covers principal privacy and a second clean import database |
| Focused AM0-AM4 | 156 passed, 2 skipped, plus both real AM3/AM4 Surreal restart tests passed |
| Relevant Core/Intelligence/time/graph/schema/package | 757 passed, 21 skipped; focused package/schema/port matrix 100 passed |
| Full supported non-E2E/non-extension Core gate | Effective 7,630 passed, 245 skipped, 261 deselected; the sandbox run passed 7,624 with six localhost-only denials, and all six passed unchanged with localhost access |
| Ruff/format/lock/diff/secret/authority/privacy/domain/public-surface scans | Whole repository Ruff and 2,145-file format check passed; lock resolved 243 packages offline; diff, secret, provider/domain and boundary scans passed; AC6/AC7 provider-free verifiers passed with AC7 reporting eleven tools |
| Two checkout-free installed-wheel reproductions with exactly eleven tools | Passed from `/tmp/ace-am4-target-a-final2.Ay4n0G` and `/tmp/ace-am4-target-b-final2.OoOBr9`; wheel SHA-256 `c9eda5a81ec8c10972036f3bfd96e70d80e5a49392b3568b4ed403a523c87334` |

## Backup and recovery limitation

Hard erasure covers only configured supported live stores and exact external-body owners. Offline
backups, unregistered replicas, provider-retained copies, logs, and prior operator exports are not
proved synchronously destroyed. Operators must declare a backup retention/recovery window and must
reapply content-free erasure receipts plus non-reappearance probes before any restored service
becomes readable. Automated backup inventory, disaster recovery, tenant restore/delete, and
second-backend proof remain AM9.

## Handoff boundary

- AM5 may consume lifecycle constraints but cannot reverse erasure, widen authority, or learn rank,
  trust, retention, or policy from deletion/use telemetry.
- AM8 may present exact preview/confirmation/receipt APIs but cannot manufacture authority,
  completeness, body availability, or deletion success.
- AM9 owns backup/recovery automation, multi-instance administration, tenant journeys, and
  second-backend conformance under these frozen identities.
