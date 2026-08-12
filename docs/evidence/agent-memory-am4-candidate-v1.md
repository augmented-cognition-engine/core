# ACE 0.7F Agent Memory AM4 candidate evidence v1

## Candidate coordinates

- Original cumulative integration base: `f761a682164d10e2ff81ba38cd2d0c987b4f8efd`
- Original verified AM4 source head: `64152cd2a92381bba32b4f7436e416682e4b79f0`
- Original AM4 implementation artifact: `769f5a89e6ab3fe39968cd0e493da67dc2dfc94b`
- Released-main convergence parent: `9e0a9d248c073b6a7883451cb1d219eb7c15999b`
- Release-source tree: `1c545b6ce5499dcca652fbeff7207551a515bc07`
- Exact two-parent convergence commit: `b1c8dddf6bc20c9241c0b2194881eacb3e016e67`
- Verified post-convergence implementation head: `7cb74ad07444752a87f9ff447f0373889ad78ba4`
- Candidate branch: `codex/v0.7-agent-memory-am4`
- Draft PR: pending publication against `main`
- Status: reconciled 0.7.0 draft candidate; not accepted, merged, tagged, or separately released

The convergence commit has first parent `64152cd2a92381bba32b4f7436e416682e4b79f0`
and second parent `9e0a9d248c073b6a7883451cb1d219eb7c15999b`. The latter is the exact
released-main coordinate frozen by the control-tower dispatch. The remote `main` ref was observed
later at descendant `11b44e84d92e0674fa433103779f4050eeca2725`; that later documentation-only
advance was not silently substituted for the frozen convergence parent.

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
| Exact convergence and conflict audit | Passed; the normal merge had no conflicts, retained released 0.7.0 identity, and changed no AM4 runtime file relative to the verified source head |
| Focused AM0-AM4 after convergence | 160 passed, including real AM3/AM4 Surreal restart and fresh-process journeys |
| Package/version/schema/port/public surface | 125 passed; the separately isolated reference adapter passed 9 tests against its `ace-core>=0.7.0,<0.8` line |
| Full supported non-E2E/non-extension Core gate | 7,825 passed, 50 skipped, 261 deselected with localhost available |
| Ruff/format/lock/diff/secret/authority/privacy/domain/public-surface scans | Whole repository Ruff and 2,145-file format check passed; lock resolved 243 packages; diff and secret scans passed; AC6/AC7 provider-free verifiers passed; installed probes reported exactly eleven tools |
| Two checkout-free installed 0.7.0 wheel reproductions | Passed from `/tmp/ace-am4-target-a.xrgkij` and `/tmp/ace-am4-target-b.1ETp5E`; both loaded their isolated installed `ace` package and reported the same exact eleven tools |
| Fresh reconciled wheel | `ace_core-0.7.0-py3-none-any.whl`, SHA-256 `a934653ca9871276e8b2c43c1ed8f4fe8d0f65be10b0f3ee151e03904bf093b8` |

## Convergence note

The released-main merge was additive and conflict-free. It brought the 0.7.0 package, release
workflow, Docker, changelog, roadmap, and reference-adapter compatibility coordinates. AM4 Core and
application runtime files were byte-identical to the verified source head after the merge. One
fresh-process test helper was then made self-contained because the released package environment no
longer made the repository `tests` package importable from the child process; the helper now defines
its inert current-authority fixture locally and the real restart/rebuild/non-reappearance journey
passes in both the focused and full gates.

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
