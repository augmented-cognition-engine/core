# ACE 1.1 Code Intelligence — Atrium UX/runtime handoff

Frozen: 2026-08-16

Control tower: task `01a001e7-e9da-7eb1-9b64-730fcd75d463`

Source product direction: `ACE_Product_Interface_Direction_v1.docx` (11/11 pages reviewed and rendered during the UX track)

Handoff checkpoint: **host-first-run extension reconciled and frozen for clean-candidate construction on 2026-08-16**. The candidate component, contract assumptions, limitations, exact paths, responsive artifacts, and verification evidence below supersede the earlier packet where they overlap.

## Authority and acceptance status

This is a contributor packet for construction of a new, clean official ACE 1.1 Code Intelligence integrated candidate. The superseded local working title **ACE Core 1.1.0 — Living Intelligence Interface** is not a release declaration. Nothing in this worktree has been committed, merged, pushed, tagged, or published. Separate-worktree tests do not establish integrated release acceptance.

The accepted product direction remains A+C: a restrained Living Brief hierarchy with an exact evidence/trust spine, without excessive editorial framing, a graph home, generic chat home, agent canvas, connector-count vanity, or decorative AI effects.

## Included candidate scope

- Five domain surfaces: Overview (the answer), Explore (the world), Build (the intelligence model), Operate (the trust layer), and Consumers (interfaces out).
- Legacy route reconciliation: Intelligence/Opportunities → Overview or Explore context; Agents → subordinate Build detail; Connections → Operate/source readiness; Strategy → Consumers/downstream use; Investigation Board remains a downstream interface, not a sixth intelligence surface.
- Human-reviewed domain intent → exact proposed plan → binding review → append-only approval → exact initial Builder-session association.
- Authoritative host-first-run extension: configured/fixed bypass; one Personal / Shared server / Dedicated appliance choice for genuinely unconfigured hosts; detected model plan as status; immediate Atrium entry with nonblocking runtime readiness.
- Exact activation-plan preview and a separate owner authorization once an independently durable `FIRST_BRIEFING_READY` revision exists.
- Living Brief, focused entity exploration, focused Why?/evidence/unknowns, challenge/correction proposal receipt, honest Domain Health, Pack/Consumers capability posture, and responsive/accessibility/icon-system closure.
- World and Market as release-ready domain experiences at the contract ceiling; Custom Intelligence remains proposal-only Preview.
- Provider neutrality and explicit provider-subscription ≠ provider API credential truth.

## Explicitly excluded

- Existing RAG/search behavior is unchanged and was not edited as part of this UX program.
- No second activation, handoff, agent, graph, connector, Pack, correction, subscription, or outcome framework.
- No giant graph, graph home, generic chat home, agent canvas, universal connector catalog, or downstream execution engine.
- No inferred health, readiness, delivery, coverage, freshness, confidence, resolution, or maintenance state.
- No blanket MODEL self-approval and no client-authored Builder identity, runtime progress, approval time, authority, or source readiness.
- No production mutation in the Code task's worktree and no local release publication.
- No claim that the unmounted host-first-run candidate provides production mode persistence, download orchestration, model readiness, Settings mutation, appliance conversion, or remote exposure.

## Host first run → existing Atrium onboarding

The authoritative extension is frozen in [`../ace-host-first-run-onboarding-v1.md`](../ace-host-first-run-onboarding-v1.md). It is a thin host gate, not a second onboarding framework:

```text
configured or administrator-fixed host ───────────────┐
unconfigured host → detect → one mode choice → persist ├→ Atrium
                                                      └→ existing “What should ACE understand?” journey

background only: recommended model download → loaded → real generation smoke test
```

Candidate UI paths:

- `core/ui/canvas/src/app/firstRun/HostFirstRun.tsx`
- `core/ui/canvas/src/app/firstRun/HostFirstRun.test.tsx`
- `core/ui/canvas/src/design/shadcn/ui/radio-group.tsx`

