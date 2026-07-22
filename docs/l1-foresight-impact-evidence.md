# L1 foresight-impact evidence gate

Date: 2026-07-22

Outcome: **L1 candidate — beneficial impact not established**

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

- [`evaluations/fixtures/l1_foresight_impact_v1.json`](../evaluations/fixtures/l1_foresight_impact_v1.json)
- [`evaluations/results/l1_foresight_impact_v1.json`](../evaluations/results/l1_foresight_impact_v1.json)
- [`scripts/evaluate_l1_foresight_impact.py`](../scripts/evaluate_l1_foresight_impact.py)

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

Verification for this candidate gate:

- focused evaluator behavior: `8 passed`;
- L1/F1/I3/kernel contract set: `27 passed`;
- full foresight, I3, and impact regression: `164 passed`;
- deterministic source transform and evaluation replay: byte-identical fixture and result;
- full zero-extension non-E2E repository run: `6546 passed`, `47 skipped`, `242 deselected`, with
  the same 21 inherited failures (20 provider-selection assumptions overridden by the active Codex
  app-server environment and one pre-existing roadmap-lane assertion);
- Ruff, format, and `git diff --check`: passed; and
- exact MCP/kernel boundary: unchanged and covered by the focused kernel set.

No schema, API, runtime, task receipt, or MCP change was made, so another database/API restart run
would not add continuity evidence to this evaluation-only gate. The eventual passing L1 study must
exercise real F1 resolution and I3 material-use identities through their already-proven restart
paths.

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
