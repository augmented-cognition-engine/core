# ACE Agent Memory AM6 evaluation preparation work packet v1

- Date: 2026-08-12
- Status: provider-free evaluation-preparation candidate; not memory-benefit evidence
- Exact base: `f761a682164d10e2ff81ba38cd2d0c987b4f8efd`
- Base branch: `codex/v0.7-cumulative-integration-acceptance`
- Candidate branch: `codex/v0.7-agent-memory-am6-evaluation-prep`
- Parallel boundary: AM3-runnable; AM4 lifecycle cases are gated placeholders only

## Outcome and claim boundary

This packet freezes the AM6 measurement vocabulary, synthetic corpus, matched conditions,
content-addressed artifact chain, deterministic comparator, result shape, and verification entry
point that can run over the existing AM0–AM3 boundary.

The provider-free fixture proves that the evaluator reproduces exact coordinates and classifies
synthetic bounded outcomes as beneficial, harmful, neutral, or underpowered under a preregistered
rule. It does **not** prove that Agent Memory is beneficial, correct in general, causally effective,
production-ready, or eligible for a policy change.

The evaluator:

- writes no Agent Memory;
- changes no rank, retention, consolidation, promotion, roster, authority, delivery, or effect
  policy;
- trains or updates no model;
- requires no provider, credential, network, database, schema, or migration;
- adds no public TaskCreate field, endpoint, command, or MCP tool; and
- invents no AM4 retention, export, import, expiry, or erasure runtime contract.

## Exact artifact chain

The provider-neutral Intelligence contracts freeze five content-addressed artifacts:

1. `ace.intelligence.agent-memory-evaluation-corpus/v1alpha1`;
2. `ace.intelligence.agent-memory-evaluation-protocol/v1alpha1`;
3. `ace.intelligence.agent-memory-condition-assignment/v1alpha1`;
4. `ace.intelligence.agent-memory-run-observation/v1alpha1`; and
5. `ace.intelligence.agent-memory-matched-comparison/v1alpha1`.

The corpus is frozen before the protocol, the protocol before assignment, every assignment before
its three observations, and every observation before comparison. Exact identities derive from the
complete canonical material. Reconstructing the fixture in a fresh process must reproduce the same
corpus, protocol, assignment, observation, and comparison coordinates.

These are evaluation artifacts, not memory records, governed policy proposals, authority receipts,
retention receipts, or delivery/effect artifacts.

## Preregistered matched conditions

Every case has exactly three conditions:

| Condition | Treatment | Boundary |
|---|---|---|
| `memory` | Existing AM3 authorized selection and smallest eligible context | May reference exact recall, Context Manifest, and I3 artifacts; cannot widen their semantics |
| `no_memory` | Memory disabled | Holds every non-memory coordinate constant |
| `full_context` | Complete authorized context baseline | Holds every non-memory coordinate constant; does not bypass scope or privacy |

Every assignment binds one exact task plus the same provider, model, prompt contract, decision
schema, toolset, and configuration across all three conditions. The deterministic fixture freezes
`provider:deterministic-fixture` and `model:none`; a provider run is optional and cannot replace the
provider-free conformance authority.

## Frozen corpus

The v1 corpus contains 18 synthetic cases. Fifteen run honestly over AM0–AM3; three are explicit
AM4 convergence gates.

| Case | Current status | Required coverage |
|---|---|---|
| `am1_ingestion_replay_restart` | runnable | ingestion completeness, exact replay, restart, episodic experience |
| `am2_family_extraction_and_spans` | runnable | all seven AM2 assertion families, precision/recall, exact source spans |
| `am2_identity_and_unresolved` | runnable | identity error, unresolved identity, unknown stays unknown |
| `am2_conflict_correction_uncertainty` | runnable | conflict, correction, contradiction, uncertainty |
| `am2_instruction_isolation` | runnable | instruction recall and prompt-shaped source-data isolation |
| `am2_independent_time_axes` | runnable | ledger, knowledge, and world time, including unknown time |
| `am1_scope_privacy_isolation` | runnable | product/principal scope, cross-scope privacy, non-disclosure |
| `am3_authorization_denial` | runnable | authorization before signals, graph, cache, and body; zero leakage |
| `am3_stale_superseded_safety` | runnable | correction priority and zero stale/superseded influence |
| `am3_harmful_influence_probe` | runnable negative probe | evaluator detects stale/superseded harmful influence |
| `am3_manifest_selection_omission` | runnable | retrieval, rank, citation, omission, selected/injected/reflected/material states |
| `am3_degraded_retrieval_signal` | runnable degraded case | missing optional signal is explicit and underpowered |
| `am3_later_restart_material_use` | runnable | independent later invocation after restart and material-use distinction |
| `am3_material_but_neutral` | runnable | material influence remains distinct from benefit |
| `am3_missing_resource_telemetry` | runnable degraded case | missing token/latency/call/cache/cost telemetry is explicit and underpowered |
| `am4_retention_expiry_placeholder` | gated | future retention/expiry behavior; no current execution |
| `am4_export_import_placeholder` | gated | future export/import identity/lifecycle behavior; no current execution |
| `am4_hard_erasure_placeholder` | gated | future dependency-complete erasure/restart behavior; no current execution |

The harmful case is a deliberately injected negative observation proving the comparator fails the
unsafe result. It is not evidence that the current AM3 implementation exhibited harmful behavior.

## Measurement registry