Exact extension-only design/handoff paths:

- `docs/design/ace-host-first-run-onboarding-v1.md`
- `docs/design/atrium-product-ux-directions-v1/README.md`
- `docs/design/atrium-product-ux-directions-v1/brief-completion-ledger.md`
- `docs/design/atrium-product-ux-directions-v1/runtime-completion-roadmap.md`
- `docs/design/atrium-product-ux-directions-v1/code-intelligence-control-tower-handoff.md`
- `docs/design/atrium-product-ux-directions-v1/mockups.js`
- `docs/design/atrium-product-ux-directions-v1/mockups.css`
- `docs/design/atrium-product-ux-directions-v1/implementation/atrium-host-first-run-1440x960.png`
- `docs/design/atrium-product-ux-directions-v1/implementation/atrium-host-first-run-390x844.png`
- `docs/design/atrium-product-ux-directions-v1/implementation/atrium-host-runtime-arrival-1440x960.png`

The component is deliberately unmounted. This worktree has no accepted early host projection, durable operating-mode persistence/ownership API, Settings mutation, resumable download manager, or exact generation-smoke receipt. Routing it with fixtures would turn design evidence into fabricated production state.

Control-tower contract assumptions:

1. read one canonical `configured | admin_fixed | unconfigured` host projection before Atrium routing;
2. persist one exact user-owned mode under authenticated local-owner authority and re-read canonical state; identical request replay is stable and crossed material fails closed;
3. administrator/environment ownership is explicit and ordinary-user immutable;
4. local-only exposure is default and remote serving requires a separate operator action;
5. readiness independently reports ACE usable now, exact resumable download state, model loaded state, and a real generation smoke-test result;
6. user-owned mode changes later through Settings without reinstalling; and
7. Dedicated appliance conversion is a separate reviewed flow with no universal-first-run boot/login/hostname/network/cleanup mutations.

Reuse the relevant detection, Compose-v2/system-vs-user ownership, service-start, and idempotent local-owner bootstrap seams in `core/engine/cli/commands/setup.py`. A health endpoint is insufficient readiness evidence. Integration requires a real inference smoke test plus safe interruption, offline, low-disk, checksum, load, and restart recovery behavior. A no-login appliance experience requires a supported renewable local/device credential or explicit product auth mode, not a restart workaround.

## Reviewed-build → Builder-session seam

### Implemented contract

`POST /v1/intelligence/builds/session/associate`

Authenticated request material:

- `bound_plan`: the exact `BoundIntelligenceBuildPlanV1Alpha1` returned by `/bind`;
- `approval_receipt_ref`: the exact receipt reference returned by `/approve`.

The server:

1. derives verified actor/product context from the signed user;
2. reloads the immutable `ReviewedIntelligenceActivationApprovalV1Alpha1` artifact by receipt reference;
3. matches actor, product, bound-plan ID/digest, activation specification ID/digest, execution request ID/digest, and approval subject;
4. derives the existing Builder `correlation_id` from `bound_plan.execution_request_id` and `goal_ref` from `bound_plan.binding_request.plan.request.outcome_id`;
5. calls the existing `IntelligenceBuilderSessionService.start` using the stored approval time;
6. records or replays only the exact sequence-1 `GOAL_SELECTED` revision.

The client sends no session ID, goal, timestamp, later stage, artifact, source state, or health state. Atrium parses the returned exact revision, requires `goal_selected` with a durable exact revision, displays that state, and stops before activation-plan preparation or `/start`.

### Error assumptions

- 401: missing/expired authentication, with the existing client refresh-once behavior.
- 403: verified caller/material does not match the stored reviewed approval or lacks the fixed owner authority.
- 409: immutable replay conflicts with different exact material.
- 503: record/session storage or host association runtime unavailable, or a malformed/non-exact association result reaches the client.

The association route does not claim natural 404 discovery semantics because the stored receipt is authorization material and missing/crossed material is deliberately not disclosed as a public existence oracle.

### What remains after association

