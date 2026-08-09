# Context Manifest V1 and surgical code-context checkpoint

Date: 2026-08-05

Outcome: **local, candidate implementation and exact-artifact checkpoint passed; public release gate remains open**

This record predates and is superseded by the current `ace-core` v0.4.1 candidate on `main`. The
evidence below concerns a local 0.3.x-era checkpoint and is preserved as historical record; it does
not describe the current package version. Nothing here should be read as a claim that 0.3.x, 0.4.0,
or 0.4.1 has cleared the public-release matrix this file describes — only 0.4.0 has published a git
tag, GitHub Release, and PyPI package to date. Absence of that public-release evidence does not by
itself mark the local implementation work recorded here as failed; it marks publication as pending.

## Frozen contract and boundary

`ace.context.manifest/v1` is an additive, deterministic projection on the existing task/status
receipt. It records cognition selection and observed use, attributable deliberation, retained
intelligence use, code scope, receiving agent/stage, stable revisions, budgets, omissions,
freshness, and degraded state. It grants no execution authority and does not create another memory
store.

The projection and public task boundary fail closed on foreign-product receipt families and unknown
code-context receipt versions. Public output excludes prompts, messages, transcripts, raw source
contents, raw code context, and chain-of-thought. Direct orchestration persistence also strips
ephemeral assembled prompt/source fields before writing a task snapshot while retaining receipt
metadata.

The public boundary remains exactly eleven thin MCP tools. This packet adds no provider, public
tool, importer, profile UI, document knowledge map, affected-test engine, or broader workspace
surface.

## Surgical code context

The internal composer combines product-scoped semantic matches with repository-relative exact
anchors, symbols, direct dependency/dependent relationships, relevant decision and observation
identities, bounded impact, repository/index revision and dirty-tree identity, freshness, and known
coverage. Source text exists only in the ephemeral internal context; the durable receipt contains
metadata and content hashes only.

Missing, ambiguous, foreign, stale, partial-scan, deleted/renamed-source, and unsafe-anchor cases
fail closed. Search, item, token, time, source-size, relationship, symbol, decision, and observation
bounds are explicit. When a structural metadata cap is reached, the receipt reports partial
coverage and the exact truncation family rather than claiming completeness.

## Acceptance matrix

Deterministic fixtures cover:

- cross-product and identical-path product isolation;
- foreign-graph rejection;
- missing and stale indexes;
- dirty working trees and revision/fingerprint drift;
- partial scans and bounded metadata truncation;
- deleted and renamed files;
- stable receipt identity across two fresh interpreter processes;
- persisted task/status continuity across fresh SurrealDB and API processes using the same store;
- source-free installed-wheel discovery and execution of the composer and frozen fixture; and
- an isolated PEP 517 build plus lock-constrained dependency resolution into an empty venv.

The additive `ace.artifact-install.acceptance/v1` verifier strengthens the final item: it snapshots
the exact dirty candidate, rejects symlinked inputs, binds path/type/mode/size/content and Git
provenance, exports hash-pinned runtime and build inputs with local source overrides disabled,
builds reproducible wheel/source archives, and installs both into separate no-system-site
environments. Fresh installed processes exercise task/status privacy, stable manifest identity,
independent-extension isolation, disabled-extension behavior, and the unchanged eleven-tool surface.

The read-only audit found no remaining production blocker for privacy, product isolation, stable
identity, backward compatibility, receipt completeness, bounded coverage, or eleven-tool
preservation.

## Verification record

- Central manifest, composer, acceptance, task-public, watcher-lifecycle, and crash-reproducer suite:
  `84 passed`, `1 deselected`.
- Adjacent cognition, context assembly, orchestration, semantic search, code scope/index identity,
  MCP code-intelligence, and scanner suite: `227 passed`, `4 skipped`.
- Complete non-E2E regression: `6827 passed`, `233 skipped`, `261 deselected`; all five tests denied
  loopback bind/connect access by the sandbox passed (`5 passed`) when rerun with local-network
  permission.
- The former native status 133 was localized to a wiring unit test starting the real macOS
  watchdog/FSEvents observer. The production SessionRunner watcher now uses a filtered
  `PollingObserverVFS` on Darwin with a 0.5-second floor, preflighted event-loop ownership,
  thread-safe debounce state, idempotent lifecycle, partial-start cleanup, and join-before-release;
  other platforms retain their existing observers. A real polling event, lifecycle/error cases,
  and the exact crash reproducer pass (`17 passed`), as do 25 debug-allocator start/stop cycles.
- Fresh-process identity continuity passed in two distinct interpreter PIDs. The automated
  offline source-free installed-wheel smoke imports both composer and fixture from the fresh venv,
  composes an available receipt, and observes exactly eleven tools.
- The opt-in network acceptance created an isolated PEP 517 build, an empty venv and pip cache,
  resolved `161` lock-constrained packages, passed `pip check`, and executed the probe outside the
  checkout. The installed composer and fixture matched the wheel, the receipt remained
  metadata-only and available, and the MCP inventory remained exactly eleven. The tested
  pre-reconciliation candidate wheel had SHA-256
  `da40054019c24123c6411c9da103142cc6444ac9691f6d0f4770777b6ea4ba27`.
- Live persistence acceptance passed against one SurrealKV store across distinct database PIDs
  `96172` → `96751` and API PIDs `96173` → `96760`. A fresh thin client retrieved the same task ID,
  output, complete four-family manifest, and `manifest_id`; initial readiness took `53.834s`, restart
  readiness `6.798s`, and post-restart status retrieval `0.021s`. Seeded prompt, correction,
  ephemeral-context, transcript, chain-of-thought, and private-source canaries remained absent from
  public status, while ephemeral fields/canaries were absent from the persisted intelligence
  snapshot.
- Ruff lint and diff whitespace checks: passed. Packet files pass Ruff formatting. Repository-wide
  formatting remains degraded by ten pre-existing modified files outside this packet, which were
  preserved unchanged.
- Thin MCP runtime inventory: exactly `11` tools.

## Remaining degraded evidence

- No published artifact has yet passed the complete compatibility, security, installation, and
  release-reconciliation matrix.
- The exact-artifact receipt is local evidence over a combined dirty candidate. Publication
  provenance remains unproven, and public-index installation was not authorized in this packet.
- Synchronous repository/source reads run in worker threads. A caller returns a fail-closed timeout
  receipt, but already-running operating-system work cannot be forcibly cancelled.
- The separate, process-long-lived worker watcher still uses watchdog's native platform observer;
  it was not the reproduced short-lived SessionRunner lifecycle failure and was not changed here.

## Next acceptance work

The manifest, code-context, restart, and failure-matrix evidence is now bound to the extension-first
journey in the
[Productized State local checkpoint](productized-state-journey-v1.md). The live G1 receipt
honestly remains partial for `product_intent_missing`, and the additive receipt supplies explicit
database-process history omitted by frozen v1. Dependency-clean installation and reproducible local
source provenance now pass for the exact candidate. Remaining work is public-artifact verification
(a git tag, a GitHub Release, and a published PyPI package), release and milestone reconciliation,
and publication. Until those checks pass, this checkpoint remains local, candidate evidence and does
not itself close a public release-line gate; it does not mark the underlying implementation as
failed.
