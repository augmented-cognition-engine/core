# ACE 0.6.0 issue #49 F1/F5 hardening work packet (v1)

**Status:** bounded implementation candidate. This packet does not merge a pull request, check or
close an issue item, change a package version, tag or publish an artifact, pass SI4, or declare ACE
0.6.0 complete.

**Frozen base:** Measured Intelligence merge-candidate audit
`7234506655223d49285f2a8c921bff31742bc7b0`.

**Executable source:** `1ddac875d2f91b60f0dfdcf49d78264c5805fe9e`.

## Issue #49 disposition boundary

This packet implements the merge-candidate audit's bounded F1 and F5 options for issue
[#49](https://github.com/augmented-cognition-engine/core/issues/49). Both items remain open until
reviewed and merged evidence supports changing the public checklist.

F3 is not implemented, resolved, waived, or re-dated here. The proposed `2026-11-05` deadline and
trusted-package, kill-switch, compatibility-matrix, and disable-on-partial containment still
require an explicit authenticated owner record on issue #49. Extension registration code is out of
scope.

## Objective

Close only the two selected implementation gaps while preserving the established product boundary:

1. make a governed-cognition review's proposal-state and head-generation checks part of the same
   atomic transaction as revision, head, activation, receipt, and proposal-state writes;
2. classify an ambiguous database result as successful only when the exact review receipt,
   proposal state, revision, and head reload consistently;
3. prove a forced two-connection real-SurrealDB race has one winner and no losing partial state;
4. pin the deprecated self-optimizer proposal lookup and projection to the
   `self_optimizer_proposal` table before any database access; and
5. retain F3 as a visible open decision rather than silently expanding the packet.

## Durable F1 contract

The existing preflight reads remain useful diagnostics, but no longer own concurrency correctness.
The transaction now rechecks the exact product-scoped proposal state and the current head
generation before any revision, head, activation, review, or proposal-state effect. The v169
unique activation-generation index remains a second atomic backstop.

If the client sees a transaction or connection failure, Core does not infer success. It reloads the
stable review identity and accepts the possible winner only when:

- the durable review is an exact retry apart from its nondeterministic review timestamp;
- the proposal has the disposition-implied durable state;
- an approval's exact immutable revision reloads; and
- the exact expected head reloads.

Missing, divergent, or partially reconciled material fails closed. A retry after restart returns
the historical durable review; it does not recompute authority or silently create a second effect.

## F5 record-coordinate contract

The deprecated facade accepts only a bounded identity of the form
`self_optimizer_proposal:<record-key>`. The record key is passed separately to a literal
`type::record('self_optimizer_proposal', $record_key)` coordinate for both lookup and projection.
A foreign table name, empty key, nested coordinate, or malformed key returns the same not-found
surface before a database query or mutation. Exact product scope remains required after lookup.

## Acceptance

- deterministic tests cover exact ambiguous-write reconciliation and missing, divergent,
  proposal-state, revision, and head mismatches;
- the generated transaction places proposal and generation guards before the first durable effect;
- a disposable real SurrealDB forces two independent clients to the transaction boundary, yields
  one winner, leaves the loser pending, and stores exactly one revision and activation;
- a simulated connection loss after durable commit returns only after exact reload and survives a
  fresh service replay;
- valid legacy reads and projections use the pinned table; foreign and malformed coordinates fail
  before database access;
- focused cognition, legacy facade, restart, Ruff, whitespace, kernel-boundary, and required
  repository verification pass; and
- evidence records the extension-contaminated first attempt separately from the authoritative
  extension-disabled lane.

## Ownership and non-claims

Core continues to own durable state, provenance, authority, review receipts, revisions, heads, and
legacy API scope. Intelligence contracts and domain packs are unchanged. No domain noun, source
policy, measured-impact criterion, or proposal-application path moves into this packet.

This packet does not prove distributed consensus, hostile-extension isolation, globally
exactly-once effects, general benefit, causality, SI4 completion, or a supported 0.6 release. It
does not check F1 or F5 before merge evidence, and it does not call F3 fixed.

## Owned files, rollback, and deletion criteria

Owned implementation is limited to governed-cognition durable review persistence, the deprecated
self-optimizer facade, focused deterministic and real-database tests, this packet, its evidence,
and restrained current-state roadmap/maturity references. There is no schema migration.

Rollback reverts the implementation commit. Existing proposals, receipts, immutable revisions,
heads, and activation history remain readable; no rollback operation may delete them. If the
in-transaction guard is unavailable, 0.6 closeout must keep F1 open rather than relying on a
preflight read alone. If the table pin is unavailable, operators should disable the deprecated
facade and keep F5 open.

Supersede this packet only with merged-source evidence that reruns the same race, restart, legacy
negative controls, and required repository gates. F3 requires an explicit owner disposition and,
if re-dated, its own bounded atomic-registration packet by the recorded deadline.

## Next bounded packet

After review and merge, rerun Core/World/Market from the merged source, bind final artifacts and
security/compatibility checks, update issue #49 F1/F5 only from merged evidence, and reconsider the
0.6 release gate. That packet still may not merge, tag, publish, or close issue #38 without a
separate release-owner action.
