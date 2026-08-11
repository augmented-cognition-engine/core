# ACE 0.6.0 Measured Intelligence merge-candidate audit work packet (v1)

**Status:** bounded release-owner decision candidate. This packet does not merge a pull request,
change package versions, tag or publish an artifact, close issue
[#38](https://github.com/augmented-cognition-engine/core/issues/38), resolve issue
[#49](https://github.com/augmented-cognition-engine/core/issues/49), pass SI4, or declare ACE 0.6.0
complete.

**Core candidate:** `37e6c8a6da0fc95e378c1be50d8704c00dd96415` over live `main`
`be5e76c79715bb34bcbdcae9a0471a5c317fafe7`.

**World direct-main candidate:** PR
[#17](https://github.com/augmented-cognition-engine/domain-world-intelligence/pull/17), executable
source `87625d55c717a9c649d4f44a06d1767b52fed255`, evidence head
`2d7a0ace72bed4d175b0884c8a9b81b6ec063d56`.

## Objective

Turn the implementation and artifact-convergence results into one inspectable release-owner audit:

```text
Core #88 -> #89 -> #90 -> #91
  + independent Market candidate
  + World measured stack reconciled directly on live World main (#17)
  + exact artifact and verification receipts
  + explicit issue #49 owner decisions
  -> reviewed merge order or bounded corrective packet
```

## Acceptance

This packet must:

1. refresh live PR, review-thread, issue, branch, and CI state rather than relying on stale local
   dispatch;
2. prove the Core stack is a strict live-main descendant and every inspected Core PR is open,
   draft, and mergeable;
3. identify the World stack's live-main divergence honestly and bind the separate direct-main
   integration candidate that resolves it without rewriting the old review branches;
4. bind the direct-main World source, repeated wheel hashes, canonical JSON hash, and combined test
   results;
5. give the release owner concrete implementation or re-date choices for issue #49 F1, F3, and F5;
6. recommend a choice without recording it as accepted; and
7. keep roadmap and capability maturity at candidate state.

## Issue #49 decision matrix

The following are proposals for the authenticated release owner. They are not decisions until the
owner records one on issue #49.

| Item | Recommended 0.6 disposition | Bounded implementation option | Explicit re-date option |
|---|---|---|---|
| F1 — cognition generation race and receipt reconciliation | **Implement before 0.6 closeout.** The next-minor deadline has arrived and governed revision activation is adjacent to the 0.6 promise. | Add an in-transaction generation guard or a two-connection real-SurrealDB concurrency proof, then reconcile the exact winning review/head/proposal state from durable receipts after conflict or restart. Require one winner, zero partial revision, stable replay, and divergent conflict. | Re-date no later than `2026-11-05` only with an owner rationale that retains the v169 unique activation-generation index, documents rollback, and states why 0.6 proposal-only behavior does not widen the accepted exposure. |
| F3 — trusted registration ceilings and partial rollback/reporting | **Re-date to `2026-11-05` unless 0.6 expands the extension surface.** Correct atomic staging spans Core registries plus delegated instrument/sentinel registration and should not be improvised inside a measured-impact release. | Introduce extension-scoped staging, validate ceilings for every mutable registration surface, publish atomically, and emit a bounded failure report; prove a late registration failure leaves every registry byte/identity-equivalent to its pre-registration snapshot. | Record `2026-11-05` plus containment: trusted installed packages only, no wider supported extension claim, retained `ACE_DISABLE_EXTENSIONS=1` kill switch, compatibility matrix, and operator disablement on unexpected partial state. |
| F5 — legacy optimizer record-type confusion | **Implement before 0.6 closeout.** The fix is narrow and independently testable. | Parse the route identity into a bounded key and load/update only `type::record('self_optimizer_proposal', $record_key)` under the exact product. Add negative controls for a same-product foreign-table record and malformed identity; no legacy projection may touch either. | Re-date only with explicit owner acceptance of the deprecated-facade containment and a dated removal or fix target; do not call the table-confusion surface resolved. |

The recommended split is therefore **implement F1 and F5; explicitly re-date F3 to 2026-11-05
with containment**. This packet does not perform any of those mutations.

## Ownership and exclusions

Core continues to own durable state, provenance, authority, Decision, Action, Outcome, and release
gates. Intelligence owns domain-neutral evaluation and proposal contracts. World and Market own
their nouns, sources, policy, controls, and outcome meaning.

This audit does not add proposal application, change effective state, widen extensions, implement
security debt, change schemas, alter the eleven-tool MCP contract, or revise external deadlines.
It does not establish causality, general benefit, live monitoring, or supported 0.6 behavior.

## Owned files and rollback

- this work packet;
- its point-in-time evidence record;
- one evidence-index entry; and
- restrained roadmap and maturity references.

Rollback removes those documentation-only additions. All implementation and external artifact
branches remain unchanged.

## Next bounded packets

After an authenticated issue #49 decision, the implementation order should be F5, F1, then either
the owner-approved F3 hardening packet or the owner-approved dated containment record. A final
merge-source audit must then rerun Core/World/Market compatibility, security, exact artifact
binding, public-index installation, and release checks. It still may not merge, tag, or publish
without a separate release-owner action.
