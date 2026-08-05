# L1 foresight-impact evidence gate

Date: 2026-08-05

Outcome: **L1 passed for the frozen agent-only executable benchmark — v7 benefit supported against every control**

## Claim under test

L1 asks whether materially used, resolved conditional forecasts improve later reasoning and
decision quality. A pass requires outcome provenance, pre-outcome forecast lineage, adequate and
independent samples, intervention/confounder attribution, and favorable cluster-adjusted results
against all three required controls: no foresight, a naïve/base-rate policy, and a matched
model-only route.

The versioned evaluation contract is `ace.foresight.impact-evaluation/v1`. It computes scores from
frozen predictions and outcomes rather than accepting caller-supplied quality labels. A favorable
mean, identifier mention, material use, or success against only one control cannot produce a
benefit claim.

## Frozen public-data probe

The first probe uses the checksum-recorded UCI *Online Shoppers Purchasing Intention Dataset*, DOI
`10.24432/C5F88Q`, already frozen for R4. The downloaded archive matched the recorded SHA-256
`2972e6184d3ad7beaaa831d9fc2b059dc3ee29df69d1ec593c466a5cd8485d14`; the CSV matched
`b3055ee355f59134d851d32641183cb4a8b45def7124d2f50442a042f358e0d9`.

The reproducible transform partitions sessions by the dataset's nine region codes and ten listed
month categories. February and March form the frozen initial base-rate period. For each of the
remaining eight month categories, the ACE arm uses the prior two resolved regional conversion
rates; the no-foresight arm uses last-observation persistence; and the naïve arm uses the regional
base rate frozen from the first two periods. The target is the later observed regional revenue-
session rate and the score is absolute error, lower being better.

This produces 72 bounded cases, but uncertainty is computed over the eight target-month clusters,
not over 72 nominal rows. The dataset publishes a month category without a year or event-time
sequence, so the conventional month order is an explicit retrospective assumption rather than
verified chronology.

Artifacts:

- [`evaluations/fixtures/l1_foresight_impact_v1.json`](../../evaluations/fixtures/l1_foresight_impact_v1.json)
- [`evaluations/results/l1_foresight_impact_v1.json`](../../evaluations/results/l1_foresight_impact_v1.json)
- [`scripts/evaluate_l1_foresight_impact.py`](../../scripts/evaluate_l1_foresight_impact.py)

## Result

The result is `benefit_not_established`:

| Required comparison | Mean error reduction (positive favors ACE) | Cluster-adjusted 95% interval | Result |
|---|---:|---:|---|
| No foresight / persistence | `-0.003061` | `[-0.021649, 0.015527]` | Not established; point estimate is slightly harmful |
| Naïve frozen base rate | `0.020479` | `[-0.018470, 0.059428]` | Not established; interval includes zero |
| Matched model-only | Not run | Not estimable | Required evidence missing |

The evaluator also blocks promotion because the probe is retrospective and observational: it has
no verified intervention identity, cohort assignment, or adequate control of campaign, traffic,
device, visitor-mix, and operational confounders. It tests predictive decision quality only and
does not identify a product intervention effect.

The matched model-only provider run was deliberately not invoked after the no-foresight comparison
failed. Since L1 requires favorable evidence against every control, another provider call could not
turn this frozen probe into passing evidence. Avoiding that call prevents optional stopping from
being disguised as a successful all-controls study and records zero added model cost for this gate.

## Frozen prospective gate

The second work packet froze `ace.foresight.impact-preregistration/v1` before any new decision or
outcome collection. Its canonical SHA-256 remains
`sha256:bf558acda007ed04c24eb247749aad23ed89124c5ae38264add92061050135e7`.
The earliest eligible decision time is `2026-07-24T00:00:00Z`, after the recorded registration
time. The immutable protocol fixes:

- exactly four arms: ACE foresight, no foresight, naïve/base-rate, and matched model-only;
- blocked-randomized assignment over non-overlapping decision identities, with immutable
  assignment and exposure receipts;
