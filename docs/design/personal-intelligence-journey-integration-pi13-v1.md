# PI13 — Personal journey runtime integration (frozen)

- Date: 2026-08-20 (revised same day to reconcile all three public acceptance runs)
- Status: **frozen by owner on 2026-08-20; corrected WS3 addendum frozen the same day** —
  implementation proceeds only in the WS0→WS6 order (§7–§8)
- Parent contract: [issue #195 — ACE 1.2 Personal Intelligence]; extends the frozen
  [1.2 work packet](personal-intelligence-v1.2-work-packet-v1.md) after the public acceptance
  runs against v1.2.0, v1.2.1, and v1.2.2 proved the journey's middle was never integrated
- Evidence basis: the three clean-context acceptance runs bound in the
  [public acceptance record](../evidence/personal-intelligence-v1.2-public-acceptance-v1.md)
  and their committed run logs under `docs/evidence/artifacts/personal-acceptance-1.2/`;
  findings F5–F10; defects #259 and #260
- Baseline: **run 3 (v1.2.2, 2026-08-20)** — J1 pass with defects, J2 pass, J3–J6 blocked at
  the F5–F10 wall, J7/J8 partial, J9/J10 pass in scope

## 1. Why this packet exists

PI2–PI7 merged real, individually conformance-tested components: adapters that parse and digest,
admission contracts, mapping grammars, a compiled pack, detection engines, ownership depth. The
three acceptance runs together prove nothing composes them — and calibrate exactly where the
composition stops:

- **Run 1 (v1.2.0).** The journey could not start: no public artifact shipped the onboarding
  profile and no build planner was registered (`builds/prepare` → 404/503); a fresh install
  crashed on every `ace` command until a `.env` was hand-created; `ace setup` had no isolation
  defaults and mutated a pre-existing developer database (incident I1, disclosed and reconciled).
  Repairs shipped as v1.2.1 (issues #252–#255).
- **Run 2 (v1.2.1).** Install and isolation held, but the planner entry point was a factory
  function the registry never invokes, so the journey still could not start; the v1.2.1 smoke
  gate missed it by bypassing the production registry path. Past a disclosed one-line local
  patch, the run established the F5–F10 wall: no implementation of
  `ace.source.snapshot/v1alpha1`, adapters and the acquisition port shipped uncalled, no API
  accepts a folder, the packaged Atrium has no Personal journey, the pack maps Markdown only,
  and the `ace.intelligence_builders` executor group is empty. Repairs shipped as v1.2.2.
- **Run 3 (v1.2.2) — the current baseline.** The repairs are proven from pristine public
  artifacts: J1 passes with two root-caused defects (#259 — `ace setup` false-fails owner
  verification because the CLI hardcodes four expected grants while the API verifies five;
  #260 — the CLI loads `.env` from the current working directory only, so `ace doctor` run
  elsewhere can validate a different installation's database while reporting PASS), and **J2
  passes** through the repaired production registry path. The journey then blocks exactly at
  the declared F5–F10 wall: `builds/start` → 503 ("no Intelligence build executor is
  registered") after bind and owner approval both succeed, and no public surface exists to
  nominate a folder. J3–J6 and the positive halves of J7/J8 remain blocked; J9 and J10 pass in
  scope with exemplary integrity.

Every slice gate lived at its own boundary; no gate owned the composition. PI13 is the missing
integration slice, gated at journey depth.

## 2. The one rule that changes

**Gates live at journey depth.** PI13's acceptance for every workstream is a J-step flipping in
the journey-depth CI lane (WS0) and surviving a fresh clean-context acceptance run — never only a
unit or conformance suite at the workstream's own boundary. A workstream whose tests pass but
whose J-step does not flip is not done.

The lane makes the whole journey visible. From its **first allowed-to-fail merge**, WS0 reports
a per-step result for **every** step J1 through J10: a step past the integrated frontier reports
**explicitly blocked**, naming the blocking step or missing workstream — but no step is ever
absent from the report. "Blocked" is a visible ledger state, not a silent gap; the run-3
consolidated verdict table is the shape the lane must always produce.

## 3. Workstreams

| WS | Deliverable | Unblocks | Acceptance |
|---|---|---|---|
| WS0 — journey-depth CI gate | A CI lane that builds the public artifacts, installs them into a bare venv, stands up an ephemeral SurrealDB, and attempts the full J1→J10 journey with a fixture corpus and a deterministic stub provider; merged FAILING (allowed-to-fail) first, flipped lane-by-lane as workstreams land; from the first merge it reports every J1–J10 step, marking not-yet-integrated steps explicitly blocked with their blocker named — never omitting a step | everything | The lane exists, runs on every PR, and its per-step J1–J10 results are visible with no absent step; no workstream merges without moving it |
| WS1 — local snapshot capability provider | A host-side implementation of `ace.source.snapshot/v1alpha1` over the PI2 adapters, registered so pack activation's `local_source_snapshot` requirement binds a real implementation with exact artifact identity | J3 start | WS0 reaches pack activation with the capability bound |
| WS2 — connect API + acquisition wiring | An API surface that names a folder/files, shows exact scope and read-only mode BEFORE any read, records the authorized selection, and routes reads through the PI3 recorded-source admission boundary under the labeled local acquisition mode | J3 | WS0 J3 flips: consent-before-read proven by a negative test (no read occurs before authorization) |
| WS3 — build executor | An `ace.intelligence_builders` entry-point executor that takes the approved plan through the existing `IntelligenceBuilderSessionService` (connect/map/watch) into `CoreIntelligenceBuildFirstBriefService`; loaded through the production registry seam only — the seam run 3 proved for the planner and found empty for the executor | J4, J5 | WS0 J4+J5 flip: inventory states render from the projection vocabulary and a cited first Brief exists |
| WS4 — full source-kind mapping | Pack source-mapping for PDF, CSV, and JSON via the PI4 locator grammar and document-mapping contracts (Markdown ships today); the profile's advertised kinds and the pack's mapped kinds must be identical by test | J3 breadth, J5 citations | WS0 fixture corpus includes all four kinds and every citation resolves to its span |
| WS5 — change detection and revision wiring | The PI7 watcher through re-ingest to a document-shaped Shift and an append-only Brief revision with semantic diff; then claim-bound correction re-derivation (PI8 contracts) on real Briefs | J6, J8 | WS0 J6 flips from explicitly blocked to passing; J8's re-derivation proposal proven on a live corpus edit |
| WS6 — Atrium Personal journey | J2 choose, J3 connect, J4 inventory, and J5 Brief surfaces over the WS2/WS3 APIs, mounting the PI6 first-run candidate with truthful first-run and runtime-readiness states; clean-user desktop and narrow browser paths against the real APIs | J2–J5 in the UI | The clean-context runner completes J2–J5 through Atrium without touching the API by hand; desktop, narrow, accessibility, first-run, and runtime states are truthful |

Frozen implementation order: **WS0 → WS1 → WS2 → WS3 → WS4 → WS5 → WS6**. WS0 lands first
and failing; every later workstream consumes the preceding journey state and moves its visible
J-ledger before the next begins. Also carried: defects
#259 (setup false-fails owner verification: CLI grant-count skew against the five verified
grants) and #260 (doctor reads `.env` from the CWD only and probes the default SurrealDB port
regardless of configured isolation) land inside WS2/WS3 territory and are fixed there; carrying
them narrows no workstream's scope, and both fixes must show as J1's "pass with defects"
becoming a clean pass in the WS0 ledger.

## 4. Method

Each workstream is a bounded, frozen mini-brief suitable for the multi-arm generate → calibrated
adversarial review → composed delivery method the PI12 program validated 3-for-3. The
clean-context acceptance runner is the iteration loop: it reruns after every workstream lands,
and each run's log is the next workstream's sharpest spec. Runs are cheap — runs 2 and 3 each
completed in under half an hour — while end-loading acceptance is what produced this packet.

## 5. Release and honesty rules

- 1.1 and 1.2.x published history is immutable. PI13 work ships as 1.2.x completion releases
  only when a J-step actually flips in WS0 and a fresh runner pass confirms it; version bumps
  without a J-flip do not ship.
- ACE 1.2 is declared **passed** only when the clean-context runner reports J1–J10 end to end,
  the maintainer cross-check concurs, and the four-record reconciliation closes. Until then the
  reconciliation records "not passed; continuation in progress" — the packet's own honesty rules
  applied to itself. WS0 lane results and maintainer-host clean-context runs are candidate
  evidence, never public release acceptance.
- Nothing in PI13 expands the eleven-tool MCP surface, changes the released retrieval/search
  (RAG) behavior of the substrate, adds Personal nouns to `ace/core` or `ace/intelligence`, or
  grants any approve/merge/promote/deploy authority.
- Because issue #195 is closed while acceptance is not passed, the continuation carries its own
  live ledger: the draft body is the
  [PI13 continuation tracker](personal-intelligence-pi13-continuation-tracker-v1.md), local
  until the owner posts it; this packet mutates no GitHub state.
- The external-user acceptance run remains a carried follow-up beyond the amended gate.

## 6. Explicitly out of scope

Everything the 1.2 packet excluded stays excluded (remote sources, universal connectors,
collaboration, Topic/Pack Kit, restore-from-export, hostile-adapter isolation). PI13 adds no new
product scope; it delivers the scope 1.2 already froze. PI13 is an **ACE 1.2 completion packet**:
it does not start, implement, rename, or make any claim for ACE 1.3.

## 7. Owner freeze record

The owner froze this corrected packet on 2026-08-20 and authorized WS0 to begin. The freeze fixes
the WS0→WS6 order and the scope above. It does not authorize a commit, merge, push, tag, publish,
GitHub write, release, or any ACE 1.3 work.

- WS0 may now implement the first visible, allowed-to-fail J1–J10 lane.
- WS1–WS6 begin only in their frozen order after the preceding workstream moves its WS0 evidence.
- The continuation tracker remains local until the owner separately authorizes a GitHub write.

The packet-freeze gate is **passed**. The next human gate is the reviewed WS0 candidate disposition.

## 8. Corrected WS3 addendum — frozen by owner on 2026-08-20

WS3 review proved that its original one-line deliverable omitted four production decisions needed
to move J4 and J5 without fabricated authority or a fabricated change event. The owner froze this
addendum after WS2 acceptance and the first partial WS3 implementation. It clarifies WS3 only;
the six workstreams, their order, WS4 citation breadth, and all exclusions remain unchanged.

### 8.1 Governed local first-run bootstrap

WS3 wires the five existing local-owner grants created by setup into the real domain-activation,
Intelligence-build, and resource-read paths. The production composition must mint and resolve the
exact approval receipt, activation/build grant heads, build authorization, and `observe_read`
authority-use receipt required by the existing services. It must use the durable governed store
and exact identity/precondition rules. Echo resolvers, hand-written receipt hashes, injected
heads, and testing stores are forbidden as WS0 evidence. This is wiring of existing authority,
not a new grant vocabulary or a wider authority model.

### 8.2 Initial-corpus first Brief

J5 is an orientation over the corpus as it exists immediately after the first authorized ingest;
it is not a change claim. WS3 therefore adds an explicit domain-neutral initial-corpus derivation
path to the existing first-Brief application service. Its closure contains the admitted
Observation and EntitySnapshot records at one exact `as_of`, with exact source locators and no
future leakage. It does not create a synthetic Shift or Signal and does not require a second read
or second capture. The existing routed Shift/Signal path remains unchanged for WS5 change
revisions.

### 8.3 Personal orientation policy

The Personal Pack declares the first-corpus synthesis policy, template, and persona needed by the
new path. The stable Pack-local identifiers are:

- policy: `personal_initial_orientation`;
- template: `personal_orientation_first_brief`;
- persona: `personal_orientation_analyst`.

The template produces a compact cited orientation of what currently matters, distinguishes source
statements from inference, states uncertainty, and refuses unsupported material claims. This
policy is declarative Pack content. Change detector and Signal-routing policy remain WS5 scope and
must not be pulled into WS3.

### 8.4 Governed cognition composition

Production WS3 composes the already-selected local structured reasoning provider through the
existing governed reasoning execution and append bindings, then supplies that cognition to the
first-Brief service. WS0 uses its deterministic stub through the same binding path. If no eligible
provider or exact governed binding is available, runtime readiness and the build response fail
closed and state the missing dependency; they never fabricate readiness or a Brief.

### 8.5 Corrected WS3 landing order and acceptance

Within WS3 the frozen order is: (a) governed bootstrap, (b) initial-corpus application contract and
Personal policy, (c) governed cognition composition, (d) executor end-to-end wiring, then (e) WS0
J4/J5 and fresh installed-artifact verification. J4 passes only through the real resource
projection under real authority. J5 passes with a Markdown-cited first Brief whose material claims
resolve to exact spans; PDF/CSV/JSON mapping breadth remains WS4. No WS3 unit-only result is a
completion claim.

The corrected WS3 addendum does not authorize WS4, a commit, merge, push, GitHub write, tag,
package publish, release, or ACE 1.3 work.

## 9. Builder-session progression addendum — frozen by owner on 2026-08-21

WS3 review then proved that the public flow could associate a Builder session at
`GOAL_SELECTED`, while the production activation and host composition required the same session
to reach `FIRST_BRIEFING_READY` and then `ACTIVE`. No production coordinator or API yet drove the
existing Connection Agent, Ontology Agent, Intelligence Agent, and Briefing Agent through their
separate governed transitions. The owner froze this progression addendum to close that WS3 gap.

1. WS3 may add a narrow local-owner Builder progression coordinator and API.
2. The coordinator must use the existing Connection Agent, Ontology Agent, Intelligence Agent,
   Briefing Agent, activation services, and Builder state machine; it must not bypass or replace
   those services.
3. Source-scope, concept-model, intelligence-model, and activation-plan dispositions remain
   separate, explicit, exact owner approvals. The implementation must not fabricate or bundle
   their approval receipts.
4. Production strategies use the already-selected provider through the existing strategy ports.
   WS0 may use a deterministic provider only through those same ports.
5. After activation, the existing production-registry executor performs recorded-source
   admission, initial-Brief derivation, and resource projection.
6. Atrium remains WS6 scope, and WS4 remains prohibited until the reviewed WS3 candidate is
   accepted.

The frozen progression order is source-scope proposal and approval, concept-model proposal and
approval, intelligence-model proposal and approval, first-briefing readiness, activation-plan
proposal and approval, activation, and registry execution. Every transition must preserve exact
session identity and current-revision preconditions, fail closed on stale or missing authority,
and expose a truthful retry-safe result. A WS3 completion claim still requires J4 and J5 to move
in WS0 and a fresh installed-artifact run against ephemeral SurrealDB.

This freeze authorizes implementation and verification of the bounded WS3 progression path only.
It does not authorize WS4, a commit, merge, push, GitHub write, tag, package publish, release, or
ACE 1.3 work.
