# PI13 WS3 partial local candidate evidence v1

- Date: 2026-08-20
- Baseline: `origin/main` / `e9a53ae63d209a266dc8a5156b1afcd5c939dd08`
- Disposition: **historical partial implementation record; blocker resolved by frozen PI13 §8;
  implementation resumed; not landed**
- Scope: WS3 and truthful WS0 J4/J5 reporting only. This record does not claim a completed
  workstream, a clean-context pass, public release acceptance, or an ACE 1.2 acceptance pass.

## Implemented WS3 slice

The root distribution now registers a zero-argument `personal_intelligence` executor in the
production `ace.intelligence_builders` entry-point group. The executor accepts only the exact
Personal onboarding profile and `v1alpha2` authorized build, requires the `recorded_sources`
port, and fails closed on missing or empty selection references.

For every exact reviewed reference, it uses `LocalSourceConnectRecordRepository` to replay the
already-authorized capture for the same product and actor. It performs no second filesystem
read and makes no remote request. The replayed selection and capture are converted to the
existing recorded-source material contract, bound to the subject, admitted through
`CoreRecordedSourceAdmissionV1Alpha2Service`, and queried through the existing resource page for
SOURCE_HEALTH, ENTITY, OBSERVATION, and BRIEF. No alternate admission store or Personal-specific
resource vocabulary was added.

The Personal Pack's existing source-mapping module now has an exact Markdown mapping over the
canonical local snapshot payload: note and title resolve from `/0/anchor_value`, and body resolves
from `/0/text`. Its manifest and solution-bundle identities were regenerated. PDF, CSV, and JSON
mapping remains WS4 and was not started.

Defect #260's configuration correction is also implemented: runtime environment discovery no
longer trusts an unrelated current-working-directory `.env`; it respects the explicit
`ACE_ENV_FILE`, source-root configuration, and `ACE_CONFIG_DIR` locations before process
environment overrides. Recorded-source readiness now reports the truthful acquisition mode and
accepts both `local` and `recorded_replay` production modes.

Claude Code CLI performed the bounded production-executor, Markdown mapping, #260, and WS0
reporting edits in workstream-specific prompts. Every resulting change was inspected here.
Claude's independent read-only review was evidence, not approval authority. The previously
observed stale hook for the decommissioned agents project did not appear. Claude authentication
was renewed through its normal browser flow; that changed no repository file.

## Focused verification

The final focused WS0/WS3 run passed 104 tests covering:

- executor entry-point loading and duplicate registration failure;
- exact profile/version/port/reference fail-closed behavior;
- durable Connect record persist/replay without a reread;
- recorded-source admission and resource queries;
- the real Personal Pack Markdown mapping against the WS0 normalized fixture shape;
- #260 environment resolution and unrelated-CWD rejection;
- local/recorded-replay readiness projection;
- J1-J10 gate structure and truthful J4/J5 blocked reporting.

Ruff passed for every changed WS0/WS3 Python file included in that run. An earlier combined
executor-focused run passed 124 tests with the one known pristine-baseline extension-disabled
kernel-start test explicitly deselected. No RAG/search behavior changed, no Personal noun was
added under `ace/core` or `ace/intelligence`, and the eleven-tool MCP boundary was not changed.

No fresh installed-artifact WS3 run is claimed. The frozen rule requires the corresponding
WS0 J-step to move first; neither J4 nor J5 can move honestly with the current packet and
production composition. Building another wheel set merely to reproduce a static blocked row
would not convert this partial slice into completion evidence.

## J4 blocker — governed authority bootstrap

The production executor, exact recorded replay, recorded-source admission, and resource
projection seams exist. A clean public-artifact journey cannot invoke them, however, because no
production composition bootstrap in the frozen WS3 path mints and resolves all of the following:

- the committed activation approval and authority grants;
- the matching activation and build authority-grant governed-state heads;
- the authorized Intelligence build receipt; and
- the exact `observe_read` authority-use receipt required by resource projection.

Supplying echo resolvers, hand-written receipts/hashes, or an in-memory testing store would make
the probe green by fabricating authority. WS0 explicitly rejects that as public-artifact evidence.
J4 therefore remains `BLOCKED` with
`WS3:governed_authority_bootstrap_unavailable`.

## J5 blocker — first-corpus and cognition contract

Three independent structural gaps prevent a real first Brief:

1. One initial admitted Markdown capture creates one EntitySnapshot for an entity, while the
   existing prepared Shift/Signal derivation request requires two distinct, ordered snapshots of
   that same entity. The production first-Brief service has no non-Shift initial-corpus path.