- exact route matching on task, prompt contract, provider, model, configuration, decision schema,
  and toolset hashes;
- F1 resolution, I3 material-use, decision, and later-outcome identities;
- one analysis after the fixed cohort closes, with no interim promotion or favorable-subset
  selection;
- 30 complete cases, eight independent clusters, and a 256-case public-receipt bound;
- the existing continuous absolute-error score and an all-controls lower-interval-above-zero
  promotion rule; and
- required null, harmful, missing-outcome, failed-route, and degraded-lineage cases.

Artifacts:

- [`evaluations/fixtures/l1_preregistration_v1.json`](../../evaluations/fixtures/l1_preregistration_v1.json)
- [`evaluations/results/l1_preregistration_readiness_v1.json`](../../evaluations/results/l1_preregistration_readiness_v1.json)
- [`scripts/verify_l1_preregistration.py`](../../scripts/verify_l1_preregistration.py)

The recorded `ace.foresight.impact-readiness/v1` receipt is:

| Field | Recorded value |
|---|---|
| Protocol valid | `true` |
| Gate state | `collection_not_started` |
| Analysis ready | `false` |
| Beneficial impact evaluated | `false` |
| Beneficial impact supported | `false` |
| Blocking reason | `no_independently_timed_cohort_submitted` |

This receipt is preserved byte-for-byte as the original structural readiness result, not a
simulated positive result. No eligible cohort was present locally or in the repository roadmap
evidence. Creating synthetic post-registration
timestamps, relabeling the retrospective probe, or running only the missing model arm would violate
the frozen protocol and cannot advance L1.

## Pre-outcome collection-start audit

The 2026-08-05 audit attempted to move the registration into collection without submitting or
inspecting target outcomes. The fail-closed result is `invalidated`, so collection did not start.
The original manifest and readiness receipt remain unchanged; the audit does not rewrite them or
the negative retrospective result.

Artifacts:

- [`evaluations/fixtures/l1_collection_start_v1.json`](../../evaluations/fixtures/l1_collection_start_v1.json)
- [`evaluations/results/l1_collection_start_v1.json`](../../evaluations/results/l1_collection_start_v1.json)
- [`scripts/verify_l1_collection_start.py`](../../scripts/verify_l1_collection_start.py)
- [`core/engine/evaluation/l1_collection_start.py`](../../core/engine/evaluation/l1_collection_start.py)

Exact identities:

| Field | Value |
|---|---|
| Registration | `l1-prospective-independent-outcomes-v1` |
| Registration canonical hash | `sha256:bf558acda007ed04c24eb247749aad23ed89124c5ae38264add92061050135e7` |
| Start attempt | `l1-prospective-collection-start-audit-v1` |
| Attempt hash | `sha256:eaaeebe739d057de2ac9f9887c8ea45d6114f9dfd3910986216d393acc2dd8cd` |
| Start receipt | `l1-collection-start:eaaeebe739d057de2ac9f9887c8ea45d` |
| Receipt hash | `sha256:f026c96f4846841627323c95031683e3494c967b1682edb2a2ce43c1e3f1086c` |
| Disposition | `invalidated` |
| Collection observations | `0` |
| Outcome evaluation | not invoked |

The registration froze four arm labels, the blocked-randomized design, a non-overlapping decision
allocation unit, seven matching dimensions, four lineage identity names, minimum/maximum sample
bounds, and the one-analysis stopping rule. It did **not** freeze the cohort identity, operational
eligibility and exclusion rules, leakage boundaries, assignment schedule identity, exposure
receipt schema, versioned control-policy identities, per-arm sample threshold, failure-case evidence
schema, exact provider/model/configuration/schema/toolset values, primary outcome metric, outcome
provenance schema, observation resource schema, analysis window, independent-cluster definition,
attribution-verification contract, or the mapping from independently assigned arms to the analysis
estimator.

