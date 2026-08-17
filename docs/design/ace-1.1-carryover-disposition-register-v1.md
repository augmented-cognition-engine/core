# ACE 1.1 carryover disposition register v1

- Date: 2026-08-17
- Baseline audited: `origin/main` `eab2aa211fbee18d8aa1b828522830e3d9b95396` (ace-core 1.1.0) plus
  the GitHub record set (issues, PRs #202/#204/#205, release v1.1.0, project timeline events)
- Companion to: [ACE 1.2 Personal Intelligence work packet v1](personal-intelligence-v1.2-work-packet-v1.md)
- Status: **proposed dispositions for owner review**. PI1 turns accepted rows into issue updates.
  "Recommended" means no authority is claimed here; every disposition is a proposal.

Legend: **1.1.x** = narrowly scoped maintenance patch under the published 1.1 promise ·
**1.2** = absorbed by the 1.2 packet · **1.3+** = assigned to a later milestone issue ·
**Owner decision** = no record currently owns it; needs an explicit call.

## 1. Release-record debts (blocking PI1)

| Item | Where recorded | Recommended disposition |
|---|---|---|
| Issue #194 closed with no closeout comment: no tag/run/digest/evidence link or final disposition on the issue; four-record reconciliation record 2 incomplete while 1.2 moved to Now | #194 (`comments: 0`), `docs/release-closeout.md`, evidence record claims vs. issue state | **1.1.x closeout fix** — one comment on #194 with tag, run, digests, evidence link, and the explicit deferral dispositions below |
| `ROADMAP.md:248` and `README.md:148` promise cloud drives, databases, warehouses, object stores for 1.2 | vs. issue #195 and `ROADMAP.md:739–741` (local-only first) | **1.1.x doc fix** — issue #195 is canonical; correct table row and README |
| `ROADMAP.md` §1.2 "not… part of the Personal Solution Bundle" wording vs. `MANIFESTO.md:188–190` (bundles link adapters) | ROADMAP vs. MANIFESTO, `docs/intelligence-os.md:225–227` | **1.1.x doc fix** — reword to "binds exact adapter versions without owning implementations" |
| Stale status lines: `docs/extension-invocation-contract.md` "E1 remains not ready" (E1 passed); `docs/capability-maturity.md` "1.0 line"/"0.3.x" fragments; `docs/README.md` "active 1.1 milestone"; `agent-memory-roadmap.md` AM1 status header; `ROADMAP.md:895` "complete by 1.0.0" for SI | sweep items B13/B14 | **1.1.x doc fix** batch |
| Public acquisition-mode table documents only PREPARED and LIVE; the RECORDED boundary (`ace/application/recorded_source_admission.py`) appears in no `.md` | sweep item B4 | **1.2 (PI3)** — documented when the local mode lands |

## 2. Carryovers absorbed into the 1.2 packet

| Item | Where recorded | Where it landed |
|---|---|---|
| Reference adapter pins `ace-core>=0.8.0,<1.2`; Core 1.2.0 breaks it | `adapters/reference_workspace_action/pyproject.toml:12`, CHANGELOG 1.1.0 | Packet §3 precondition + PI2 |
| Issue #49 **F3** atomic mutable-registration hardening (re-dated 2026-11-05, unwaived); containment argument assumed no extension-surface expansion | #49; 0.6 hardening packets; `docs/capability-maturity.md:234–237` | Packet §3 precondition; gates PI10 |
| SI1 bounded controls (as-of isolation, append-only revision, no future leakage) required by the J6 promise | issue #47; `ROADMAP.md:786–798, 1228` | Packet §3 + PI7; general SI gate stays out of scope |
| Source Health "explicitly unsupported"; no watcher; changed paths caller-supplied | `docs/design/intelligence-resource-plane-v0.8.0-work-packet-v1.md:110`; single-chain evidence:109 | PI6/PI7 lift it explicitly for local sources |
| Progressive capability and context disclosure ledger row tagged 1.2 | ROADMAP outcome ledger | Packet decision 12 |
| Topics share-ready by construction, promotion previewable and identity-preserving, disclosure keeps packs/manifests out of the default path | `docs/design/scale-invariant-product-architecture-v1.md:253–258`; VISION Topic framing | Packet decision 10 (records scale-invariant now; promotion UX stays 1.4) |
| Ownership caveats: export not runnable-restore; no import service; no write-quiescence primitive; deletion proof bounded to primary store; empty-install delete preview 409 | `personal-intelligence-ownership-v1-work-packet.md:22–24, 68–82`; AM4 packet:116–129; 1.0 acceptance:55–56 | PI9 + packet §8 truthful-limitations list |
| E2 connector-lifecycle slice needed for local adapters without the full E2/Adapter Kit gate | `ROADMAP.md:1227, 557–560`; issue #197 | PI2/PI10 consume; Adapter Kit stays 1.4 (out of scope §7) |
| AM7 locator semantics (page/region locators, content-addressed external bodies) overlap PI4's citation grammar | `agent-memory-roadmap.md:509–541` | PI4 keeps locator contracts AM7-compatible; AM7 itself stays later |
| **`ACE Builds ACE` matched reference program** — **decided by owner 2026-08-17: re-scoped into 1.2.** Bounded 1.2 implementation Decisions are the program subject; shipped 1.1 capabilities only; no self-authority; honest negative result valid | `ROADMAP.md:726, 907`; `governed-code-improvement-loop-v1.md` | Packet decision 13 + PI12; evidence `ace-builds-ace-v1.md`; recorded on #194 closeout comment |
| **Code Intelligence composition direction** — owner direction 2026-08-17: Code Intelligence is a composable System capability co-activatable by any bundle/Topic AND remains a standalone Solution Bundle for non-ACE products; no embedded/standalone fork; never a required dependency of Personal Intelligence; typed cross-pack relation grammar stays 1.5 | owner direction; consistent with `ROADMAP.md` "One intelligence core. Many intelligence products." and the pack-kind model | Packet decision 14 + PI10 co-activation gate + PI12 composition; PI1 reflects the direction into the ROADMAP 1.5 narrative so 1.5 inherits it explicitly |

## 3. Recommended 1.1.x maintenance batch (not 1.2 scope)

| Item | Where recorded |
|---|---|
| #49 **F4** — embed executed restart e2e receipt / immutable CI run identity in the security bundle | issue #49 |
| #49 **F7** — enforce ≥32-byte JWT signing entropy ("before production traffic") | issue #49 |
| Incident admission: fresh-process/live index revalidation, degraded runtime composition | `code-intelligence-incident-admission-boundary-v1.md:163–164` |
| Incident local-index binding not composed into live Code lens/handoff; `incident_source_unconnected` omission | `code-intelligence-incident-local-index-binding-v1.md:164–173` |
| Pageable per-family Code-lens revalidation | `code-intelligence-resource-admission-v1.md:252–254` |
| Atrium UI for resource admission | `code-intelligence-resource-admission-v1.md:211` |

## 4. Assigned to later milestones (confirm on the milestone issues)

| Item | Recommended home |
|---|---|
| Improvement loop 3 (agent/procedure/routing/framework revisions); AM5/AM6 governed memory evolution and evaluation | **1.6** (matches `governed-code-improvement-loop-v1.md` and `agent-memory-roadmap.md`) |
| Backup/rollback/recovery UX, upgrade flows, migration receipts; restore/import service; pre-v142 migration recovery; SurrealDB downgrade-in-place absence | **1.3** (#196) |
| Watcher/LSP/multi-language/multi-repo Code Intelligence expansion | **1.3+** per the wheel-acceptance non-claims |
| Adapter Kit, open adapter contract, connector SDK breadth, heterogeneous-evidence breadth, `v1alpha1` pack-manifest removal window | **1.4** (#197) |
| H1 collaboration/tenancy; AM9 backend portability, backup inventory, tenant delete/restore, DR; distributed ingestion; F6 per-reviewer identity | **1.7/2.0** (#200/#152) |

## 5. Owner decisions required (no record owns these today)

### Resolved by owner 2026-08-17

- **Improvement loops 1–2** — the public 1.1 release delivered bounded read-only reasoning and
  handoff, not active loops (per `ace-1.1.0-public-release-v1.md`). ROADMAP:247, the 1.1
  improvement-model section, and `governed-code-improvement-loop-v1.md`'s 1.1 roadmap-fit are
  reconciled: 1.1 freezes the loop **contracts**; active linked repair is sequenced to 1.3 and
  future-work learning to 1.6.
- **`ACE Builds ACE`** — executed in ACE 1.2 with bounded 1.2 Decisions as its subject (decision
  13 / #220), not 1.1. ROADMAP and the improvement-loop design doc now say so.
- **SI1–SI4** — the general two-external-pack gate targets a post-1.2 milestone; ACE 1.2 delivers
  the bounded SI1 slice (as-of isolation, no future leakage) via PI7 (#215). Recorded on #47; the
  ROADMAP phase-8 row was corrected in PI1.
- **World-to-Code demonstration** — **deferred** until after the 1.2 local journey passes; it is a
  top-of-funnel demo that blocks nothing. Revisit at 1.2 close.
- **F2 naming collision** — the two "F2"s are in distinct registers (0.6 foresight consequence
  broadening vs. #49 security observability). Disambiguated by a note on #49; no rename, to avoid
  breaking the F-series references.

The remaining rows below stay open pending an owner call.

| Item | Where recorded | Tension |
|---|---|---|
| **World-to-Code demonstration** — promised "after the repository journey passes"; that journey passed | issue #194 scope | Candidate marketing deliverable; needs a home or an explicit drop |
| **Improvement loops 1–2 (linked repair, architecture opportunity)** — ROADMAP:247 credits 1.1 with "governed improvement loops"; release notes claim only read-only reasoning + handoff | ROADMAP vs. v1.1.0 release notes | Decide shipped-vs-deferred; reconcile ROADMAP:247 either way |
| **Concurrent-work reconciliation** (stale Context Manifest, notify/pause/steer/cancel/replan) | `ROADMAP.md:719–724` | In the 1.1 product-contract text, not in the release; needs a milestone |
| **SI1–SI4 re-targeting** — ledger still says "complete by 1.0.0"; all four remain not ready; #47 has no milestone | #47; `ROADMAP.md:895, 1228–1231` | Re-date on #47 acknowledging the 1.2 bounded slice; pick the general gate's milestone |
| **F2 (0.6 foresight consequence-type broadening)** and **#49 F2 observability item** (both named "F2") | `ROADMAP.md:1225`; issue #49 | Assign each; consider renaming one to avoid collision |
| Orphaned-authentication-receipt retention/denial-linkage policy | `code-intelligence-resource-admission-v1.md:206–209` | Unowned |
| K2/K3 repeated large-corpus evidence; foresight Brier/reliability scoring; transport-matched blinded human judgment | `state-engine-core-boundary-v1.md:111–113`; `docs/foresight.md:326–327`; `evaluations/README.md:57` | Unowned evaluation debt |
| Architecture debts: reversed MCP-tools dependency, API-helper imports in services, broad API registration, no uniform store boundary | `docs/architecture.md:224–243` | Deliberately deferred; decide whether 1.2's application work is the trigger for any |
| 0.8B B1–B3 runtime realignment and 0.8D Atrium acceptance leftovers — no closing record found | `intelligence-os-runtime-boundary-v0.8.0-work-packet-v1.md:91–110`; `atrium-intelligence-experience-v0.8.0-work-packet-v1.md:75–80` | Verify whether since closed; else assign or record as accepted |
| Agent Memory sequence "remains a proposed cross-release capability roadmap" — never reconciled with the public roadmap | `agent-memory-roadmap.md:3–4, 660–670` | Reconcile status during PI1 or record why not |

## 6. Atrium UX worktree carryovers (frozen 2026-08-16, never merged)

The Atrium UX contributor packet (codex worktree `0469`, detached at pre-1.1.0 commit `d73906b`;
`docs/design/atrium-product-ux-directions-v1/` + `ace-host-first-run-onboarding-v1.md` +
`HostFirstRun.tsx` candidate, 424/424 Canvas tests) targeted the "official ACE 1.1 integrated
candidate" — which has since shipped and closed **without it**. Its queue needs a 1.2-era home,
and 1.1.x cannot take the feature-shaped pieces (a host-mode API, Settings mutation, and download
service are new public promises, which the release rules reserve for a minor release).

**Preservation risk:** the frozen design docs, screenshots, decision ledger, and candidate
component exist only in a disposable worktree. Land them in the repository (as design-record
commits) regardless of disposition, before the worktree is cleaned up.

| Item | Recommended disposition |
|---|---|
| Host first-run experience for the **Personal** mode: canonical `configured / admin_fixed / unconfigured` host projection, durable user-owned mode persistence, Settings mutation, production routing of the frozen `HostFirstRun` candidate, hardware/runtime detection wiring | **1.2** — this is the personal product's front door and belongs to J1/PI6; adopt the frozen candidate and its seven control-tower contract assumptions |
| Resumable model-download service, honest usable/downloaded/loaded/generated readiness, real inference smoke-test receipts (nonblocking lane) | **1.2 (J1 nonblocking lane) or 1.3** — owner call; the candidate treats it as nonblocking status, so deferring the service to 1.3 does not block J1 |
| Shared-server remote-access exposure and Dedicated-appliance conversion flows | **1.7** (portable deployment); explicitly separate reviewed flows per the handoff |
| Live-SurrealDB integration verification of the shipped 1.1 seams (build association, `GOAL_SELECTED` progression, activation-plan coordinator, resource-state projection) | **1.1.x hardening** — verifies published promises; also exercised naturally by 1.2's use of the Builder |
| Runtime progression `GOAL_SELECTED` → sources → models → `FIRST_BRIEFING_READY` with real source/modeling agent dispositions | **1.2** — this is exactly the J3–J5 spine; PI2–PI6 supply the missing runtime |
| Pack upgrade discovery contract, customer-facing rollback action, reviewed customization mutation | **1.3** (update experience) and **1.4** (Pack Kit), matching the roadmap's existing split |
| Consumer subscription target storage, `immediate`/`digest` delivery, stream/webhook destination contracts, general consumer Outcome return | **1.4/1.5** — contract dependencies per the worktree's own audit; currently correctly fail closed |

**Closed, no carryover:** the nine co-developer runtime recommendations (product-scoped cognify
projections, sentinel degraded states, `orchestration_run` product persistence, SurrealDB 3.2 +
v179 + export/import verification, foresight ORDER BY compatibility, configurable vector max
distance defaulting 0.45, `reasoning_content` + OpenAI-compatible timeout + gates + leak fix,
bounded delegated cognition review, ≤v135 assertion-history upgrade path) verify by sampling on
`origin/main` (`config.py:322`, `ace/core/delegated_cognition.py`,
`docs/operations/ace-1.1-database-upgrades.md`, v179 schema). Their bounded defaults — dry-run
migrations, trusted human/admin issuer for delegated review — are accepted safety boundaries,
recorded as such, not unfinished work.

## 7. Standing non-claims (no action; restated for 1.2 truthfulness)

Universal language coverage, hostile-code/compromised-host isolation, exhaustive secret detection,
managed hosting, collaboration, distributed availability, universal connectors, and general causal
benefit remain non-claims (`ace-1.1.0-public-release-v1.md`, `capability-maturity.md`). The 1.1
"safe-deletion proof" non-claim concerns dead-code deletion in Code Intelligence and is unrelated
to the 1.2 user-data deletion journey; the two must not be conflated in release language.