2. The Personal Pack declares ontology and source mapping only. It has no detector, attention
   routing, or brief-synthesis policy/template/personas for the runtime to resolve.
3. Production build composition supplies no governed first-Brief cognition: no selected reasoning
   provider plus reasoning execution and append bindings are passed into the first-Brief service.

Inventing any of those policies, changing first-Brief semantics, or choosing cognition bindings
inside an implementation prompt would alter the frozen packet. J5 therefore remains `BLOCKED`
with `WS3-WS4:first_brief_unavailable`.

## Owner decision — resolved by corrected PI13 §8

On 2026-08-20 the owner froze the corrected packet with:

1. the production governed-authority bootstrap for the clean local first-run journey;
2. first-corpus semantics: an explicit non-Shift first-Brief derivation or a required second
   ordered capture of the same entity;
3. the Personal detector/routing/brief-synthesis policy, including template and personas; and
4. the governed reasoning provider and reasoning/append bindings for first-Brief cognition.

WS3 resumes in that corrected order and must move J4 and J5 through WS0 before the required fresh
bare-venv/ephemeral-SurrealDB verification can support candidate disposition. WS4 has not started.
No commit, merge, push, GitHub write, tag, package publish, or release occurred.

## 2026-08-21 continuation — frozen Builder-session progression coordinator

The owner-frozen Builder-session addendum is now implemented locally through the existing
Connection, Ontology, Intelligence, and Briefing Agent seams. The host coordinator makes source,
concept, and intelligence decisions separate exact owner approvals; it derives observations only
from the recorded Connect transaction; and it leaves first-Brief preparation without a fifth
approval. Every selected-provider call is preceded by a durable exclusive intent that binds the
exact request material. An identical retry reopens the durable Connect and artifact chain instead
of repeating a provider call or owner decision; stale, crossed, unavailable, or coherently forged
material fails closed.

Independent review accepted this coordinator slice after 142 focused WS3 regressions and 185
broader related tests passed (two expected skips; only existing warnings). This is local candidate
evidence only. It does not claim WS3 complete, move J4/J5, claim a fresh installed-artifact run,
or begin WS4. The remaining frozen WS3 work is thin host API composition and the existing
activation-plan path to the same session's canonical `ACTIVE` state.

## 2026-08-20 continuation — WS3a through WS3d focused candidate

After the owner froze PI13 §8, the local candidate added the four corrected WS3 slices in order:

1. the durable local first-run activation/build/read bootstrap over the five setup grants;
2. a domain-neutral initial-corpus Brief synthesis path and the frozen Personal orientation
   policy/template/persona, with no Shift, Signal, or second capture;
3. a product-scoped production cognition resolver that reads exact current reasoning/append
   configuration, capability, and grant heads before adapting the already-selected provider; and
4. executor wiring that retains `RecordedSourceAdmission`, derives one exact corpus cut from its
   Observation/EntitySnapshot material and transaction receipt, creates the first Brief, and only
   then queries the resource projection.

The build response now preserves the specific missing cognition dependency as an unavailable
result. The resolver performs no commits and never mints or widens authority. The Personal
executor rereads no source, uses no wall clock for the corpus cut, and leaves first-Brief failures
fail closed before projection.

Focused verification passes **141 tests** across cognition resolution, executor ordering,
initial-corpus synthesis, existing Brief/Case synthesis, Pack policy/installed artifacts,
Builder/activation composition, governed first-run bootstrap, build API behavior, and public
boundaries. The one known pristine-baseline
`test_extension_disabled_kernel_starts_without_live_composition` failure is explicitly deselected;
running it alone still reproduces the unchanged LIVE-import failure. Ruff and `git diff --check`
pass. No Personal noun was added under `ace/core` or `ace/intelligence`; RAG/search and the eleven
MCP tools were not changed.

This is not a completed WS3 or J-step claim. Setup's frozen five grants do not currently authorize
the `reason` and `append_immutable_records` operations required by the exact governed bindings,
and no production provisioning path creates their configuration/capability heads. The resolver
correctly fails closed rather than fabricating them. Choosing a new cognition grant or explicitly
widening and migrating one of the five existing grants changes governed authority material and is
the next human gate. Until that decision is frozen and implemented, WS0 J4/J5 cannot move and no
fresh installed-artifact WS3 run can support candidate disposition. WS4 remains unstarted.

## 2026-08-21 continuation — authorized widening and durable provisioning

The owner authorized preserving the five-grant model and widening only
`authority_grant:atrium-resource-feedback` to the exact sorted operation set containing its
existing feedback operation, `reason`, and `append_immutable_records`. The production bootstrap
now accepts only an exact current widened grant or the exact historical singleton grant. The
historical form migrates append-only to sequence 2, preserves its original effective time and
revision, names that exact deterministic prior revision, and returns `migrated`; arbitrary scope,
approval, sequence, prior-history, receipt, lifecycle, or payload changes fail closed before any
write. The other four grant identities and materials remain unchanged.