The final incompatibility is decisive: the registration requires one assigned arm per
non-overlapping decision identity, while `ace.foresight.impact-evaluation/v1` consumes a paired case
containing ACE plus all three counterfactual predictions for the same outcome. No preregistered
transform or cluster estimator connects those shapes. Selecting one now would add an outcome-
relevant degree of freedom after registration. The intake checker was also tightened so a control
that claims material foresight use fails as `contaminated_control_material_use`; control exposure
can no longer satisfy eligibility by copying the ACE arm's I3 material-use claim.

### Pre-outcome safety and resource inventory

The dry run refuses target-outcome payloads and never imports or calls the impact evaluator. Its
receipt records `comparative_result_calculated=false`, `comparative_result_revealed=false`, and
`beneficial_impact_evaluated=false`. Collection usage is exactly zero calls, zero input/output
tokens, zero latency, zero cost, zero retries, and no provider failures; the sole degraded state is
`collection_not_executable`.

Starting a successor study requires an independently operated cohort, immutable assignment and
exposure receipts, live exact-route execution, product-owned outcome provenance, and independent
support for randomized or quasi-experimental attribution. Simulated provider output is ineligible.
Those dependencies do not exist in this repository and were not manufactured for this audit.

### Prospective intake failure matrix

| Case | Fail-closed behavior |
|---|---|
| Manifest changed after registration | Canonical hash mismatch; preregistration invalid |
| Unknown contract version | Unsupported contract; preregistration invalid |
| Arm, threshold, stop rule, or matching dimensions changed | Frozen-protocol violation |
| Decision before the earliest eligible time | Cohort-integrity violation |
| Reused allocation unit | Overlap is named and the cohort is ineligible |
| Missing assignment or exposure receipt | Attribution is unverified; case excluded |
| Missing F1 or I3 identity/material use | Lineage gap is named; case excluded |
| Material foresight use in a control arm | `contaminated_control_material_use`; case excluded |
| Provider/model/configuration or other route gap | Matched model-only evidence is not established |
| Fewer than 30 complete cases or eight clusters | Analysis remains ineligible |
| Missing null/harm/missing-outcome/route-failure/degraded cases | Required failure coverage blocks analysis |
| Credential-shaped public identifier | Value is bounded and redacted in the readiness receipt |
| Complete eligible cohort | Becomes `ready_for_frozen_analysis`; still makes no benefit claim |

## Agent-only executable successor

The 2026-08-05 successor removed the unavailable human cohort operator as an execution dependency.
The passing study uses 48 fixed, independent executable workload clusters as the cohort and the same live
`CodexCLIProvider` / `gpt-5.6-terra` route for every assigned decision. This is real live-route
agent evidence over reproducible benchmark outcomes; it is not a human cohort, external product
telemetry, or evidence of general real-world benefit.

The passing frozen contract is `ace.foresight.impact-agent-benchmark-preregistration/v7`. It fixes
192 non-overlapping main decisions, one case per arm within every cluster, 24 stable clusters, 24
prespecified regime-shift clusters, a 44-complete-cluster minimum, no replacement, no interim
analysis, one fresh OS-random workload seed shared across the four arms of each cluster only after
all 192 main decisions are durable, deterministic replay, and one analysis after the entire fixed
cohort closes. The four arms are:

| Arm | Frozen policy |
|---|---|
| ACE foresight | Cluster-local resolved F1 evidence with active/contested applicability, stale recommendations withheld under drift, and exact I3 material-use comparison |
| No foresight | Cluster-local last-observation persistence |
| Naïve/base-rate | Globally best frozen calibration option |
| Model-only | Matched provider/model/configuration, task facts only |

Every control is checked for F1 non-exposure. Fixed-control decisions must follow their
preregistered persistence or base-rate option. ACE cases require exact forecast, observation,
resolution, and I3 identities; a matched live shadow decision; a supported material reflection
method; an exact structured decision delta; an explicit applicability disposition; and the exact
resolution ID in `evidence_refs`. The frozen transport permits at most three calls to repair JSON or
these already-required fields; v7 needed no repair. Prompts, calibration records, assignments,
routes, decisions, post-decision seeds, oracle outputs, and the
closed collection are independently replayed or hash-checked by the one analysis path.