The new seam does not progress the Builder. Real Connection/source admission, Ontology/concept-model review, Intelligence-model review, first cited Brief production, blocked/retry work, and transition to `FIRST_BRIEFING_READY` still require their existing runtime services/agents and human/Core dispositions. Only after that exact later revision exists may the existing activation-plan coordinator prepare a plan and solicit the second human authorization.

## Human and delegated review boundary

Interactive human review is the default and current supported experience:

- Decision 1 validates the reviewed system inputs and records the specification approval.
- Decision 2 separately authorizes the admitted activation plan and continuous maintenance.

A future integrated state may display delegated service review only when the control tower supplies a contract-backed service principal, point-of-use authority, exact reviewed subject/material, and immutable review/approval receipt. The UI may label that literal receipt as delegated review; it must not translate MODEL execution, a model response, or absence of human input into approval. Reuse the one authority/receipt system and never infer delegated status from actor naming or runtime stage.

## Customer-visible limitations and decision ledger

| Decision | Included truth | Intentionally rejected |
|---|---|---|
| A+C visual direction | Calm current-state Brief plus rigorous evidence/health spine | An editorial newsroom, generic SaaS dashboard, or decorative brain/AI animation |
| Overview vs Explore | Overview prioritizes current answer, material movement, signals, unknowns, and attention; Explore is question/search-first and opens focused relationships | A graph as home, a browse-first entity warehouse, or equal-weight four-part cards |
| Why? | Understandable conclusion → direct evidence → unknowns, with exact references and a separate operator depth | Raw traces as the primary explanation or evidence sharing a source treated as direct derivation |
| Domain Health | Eight visible dimensions with literal supported/unsupported basis; attention first, supported next, unmeasured subordinate | Composite health score, proxy percentages, or status-color decoration |
| Icons/color | One Lucide family; neutral hierarchy; semantic color only for literal states; shield reserved for Operate/trust | Repeated shield glyphs, mixed icon families, or accent colors masquerading as status |
| Host first run | Configured/fixed bypass; one explicit three-mode choice; detected plan as status; direct Atrium entry | Long survey, tutorial carousel, provider interrogation, or a second onboarding framework |
| Host readiness | Usable/downloaded/loaded/generated are independent literal states; exact progress and recoverable failures remain visible | Blocking on a large download or presenting process/health state as successful generation |
| Host safety | Local-only by default; user mode changes later; appliance conversion and remote exposure are separate reviewed actions | Silent exposure or boot/login/hostname/cleanup mutations from universal first run |
| New-build activation | Exact human approval then server-derived/replayed `GOAL_SELECTED`, followed by honest waiting | Spinner/timer progress, client-generated session identity, or approval implying first-Brief readiness |
| Custom Intelligence | Proposal-only Preview | Pretending a universal custom runtime, source catalog, or executor exists |
| Consumers | Exact available/contract-only/not-exposed posture and record-only subscription lifecycle | Stream/webhook/digest delivery without destination, receipt, retry, and provenance-return contracts |

Customer-visible limitations that remain:

- Live SurrealDB has not exercised the complete new-build association → progression → activation → resource-state chain.
- World/Market installed executors, exact customer source providers/credentials, and retry-worker completion remain deployment dependencies.
- Domain Health supports only values the current resource and activation contracts prove; unsupported dimensions remain visible as unsupported.
- Resource-state aggregation beyond one closed 200-record page requires an exact multi-page closure contract.
- Pack customization, upgrade discovery/compatibility, and rollback mutation are not exposed; exact activation history read is available by activation key.
- Consumer `immediate`/`digest`, stream, and webhook delivery remain unexposed; there is no general downstream Outcome API.
- Fixed local-owner authority is the current approval ceiling; multi-principal/delegated review is an integration dependency.
- Host operating-mode persistence/ownership, Settings mutation, resumable download orchestration, exact load/smoke receipts, renewable device credentials, and the separate appliance-conversion workflow are not implemented in this worktree.

