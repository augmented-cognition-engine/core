# ACE 0.7E Domain Packs + Activation work packet (v1)

**Status:** Phase 1 additive implementation candidate. This packet is stacked on the 0.7C Map
head `e1f6492db2417cbeccee14c04c5803ba1502afa6`. The separate 0.7D Watch + Brief lane is still in
progress. This packet does not integrate unpublished 0.7D code, claim independent World/Market
proof, close issue #39, or declare 0.7.0 ready.

**Control-tower boundary accepted:** 2026-08-11. The accepted additive v1alpha2 activation-plan
seam must preserve every v1alpha1 Domain Activation identity and receipt unchanged.

## Outcome and phase boundary

The 0.7E outcome is that exact approved onboarding proposals can become a separately authorized
Domain Activation, and two materially different external Domain Packs can reproduce the same
Core + Intelligence API without platform domain nouns or forks.

Work is divided into two phases:

1. **Phase 1 — independent foundation:** audit 0.7A–0.7C, freeze this packet, add the sibling exact
   activation-plan contract and admission seam, stabilize lifecycle compatibility, define
   acceptance fixtures and the two-consumer packet, and prove focused restart/rollback behavior.
2. **Phase 2 — exact 0.7D integration:** only after the control tower supplies the completed 0.7D
   branch and commit, consume its approved Intelligence Agent and Briefing Agent handoffs and bind
   them to runtime Monitors, Subscriptions, Shifts, and canonical Brief resources.

0.7D owns separate proposal/preview contracts, immutable edit and approval, a cited provider-free
first Brief preview, and restart-stable identities. Its Brief is deliberately inert and
pre-activation. 0.7E owns conversion to activation-bound runtime resources, activation authority,
compatibility, upgrade/rollback, and external World/Market convergence. Phase 1 must not invent
temporary runtime resources as substitutes for the unpublished 0.7D contracts.

## Stack and reuse audit

| Layer | Exact current seam | 0.7E treatment |
|---|---|---|
| 0.7A schema/compiler | Stable manifest v1, compiler/runtime v1, declared compatibility ranges, deterministic Pack IR and structured diagnostics | Reuse unchanged. Admission re-negotiates current host compatibility instead of trusting a previously prepared plan. |
| 0.7A conformance | `run_domain_pack_conformance`, exact compilation and fixture identities, supported/deprecated status, stable receipt | Reuse unchanged. v1alpha2 admission requires exact passing receipt bodies for both stable and documented prior-window packs. |
| 0.7A activation spec | `DomainActivationSpecV1` v1alpha1 binds Pack IR, overlay, compilation, capabilities, authorities, and conformance references | Embed and independently revalidate unchanged. Do not add, alias, or reinterpret fields. |
| Existing v1alpha1 activation | `DomainActivationRevisionV1` and `DomainActivationAdmissionService` resolve approval against `spec_id` and commit an opaque Core revision | Preserve unchanged for compatibility. It cannot satisfy 0.7E exact-plan approval and is not silently upgraded. |
| Core authority/state | `CoreAuthorityResolver`, optimistic governed-state head, append-only revision, atomic commit and immutable commit receipt | Reuse unchanged. The sibling envelope sets `approval_subject_ref` to the exact v1alpha2 plan ID. Core remains domain-neutral. |
| 0.7B Connect | Exact source-scope/profile proposals and approved source-profile handoff | Consume only in Phase 2 through the cumulative exact handoff chain. No credentials or connector execution enter a pack or plan. |
| 0.7C Map | Exact cited concept-model proposal/disposition and approved handoff | Consume only in Phase 2. No ontology mutation or pack generation occurs in this independent packet. |
| 0.7D Watch + Brief | Separate planned intelligence-model and first-Brief preview handoffs | Dependency only. Do not import unpublished contracts or duplicate their proposals/previews. |
| Monitoring/subscriptions/live bridge | Existing owner-governed monitor, subscription, Shift, Brief, runtime-use, and Core persistence seams | Phase 2 composes them after exact activation; it does not replace their receipts or grant activation authority to packs. |

### Exact conflict found and resolved