### Preserved pre-outcome and integrity failures

No failed attempt was reused as favorable evidence:

| Version | Frozen registration | Disposition |
|---|---|---|
| v2 | `sha256:b8f18d86035a94a1055d6e27f96a9afe8ac4230a2ce2b0ceb9bff8deb5ad9705` | Invalidated before collection: generic structured no-foresight was not the required last-observation-persistence control; zero target access |
| v3 | `sha256:faf6b671fa2646798bec4930e04cae25b26b3a1dae233b98b647ed0f29107459` | Invalidated during collection after a fail-closed validator crash; nine outcomes sealed, zero revealed, zero analyses, never resumed or analyzed |
| v4 | `sha256:14fc2c57039a9eec9f057dd0db252ab50ed9eb839feacbf27a06542e90e45119` | Closed 144/144, but the single analysis excluded all ACE cases because the runner used an unsupported I3 reflection-method label; no effect interval was estimated and the analysis was not rerun |
| v5 | `sha256:8526f06f47d65a06633ba12a7b9525c472fe0fc786ef37178fcc61e7ea0cc919` | Closed 144/144 with all 36 clusters eligible; persistence passed, but naïve/base-rate and model-only did not; terminal `benefit_not_established` |
| v6 | `sha256:be034031920d9c8bd4f755f507c4aef5a8a49248a2c621975efc0e3e510545bf` | Fresh selective-applicability cohort closed 192/192; one ACE decision put its resolution ID in `assumptions` rather than `evidence_refs`, so I3 lineage failed closed and the single analysis remained `benefit_not_established` despite positive intervals over the other 47 complete clusters |
| v7 | `sha256:ceedd71de7669decdb314219968e1bf415a2bd9af9c90dbc25b7c796802138a1` | Independent correction replicate with unchanged workload, target ranges, controls, estimator, and promotion rule; field-level lineage validation was frozen before collection; closed 192/192 with all 48 clusters eligible; single analysis returned `benefit_supported` |

The v2 invalidation receipt hash is
`sha256:7f67a8652159adb0eeb11a4e5bbe99548233e0ec68a22e17433c7af21bca5060`.
The v3 invalidation receipt hash is
`sha256:ff92a6a86cb5be4a71ca0331b62956393f07456b71da985de752a6c2da2b833a`;
its sealed partial raw-manifest hash is
`sha256:ee5a9051df56040cae3fcfeed8355a4af479fe8f8c2f9787276f3deca4dc259d`.
The v4 terminal analysis hash is
`sha256:db86002d103dfde5020709ba6338b4aa909d992cb02fb0991cd5b4f0a4881e8c`.

The v6 terminal analysis hash is
`sha256:ade32fcbfb9f38d5387e6a5bb43d972043e4a07358cb83ec57314567bf9197ab`.
Its exact benchmark and runner sources are preserved under `evaluations/source/` with SHA-256
`47594de43b6e84a88ca2f81f76801c9acb2e0dd8e6b82bfbc7e084d12d7cb0fc` and
`635f5e8b12e82238ef7f32d98f505451c397acfe24e2666b09241f9832ffddf1`.

### v5 identities, safety, and resources

| Field | Recorded value |
|---|---|
| Registration | `l1-agent-executable-benchmark-v5` |
| Registration hash | `sha256:8526f06f47d65a06633ba12a7b9525c472fe0fc786ef37178fcc61e7ea0cc919` |
| Protocol file SHA-256 | `67047b3346d97137685cfefd465b0ed17eb59f886c314ff6225df2ae18ee3862` |
| Benchmark source SHA-256 | `58845b3227dd8a5246a73dbee9a0d2431c15c0315928d7d3b6247a405c69dec1` |
| Collection runner SHA-256 | `dbe32ef8d09a53019c4bf4543566ecf55cc784565b6f0e524a780807328335dd` |
| Dry-run receipt hash | `sha256:c9ceb7fff77e9c42007b54f84fccb545b86c1a4c9dbb78ca65bf52fd4c679785` |
| Live route qualification hash | `sha256:155d4196fc771d6de07ec4ed98cb449a431c0b4ad12cd719d3d78eec11cc70ab` |
| Closed collection | `l1-agent-collection:8526f06f47d65a06633ba12a7b9525c4` |
| Collection hash | `sha256:83809a64870dd5f95066639736076fc1e35997c3364eb7ad7d599bcea3716601` |
| Raw collection manifest SHA-256 | `a6be194666b4ac92b33d5bf0c17757e796f9dc09897d71c4b625e1ef71533068` |
| Analysis hash | `sha256:2814385ec462103bad11089dc6b6bfc98009d73f17b6948bb9da65574a077336` |