## Verification evidence

Current separate-worktree results:

| Layer | Result | Scope |
|---|---:|---|
| Reviewed activation/session backend | 42 passed | association, approval reload/matching, activation-plan coordinator, resource-state projection |
| Public boundary/auth/owner authority | 20 passed | host-adapter allowlist, authentication separation, fixed local-owner authority |
| Ruff | passed | `intelligence_builds.py`, activation authority, focused association tests |
| Focused Canvas | 42 passed | build API client and onboarding component, including no-session fail-closed and exact `GOAL_SELECTED` association |
| Host first run focused | 16 passed | 12 projection/choice/readiness tests plus 4 no-inline-form design-enforcement tests |
| Full Canvas | 54 files / 424 passed | full Vitest suite, including the unmounted host-first-run candidate |
| Production build | passed | TypeScript plus Vite production build; existing large-chunk warning only |
| Chromium Atrium packet | 8 passed / 1 skipped | desktop, 768×1024, 390×844, entity Explore, Why?, Domain Health, lifecycle disclosures, error/degraded/loading states, Custom Preview, first-Brief-ready state, keyboard/current-page/reduced-motion assertions; external-domain test skipped because its backend was unavailable |
| Focused capture | 1 passed | first-Brief-ready desktop and 768×1024 screenshots |
| Host static visual packet | inspected / exact dimensions | 1440×960 choice, 390×844 choice, and 1440×960 nonblocking Atrium arrival; no production browser route claimed |
| Diff hygiene | passed | `git diff --check` |

The browser packet uses mocked HTTP resources and does not prove live SurrealDB or production adapters. The host-first-run candidate is not mounted, so its three inspected artifacts are not browser E2E acceptance. A later full capture-mode rerun lost its local Vite server after two large screenshots and produced seven capture-only failures; the same 8-test packet passed normally immediately beforehand, and the focused capture rerun passed. Treat this as capture-harness instability and do not count it as integrated visual acceptance.

No automated axe audit was added. Accessibility evidence is the semantic component/enforcement coverage plus browser assertions for keyboard skip navigation, focus restoration, current-page state, document titles, reduced motion, accessible busy/name changes, and icon hiding. The control tower should run its integrated accessibility gate.

The repository-wide backend suite was not run for this packet; the focused and boundary suites above are the exact evidence available.

## Live-Surreal status and runtime gaps

Status: **not run** for this frozen packet. Backend focused tests use in-memory record/session/governed-state doubles. Browser tests use mocked HTTP routes.

Required integrated runtime evidence:

1. unconfigured host detection → exact mode persistence → restart/re-read bypass, plus administrator-fixed bypass/immutability;
2. interrupted/resumed model download → exact load state → real generation smoke receipt, with offline and low-disk failure evidence;
3. `/prepare` → `/bind` → human `/approve` → `/session/associate` against live SurrealDB;
4. identical restart replay returns the same immutable session revision with `replayed=true` and no duplicate record;
5. crossed product/actor/bound/execution/spec/approval material fails closed;
6. real progression from `GOAL_SELECTED` through source/model stages with exact durable revision chain;
7. `FIRST_BRIEFING_READY` handoff → activation-plan prepare → separate approval → activate → existing `/start`;
8. authorized resource read → literal live Domain Health projection with complete-page closure;
9. exact blocked revision → governed retry → later durable outcome.

## Current visual/reference lock

Refero style lock:

- `https://styles.refero.design/style/e5f5f8cf-e68d-4ed1-bbf5-6b67569af648`
- `https://styles.refero.design/style/d5307f56-76de-4d13-9741-f969c42e9aa5`

The original three reference-locked comparison directions remain in `artifacts/`; A+C is the selected direction. Current implementation screenshots remain in `implementation/`, including:

- `atrium-host-first-run-1440x960.png`, `atrium-host-first-run-390x844.png`, and `atrium-host-runtime-arrival-1440x960.png` for the authoritative pre-Atrium extension and nonblocking arrival;
- `atrium-living-brief-overview.png`, `atrium-living-brief-1280x800.png`, `atrium-living-brief-768x1024.png`, `atrium-living-brief-narrow.png`;
- `atrium-explore-answer.png`, `atrium-explore-answer-narrow.png`, `atrium-explore-why.png`;
- `atrium-operate.png`, `atrium-build.png`, `atrium-consumers.png`;
- `atrium-exact-plan-review.png`, `atrium-exact-plan-effects.png`, `atrium-activation-readiness.png`;
- `atrium-live-builder-ready.png`, `atrium-entity-intelligence.png`, `atrium-entity-intelligence-narrow.png`;
- explicit loading, unavailable, refresh-failed, degraded, and Custom Preview states.

Disposable current capture outputs are under `core/ui/canvas/test-results/` and are not candidate source assets.

Host-first-run pattern roles are reference-locked to Tailscale-like infrastructure clarity, OpenAI Developers-like technical restraint, Typeform-like unmistakable choice cards, and Miro-like one-question focus. These roles do not replace A+C tokens or components. Long account surveys, tutorial carousels, generic AI gradients, remote-enable shortcuts, and a second visual vocabulary are explicitly rejected.

## Required path reconciliation

### Directly overlapping paths

| Path | This track's semantic change | Reconciliation instruction |
|---|---|---|
| `core/engine/api/main.py` | Mounts the record-only Intelligence subscription lifecycle router | Rebuild router imports/mount order in the clean candidate; retain only routes accepted by the control tower and verify OpenAPI collisions/auth boundaries |
| `core/engine/core/intelligence_resource_plane.py` | Adds `query_intelligence_resource_page_with_query` so resource-state enrichment can reuse the exact authorized query plus page | Reconcile with Code Intelligence resource-plane changes; preserve one authorization/read boundary and avoid a parallel projection reader |
| `core/ui/canvas/src/app/ext/defaults/KernelNav.tsx` | Replaces legacy labels with five domain surfaces, one icon family, current-domain context, `aria-current`, stable ACE label, and “Interfaces out” | Preserve Code navigation additions without restoring Agents/Connections as peer domain surfaces; keep Investigation Board downstream |
| `tests/test_public_core_boundaries.py` | Extends the explicit host-adapter allowlist for activation, activation-plan, resource-state, feedback, and subscription adapters | Union intentional adapters in the clean candidate, then re-audit imports; do not copy the allowlist mechanically |

### Adjacent semantic overlaps even where filenames differ

- Build plan/approval/session: `ace/application/intelligence_builder.py`, `ace/application/intelligence_builder_activation.py`, `ace/application/intelligence_build_host.py`, `core/engine/api/intelligence_builds.py`, `core/engine/core/intelligence_build.py`, `core/engine/core/intelligence_build_plan.py`, `core/engine/core/intelligence_activation_authority.py`, `core/engine/core/intelligence_builder_activation_plan.py`.
- Resource/query/health: `ace/application/intelligence_resource_plane.py`, `ace/application/intelligence_resource_projection.py`, `ace/application/intelligence_system_projection.py`, `core/engine/api/intelligence_resources.py`, `core/engine/core/intelligence_build_resource_state.py`, and the Canvas resource/build clients.
- Authority/public boundaries: `core/engine/core/local_owner_authority.py`, `core/engine/api/auth_routes.py`, `ace/application/__init__.py`, public contract exports, and public-boundary tests.
- UX/session projection: `IntelligenceOS.tsx`, `OnboardingPreview.tsx`, `onboardingModel.ts`, `onboardingJourney.ts`, and their tests/E2E routes.
- Host-first-run semantics: `core/engine/cli/commands/setup.py`, local-owner bootstrap/auth composition, the future early app-routing gate (likely `main.tsx` or its accepted replacement), Settings mode mutation, and the existing Atrium onboarding entry. The candidate does not edit those production seams; reconcile detection/persistence/readiness there rather than copying fixture state into `IntelligenceOS.tsx`.