The existing v1alpha1 admission envelope and authority lookup hard-code `spec_id` as the approval
subject. The 0.7E dispatch requires approval over the separate immutable activation-plan identity.
No v1alpha1 field could preserve that plan without changing historical identities.

The accepted resolution is a sibling path:

- `ace.application.intelligence-activation-plan/v1alpha2` is the exact approval subject;
- `ace.intelligence.domain-activation-revision/v1alpha2` durably embeds that plan and its unchanged
  v1alpha1 activation specification;
- `DomainActivationPlanAdmissionService` admits only v1alpha2 history and rejects mixed
  v1alpha1/v1alpha2 heads pending an explicit future migration packet; and
- the old contracts, service, payload contract, identities, and receipts remain byte-compatible.

No Core receipt field learns an onboarding, monitor, Brief, World, or Market noun. Core continues
to store an opaque payload and exact plan subject reference.

## Exact plan material

The v1alpha2 plan content-addresses and preserves:

- lifecycle action: initial activation, upgrade, suspension, reactivation, rollback, or retirement;
- exact embedded `DomainActivationSpecV1.spec_id` and `sha256:<spec_hash>`;
- closed requested effect set and digest;
- exact requested capability-binding material and digest;
- exact requested authority-binding material and digest;
- exact expected current activation head;
- for rollback, the exact earlier active revision ID and digest;
- plan creation time; and
- the derived immutable plan ID and digest.

The v1alpha2 revision separately preserves the approved disposition, approval receipt reference,
actor, occurrence time, plan body, state, lineage, revision identity, and revision digest. The Core
commit receipt binds the same revision material and contains the resolved approval whose subject is
the exact plan ID.

`ace.application.domain-activation-commit-reference/v1alpha2` exposes only stable opaque plan,
revision, and Core commit-receipt coordinates for reference-only downstream lineage. It is marked
`historical_reference` and `live_authority = false`. A historical approval or reference can never
authorize present activation, upgrade, suspension, reactivation, rollback, runtime use, or another
effect. Each of those operations still requires its own current plan, approval, compatibility,
conformance, authority, and head validation. This gives the later 0.7F AM1 lane stable coordinates
without making 0.7E depend on AM0 implementation.

Serialized lineage coordinates must be resolved with `validate_activation_commit_reference`
against the exact committed tuple before use. The contract is not a bearer token: forged product
scope, state, plan, revision, receipt, digest, or `live_authority` material fails closed, as do
non-committed input and a commit receipt that fails its own derived-identity revalidation.

Any changed spec, effect, capability, authority, lifecycle action, expected head, rollback target,
or time creates a new plan identity and requires a new approval. The original activation approval
does not authorize upgrade, suspension, reactivation, rollback, or retirement.

## Compatibility matrix

| Prepared/persisted material | v1alpha1 admission | v1alpha2 exact-plan admission | Result |
|---|---:|---:|---|
| Existing v1alpha1 spec + v1alpha1 revision | yes, unchanged | no | Existing compatibility and receipts are preserved. |
| Existing v1alpha1 persisted head + proposed v1alpha2 revision | unchanged head remains readable | no | Fail closed as mixed history; migration is separate future work. |
| v1alpha2 plan/revision embedding exact v1alpha1 spec | no | yes | Intended 0.7E path. Approval subject is plan ID. |
| Stable manifest v1, compiler/runtime v1, passing exact current receipt | existing stable behavior | yes | Supported. |
| Documented prior manifest v1alpha1 window with matching deprecated receipt | existing historical behavior | yes | Deprecated but accepted while the 0.7A window remains open. |
| Migration-required or rejected manifest | no live effect | no | Fail before authority resolution or commit. |
| Missing, failed, stale, foreign, or host-mismatched conformance receipt | stable path refuses | no | Fail before authority resolution or commit. |
| Spec, overlay, Pack IR, compilation, capability, or authority drift | no | no | Reconstructed spec must be byte/identity-equivalent. |
| Plan approval naming `spec_id`, another plan, or an earlier plan | v1alpha1 semantics unchanged | no | Exact plan subject is mandatory. |
| Stale expected head or superseded plan | optimistic conflict only | no | Preflight fails; the atomic Core head guard remains the race backstop. |

Package versions never substitute for contract compatibility. The host re-negotiates the manifest,
compiler, and runtime contracts at admission and checks the conformance receipt against that
current result.