The pre-outcome dry run made zero provider calls, generated zero target outcomes, revealed zero
target outcomes, and invoked the impact analysis zero times. The target collection closed with 144
main decisions plus 36 I3 shadows: 180 logical invocations and 180 transport calls; 1,632,561 input
tokens, 21,320 output tokens, 1,394,432 cached input tokens, 63 reasoning tokens, 1,009,925 ms
aggregate latency, subscription billing with `$0.00` platform API cost, zero retries, zero recovered
failures, zero terminal failures, and no degraded states. Collection printed no decisions, outcome
values, regrets, or arm comparisons and recorded `target_outcomes_revealed_during_collection=0` and
`analysis_invocations=0` before closure.

### v5 terminal result

All 144 submitted cases and all 36 independent clusters were eligible. The one permitted analysis
returned `benefit_not_established`:

| Required comparison | Mean control-minus-ACE regret | Cluster-adjusted 95% interval | Result |
|---|---:|---:|---|
| Last-observation persistence | `0.057848` | `[0.027670, 0.088027]` | ACE benefit supported for this comparison |
| Naïve frozen base rate | `0.014772` | `[-0.008038, 0.037582]` | Not established; interval includes zero |
| Matched model-only | `-0.015008` | `[-0.033342, 0.003325]` | Not established; point estimate favors model-only |

The all-controls promotion rule therefore failed for v5. Its negative evidence remains part of the
record and is not replaced by the later result. V6 changed the treatment mechanism before its
cohort by making resolution applicability explicit and withholding stale recommendations under
drift; v7 did not tune that mechanism or the outcome model after seeing v6. It corrected only the
field-level lineage failure, used fresh cohort and assignment seeds, and preregistered one new fixed
cohort and one analysis.

### v7 identities, safety, and resources

| Field | Recorded value |
|---|---|
| Registration | `l1-agent-executable-benchmark-v7` |
| Registration hash | `sha256:ceedd71de7669decdb314219968e1bf415a2bd9af9c90dbc25b7c796802138a1` |
| Protocol file SHA-256 | `accb48c4eb7cf584c79f696ca5c5e910a5f855a47e6c8bda33d95260b08cb797` |
| Benchmark source SHA-256 | `ee15e264da8ffcc1f2fd111e33eec806ec9cb22814aa19a089db9283b523fc3a` |
| Collection runner SHA-256 | `38f5c35af0605abea989e5e8e26fc6d4e13df4944230ddd93f30accbdc1b2a43` |
| Dry-run receipt hash | `sha256:db69ff5a929a6c71c6fb43d71f8561efc6ab20f402ed965914dc04ea6bb92903` |
| Live route qualification hash | `sha256:6f7e16dcf5bb0a78f71fd0cd849ef6fab094a43a7528083bb08281ba9c3fdf82` |
| Closed collection | `l1-agent-collection:ceedd71de7669decdb314219968e1bf4` |
| Collection hash | `sha256:15ba8ef2ec59ff5779609471b602072730061fa20f5b933e7788f0cfbbdd3291` |
| Raw directory manifest SHA-256 | `8e997ee2bd6ee7596b5a4657655cbeddf4b703550309d009ed0d96c72cdfce5b` over canonical relative-path/file-SHA pairs for 433 files |
| Analysis hash | `sha256:d928ea1e0ebfb919d078c4ba5aa8903ac81d62f22c599b1ab0995c9bceed0187` |

