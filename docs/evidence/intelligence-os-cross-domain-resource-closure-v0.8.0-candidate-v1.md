# Intelligence OS cross-domain resource closure — 0.8.0 candidate

**Status:** Core correction and public World candidate passed; independent Market proof and final
release acceptance remain open.

**Core base:** `c97b86651c807cb465b1349af1e0835efbb4bdcf`

## Boundary correction

The 0.8 public resource plane originally assumed that every domain stored Decisions, Outcomes, and
Feedback proposals in the Core demonstration space named `prepared`. That was narrower than the
public immutable-record contract: World correctly stores its decision loop in
`world_intelligence` and measured proposals in `measured_impact`. The reader now scans only the
authenticated product's immutable records and admits only exact known contracts and envelope
identities. Record-space names remain domain/runtime storage choices, not public resource types.

LIVE source acquisition also admits normalized Observations and Entity snapshots after their
intrinsic ingest/project timestamps. Their public resource identity now uses the immutable record's
admission time while retaining the intrinsic timestamp in the exact payload. A later admission is
accepted; time inversion is not.

Measured-impact governance proposals project as Feedback resources only while they remain
non-effective, non-selectable proposals requiring human review. This change creates no activation,
mutation, or self-learning authority.

## Candidate verification

- focused resource-plane and measured-impact gate: **59 passed, 2 skipped**;
- new projection regression gate: **13 passed**;
- full non-e2e Core gate: **7,904 passed, 48 skipped, 249 deselected**, with one unrelated transient
  SurrealDB teardown write conflict; the isolated retry passed **1/1**;
- naked-kernel gate: **7,890 passed, 50 skipped, 261 deselected**;
- exact kernel boundary: **4 passed**;
- Ruff lint and format: passed.

The first sandboxed full run also truthfully failed six tests because loopback sockets were denied.
The unrestricted CI-equivalent rerun removed those environment failures. No product assertion was
weakened to make the gate pass.

## Public World candidate

World Intelligence composes its existing recorded Federal Register monitoring, governed Reality
Brief, reviewed create-only Action, matched Outcomes, and proposal-only measured feedback. Its new
0.8 acceptance assembles one real LIVE Case over the exact Shift, Signal, and two Observation
records, then reads the complete journey through the unchanged public resource plane:

`Observation → Signal → Shift → Case → Brief → Decision → Action → Outcome → Feedback`

The same query and resource identities reopen after reconstructing the resource-plane service.
World's source-only evaluation controls remain explicitly degraded as unsupported public subjects;
they are not mislabeled as Briefs or Cases. The focused candidate gate passes **1/1**.

## Remaining release gate

This packet does not claim 0.8.0 release acceptance. Market Intelligence must reproduce the same
domain-neutral public plane with its independent competitor/product/narrative ontology. After both
domain candidates merge, final artifacts must be built and installed outside all source trees,
restart/reopen must pass from those exact artifacts, Atrium and the machine interface must consume
the same public contracts, and the release/tag/publication receipt must bind the final identities.
