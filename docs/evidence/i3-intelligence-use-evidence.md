# I3 inspectable continuity and material intelligence-use evidence

Date: 2026-07-22

Outcome: **I3 passed**

## Claim and boundary

ACE can now show which retained intelligence was retrieved, which item actually entered a later
reasoning context, whether bounded output attribution reflected it, and whether an isolated matched
comparison changed a declared structured decision field.

I3 does **not** claim that a material change was correct or beneficial. A harmful item can be
decision-material. Benefit remains `outcome_unsupported` unless a later L1 evaluation connects the
decision to adequately attributed outcome evidence. Retrieval, copied wording, model self-report,
and cross-model differences never receive materiality credit.

## Versioned contract and supported reads

`intelligence-use-receipt-v1` is an additive task-backed projection over existing `task`,
`decision`, `observation`, and `insight` identities. It is not a second memory system. Schema v155
adds the optional task field; no new table, execution authority, API write contract, or MCP tool was
introduced.

The same normalized receipt is available through:

- `ace_status(task_id="task:…")` on the existing thin task/status journey; and
- the task record in the strictly read-only Living Product Graph projection.

The receipt is bounded to 64 intelligence items and 64 values per nested collection. Common
credential forms are redacted. Retained content, unrestricted prompts, original private task text,
model scratchpads, hidden chain-of-thought, and credentials are not copied into the receipt.

For every item the receipt retains:

- stable intelligence ID, type, content hash, source product, and receiving product;
- receiving task, decision, component, stage, and invocation;
- retrieval rank, query, reason, and relevance where present;
- validity, trust, provenance, lifecycle, and contestation;
- independent `retrieved`, `injected`, `reflected`, and `decision_material` booleans;
- exact materially changed fields; and
- explicit reasons why injection, reflection, or materiality was not established.

Unknown future versions normalize to an empty degraded v1 projection with the unsupported version
named. Missing controls remain `comparison.state="unknown"`; no variant is reconstructed from prose,
logs, or model output.

## Materiality rule

The comparison is limited to the six structured I1 decision fields:

1. `selected_option`
2. `scope`
3. `assumptions`
4. `alternatives`
5. `reconsideration_conditions`
6. `evidence_refs`

An item is decision-material only when all of the following are true:

- its product identity matches the receiving product and its lineage is complete;
- validity and lifecycle permit use; contested intelligence is explicitly deferred, escalated, or
  preserved as disagreement;
- it was retrieved, actually injected, and reflected through bounded or structured attribution;
- relevance is established;
- the comparison targets exactly that one intelligence item;
- treatment and control match on task hash, prompt-contract hash, provider, exact model,
  configuration hash, I1 decision schema, and toolset hash; and
- at least one declared I1 field changes exactly.

Identifier mention, verbatim overlap, and ordinary structural/model attribution may establish
reflection, but are not materiality-eligible on their own. Stale, invalidated, expired, foreign,
missing-lineage, unmatched, failed, or control-less items cannot be decision-material.

Both decision variants, changed and unchanged fields, invocation IDs, output hashes, matching
dimensions, calls, tokens, latency, retries, billing semantics, failures, degraded states, and
limitations remain inspectable.

## Frozen deterministic public-data scenario

The frozen scenario uses the public UCI Online Retail II dataset context, DOI
`10.24432/C5F88Q`. The bounded product decision is whether to keep a cancellation-handling cohort
staged or proceed to general rollout. The fixture is
[`evaluations/fixtures/i3_intelligence_use_v1.json`](../../evaluations/fixtures/i3_intelligence_use_v1.json);
generated receipts and a compact report are in
[`evaluations/results/i3_intelligence_use_v1.json`](../../evaluations/results/i3_intelligence_use_v1.json)
and [`evaluations/results/i3_intelligence_use_v1.md`](../../evaluations/results/i3_intelligence_use_v1.md).

The deterministic matrix contains 13 receipts: 11 matched comparisons, one provider/model/config
mismatch, and one evaluation failure. Ten are complete and three are intentionally degraded. Four
receipts are decision-material: ordinary material, safely handled contested, harmful, and restart
continuity. The null and reflected-only cases preserve no-delta behavior.

