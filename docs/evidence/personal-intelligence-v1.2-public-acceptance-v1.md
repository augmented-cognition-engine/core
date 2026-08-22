# ACE 1.2 Personal Intelligence public acceptance v1

Status: **not passed as a public release acceptance — PI13 continuation complete for nine of ten steps; unlanded and unpublished; J6 deferred to 1.3**

This record binds the public J1–J10 acceptance evidence for ACE 1.2 Personal Intelligence. Its
verdict is honest and current: the released substrate demonstrates real integrity on every surface
it exposes, and the integrated Personal journey the packet froze does not yet exist in the public
artifacts. ACE 1.2 is not declared passed by this record; the four-record reconciliation carries
this status until a clean-context run reports J1–J10 end to end and the maintainer cross-check
concurs.

## Gate provenance (amended, disclosed)

The frozen packet gate required "a clean user who is not an ACE maintainer." No such human runner
was available; by owner amendment (issue #195, 2026-08-20) the journey is executed by a
**clean-context agent session** — a fresh session with no repository, build, or project memory,
briefed only with public artifacts and public documentation from a frozen brief — followed by a
maintainer cross-check, with both provenances disclosed and the external-user run carried as a
pending follow-up. Controls per run: brief frozen before launch with its digest registered on
issue #195, no coaching mid-run, failures recorded as results, the runner's complete log as
primary evidence. The runs execute on the maintainer's host confined to a clean workspace; the
host is not a clean machine, and that deviation is disclosed here.

- Run 1 brief sha256 `db473990ae32583c5274a023d8b7b3c5daa6dd4ba3ee26e041c237dd98877333`
- Run 2 brief sha256 `9e5abe81e6a6dae2a73cee2f0622016a24b2f3da70906ebcf41751ff5bd1c3e2`
  (byte-identical to run 1's except the release URL, install pin, and workspace path)

Sanitized copies of each run's full log and per-step verdict draft are committed under
`docs/evidence/artifacts/personal-acceptance-1.2/`.

## Run 1 — v1.2.0 (2026-08-20)

All 8 release-asset digests verified; `ace-core==1.2.0` installed cleanly. **Verdict: fails at
J2/J3.** No public artifact shipped the onboarding profile and no build planner was registered
(`builds/prepare` → 503), so the journey could not start; a fresh install crashed on every `ace`
command until a `.env` was hand-created; `ace setup` had no isolation defaults and, on this host,
applied schema migrations to the pre-existing developer database and treated a foreign API as its
own before failing (incident I1 — disclosed, reconciled); getting-started docs described 1.0.3 and
required a forbidden git clone. Repairs shipped as v1.2.1 (issues #252–#255, PRs #256/#257),
including the journey-start smoke gate in the release build.

## Run 2 — v1.2.1 (2026-08-20)

All 16 release-asset digests verified; the isolation repairs held (nothing outside the run
workspace was read or written). **Verdict: fails at J2, then fundamentally at J3.**

- The v1.2.1 planner entry point was a factory function the planner registry never invokes (it
  instantiates classes only), so `builds/prepare` still returned 503 — and the v1.2.1 smoke gate
  missed it by invoking the entry point manually instead of through the production registry path
  (findings F3/F4; repaired in v1.2.2).
- With a disclosed one-line local patch past F3, the journey dead-ends at J3: no public artifact
  implements `ace.source.snapshot/v1alpha1`; the local-source adapters and acquisition port ship
  uncalled; no API accepts a folder path; the packaged Atrium contains no Personal journey; the
  pack maps Markdown only against a profile advertising four kinds; and the
  `ace.intelligence_builders` executor group is empty (findings F5–F10). J4–J6 and J8 are
  therefore blocked. `ace setup` also false-fails owner verification on a healthy stack (#259)
  and bare `ace doctor` probes the default SurrealDB port regardless of configured isolation
  (#260).
- What exists behaved with integrity: every governed boundary failed closed with receipts; Ask
  returned a contract-shaped honest no-answer naming its missing coverage (J7 partial pass);
  restart reopened every existing identity exactly (J9 pass); ownership export/deletion delivered
  exact counts, checksums, disclosed exclusions, and verified non-reappearance on the records
  that existed (J10 scoped pass).

## Run 3 — v1.2.2 (2026-08-20; brief sha256 `90e8b87ad34a105c31af7e029e5722d90593310fd0de427ef19ccd62d49ec58e`)

All release-asset digests verified; the run stayed fully isolated (own compose project, ports,
and relocated config dir) and stopped its runtime cleanly. **Verdict: not accepted end to end,
exactly as the v1.2.2 release notes disclose — and the repairs are proven.** J1 passes ("ACE is
operationally ready") with two remaining defects now diagnosed to root cause: the false
owner-verification failure is the CLI hardcoding four expected grants while the API verifies five
(#259), and `ace doctor` validates a different installation's database when run outside the
directory holding the generated `.env` (#260). **J2 passes** — Personal Intelligence is chosen
through the repaired `builds/prepare` planner, demonstrating the 1.2.2 headline fix from public
artifacts. The journey then blocks at the declared F5–F10 wall: `builds/start` returns 503 ("no
Intelligence build executor is registered") after bind and owner approval both succeed, and no
public surface exists to nominate a folder, so J3–J6 and the positive halves of J7/J8 remain
blocked pending PI13. J9 and J10 pass in scope with the same integrity as run 2, including the
exemplary export → deletion-preview → deletion-proof → verified non-reappearance flow.

## Consolidated per-step verdict (as of run 3)

| Step | Verdict | Basis |
|---|---|---|
| J1 Install | Pass with defects | Artifact integrity exact; #259 (root-caused: CLI hardcodes four grants vs five verified) and #260 remain |
| J2 Choose | Pass (as of v1.2.2, run 3) | Planner loads and plans through the production registry path |
| J3 Connect | Fail (F5–F7) | No snapshot capability, no acquisition wiring, no connect API |
| J4 Inventory | Blocked on J3 | — |
| J5 First Brief | Blocked on J3 | — |
| J6 Change | Blocked on J5 | — |
| J7 Ask | Partial pass | Honest no-answer with receipts; cited answers untestable without Briefs |
| J8 Correct | Partial | Fail-closed claim-bound surface; re-derivation untestable without Briefs |
| J9 Restart | Pass (scoped) | Identity-exact reopen of everything that existed |
| J10 Own | Pass (scoped) | Truthful export/deletion with verified non-reappearance |

## Root cause and continuation

Every 1.2 slice carried conformance evidence at its own boundary; no gate owned the composition,
so components merged without a runnable journey. The continuation is scoped in
[PI13 — Personal journey runtime integration](../design/personal-intelligence-journey-integration-pi13-v1.md):
a journey-depth CI gate first, then the six integration workstreams, with the clean-context
runner as the per-landing iteration loop. Release closeout rules are unchanged: ACE 1.2 is
declared passed only by a full J1–J10 clean-context pass, maintainer concurrence, and the
four-record reconciliation.

## PI13 continuation status (2026-08-21) — candidate evidence, not a public run

This section records where the continuation reached. It is **candidate evidence and nothing more**: the
runs below execute freshly built local wheels from the unlanded `pi13-continuation` branch, not published
artifacts, so under the packet's own rules (§5) they can never constitute public release acceptance.

### What the journey-depth lane reports

The WS0 lane builds Core, the Personal pack and bundle, and all local adapter distributions; installs only
those wheels into a bare virtual environment outside the checkout; stands up an ephemeral memory-only
SurrealDB at schema v179; and walks the public route sequence end to end —
`/auth/token`, `/auth/local-owner/bootstrap`, Connect preview and authorize over the fixture corpus,
`/prepare`, `/bind`, `/bootstrap/local-first-run`, `/session/associate`, the seven Builder progression
routes, `/activation-plan/prepare|approve|activate`, `/start`, and `resources/query`. Its provider is
deterministic but never injected: it is selected through the production `get_llm()` path.

| Step | Run 3 (v1.2.2, published) | PI13 lane (unpublished) |
|---|---|---|
| J1 Install | Pass with defects #259, #260 | **PASS** — #259 fixed; #260 corrected |
| J2 Choose | Pass | **PASS** |
| J3 Connect | Fail (F5–F7) | **PASS** — installed snapshot binding, both exact routes, consent-before-read with zero provider calls |
| J4 Inventory | Blocked | **PASS** — `source_health=5 entity=5 observation=5`, every observation resolving to an admitted source across csv/json/md/pdf |
| J5 First Brief | Blocked | **PASS** — 1 Brief, 6 cited claims, 0 uncited, 0 unresolved citations, spanning all four kinds |
| J6 Change | Blocked | **BLOCKED — deferred to 1.3** (packet §12) |
| J7 Ask | Partial | **PASS** — cited answers *and* an honest refusal, after the §11 refusal narrowing |
| J8 Correct | Partial | **PASS** — a correction bound to one exact cited claim, recorded as a proposal only |
| J9 Restart | Pass (scoped) | **PASS** — all 16 resources reopened with exact identities (scope: reopened connection pool, not a service restart with a persisted volume) |
| J10 Own | Pass (scoped) | **PASS** — 84 records exported, 84 previewed, exact deletion proof, zero survivors |

### The one step that did not close, and why it is disclosed rather than worked around

J6 remains blocked. Change detection is complete and proven — Core's content-revision detector family,
Core-resolved `prior_snapshot` baselines, the Personal Pack's declared detectors, and the executor's
append-only Brief-revision routing — but no public surface admits a second capture of an edited source.
A second PREPARED build cannot carry new material without loosening the rule that an ACTIVE Builder
session binds one exact activation approval, which is the reason the build path can be trusted. The
substrate's continuous-update path is live source ingress, which has no public route and which the
Personal journey does not compose. Packet §12 moves it to 1.3 — *Intelligence Operations and Safe
Evolution* — where a watcher belongs. **Continuous update is therefore not in the public Personal
journey for 1.2, and this record says so plainly.**

### Defects this continuation found that no unit test could

Each was reproduced against real installed artifacts and a real database, and each was fixed test-first:

- `scripts.schema_apply` duplicated a `sys.path` entry, so `importlib.metadata` enumerated every
  distribution twice and installed-Pack discovery broke process-wide;
- the installed-Pack resolver read one twice-enumerated dist-info as two ambiguous Packs;
- recorded-source admission replay and the resource-projection recorded-source decoders validated durable
  payloads strictly, but SurrealDB returns JSON, so every real replay and the whole `source_health`
  projection failed closed;
- the build cognition resolver rejected the build's own product-scoped record-store fence, which
  production `/start` always supplies;
- the OpenAI-compatible provider never recorded usage into the in-process accumulator, so every governed
  structured call failed closed for missing telemetry;
- `BriefV1Alpha1` compared a citation's ingestion instant against the Brief's validity cut, which refused
  every orientation over a historical corpus;
- grounded Ask scored claims on unfiltered token overlap, so one shared common word answered anything and
  the honest-no-answer guarantee held only while a corpus was empty.

### What the Atrium said, and what it says now

The steps above were verified through public HTTP routes. The Atrium is where an owner actually forms
expectations, and it carried three defects of its own (`personal-intelligence-pi13-ws6-candidate-v1.md`):

- The onboarding flow's final stage was labelled **"Activate continuous maintenance"** and reached
  `complete` on an active Builder session — asserting, at the exact point of reading, the one capability
  J6 shows is absent. It is now "Activate the domain" and states that Briefs are rebuilt when you ask
  and that this release does not update them on its own.
- Whether a source group's evidence lives on the owner's machine existed only as prose, so the Connect
  surface could not be mounted from anything trustworthy. The onboarding-profile contract now carries
  `requires_authorized_root` (additive, defaulted, no Personal noun in `ace/intelligence`), and the
  Atrium fails closed on a malformed value.
- Selecting a local source group was enough to proceed to planning. Selection and preview now both leave
  planning blocked; only allowing the read of the exact shown scope unblocks it, and deselecting the
  group or changing profile withdraws that authorization.

And the finding that made those three consequential: `core/engine/atrium/static` is a committed build
artifact that nothing rebuilt or checked. The bundle the package serves contained none of the Atrium
work in this continuation and still contained the retired maintenance claim. It has been rebuilt from
source, and CI now fails when it drifts.

### What acceptance still requires

Unchanged and owner-held: a clean-context J1–J10 run against **published** artifacts, the maintainer
cross-check, and the four-record reconciliation closing. The external-user acceptance run remains a
carried follow-up. Until the continuation lands and is published, this record's verdict stays **not
passed**, and the reconciliation continues to carry that status.
