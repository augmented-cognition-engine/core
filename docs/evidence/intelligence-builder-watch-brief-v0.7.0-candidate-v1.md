# ACE 0.7D Intelligence Builder Watch + Brief candidate evidence (v1)

**Status:** local stacked candidate above draft PR #103. This record advances only 0.7D Watch +
Brief. It is not release evidence and does not claim Activate, independent World/Market proof,
Agent Memory, Agent Composition, the cumulative onboarding demo, or 0.7.0.

## Outcome

The public Python application surface consumes the exact approved 0.7C concept-model handoff and
bounded observations from two authorized neutral sources. It produces an editable intelligence
model, persists a materiality edit as immutable revision 2 with exact semantic diff and lineage,
resolves human/Core approval for that revision, and passes its exact disposition to a separate
Briefing Agent. The Briefing Agent produces one deterministic first Brief with a material shift,
provenance, uncertainty, source disagreement, an explicit unknown, counterevidence/alternatives,
why-it-matters text, and freshness. A fresh service reopens the same artifacts and session.

Neither service owns connector transport, credentials, scheduling, monitor/subscription binding,
delivery, decision/action execution, pack activation, grant creation, or authoritative runtime
state. Core receives generic opaque onboarding records and approval subjects; no Watch/Brief nouns
enter Core receipt contracts.

## Exact provider-free reproduction

| Material | Exact identity |
|---|---|
| authorized observation set | `authorized_observation_set:0e61535fa23b45cc8d1de91fbd99b6a9` |
| observation-set persistence receipt | `append_only_receipt:575f42274b3b437e3c7f8059e4960489` |
| initial intelligence proposal | `intelligence_model_proposal:f7e733012b23e3745f76a261ee2d33b3` |
| initial proposal persistence receipt | `append_only_receipt:106364ea4c49231eeda99dce6f9050f0` |
| edited intelligence proposal | `intelligence_model_proposal:a0df1a06c1e8502d19d9566cde70a025` |
| edited proposal persistence receipt | `append_only_receipt:9d83e8c326b58c197ac6980a4c1b433c` |
| approved disposition/handoff | `intelligence_model_disposition:6ce7775b3d5674ab313761497b87296b` |
| disposition persistence receipt | `append_only_receipt:a0b02990799de51ef7622884efd6e41f` |
| Brief derivation | `briefing_derivation:4fe1ceb921eb80ecffd87925a2b27b7d` |
| first Brief preview | `first_briefing_preview:d5c5dd4bc9d96e8c0057a2af57ee10fb` |
| first Brief persistence receipt | `append_only_receipt:79ec3728a2ba2007fcd9f4fcd294d9c3` |
| reopened first-briefing-ready session | `intelligence_builder_session_revision:f269f1f6c255f1ae4a57a1704509213b` |

Two independent installed-wheel target directories (`site-a` and `site-b`) reproduced every
identity above while importing `ace.testing.watch_brief` from the installed target rather than the
source checkout. The built wheel SHA-256 was
`94d8be1af06a1296003b6c445029bc8908e261fc4d9532c27ca3624785fcd55d`.

## Proposal and Brief contents

The provider-free Watch strategy proposes three targets over the neutral `record` concept: status,
value, and a provisional relationship. It includes status/value baselines, categorical-transition
and numeric-delta detector declarations, explicit materiality rules/rationales, one reviewer
audience, route and cadence, suppression/grouping, and statements classified as observation,
claim, inference, disagreement, and unknown. The two sources explicitly disagree on status; that conflict is
retained but does not block this preview.

The immutable user edit changes the value threshold from ten to twelve units and records exactly
`materiality_rules.changed:value_materiality`. The first Brief binds the approved revision and
observation set through its derivation identity, cites all four exact evidence fields, surfaces the
status disagreement rather than averaging it away, marks unresolved relationship semantics as
unknown, and proposes attention/questions without creating a decision or action.

## Failure controls

Focused tests prove:

- widened or unadmitted observation inputs and stale concept/evidence/session handoffs fail closed;
- observation and intelligence citations must bind exact source-profile/sample/evidence material;
- unsupported detector/effect fields and imperative content are forbidden;
- materiality edits require immutable lineage and the actual computed semantic diff;
- stale revisions and denied/self approval cannot advance state;
- low confidence, blocking evidence conflict, incomplete closure, stale inputs, no material items,
  and synthesis failure use distinct resumable blocked states;
- fabricated claims, citation gaps, and hidden disagreement fail before Brief persistence; and
- restart reopens the exact approved model/disposition/Brief bodies and handoff identities.

## Verification

- cumulative focused 0.7B–0.7D suite: **36 passed**.
- 0.7A–0.7D, package identity, narrative/evidence, naked-kernel, exact eleven-tool MCP, and TP0
  linked-worktree regression gate: **123 passed, 3 expected skips**.
- final installed-wheel two-directory reproduction: passed with the exact identities and wheel
  hash above.
- repository-wide Ruff, `git diff --check`, and `uv lock --check`: passed.
- full non-e2e/non-extension gate with no linked-worktree baseline deselections:
  **7,535 passed, 50 skipped, 261 marker-deselected**. One first run encountered an external
  SurrealDB teardown write conflict after all test assertions passed; its exact test plus TP0 and
  kernel boundaries passed **13/13** in isolation, and the complete undeselected rerun then passed.

## Linked-worktree test-harness reliability

The frozen TP0 adapter source and historical hash remain byte-for-byte unchanged. A read-only
test-harness resolver now handles ordinary `.git` directories, linked-worktree `.git` files,
`commondir`, loose/packed refs, and detached HEAD. The baseline suite injects it without weakening
or deselecting any original assertion. A synthetic regression covers ordinary and linked layouts.

## Downstream handoff and limitations

0.7E receives immutable proposal/disposition/Brief IDs and digests plus reloadable exact source
scope/profile, concept, observation, and intelligence bodies. It must construct and obtain approval
for its own sibling activation-plan-bound admission contract; no 0.7D artifact or receipt grants
activation authority. Only after 0.7E validates an exact committed activation may it construct
`ace.application.domain-activation-commit-reference/v1alpha2`, permanently marked
`historical_reference` and `live_authority=false`; 0.7D never emits that reference. 0.7F Agent
Memory and 0.7G Agent Composition may consume public identities
but require their own contracts and may not mutate 0.7D content, thresholds, citations, state
transitions, or authority.

The deterministic fixture evaluates bounded declared evidence, not a learned real-world ontology
or live source stream. Provider ports exist, but no provider implementation or model-quality claim
is included. There is no frontend, new connector transport, scheduler, delivery, authoritative
monitor/subscription, pack generation/activation, domain repository change, or release.

## Rollback

Stop composing the additive Intelligence Agent and Briefing Agent exports. Existing opaque Core
records remain immutable history. Rollback deletes no record, changes no grant, performs no
delivery/action, activates no pack, and leaves 0.7A–0.7C behavior untouched.