The same authorized setup call now create-or-verifies the two exact cognition capability heads
and the fixed reasoning/append configuration heads consumed by the production resolver. Existing
heads must match their exact active payload, identity, sequence, approval, and receipt and carry no
fabricated grant receipt entries. The response truthfully projects `created`/`verified` cognition
state and `created`/`verified`/`migrated` grant state.

Focused verification passes 20 authority/cognition tests and the surrounding WS3 regression set
passes 135 tests with the one known pristine-baseline extension-disabled kernel-start test
deselected. The corrected WS0 gate/report suite passes 67 tests. Ruff and diff hygiene pass. A
disposable in-memory SurrealDB at schema v179 confirmed
both production-adapter paths: fresh setup created five grants and four cognition heads then
verified all nine; an exact historical five-grant database returned
`verified, verified, migrated, verified, verified`, retained five grant heads, advanced only the
feedback grant to sequence 2 with its exact prior revision, and created the four cognition heads.

This resolves the prior authority/cognition provisioning gate, but it does **not** complete WS3 or
move J4/J5. The clean journey exposes the next structural gap: the public production flow can
associate an exact Builder session only at `GOAL_SELECTED`, while activation and
`DurableIntelligenceBuildHostComposer` require the session to have traversed the existing
Connection, Ontology, Intelligence, and Briefing Agent stages to `FIRST_BRIEFING_READY` and then
`ACTIVE`. No production API or orchestrator currently drives those stages and their exact human
approval receipts. Without one exact active session the composer correctly withholds
`recorded_sources` and `first_brief`, so the production executor cannot create J4 inventory or the
Markdown-cited J5 Brief. WS0 now reports this blocker instead of the obsolete authority and
first-corpus blockers.

The next packet decision is whether WS3 may add the narrow production local-owner Builder
progression/approval coordinator over the existing agents and state machine. The recommended
shape preserves every existing stage and explicit disposition boundary, exposes only exact
proposal/approval operations needed for the local first run, uses WS0's deterministic provider
through those same strategy ports, and leaves Atrium mounting to WS6. Reordering activation or
bypassing the Builder state machine would be a materially different architecture and is not
authorized by the frozen addendum. No WS4 work, commit, merge, push, GitHub write, tag, package
publish, or release occurred.

## 2026-08-21 continuation — thin host API over the progression coordinators

The frozen addendum-9 proposal/approval operations are now exposed as seven exact local-owner
routes below `/v1/intelligence/builds`: `builder/source/propose`, `builder/source/approve-connect`,
`builder/concept/propose`, `builder/concept/approve`, `builder/intelligence/propose`,
`builder/intelligence/approve`, and `builder/first-brief/prepare`. Each route calls only its
existing coordinator with the production runtime dependency, keeps every coordinator return type
unchanged, and maps denied → 403, not found → 404, conflict/stale/tamper → 409, unavailable → 503,
and strict validation → 422. `approve-connect` is one explicit source-scope owner decision
(`approve_builder_source_scope`) immediately followed by connect using that exact minted receipt;
no approval-only shortcut exists and no other approval is bundled. Response envelopes live in
`core/engine/core/intelligence_builder_host_contracts.py` and carry only the relevant exact
artifact, the reviewed approval when one was made, and the resulting session revision — never a
raw admission or store object. Activation-plan routes are untouched.

Claude Code CLI composed the routes and their contract tests under a bounded prompt; every change
was read and independently verified here. Ten focused API tests drive the real coordinators over
in-memory durable stores through HTTP from `GOAL_SELECTED` to `FIRST_BRIEFING_READY`, prove
approval-before-connect through the minted receipt reference, assert exact response key sets,
exercise 403/404/409/503 on the source routes and 422 on all seven, and confirm rejected input
touches no store and no provider.

Independent verification additionally found two boundary defects in previously accepted WS3
material: the concept-progression, intelligence-progression, and observation-admission host
modules imported `ace.intelligence.contracts.*` directly, and eight WS3 host adapters were missing
from the `tests/test_public_core_boundaries.py` allowlist. Both are repaired without changing
behavior: the hosts validate digests/references with local exact patterns, observation admission
takes `CanonicalJsonValueV1Alpha1` from the public `ace.application.intelligence_agent_contracts`
surface (which already types observation attributes with it and now exports it) and lets that
contract own the bounded canonical size, and the allowlist names the adapters with rationale.