## Lifecycle state and authorization matrix

| Action | Required current state | Required spec relation | Result state | Separate exact approval |
|---|---|---|---|---|
| initial activation | no head | new exact spec | active | yes |
| upgrade | active | changed spec | active | yes |
| suspend | active | exact current spec | suspended | yes |
| reactivate | suspended | exact current spec | active | yes |
| rollback | any current v1alpha2 state; target must be an earlier active revision | exact target spec | active | yes |
| retire | active or suspended | exact current spec | retired | yes |

Live actions require `pack_activation`, may additionally bind runtime monitors, subscriptions,
Shift derivation, and canonical Brief synthesis, and must carry every exact spec capability and
authority binding. Suspension and retirement request only their closed lifecycle effect and cannot
reuse runtime grants. Scheduling, delivery, connector transport, credential access, provider
selection, persistence authority, and external action are not plan effects and are never pack
capabilities.

## Activation and rollback threat model

| Threat | Fail-closed control | Acceptance proof |
|---|---|---|
| An approval over a spec is replayed as approval over a wider plan | Core resolves approval against `plan_id`; envelope and receipt preserve that subject | Wrong-subject approval fails before commit. |
| Effect or capability widening retains an old identity | Closed sorted material has independent digests and is part of `plan_digest` | One changed effect/capability creates a new plan and approval requirement. |
| A plan prepared against an old head activates after an intervening change | Plan embeds exact expected head; preflight compares the current head; Core commit repeats the atomic guard | Stale and race paths produce no revision or receipt. |
| A pack or receipt was changed after plan preparation | Admission revalidates Pack IR, current compatibility, exact conformance body, compilation, overlay, bindings, and reconstructed spec equality | Drift, foreign pack, failed receipt, and stale host contract fail before authority lookup. |
| Rollback points at fabricated or cross-scope history | Admission loads the exact historical revision and verifies v1alpha2 contract, activation ID, earlier sequence, active state, target digest, and exact target spec | Missing, mixed-version, wrong-state, cross-scope, digest-drifted, or current/future target fails. |
| Suspension or retirement silently reuses live grants | Lifecycle-only plans carry no requested runtime capabilities/authorities | Authority resolver is not called for runtime grants. |
| Reactivation silently inherits initial approval | Reactivation is a distinct content-addressed action and plan subject | Initial approval fails against reactivation plan ID. |
| Persisted payload is rewritten after commit | Reload revalidates the plan, revision, opaque envelope, head, and Core receipt pair | Restart equality and drift failures are tested. |
| Old persisted identities are rewritten during adoption | v1alpha1 service and contracts are untouched; v1alpha2 rejects a mixed head | Legacy regression and mixed-history negative gate. |
| A Domain Pack gains execution or credentials | Pack compiler retains inert-data and authority-escalation checks; plan effect enum has no connector, credential, provider, arbitrary persistence, delivery, or external-action effect | Existing 0.7A security suite plus exact plan schema checks. |

The remaining Phase 2 threat analysis must bind approved 0.7D handoff IDs/digests to every emitted
monitor, subscription, Shift, and canonical Brief coordinate. No temporary resource contract may
stand in for that proof.

## Acceptance fixtures

### Core provider-free fixture

`tests/intelligence/test_domain_activation_plan_admission.py` owns a domain-neutral fixture pack
with ontology, numeric detection, persona routing, synthesis, one capability declaration, one
bounded source authority request, and one golden Observation transition. It proves:

1. stable compilation and current conformance revalidation;
2. exact plan approval subject and immutable commit receipt;
3. restart-stable plan, revision, envelope, head, and receipt identity;
4. effect/capability digest drift refusal;
5. separate upgrade, suspension, reactivation, and rollback plans and receipts;
6. stale head, wrong approval subject, and rollback-target mismatch refusal;
7. v1alpha1/v1alpha2 mixed-history refusal; and
8. stale/mismatched conformance refusal.

The fixture contains only domain-neutral `record`, `value`, reviewer, routing, and policy terms. It
does not substitute for either external domain proof.

### External World and Market packets