| Required case | Frozen receipt behavior |
|---|---|
| Material | Valid relevant correction changes declared I1 fields in an isolated matched pair |
| Null | Retrieved, injected, and reflected; all six I1 fields unchanged; no material credit |
| Irrelevant | Retrieved at low relevance and not injected; remains retrieved |
| Reflected but non-material | Identifier mention is visible but changes no I1 field and is not materiality-eligible |
| Stale | Reflection retained; `validity_stale` blocks materiality |
| Invalidated | Retrieved but filtered from injection; invalidation and lifecycle retained |
| Contested | Disagreement is preserved explicitly; the bounded defer/change is material |
| Harmful | Exact matched delta is material; later harmful finding remains `beneficial_impact="harmful"` |
| Product mismatch | Foreign source product is visible; `product_mismatch` blocks credit |
| Provider/model/config mismatch | All three mismatches are named; comparison is degraded and non-causal |
| Provider/evaluation failure | Control timeout is retained; comparison is failed and non-material |
| Partial/degraded lineage | Missing content hash and provenance are named; materiality is blocked |
| Fresh invocation after restart | Stable retained identity and material receipt survive a real database/API restart |

## Live matched provider route

[`evaluations/results/i3_live_provider_v1.json`](../../evaluations/results/i3_live_provider_v1.json)
records the frozen one-treatment/one-control stopping rule on the supported subscription-backed
Codex route. Both invocations used `CodexCLIProvider`, exact model `gpt-5.6-terra`, the same task and
prompt contracts, configuration hash, decision schema, toolset hash, and provider-default
temperature policy. The comparison was complete and matched with no failures or retries.

Recorded route metrics:

- calls: `2`;
- input tokens: `16,799`;
- output tokens: `180`;
- treatment latency: `4,790 ms`;
- control latency: `3,325 ms`;
- total measured invocation latency: `8,115 ms`;
- retries: `0`;
- billing semantics: `chatgpt_subscription_no_platform_api_charge`; and
- failures/degraded states: none.

The retained correction changed five I1 fields: `selected_option`, `assumptions`, `alternatives`,
`reconsideration_conditions`, and `evidence_refs`; `scope` was unchanged. The receipt is
decision-material and explicitly `outcome_unsupported`. One pair establishes only this scoped
memory-effect result, not general quality, provider superiority, or beneficial impact.

## Real restart and fresh-client acceptance

`tests/test_i1_restart_persistence.py` starts a disposable SurrealKV database and production
uvicorn API, exercises the supported thin client, stops the API, starts a new API process against
the same store, and creates a new task through a fresh client. Production startup replays schema
zero through v155.

The post-restart deterministic orchestration fixture retrieves an active correction captured
before restart, records its exact stable ID in a matched treatment/control comparison, and persists
a material I3 receipt. `ace_status` returns the same source/receiver lineage, exact delta,
comparison, and `outcome_unsupported` boundary. The fixture makes zero model calls; it proves real
database/API/process/client continuity rather than provider quality.

## Verification record

- I3 contract, evaluator, task projection, Living Product Graph, loader, attribution, and
  orchestration focused regression: `176 passed` in `13.42s`.
- Post-compatibility-fix I3, legacy-loader-shape, and exact naked-kernel boundary regression:
  `17 passed` in `1.34s` (including all four kernel-boundary tests).
- Disposable schema-zero-to-v155 SurrealDB/API restart and fresh-client material-use acceptance:
  `1 passed` in `24.36s`.
- Frozen live Codex matched comparison: complete, matched, decision-material, zero failures/retries.
- Full zero-extension non-E2E regression: `6538 passed`, `47 skipped`, `242 deselected`, with
  `21` inherited failures (`20` provider-selection assumptions overridden by the active Codex
  app-server environment and one pre-existing roadmap-lane assertion). No I3 test failed.
- Ruff checks passed for every touched Python module; Ruff format checks passed for the new and
  restart-fixture files; `git diff --check` passed.

## Limitations and deferred claims

- The live route is one frozen matched pair. It does not establish general or longitudinal lift.
- Runtime task receipts without an executed matched control honestly stop at retrieved, injected,
  or reflected and report an unknown comparison.
- Bounded attribution is evidence of reflection, not hidden reasoning or a causal explanation.
- The deterministic restart route proves persistence and receipt semantics with zero model calls;
  the separate live route proves one real-provider matched comparison but not API restart.
- I3 does not test foresight benefit, reliability curves, sample-size-aware lift, intervention or
  confounder attribution, or no-foresight/naive/model-only controls. Those belong to L1.
- I2 deliberation attribution, T1 distributed recovery, F2 consequence breadth, E1/E2 extension
  work, and new provider routes were not begun.