## Exact dirty-path manifest for candidate review

The following is the cumulative UX/runtime track manifest at freeze time. `.pnpm-store/` is disposable local package cache and explicitly excluded.

```text
ace/application/__init__.py
ace/application/decision_feedback.py
ace/application/domain_activation_plan.py
ace/application/domain_activation_plan_contracts.py
ace/application/installed_pack_artifacts.py
ace/application/intelligence_build_host.py
ace/application/intelligence_builder.py
ace/application/intelligence_builder_activation.py
ace/application/intelligence_resource_feedback.py
ace/application/intelligence_resource_plane.py
ace/application/intelligence_resource_projection.py
ace/application/intelligence_system_projection.py
ace/application/monitoring.py
ace/core/state.py
ace/intelligence/contracts/__init__.py
ace/intelligence/contracts/feedback.py
ace/intelligence/contracts/resource_feedback.py
ace/intelligence/contracts/system_projection.py
core/engine/api/auth_routes.py
core/engine/api/intelligence_builds.py
core/engine/api/intelligence_catalog.py
core/engine/api/intelligence_resources.py
core/engine/api/intelligence_subscriptions.py
core/engine/api/main.py
core/engine/core/governed_state.py
core/engine/core/installed_intelligence_catalog.py
core/engine/core/intelligence_activation_authority.py
core/engine/core/intelligence_build.py
core/engine/core/intelligence_build_plan.py
core/engine/core/intelligence_build_resource_state.py
core/engine/core/intelligence_builder_activation_plan.py
core/engine/core/intelligence_resource_feedback.py
core/engine/core/intelligence_resource_plane.py
core/engine/core/intelligence_subscriptions.py
core/engine/core/local_owner_authority.py
core/ui/canvas/playwright.config.ts
core/ui/canvas/src/api/intelligenceBuildsApi.test.ts
core/ui/canvas/src/api/intelligenceBuildsApi.ts
core/ui/canvas/src/api/intelligenceCatalogApi.test.ts
core/ui/canvas/src/api/intelligenceCatalogApi.ts
core/ui/canvas/src/api/intelligenceResourcesApi.test.ts
core/ui/canvas/src/api/intelligenceResourcesApi.ts
core/ui/canvas/src/app/atrium/AskAce.tsx
core/ui/canvas/src/app/atrium/DomainHealthRail.test.tsx
core/ui/canvas/src/app/atrium/DomainPackConsumers.test.tsx
core/ui/canvas/src/app/atrium/DomainPackConsumers.tsx
core/ui/canvas/src/app/atrium/EntityIntelligence.test.tsx
core/ui/canvas/src/app/atrium/EntityIntelligence.tsx
core/ui/canvas/src/app/atrium/IntelligenceOS.tsx
core/ui/canvas/src/app/atrium/LivingIntelligence.challenge.test.tsx
core/ui/canvas/src/app/atrium/LivingIntelligence.test.ts
core/ui/canvas/src/app/atrium/LivingIntelligence.tsx
core/ui/canvas/src/app/atrium/OnboardingPreview.test.tsx
core/ui/canvas/src/app/atrium/OnboardingPreview.tsx
core/ui/canvas/src/app/atrium/ResourceCard.test.tsx
core/ui/canvas/src/app/atrium/ResourceCard.tsx
core/ui/canvas/src/app/atrium/atriumIcons.test.ts
core/ui/canvas/src/app/atrium/atriumIcons.ts
core/ui/canvas/src/app/atrium/entityIntelligenceModel.test.ts
core/ui/canvas/src/app/atrium/entityIntelligenceModel.ts
core/ui/canvas/src/app/atrium/onboardingJourney.test.ts
core/ui/canvas/src/app/atrium/onboardingJourney.ts
core/ui/canvas/src/app/atrium/onboardingModel.ts
core/ui/canvas/src/app/atrium/trustProjection.test.ts
core/ui/canvas/src/app/atrium/trustProjection.ts
core/ui/canvas/src/app/atrium/useIntelligenceProductCatalog.ts
core/ui/canvas/src/app/atrium/useIntelligenceResources.test.tsx
core/ui/canvas/src/app/ext/defaults/KernelNav.tsx
core/ui/canvas/src/app/firstRun/HostFirstRun.test.tsx
core/ui/canvas/src/app/firstRun/HostFirstRun.tsx
core/ui/canvas/src/design/shadcn/ui/radio-group.tsx
core/ui/canvas/src/index.css
core/ui/canvas/tests/e2e/atrium-domain-resource-page.spec.ts
core/ui/canvas/tests/e2e/atrium-entity-intelligence.spec.ts
core/ui/canvas/tests/e2e/atrium-intelligence-os.spec.ts
docs/design/atrium-consumer-stream-webhook-runtime-audit-v1.md
docs/design/ace-host-first-run-onboarding-v1.md
docs/design/atrium-domain-pack-consumers-p1.md
docs/design/atrium-entity-intelligence-explore-v1.md
docs/design/atrium-live-domain-health-projection-v1.md
docs/design/atrium-product-ux-directions-v1/README.md
docs/design/atrium-product-ux-directions-v1/brief-completion-ledger.md
docs/design/atrium-product-ux-directions-v1/code-intelligence-control-tower-handoff.md
docs/design/atrium-product-ux-directions-v1/mockups.css
docs/design/atrium-product-ux-directions-v1/mockups.html
docs/design/atrium-product-ux-directions-v1/mockups.js
docs/design/atrium-product-ux-directions-v1/runtime-completion-roadmap.md
docs/design/atrium-system-projection-contract-v1.md
docs/design/atrium-trust-layer-contract-audit-v1.md
docs/design/atrium-world-market-onboarding-v1.md
docs/evidence/atrium-reviewed-activation-approval.md
tests/intelligence/test_domain_activation_plan_admission.py
tests/intelligence/test_intelligence_builder_activation_plan_coordinator.py
tests/intelligence/test_intelligence_resource_feedback.py
tests/intelligence/test_outcome_provenance_return.py
tests/intelligence/test_system_projection_contracts.py
tests/intelligence/test_system_resource_health_projection.py
tests/test_api_intelligence_build_plan.py
tests/test_api_intelligence_build_resource_state.py
tests/test_api_intelligence_builder_activation_plan.py
tests/test_api_intelligence_builds.py
tests/test_api_intelligence_catalog.py
tests/test_api_intelligence_resource_feedback.py
tests/test_api_intelligence_subscriptions.py
tests/test_auth_separation.py
tests/test_governed_state_substrate.py
tests/test_installed_pack_artifacts.py
tests/test_intelligence_activation_authority.py
tests/test_local_owner_authority.py
tests/test_public_core_boundaries.py
```