World and Market changes remain in their own repositories. Each consumer packet must supply its
own installed distribution, manifest/resources, golden fixtures, and one provider-free activation
journey. Core records only exact external commit or release identities and neutral receipts.

| Required consumer evidence | World packet | Market packet | Cross-domain assertion |
|---|---|---|---|
| Repository/commit and built artifact hash | required | required | separate artifacts and histories |
| Manifest, Pack IR, compilation and conformance IDs | required | required | unchanged compiler/helper API |
| Declared capabilities/authorities/effects preview | required | required | no implicit grants or pack effects |
| Exact approval plan/revision/commit IDs | required | required | unchanged v1alpha2 admission API |
| Restart reload coordinates | required | required | byte-identical durable material |
| Upgrade then exact rollback receipt | required | required | prior target preserved; no deletion |
| Domain-specific ontology/detectors/personas/policy | required | required | materially different, no identifier collision |
| Negative stale/mismatched conformance path | required | required | fail closed with zero live effect |
| Independent runtime consumer proof after Phase 2 | required | required | unchanged Monitor/Subscription/Shift/Brief APIs |

Material difference must be demonstrated across entity/relation shape, source mapping, detector
family or cadence, persona/routing, synthesis policy, and epistemic/decision policy—not merely pack
name or fixture values. Domain nouns and consumer code stay outside Core.

## Phase 2 implementation plan

After the control tower supplies the exact completed 0.7D branch/commit:

1. diff only its published contracts and evidence against this base;
2. import the exact approved intelligence-model and first-Brief handoff types without changing
   their identities;
3. extend the activation plan with exact handoff references and generated inert pack/configuration
   bytes, producing a new plan identity if any material changes;
4. compile and conform the generated pack through unchanged 0.7A APIs;
5. after exact plan approval and admission, compose existing monitor, subscription, live-derivation,
   and canonical Brief services using the committed activation revision as their authority binding;
6. prove restart, later Observation update or explicit no-material-shift, and governed feedback;
7. dispatch separate World and Market consumer packets; and
8. record cumulative installed-wheel, naked-kernel, exact eleven-tool, and two-domain evidence.

If published 0.7D identities cannot be embedded without altering them, stop and return the conflict
to the control tower. Do not create a compatibility alias or temporary runtime resource.

## Owned files and repository boundaries

Phase 1 Core ownership is limited to:

- `ace/application/domain_activation_plan_contracts.py`;
- `ace/application/domain_activation_plan.py`;
- additive public exports in `ace/application/__init__.py`;
- focused tests under `tests/intelligence/`;
- this work packet and its later candidate evidence record; and
- narrowly required package/schema documentation.

Phase 2 may add one separate Activation Agent service and focused tests after the 0.7D commit is
known. World and Market manifests, fixtures, SDK glue, and evidence must not be added to this Core
patch.

## Verification matrix

Phase 1 must pass:

- focused v1alpha2 plan/admission/lifecycle/negative tests;
- existing v1alpha1 activation, 0.7A compiler/conformance, and 0.7B–0.7C regression;
- package import and installed-wheel reproduction from two clean target directories;
- restart reload and rollback target proof;
- explicit extensions-disabled naked-kernel startup;
- exact eleven-tool MCP surface;
- Ruff, lock, whitespace, package-data, and documentation integrity checks; and
- a proportionate broader non-E2E suite with any linked-worktree limitations reported honestly.

No merge, release, package publication, push, or PR belongs to this packet without separate
control-tower authorization.

## Rollback

Stop exporting or composing the additive v1alpha2 application contracts and admission service.
No v1alpha1 contract, persisted identity, receipt, compiler output, conformance result, or runtime
binding is rewritten. Any already committed v1alpha2 revisions remain immutable opaque Core
history. Rollback of a product activation is itself a separately approved v1alpha2 rollback plan;
code rollback is not authority to alter product state.

## Open dependency and non-claims

Phase 2 is blocked only on the control tower supplying the exact completed 0.7D branch/commit. This
packet does not yet implement the Activation Agent, generate a pack from onboarding proposals,
materialize runtime Monitors or Subscriptions, consume a first-Brief preview, edit World or Market,
prove installed-wheel convergence, or close 0.7E. It changes neither the MCP tool registry nor the
naked-kernel extension boundary.
