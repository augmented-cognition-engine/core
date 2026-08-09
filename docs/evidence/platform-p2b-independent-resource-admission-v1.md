# Platform P2B — independent PREPARED resource admission

**Status:** candidate/local platform substrate slice verified  
**Date:** 2026-08-07

> **Reproducibility status: candidate/local implementation evidence, not public artifact
> verification.** This record documents work against a local ACE Core 0.4.1 candidate; Core 0.4.1
> itself has no git tag, GitHub Release, or PyPI publication yet, so the versions and wheel digests
> below are local build artifacts, not public releases. The World Intelligence conformance journey
> this record relies on lives in `augmented-cognition-engine/domain-world-intelligence`, whose
> source is public but which carries no version tag, GitHub Release, or PyPI publication. Until both
> repositories are tagged, released, and published, an outside reader cannot independently re-derive
> the identities cited below. This record therefore establishes local implementation evidence only.
> It does not establish the public two-domain neutrality proof (GI2, open per the roadmap), and no
> roadmap outcome may be promoted to `passed` on its basis.

The World P2B replay falsified a narrow mismatch between ACE's public resource DAG and its durable
PREPARED ledger. `ShiftV1Alpha1` explicitly permits a material Shift without a Signal predecessor,
but `PreparedResourceAdmissionV1Alpha1` required every durable transaction to contain both one
Shift and one Signal plus an attention disposition. That forced consumers either to invent an
attention event or leave a valid Shift outside the durable ledger.

## Platform result

- `PreparedResourceSetAdmissionV1Alpha1` admits any valid activation-bound PREPARED resource DAG
  without implying routing, attention, delivery, or action.
- `PreparedIntelligenceLedgerService.admit_resource_set()` validates exact product, activation,
  Pack IR, resource identity, temporal availability, topological order, and lineage before one
  append-only Core transaction.
- `replay_resource_set()` revalidates the exact transaction and rejects attention-bearing
  transaction shapes, preventing the routed and non-routed admission contracts from being
  confused.
- Existing `PreparedResourceAdmissionV1Alpha1`, attention receipts, routed Brief synthesis, and all
  prior identities remain unchanged.

## Consumer result

World's corroborated-claim Shift is now represented as a five-resource PREPARED set—two exact
Observations, two Entity Snapshots, and one Shift—with no Signal. The pinned admission is
`resource_set_admission:8ab29e2440d68523e35aae01abbfb7c4` with digest
`sha256:3d151217b47a3e6182c7a218f047f23d2490beff41e71f2deecdab93d9c6ed7b`.

This closes the independent-admission mismatch only. It does not create a Case, aggregate several
derivations, synthesize a multi-development Brief, deliver anything, or authorize external action.

## Verification

- ACE independent-admission tests: `2 passed`.
- Complete ACE Intelligence suite: `279 passed`.
- Unchanged Market conformance suite: `88 passed, 1 skipped`.
- World conformance suite: `26 passed, 3 xfailed`.
- World PREPARED interpreter replay: 8 Observations, 5 Shifts, 4 Signals, 4 exact routes, numeric
  delta `-12.2977%`, zero LIVE resources.
- Isolated wheel probe: `ace-core==0.3.0` and `ace-ext-world-intelligence==0.3.0` installed outside
  both checkouts; the public admission contract imported, the default World pack recompiled to its
  pinned identity, and packaged replay identities matched. Wheel digests were
  `sha256:e5d627313575540b2e3b06e06bf4f01a8f56f2e4b19e1e0e3565f49cba52b966` (ACE) and
  `sha256:ba747d6ed3643375e52fa60e1c6e102b3b202c2b1b1444b8743f9fc0bda3f245` (World).

The next generic falsification target is `WI-CR-005`: an immutable Case closure that can bind
several exact derivations for governed Brief synthesis without weakening provenance or replay.
