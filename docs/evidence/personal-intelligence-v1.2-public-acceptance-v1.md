# ACE 1.2 Personal Intelligence public acceptance v1

Status: **not passed — journey integration continuation in progress (PI13)**

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