Exact visual artifact manifest (also untracked candidate additions; copy selectively):

```text
docs/design/atrium-product-ux-directions-v1/artifacts/a-living-brief-explore-why-1440x960.png
docs/design/atrium-product-ux-directions-v1/artifacts/a-living-brief-narrow-390x844.png
docs/design/atrium-product-ux-directions-v1/artifacts/a-living-brief-onboarding-1440x960.png
docs/design/atrium-product-ux-directions-v1/artifacts/a-living-brief-overview-1440x960.png
docs/design/atrium-product-ux-directions-v1/artifacts/b-evidence-ledger-explore-why-1440x960.png
docs/design/atrium-product-ux-directions-v1/artifacts/b-evidence-ledger-onboarding-1440x960.png
docs/design/atrium-product-ux-directions-v1/artifacts/b-evidence-ledger-overview-1440x960.png
docs/design/atrium-product-ux-directions-v1/artifacts/c-command-atlas-explore-why-1440x960.png
docs/design/atrium-product-ux-directions-v1/artifacts/c-command-atlas-onboarding-1440x960.png
docs/design/atrium-product-ux-directions-v1/artifacts/c-command-atlas-overview-1440x960.png
docs/design/atrium-product-ux-directions-v1/implementation/atrium-activation-readiness.png
docs/design/atrium-product-ux-directions-v1/implementation/atrium-build.png
docs/design/atrium-product-ux-directions-v1/implementation/atrium-canonical-system-projection.png
docs/design/atrium-product-ux-directions-v1/implementation/atrium-consumers.png
docs/design/atrium-product-ux-directions-v1/implementation/atrium-custom-preview-choice.png
docs/design/atrium-product-ux-directions-v1/implementation/atrium-custom-preview-complete.png
docs/design/atrium-product-ux-directions-v1/implementation/atrium-custom-preview-review-narrow.png
docs/design/atrium-product-ux-directions-v1/implementation/atrium-custom-preview-review.png
docs/design/atrium-product-ux-directions-v1/implementation/atrium-degraded-operate.png
docs/design/atrium-product-ux-directions-v1/implementation/atrium-degraded-overview.png
docs/design/atrium-product-ux-directions-v1/implementation/atrium-entity-intelligence-narrow.png
docs/design/atrium-product-ux-directions-v1/implementation/atrium-entity-intelligence.png
docs/design/atrium-product-ux-directions-v1/implementation/atrium-exact-plan-effects.png
docs/design/atrium-product-ux-directions-v1/implementation/atrium-exact-plan-review.png
docs/design/atrium-product-ux-directions-v1/implementation/atrium-explore-answer-narrow.png
docs/design/atrium-product-ux-directions-v1/implementation/atrium-explore-answer.png
docs/design/atrium-product-ux-directions-v1/implementation/atrium-explore-why.png
docs/design/atrium-product-ux-directions-v1/implementation/atrium-host-first-run-1440x960.png
docs/design/atrium-product-ux-directions-v1/implementation/atrium-host-first-run-390x844.png
docs/design/atrium-product-ux-directions-v1/implementation/atrium-host-runtime-arrival-1440x960.png
docs/design/atrium-product-ux-directions-v1/implementation/atrium-live-builder-ready.png
docs/design/atrium-product-ux-directions-v1/implementation/atrium-living-brief-1280x800.png
docs/design/atrium-product-ux-directions-v1/implementation/atrium-living-brief-768x1024.png
docs/design/atrium-product-ux-directions-v1/implementation/atrium-living-brief-narrow.png
docs/design/atrium-product-ux-directions-v1/implementation/atrium-living-brief-overview.png
docs/design/atrium-product-ux-directions-v1/implementation/atrium-loading.png
docs/design/atrium-product-ux-directions-v1/implementation/atrium-operate.png
docs/design/atrium-product-ux-directions-v1/implementation/atrium-refresh-failed.png
docs/design/atrium-product-ux-directions-v1/implementation/atrium-unavailable.png
```

## Control-tower construction sequence

1. Rebuild the four directly overlapping paths in the clean candidate before copying adjacent adapters.
2. Reconcile public exports/authority once, then admit the reviewed-build association route and its exact tests.
3. Construct one early host projection/mode-persistence boundary by adapting the existing setup/detection/local-owner seams; add exact API/unit tests before mounting the host-first-run candidate.
4. Add resumable download plus exact loaded/generation-smoke projection and Settings mutation; keep appliance conversion and remote exposure separate.
5. Integrate the Canvas host gate and existing Atrium API/client/onboarding association while preserving human-default review copy and the direct first-real-outcome handoff.
6. Run live-Surreal association/replay/cross-scope tests before enabling the new-build UI in an accepted integrated state.
7. Run full backend/public-boundary, Canvas, host-first-run/Atrium browser responsive, accessibility, interruption/resume, offline/low-disk, and visual-regression gates in the integrated worktree.
8. Accept, revise, or reject each broader UX/runtime slice independently; do not infer acceptance from this cumulative dirty manifest.