The protocol freezes 31 measures rather than interpreting absent data as zero or success.

### Admission, extraction, identity, and reconciliation

- ingestion completeness and replay correctness;
- extraction precision and recall, with family strata;
- exact source-span accuracy;
- identity error and unresolved-identity rate; and
- correction, contradiction, uncertainty, and instruction-policy recall.

### Retrieval, safety, and omission

- retrieval precision and recall;
- rank quality;
- citation correctness;
- omission coverage;
- unauthorized retrieval count, with zero tolerance;
- stale influence count;
- superseded influence count; and
- dependency invalidation rate.

### Resources, routes, and use states

- context tokens and residual window tokens;
- latency, provider calls, cache reuse, and cost;
- observed route and tier coordinates, aggregated as deterministic frequencies; and
- selected, injected, reflected, and decision-material rates.

### Bounded task outcome

- task correctness in basis points; and
- beneficial, harmful, neutral, or underpowered comparison disposition.

An unavailable required measure contains no numeric value and names its reason. The comparison then
sets paired/control status false and material influence, benefit, and correctness to underpowered.
Optional retrieval-signal loss and required resource-telemetry loss therefore cannot silently look
like a zero-cost or fully evaluated success.

## Material influence, benefit, correctness, and causality

The comparison keeps four independent dimensions:

| Dimension | v1 meaning |
|---|---|
| Material influence | Whether the exact memory and no-memory decision digests differ under held constants |
| Benefit disposition | Synthetic bounded label: beneficial, harmful, neutral, or underpowered |
| Correctness | Correct, incorrect, mixed, or underpowered against the frozen synthetic oracle |
| Causality | Always `not_established` in this preparation fixture |

A material difference is not automatically beneficial or correct. A neutral result can be
material. A correct result can be neutral. Missing evidence is underpowered rather than neutral.
The synthetic benefit label proves the evaluator's rule only; it is not an Agent Memory benefit
claim.

## Comparison rule

The deterministic comparator:

1. verifies exact corpus, protocol, assignment, case, condition, and time closure;
2. requires exactly one memory, no-memory, and full-context observation;
3. verifies every case-required measurement is available in every condition;
4. makes any AM4-gated case underpowered until `future_accepted_am4_coordinate` is replaced through
   a separately accepted convergence change;
5. labels any unauthorized retrieval, stale influence, or superseded influence as harmful;
6. records material influence only from a changed memory/no-memory decision digest;
7. labels a synthetic result beneficial only when memory beats no-memory by the preregistered
   threshold and remains within the frozen full-context correctness gap;
8. labels a negative task-score delta harmful and an unchanged score neutral; and
9. emits no proposal or policy mutation for any disposition.

## AC6 reuse and separation

AM6 reuses semantically valid AC6 patterns:

- freeze before assignment and observation;
- exact matched coordinates;
- provider-free acceptance authority;
- content-addressed artifact identity;
- visible failures, missing telemetry, negative results, and limitations;
- deterministic fresh-process reproduction; and
- claim bounding.

AM6 does not reuse AC6's composition conditions, participant materiality thresholds, dynamic
composition proposal, roster semantics, or policy-admission path. Composition policy and memory
policy remain separate owners.

## AM4 convergence gate

The three AM4 cases carry only the literal `future_accepted_am4_coordinate`. They do not name or
construct a retention policy, export service, erasure service, derivative index implementation,
receipt grammar, lifecycle transition, or persistence behavior.

After AM4 is independently accepted, the minimal convergence change is:

1. record the exact accepted AM4 commit and owning contract coordinates as corpus source artifacts;
2. replace each placeholder gate with exact existing AM4 observation inputs;
3. add the AM4-required measures without changing the AM3 case coordinates or matched constants;
4. rerun the same provider-free verifier and focused privacy/package boundaries; and
5. publish the new result as AM4-converged evidence without rewriting this v1 preparation record.

No AM4 branch, PR, or runtime implementation is a dependency of the current executable suite.

## Artifacts

- contracts: `ace/intelligence/contracts/agent_memory_evaluation.py`;
- deterministic comparator: `ace/intelligence/agent_memory_evaluation.py`;
- frozen corpus/protocol fixture: `evaluations/fixtures/agent_memory_am6_evaluation_prep_v1.json`;
- provider-free runner: `evaluations/source/agent_memory_am6_evaluation.py`;
- frozen result: `evaluations/results/agent_memory_am6_evaluation_prep_v1.json`;
- verifier: `scripts/verify_agent_memory_am6_evaluation.py`; and
- conformance: `tests/agent_memory/am6/test_evaluation_prep.py`.

## Verification and publication gate

Before publication, this lane must record:

- focused AM6 conformance;
- AM0–AM3 focused regression and AC6 provider-free verifier;
- privacy, Core/Intelligence import, package, naked-kernel, and exact eleven-tool MCP boundaries;
- fixture/result deterministic diff and fresh-process reproduction;
- Ruff, format, lock, diff, secret, authority, privacy, AM4-invention, and domain scans;
- installed-wheel checkout-free verifier reproduction because runtime code is included; and
- effective diff against exact base `f761a682164d10e2ff81ba38cd2d0c987b4f8efd`.

Publication may be a stacked draft against `codex/v0.7-cumulative-integration-acceptance` only if
the effective diff remains AM6-only and independently reviewable. Merge, release, tag, package
publication, policy activation, and downstream dispatch remain prohibited.