Verification: boundary suite 9 passed with the one known pristine-baseline kernel-start test
deselected; focused WS3 coordinator, strategy, and API sweep 196 passed; Ruff check/format and
`git diff --check` clean. This is local candidate evidence only: no J-step moved, no
installed-artifact run is claimed, WS4 has not started, and nothing was committed, merged, pushed,
tagged, published, or released. The remaining WS3 frontier is composing the existing
activation-plan path so the same durable session reaches `ACTIVE` and the production executor runs.

## 2026-08-21 continuation — activation composition proof and the canonical approval window

With the thin routes in place, a focused composition test
(`tests/test_pi13_ws3_activation_composition.py`) proves how far the public route sequence now
composes without any fabricated authority: the five setup grants and cognition heads are
provisioned through `bootstrap_local_owner_authority`; the bound plan comes from the real installed
Personal Pack artifact; `/approve` records the activation-spec approval; `/session/associate`
derives the `GOAL_SELECTED` session from it; the seven `/builder/...` routes carry the session
through source, concept, intelligence, and first-Brief stages to `FIRST_BRIEFING_READY` with exactly
three selected-provider calls and four separate exact owner approvals; and the existing
`/activation-plan/prepare` and `/activation-plan/approve` reload that session's durable observation
set, intelligence model and disposition, and first Brief, admit the v1alpha2 plan through
`RecordedDomainActivationPlanAuthority`, and advance the session to `ACTIVATION_PENDING`.

`/activation-plan/activate` fails closed. `DomainActivationCompatibilityService` requires the
activation-spec approval's `approved_at` to lie inside `[plan.created_at, plan revision occurred_at]`
and to be a different receipt from the plan's own approval. In the public flow the spec approval is
minted once at J3 and is the receipt that associates the session, while the host plan-approve route
uses the plan-approval instant for both `created_at` and `occurred_at`; the window is therefore
unsatisfiable by construction, the session rests durably at `ACTIVATION_PENDING`, and the composer
correctly withholds `recorded_sources` and `first_brief`. A second test proves the state machine is
not bypassed: an `INTELLIGENCE_MODEL_APPROVED` session cannot prepare or approve a plan (409) and
spends no provider call. The to-`ACTIVE` path is pinned as a strict expected failure so it flips
the moment the gate is resolved.

WS0's J4/J5 rows now name `WS3:canonical_activation_approval_window_unsatisfiable` with the
evidence above; the gate suite passes 67 tests. Candidate options and the recommendation (derive
the plan's `created_at` from the session's durable first revision, which equals the spec approval's
`approved_at`) are recorded in the tracker's current gate for the owner. No activation or approval
semantics were changed; no J-step moved; no installed-artifact run is claimed; WS4 has not started;
nothing was committed, merged, pushed, tagged, published, or released.

## 2026-08-21 continuation — canonical activation window resolved; session reaches ACTIVE

The owner resolved the canonical approval window by anchoring the v1alpha2 plan's `created_at` on
the Builder session's durable start. `IntelligenceBuilderSessionService.load_first` returns the
first durable revision from the same validated chain `load_latest` already reads, and the host
activation-plan prepare/approve routes use that revision's `occurred_at` — the J3 activation-spec
approval's `approved_at`, because `/session/associate` starts the session at it — as the plan's
`created_at`, keeping the request time as the durable read instant and the plan revision's
`occurred_at`. The coordinator's `prepare` distinguishes `evaluated_at` from `created_at` (default
unchanged) and fails closed when asked to read before the window starts. The spec approval and the
plan's own later approval therefore both fall inside `[created_at, occurred_at]` by construction:
no approval is re-minted or bundled, no client value sets the window, and the state machine is
untouched.

Focused composition evidence (`tests/test_pi13_ws3_activation_composition.py`): the public route
sequence reaches `ACTIVE` with three selected-provider calls and four separate owner approvals, the
activation receipt replays identically, the plan's `created_at` equals the session start and the
spec approval time, the preview is a pure function of durable material, and a pre-briefing session
still cannot plan. `tests/test_api_intelligence_builder_activation_plan.py` pins that the host
derives `created_at` from the durable session port and maps a missing session to 404;
`tests/intelligence/test_intelligence_builder_connect.py` covers `load_first`. Combined focused
sweep 392 passed (1 known pristine-baseline test deselected); repo-wide Ruff check/format and diff
hygiene clean.

This completes the WS3 composition in focused proof only. J4/J5 remain blocked in WS0 on the lane
executing the walk against installed artifacts and the ephemeral SurrealDB; WS4 has not started;
nothing was committed, merged, pushed, tagged, published, or released.
