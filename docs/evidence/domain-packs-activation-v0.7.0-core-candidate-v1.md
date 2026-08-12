# ACE 0.7E Domain Packs + Activation Core candidate evidence (v1)

**Status:** Core contract/admission candidate complete; external World and Market consumer packets
remain open. This candidate is stacked directly on accepted 0.7D commit
`dab0866af239af9a13b4d2772a0d3950f932fa2e` (draft PR #104). It does not merge, release, tag,
publish a package, close issue #39, or claim the two-domain product proof.

## Accepted activation boundary

The existing `DomainActivationSpecV1`, `DomainActivationRevisionV1`, v1alpha1 admission service,
persisted identities, and receipt behavior are unchanged. The additive candidate provides:

- `ace.application.activation-onboarding-handoff/v1alpha2`: exact accepted 0.7D session, Map,
  Observation, Watch proposal/disposition, Brief derivation, and first-preview coordinates; its
  authority stage is the literal `pre_activation_handoff` and `live_authority` is the literal
  `false`;
- `ace.application.intelligence-activation-plan/v1alpha2`: the exact approval subject, binding the
  handoff, unchanged embedded activation spec, requested effects, capabilities, authorities,
  lifecycle action, expected head, and optional rollback target;
- `ace.intelligence.domain-activation-revision/v1alpha2`: immutable lifecycle state and plan,
  approval, actor, lineage, identity, and digest material;
- `DomainActivationPlanAdmissionService`: independent reconstruction of the exact 0.7D handoff,
  current compatibility and conformance, embedded spec, requested material, lifecycle/head,
  rollback history, approval, authority grants, and atomic Core commit; and
- `ace.application.domain-activation-commit-reference/v1alpha2`: stable opaque committed plan,
  revision, and Core receipt coordinates, permanently marked `historical_reference` and
  `live_authority = false`.

No lifecycle operation accepts the historical reference as authority. Initial activation,
upgrade, suspension, reactivation, rollback, and retirement each require a new exact plan, current
approval, admission validation, and immutable receipt. Mixed v1alpha1/v1alpha2 history, stale
heads or receipts, crossed Watch/Brief material, embedded-spec drift, effect widening, and
rollback-target mismatch fail closed.

## Reproduced exact candidate identities

The provider-free accepted 0.7D reference journey closed into these deterministic coordinates:

```json
{
  "session_revision_id": "intelligence_builder_session_revision:f269f1f6c255f1ae4a57a1704509213b",
  "observation_set_id": "authorized_observation_set:0e61535fa23b45cc8d1de91fbd99b6a9",
  "intelligence_model_proposal_id": "intelligence_model_proposal:a0df1a06c1e8502d19d9566cde70a025",
  "intelligence_model_disposition_id": "intelligence_model_disposition:6ce7775b3d5674ab313761497b87296b",
  "briefing_derivation_id": "briefing_derivation:4fe1ceb921eb80ecffd87925a2b27b7d",
  "first_briefing_preview_id": "first_briefing_preview:d5c5dd4bc9d96e8c0057a2af57ee10fb",
  "activation_onboarding_handoff_id": "activation_onboarding_handoff:5f149bc12671ae32ece4894d9a62dd6c",
  "activation_onboarding_handoff_digest": "sha256:5f149bc12671ae32ece4894d9a62dd6c3a5581d78f0f482bca76dd26f8831021",
  "activation_plan_id": "intelligence_activation_plan:59a927411a8a99e4a4c93d9c6ee0ddf4",
  "activation_plan_digest": "sha256:59a927411a8a99e4a4c93d9c6ee0ddf4b778a6baceec6188b2c2d2d3fa15dde6",
  "activation_revision_id": "activation_revision:8dd82bd06590aad5dba19707d0304298",
  "activation_revision_digest": "sha256:8dd82bd06590aad5dba19707d030429836cf39c4633b6cffa0ebfbb6ab5efe94",
  "core_commit_receipt_id": "governed_state_commit:873014a8ee951ae3b84c797a9eaf8b16",
  "core_commit_receipt_digest": "sha256:873014a8ee951ae3b84c797a9eaf8b16898db49f3b9bf13d46cc3f526ada4c7d"
}
```

These are deterministic fixture identities, not deployed runtime authority.

## Verification

- focused v1alpha2 activation-plan, exact 0.7D handoff, lifecycle, rollback, restart, reference, and
  negative conformance tests: **9 passed**;
- complete Intelligence suite: **465 passed, 12 expected skips**;
- naked-kernel, exact eleven-tool MCP, package identity, and focused boundary selection:
  **29 passed**;
- full non-E2E/non-extension gate with no linked-worktree exclusions:
  **7,544 passed, 50 expected skips, 261 marker-deselected**;
- explicit kernel boundary rerun: **4 passed**;
- repository-wide Ruff lint, intended-file Ruff format, lock consistency, and whitespace checks:
  passed; and
- a wheel built from the candidate and installed into two clean target directories. Both imported
  `ace` from their installed target, reproduced the same 0.7D
  proposal/disposition/Brief coordinates and the same
  `activation_onboarding_handoff:5f149bc12671ae32ece4894d9a62dd6c`, and reported
  `live_authority = false`.

The repository-wide format check continues to identify ten unchanged inherited 0.7A/0.7B files
that predate this packet's formatting. Every intended 0.7E file passes the formatter; this packet
does not rewrite those unrelated stack files.

## External two-domain proof and handoff

The Core half is ready for separate World and Market packets. Each consumer must retain its domain
nouns and implementation in its own repository and supply:

1. an independent artifact/repository identity and materially different pack modules/fixtures;
2. unchanged compiler, conformance, activation-plan, and admission API use;
3. exact declared effect/capability/authority preview and approval;
4. committed plan/revision/Core receipt and restart-reload coordinates;
5. upgrade plus separately approved exact rollback proof;
6. consumer-side Monitor, Subscription, Shift, and canonical Brief bindings rooted in the committed
   activation coordinates; and
7. installed-wheel and stale/mismatched-conformance negative reproduction.

Until both packets are accepted, 0.7E's two-domain product proof remains open. No World or Market
content is mixed into this Core contract patch.
