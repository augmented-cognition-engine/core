# L1 foresight-impact evidence gate

Date: 2026-07-23

Outcome: **L1 candidate — protocol valid; collection not started; beneficial impact not established**

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

The second work packet freezes `ace.foresight.impact-preregistration/v1` before any new decision or
outcome collection. Its canonical SHA-256 is
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

This is the executed authoritative gate, not a simulated positive result. No eligible cohort was
present locally or in the repository roadmap evidence. Creating synthetic post-registration
timestamps, relabeling the retrospective probe, or running only the missing model arm would violate
the frozen protocol and cannot advance L1.

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
| Provider/model/configuration or other route gap | Matched model-only evidence is not established |
| Fewer than 30 complete cases or eight clusters | Analysis remains ineligible |
| Missing null/harm/missing-outcome/route-failure/degraded cases | Required failure coverage blocks analysis |
| Credential-shaped public identifier | Value is bounded and redacted in the readiness receipt |
| Complete eligible cohort | Becomes `ready_for_frozen_analysis`; still makes no benefit claim |

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

Verification for this candidate gate:

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

## What is required to pass L1

L1 remains candidate until a preregistered study provides:

1. independently timed, non-overlapping decision cohorts with adequate effective sample size;
2. real pre-decision F1 resolution identities materially used by later I3-traced decisions;
3. verified intervention or sufficiently supported quasi-experimental attribution, including
   assignment, exposure, confounders, guardrails, and outcome provenance;
4. matched no-foresight, naïve/base-rate, and exact-provider/model/configuration model-only arms;
5. cluster-adjusted intervals excluding no benefit for every required comparison; and
6. explicit null, harmful, missing-outcome, failed-route, and degraded-lineage cases.

F2 remains gated. The negative probe does not reopen F1 or I3, and no broader consequence type,
execution adapter, extension route, or autonomous revision behavior was started.

The preregistration and intake checks improve inspectability and resistance to selective analysis;
they do not prove that submitted receipts are truthful, that the chosen metric captures user
benefit, that a decision is correct, or that any observed difference is causal or general.