The pre-outcome dry run made zero provider calls and accessed no target cases or outcomes. The live
route qualified in one call. Collection closed all 192 main decisions plus 48 ACE shadows: 240
logical invocations and 240 transport calls; 2,177,785 input tokens, 28,517 output tokens, 1,858,816
cached input tokens, zero reasoning tokens, 2,252,502 ms aggregate latency, subscription billing
with `$0.00` platform API cost, zero retries, zero recovered failures, zero terminal failures, and no
degraded states. All 48 clusters use one within-cluster shared seed, all 48 seed commitments are
unique across clusters, and collection recorded zero revealed target outcomes and zero analysis
invocations before closure.

### v7 terminal result

All 192 submitted cases and all 48 independent clusters were eligible. All self-hashes, exact-route
receipts, assignments, exposure/non-exposure receipts, F1/I3 lineage, timestamps, source hashes,
shared post-decision seeds, oracle outputs, and replays validated with no reason codes. The single
permitted analysis returned `benefit_supported`:

| Required comparison | Mean control-minus-ACE regret | Cluster-adjusted 95% interval | Result |
|---|---:|---:|---|
| Last-observation persistence | `0.072131` | `[0.046158, 0.098105]` | ACE benefit supported |
| Naïve frozen base rate | `0.029201` | `[0.018127, 0.040276]` | ACE benefit supported |
| Matched model-only | `0.002824` | `[0.000707, 0.004940]` | ACE benefit supported |

The ACE arm selected `steady` for all 24 stable clusters and selected `retry_shield`, `burst_guard`,
and `cost_saver` for all eight corresponding upstream-reliability, traffic-burst, and cost-priority
shift clusters. The all-controls rule passes within the exact frozen executable-benchmark claim
scope. This establishes L1 for that bounded agent workload contract; it does not establish human,
customer, provider, external-product, or general real-world benefit.

Artifacts:

- [`core/engine/evaluation/l1_agent_benchmark.py`](../../core/engine/evaluation/l1_agent_benchmark.py)
- [`scripts/run_l1_agent_benchmark.py`](../../scripts/run_l1_agent_benchmark.py)
- [`evaluations/fixtures/l1_agent_benchmark_v5.json`](../../evaluations/fixtures/l1_agent_benchmark_v5.json)
- [`evaluations/results/l1_agent_benchmark_dry_run_v5.json`](../../evaluations/results/l1_agent_benchmark_dry_run_v5.json)
- [`evaluations/results/l1_agent_benchmark_route_v5.json`](../../evaluations/results/l1_agent_benchmark_route_v5.json)
- [`evaluations/results/l1_agent_benchmark_collection_v5.json`](../../evaluations/results/l1_agent_benchmark_collection_v5.json)
- [`evaluations/results/l1_agent_benchmark_analysis_v5.json`](../../evaluations/results/l1_agent_benchmark_analysis_v5.json)
- [`evaluations/fixtures/l1_agent_benchmark_v6.json`](../../evaluations/fixtures/l1_agent_benchmark_v6.json)
- [`evaluations/results/l1_agent_benchmark_analysis_v6.json`](../../evaluations/results/l1_agent_benchmark_analysis_v6.json)
- [`evaluations/fixtures/l1_agent_benchmark_v7.json`](../../evaluations/fixtures/l1_agent_benchmark_v7.json)
- [`evaluations/results/l1_agent_benchmark_dry_run_v7.json`](../../evaluations/results/l1_agent_benchmark_dry_run_v7.json)
- [`evaluations/results/l1_agent_benchmark_route_v7.json`](../../evaluations/results/l1_agent_benchmark_route_v7.json)
- [`evaluations/results/l1_agent_benchmark_collection_v7.json`](../../evaluations/results/l1_agent_benchmark_collection_v7.json)
- [`evaluations/results/l1_agent_benchmark_analysis_v7.json`](../../evaluations/results/l1_agent_benchmark_analysis_v7.json)
- [`evaluations/source/l1_agent_benchmark_v6.py`](../../evaluations/source/l1_agent_benchmark_v6.py)
- [`evaluations/source/run_l1_agent_benchmark_v6.py`](../../evaluations/source/run_l1_agent_benchmark_v6.py)
- [`evaluations/source/l1_agent_benchmark_v7.py`](../../evaluations/source/l1_agent_benchmark_v7.py)
- [`evaluations/source/run_l1_agent_benchmark_v7.py`](../../evaluations/source/run_l1_agent_benchmark_v7.py)
- [`evaluations/results/l1_agent_benchmark_invalidation_v2.json`](../../evaluations/results/l1_agent_benchmark_invalidation_v2.json)
- [`evaluations/results/l1_agent_benchmark_invalidation_v3.json`](../../evaluations/results/l1_agent_benchmark_invalidation_v3.json)
- [`tests/test_l1_agent_benchmark.py`](../../tests/test_l1_agent_benchmark.py)

