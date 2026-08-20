# PI13 — Personal journey runtime integration (draft for owner review)

- Date: 2026-08-20
- Status: **draft; not frozen** — owner review required before any PI13 code lands
- Parent contract: [issue #195 — ACE 1.2 Personal Intelligence]; extends the frozen
  [1.2 work packet](personal-intelligence-v1.2-work-packet-v1.md) after the public acceptance
  runs against v1.2.0 and v1.2.1 proved the journey's middle was never integrated
- Evidence basis: the two clean-context acceptance runs (to be bound in
  `docs/evidence/personal-intelligence-v1.2-public-acceptance-v1.md`), findings F5–F10

## 1. Why this packet exists

PI2–PI7 merged real, individually conformance-tested components: adapters that parse and digest,
admission contracts, mapping grammars, a compiled pack, detection engines, ownership depth. The
acceptance runs proved nothing composes them: no `ace.source.snapshot/v1alpha1` provider ships,
the adapters are imported by nothing at runtime, no API accepts a folder, the
`ace.intelligence_builders` executor group is empty, the packaged Atrium has no Personal journey,
and the pack maps Markdown only. Every slice gate lived at its own boundary; no gate owned the
composition. PI13 is the missing integration slice, gated at journey depth.

## 2. The one rule that changes

**Gates live at journey depth.** PI13's acceptance for every workstream is a J-step flipping in
the journey-depth CI lane (WS0) and surviving a fresh clean-context acceptance run — never only a
unit or conformance suite at the workstream's own boundary. A workstream whose tests pass but
whose J-step does not flip is not done.

## 3. Workstreams

| WS | Deliverable | Unblocks | Acceptance |
|---|---|---|---|
| WS0 — journey-depth CI gate | A CI lane that builds the public artifacts, installs them into a bare venv, stands up an ephemeral SurrealDB, and walks J1→J5 with a fixture corpus and a deterministic stub provider; merged FAILING (allowed-to-fail) first, flipped lane-by-lane as workstreams land | everything | The lane exists, runs on every PR, and its per-step results are visible; no workstream merges without moving it |
| WS1 — local snapshot capability provider | A host-side implementation of `ace.source.snapshot/v1alpha1` over the PI2 adapters, registered so pack activation's `local_source_snapshot` requirement binds a real implementation with exact artifact identity | J3 start | WS0 reaches pack activation with the capability bound |
| WS2 — connect API + acquisition wiring | An API surface that names a folder/files, shows exact scope and read-only mode BEFORE any read, records the authorized selection, and routes reads through the PI3 recorded-source admission boundary under the labeled local acquisition mode | J3 | WS0 J3 flips: consent-before-read proven by a negative test (no read occurs before authorization) |
| WS3 — build executor | An `ace.intelligence_builders` entry-point executor that takes the approved plan through the existing `IntelligenceBuilderSessionService` (connect/map/watch) into `CoreIntelligenceBuildFirstBriefService`; loaded through the production registry seam only | J4, J5 | WS0 J4+J5 flip: inventory states render from the projection vocabulary and a cited first Brief exists |
| WS4 — full source-kind mapping | Pack source-mapping for PDF, CSV, and JSON via the PI4 locator grammar and document-mapping contracts (Markdown ships today); the profile's advertised kinds and the pack's mapped kinds must be identical by test | J3 breadth, J5 citations | WS0 fixture corpus includes all four kinds and every citation resolves to its span |
| WS5 — change detection and revision wiring | The PI7 watcher through re-ingest to a document-shaped Shift and an append-only Brief revision with semantic diff; then claim-bound correction re-derivation (PI8 contracts) on real Briefs | J6, J8 | WS0 extended to J6; J8's re-derivation proposal proven on a live corpus edit |
| WS6 — Atrium Personal journey | J2 choose, J3 connect, J4 inventory, J5 Brief surfaces over the WS2/WS3 APIs, mounting the PI6 first-run candidate; browser tests against the real APIs | J2–J5 in the UI | The clean-context runner completes J2–J5 through Atrium without touching the API by hand |

Sequencing: WS0 first and failing. WS1→WS2→WS3 in order (each consumes the previous). WS4
parallel to WS3. WS5 after WS3. WS6 parallel once WS2/WS3 APIs stabilize. Also carried: the F1
(#259) and F2 (#260) defects land inside WS2/WS3 territory and are fixed there.

## 4. Method

Each workstream is a bounded, frozen mini-brief suitable for the multi-arm generate → calibrated
adversarial review → composed delivery method the PI12 program validated 3-for-3. The
clean-context acceptance runner is the iteration loop: it reruns after every workstream lands,
and each run's log is the next workstream's sharpest spec. Runs are cheap; end-loading acceptance
is what produced this packet.

## 5. Release and honesty rules

- 1.1 and 1.2.x published history is immutable. PI13 work ships as 1.2.x completion releases
  only when a J-step actually flips in WS0 and a fresh runner pass confirms it; version bumps
  without a J-flip do not ship.
- ACE 1.2 is declared **passed** only when the clean-context runner reports J1–J10 end to end,
  the maintainer cross-check concurs, and the four-record reconciliation closes. Until then the
  reconciliation records "not passed; continuation in progress" — the packet's own honesty rules
  applied to itself.
- Nothing in PI13 expands the eleven-tool MCP surface, adds Personal nouns to `ace/core` or
  `ace/intelligence`, or grants any approve/merge/promote/deploy authority.
- The external-user acceptance run remains a carried follow-up beyond the amended gate.

## 6. Explicitly out of scope

Everything the 1.2 packet excluded stays excluded (remote sources, universal connectors,
collaboration, Topic/Pack Kit, restore-from-export, hostile-adapter isolation). PI13 adds no new
product scope; it delivers the scope 1.2 already froze.