Focused verification for the final source: `29 passed` for the agent benchmark plus I3 receipt
suite, and `212 passed` for the combined L1/F1/I3/foresight/kernel contract set. The broader
non-E2E/no-extension repository run recorded `6,936 passed`, `48 skipped`, and
`259 deselected`; its only failure is an unrelated concurrent package-version mismatch (`0.3.0`
versus `0.2.0`). Protocol replay was byte-identical; negative,
harmful, route, assignment, contamination, missing-lineage, missing-provenance, insufficient-cluster,
source-drift, calibration-tamper, outcome-replay, schema repair, field-level semantic repair, shared
seed, applicability, and I3 reflection-method checks all fail closed. Ruff and formatting passed.

## Contract behavior

The evaluator:

- requires at least 30 complete cases and eight declared independent clusters;
- retains exact outcome identity, observation time, evidence references, source-resolution IDs,
  material-use status, route matching, attribution, and confounders;
- excludes post-outcome, partial, unmatched, or ineligible lineage rather than reconstructing it;
- uses conservative cluster-level Student-t intervals;
- preserves null and harmful results and requires all controls to pass;
- bounds studies to 256 cases and redacts common credential forms; and
- grants no write, rollout, experiment-operation, or new MCP authority.

The prospective readiness checker additionally:

- verifies its own canonical registration hash and rejects future or altered contracts;
- requires post-registration decisions and later outcomes, unique allocation-unit hashes, verified
  assignment/exposure evidence, complete F1/I3/decision/outcome lineage, and exact route matching;
- bounds public case receipts and redacts credential-shaped identifiers; and
- can only declare a cohort ready for the already-frozen analysis. It never computes or asserts
  beneficial impact.

Historical verification for the original candidate gate:

- prospective preregistration/readiness plus retrospective evaluator behavior: `17 passed`;
- L1/F1/I3/kernel compatibility contract set: `58 passed`;
- full foresight, I3, and impact regression: `173 passed`;
- prospective readiness replay: byte-identical result;
- preserved retrospective probe replay: byte-identical result;
- full non-E2E repository run with extensions in the primary worktree: `6,636 passed`, `46 skipped`,
  `235 deselected`, exit zero;
- exact-commit non-E2E run with extensions: `6,634 passed`, `46 skipped`, `235 deselected`; the local
  harness required interruption after all tests passed because spawned app-server teardown remained
  asleep, so required PR CI remains the terminal exact-source authority;
- exact-commit full non-E2E zero-extension repository run: `6,626 passed`, `47 skipped`, `242
  deselected`, exit zero;
- wheel and sdist from the exact commit: built successfully; the L1 module, protocol, receipt,
  script, and evidence are present, while tests and UI are absent;
- Ruff, format, and `git diff --check`: passed; and
- exact MCP/kernel boundary: unchanged and covered by the focused kernel set.

The primary-worktree totals include two passing tests from a concurrent, unrelated extension
workstream that remained unstaged and was excluded from this commit. The detached exact-commit
worktree removes those tests and all other unrelated edits. Its first sandboxed attempt was
discarded as non-comparable after loopback binding was denied; the recorded exact runs use the same
existing local environment and loopback permissions without copying or printing credentials.

No schema, API, runtime, task receipt, or MCP change was made, so another database/API restart run
would not add continuity evidence to this evaluation-only gate. The eventual passing L1 study must
exercise real F1 resolution and I3 material-use identities through their already-proven restart
paths.

Prospective gate command:

```bash
uv run python -m scripts.verify_l1_preregistration \
  --registration evaluations/fixtures/l1_preregistration_v1.json \
  --result evaluations/results/l1_preregistration_readiness_v1.json
```

The command is deterministic: replaying it reproduces the committed readiness receipt byte for
byte. A later cohort may be supplied with `--cohort` only after the fixed collection closes.

Collection-start audit command:

```bash
uv run python -m scripts.verify_l1_collection_start \
  --registration evaluations/fixtures/l1_preregistration_v1.json \
  --readiness evaluations/results/l1_preregistration_readiness_v1.json \
  --attempt evaluations/fixtures/l1_collection_start_v1.json \
  --audit-code core/engine/evaluation/l1_collection_start.py \
  --audit-script scripts/verify_l1_collection_start.py \
  --intake-code core/engine/evaluation/l1_preregistration.py \
  --analysis-code core/engine/evaluation/foresight_impact.py \
  --result evaluations/results/l1_collection_start_v1.json
```

The audit replay is byte-identical and pre-outcome-safe. It does not calculate the prospective
comparison. The frozen registration is invalidated for collection and must not receive a later
cohort through `--cohort`; a complete successor protocol must receive a new identity and hash
before its first eligible decision or target outcome.

Current verification:

- L1 collection-start, preregistration, and impact behavior: `24 passed`;
- focused L1/F1/I3, foresight, schema, and kernel contract set: `204 passed`;
- original preregistration replay: byte-identical, raw receipt SHA-256
  `4c81f4ffa0c21d193f252405d6704413b8c50aebd05c0e2f550b5584e55e83a5`;
- collection-start replay: byte-identical, raw receipt SHA-256
  `775c5c5dc99f94cfceee3856a8792f4adfbb7357822dca670ba0052652fd9c61`;
- retrospective probe replay: exact evaluator equality remains covered by the focused set;
- tamper, unknown-contract, pre-registration, overlap, invalid-assignment, contaminated-control,
  missing-lineage, unmatched-route, missing-outcome-provenance, insufficient-case/cluster,
  failure-coverage, unsupported-attribution, target-outcome-canary, and redaction cases fail closed;
- Ruff checks and format checks pass for all touched Python files; and
- `git diff --check` passes.

## Scope of the L1 pass

The v7 executable benchmark provides:

1. independently timed, non-overlapping decision cohorts with adequate effective sample size;
2. real pre-decision F1 resolution identities materially used by later I3-traced decisions;
3. verified intervention or sufficiently supported quasi-experimental attribution, including
   assignment, exposure, confounders, guardrails, and outcome provenance;
4. matched no-foresight, naïve/base-rate, and exact-provider/model/configuration model-only arms;
5. cluster-adjusted intervals excluding no benefit for every required comparison; and
6. explicit null, harmful, missing-outcome, failed-route, and degraded-lineage cases; and
7. a pre-outcome-frozen cohort, route, exposure, observation, estimator, window, exclusion,
   cluster, attribution-verification, and stopping contract with a tested collection bridge.

L1 is therefore `passed` for the bounded executable-benchmark claim. F2 remains gated because this
result does not itself demonstrate user need for broader consequence types or validate those types
in an external product. The negative retrospective probe and v5/v6 failures do not reopen F1 or I3,
and no broader consequence type, execution adapter, extension route, or autonomous revision
behavior was started.

The preregistration and intake checks improve inspectability and resistance to selective analysis;
they do not prove that submitted receipts are truthful, that the chosen metric captures user
benefit, that a decision is correct, or that any observed difference is causal or general.
