# Graph-grounded calibrated foresight

> **Status:** F1 passed on 2026-07-22. The implemented engine remains experimental and the v1
> contract below is not yet a general 0.1.x compatibility promise. See the
> [F1 closeout evidence](evidence/f1-foresight-evidence.md).

**ACE provides graph-grounded, calibrated foresight. It projects conditional consequences of
decisions, exposes the mechanisms and uncertainty behind them, observes what actually happens,
and uses resolved forecasts to improve later reasoning.**

This is a bounded consequence model over a product or domain. It is not a foundation-scale learned
model of the physical world, a latent simulator trained from raw sensory data, or a claim that ACE
can infer reliable causality from sparse observations. The configured model supplies general
inference; ACE owns the local state, forecast structure, provenance, observation, reconciliation,
and calibration loop.

## Why foresight exists

ACE should help a person reason about what a decision may cause before acting, not merely explain
the decision afterward. Useful foresight therefore has to do more than generate plausible future
prose. It must:

1. state the intervention and conditions under which the forecast applies;
2. separate the expected future from a no-action baseline and credible alternatives;
3. expose the mechanism, evidence, assumptions, and uncertainty behind each consequence;
4. define observable resolution and falsification rules before the outcome is known;
5. preserve prediction and observation as separate, provenance-bearing records; and
6. make later use of resolved forecasts inspectable and evaluate whether that use helped.

Sparse evidence must widen uncertainty or cause abstention. It must not be hidden behind confident
language.

## Current implementation boundary

The experimental engine already provides important pieces of the loop:

- `forecaster.py` attaches measurable predictions, horizons, leading indicators, risks, and
  falsification conditions to decisions;
- `planner.py`, `fork_planner.py`, and `value_model.py` project and compare bounded hypothetical
  paths;
- `signal_engine.py` and `scenario_builder.py` turn selected internal trends into scenarios;
- `reconciler.py` compares predicted capability deltas with later measurements and writes outcomes;
- calibration records can be loaded into later orchestration context; and
- the Living Product Graph keeps predictions separate from observed outcomes.

These components establish a scaffold, not the completed claim. The current forecast context is
limited, point estimates dominate, intervention and confounder attribution are weak, leading
indicators are not a general active-resolution mechanism, calibration is coarse, and material
benefit to later decisions has not been demonstrated. Rollouts and signal-driven scenario branches
also do not yet share one complete, resolvable forecast lifecycle.

### Implemented F1 foundation

The implemented F1 foundation adds:

- versioned `ace.foresight.forecast/v1` and `ace.foresight.resolution/v1` projections;
- versioned `ace.foresight.intervention-observation/v1` records captured through the existing
  `ace_capture` tool, preserving the eleven-tool boundary;
- versioned `ace.foresight.indicator-observation/v1` evidence and
  `ace.foresight.indicator-state/v1` operational summaries;
- versioned `ace.foresight.outside-view-baseline/v1` empirical reference classes and comparative
  resolution diagnostics;
- versioned `ace.foresight.prediction-score/v1` consequence scores using declared central
  predictive intervals for continuous deltas;
- versioned `ace.foresight.comparator-observation/v1` evidence and
  `ace.foresight.comparator-state/v1` operational summaries;
- versioned `ace.foresight.comparator-plan/v1` advisory measurement designs frozen with forecasts;
- versioned `ace.foresight.measurement-observation/v1` raw samples and
  `ace.foresight.measurement-ingestion/v1` fail-closed assembly receipts;
- additive schema v146-v154 fields without rewriting historical predictions, observations,
  outcomes, or calibration;
- explicit legacy, partial, malformed, and unsupported-version compatibility states;
- conditional forecast fields for applicability, no-action baselines, consequence ranges,
  mechanisms, assumptions, dependencies, confounders, evidence references, indicators, and
  falsification;
- product-scoped current-state baselines from the latest available capability-quality observations,
  including timestamps and record references, with explicit incompleteness when evidence is absent;
- explicit `confirmed`, `contradicted`, `mixed`, `unresolved`, `invalid`, and `open` resolution
  states;
- non-scorable cancellation, failed-applicability, missing-observation, missing-evidence, and
  unobserved-intervention paths—none silently become neutral calibration;
- immutable forecast payloads during reconciliation;
- product-scoped calibration reads and writes, excluding unscoped legacy calibration from later
  orchestration influence;
- product-scoped, provenance-bearing intervention observations with deterministic request identity,
  explicit status, timing, exposure, applicability evidence, confounders, and evidence gaps;
- identical-retry replay and conflicting-retry rejection, including runtime-restart continuity; and
- an evidence-gated resolution trigger: cancellation and failed applicability resolve immediately
  as invalid and unscored, while valid interventions wait for the forecast horizon and sufficient
  outcome evidence;
- frozen machine-resolvable capability-quality indicator rules, evaluated on quality-change and
  hourly reconciliation paths with restart-safe idempotent evidence; and
- explicit manual status for prose-only indicators rather than invented automatic measurements;
- product-isolated retrieval of settled, applicable, scored intervention outcomes using explicit
  capability-overlap, discipline, and horizon similarity features;
- explicit cold-start maturity states: zero local cases remain useful `cold_start` forecasts,
  one or two cases are `anecdotal`, three or more may be `provisional`, and only a larger effective,
  similar, low-uncertainty sample becomes `supported`; and
- resolution-time comparison of the frozen model projection against the frozen empirical prior,
  clearly labeled as an absolute-error diagnostic rather than a proper score; and
- central interval score, interval coverage, interval width, and point error for eligible
  continuous consequences, with explicit abstention when interval semantics are missing; and
- optional observed no-action, holdout, phased-rollout, and alternative-intervention comparators,
  with deterministic difference-in-differences effects, attribution strength, confounders,
  provenance, and explicit resolution eligibility; and
- optional target-grounded comparator plans that propose conditional assignment, timing,
  measurement sources, guardrails, and fallback observation without pretending the plan is data;
  and
- deterministic plan-to-observation linkage that records execution alignment, deviations, and an
  effective attribution strength without converting plan compliance into causal proof; and
- automatic, idempotent assembly of explicit plan/target/arm/phase structured metric samples into
  the existing comparator contract only when the complete measurement matrix is consistent.

F1 is passed within its documented continuous-delta v1 scope. The engine does not guarantee that
every forecast has observed baseline evidence or automatically execute a comparator plan.
Measurement Ingestion v1 accepts only
explicit structured samples; it does not connect arbitrary telemetry sources or infer experiment
arms from generic capability-quality history. A captured
comparator is not automatically causal: even a declared randomized design is not independently
verified by capture; matched, quasi-experimental, and observational designs retain weaker
attribution labels. ACE also
does not yet automatically evaluate indicators outside capability-quality measurements, properly
score binary or categorical consequences, establish reliability curves from adequate samples, or
prove beneficial later decision use.

### Intervention Observation v1

The supported thin-client capture path accepts `observation_type="intervention"` with a structured
`intervention` payload. It requires a caller-stable `request_id`, decision and prediction identities,
observed status and time, and may include applicability-condition observations, exposure, evidence
references, confounders, missing evidence, and a reason. The authenticated product owns the record;
both linked records must belong to that product and the prediction must belong to the decision.

The record identity is derived from product plus request ID. Repeating an identical request returns
the existing observation; reusing the request ID with different content returns a conflict and never
overwrites the first observation. Intervention records are not synthesized into generic learned
prose. The hourly reconciler reloads the latest persisted intervention record, so in-memory event
delivery is not required for eventual resolution after restart.

### Active leading indicators

Forecast v1 can freeze optional machine-resolvable rules beside each prose leading indicator. A
rule names a capability-quality target, optional dimension, threshold operator, and the evidence
effect when the rule is met or not met. Supported operators are `gte`, `lte`, `delta_gte`, and
`delta_lte`. Delta rules require a provenance-bearing baseline; without one their evaluation is
recorded as inconclusive rather than guessed.

Quality-change reconciliation and the hourly restart-recovery path evaluate these frozen rules.
Every evaluation becomes a separate, idempotent Indicator Observation v1 record. The prediction's
replaceable Indicator State v1 projection aggregates only the latest observation for each indicator
as supporting, weakening, falsifying, mixed, inconclusive, or unobserved. It may update before the
forecast horizon, but it never rewrites the forecast contract.

Indicators without a valid structured rule remain explicitly `manual`. Manual evidence can be
captured through the existing `ace_capture` tool with `observation_type="forecast_indicator"` and a
structured `indicator` payload. A falsifying leading indicator is an early warning, not by itself a
scored final outcome: final resolution still requires intervention applicability and sufficient
outcome evidence under the frozen resolution rule.

### Comparator Planning v1

New forecasts may freeze an optional `ace.foresight.comparator-plan/v1` beside their consequences.
The plan can recommend a no-action cohort, holdout, phased rollout, or alternative intervention;
name an assignment design and unit; list conditions an operator must confirm; define target-aligned
baseline and outcome sources; propose cadence and duration; and record operational, privacy,
fairness, safety, and stop guardrails. Plans are readable through
`GET /foresight/{product_id}/comparator-plans` and the Living Product Graph without adding an MCP
tool.

The plan exists to help a team with no historical outcomes create better future evidence. It does
not make existing data a prerequisite. Model-suggested `feasible` designs are downgraded to
`conditional` until an operator confirms real constraints. ACE does not invent a statistically
sufficient sample size when variance and minimum-effect inputs are absent; the plan explicitly
records `sample_size.state="not_estimated"` instead.

Comparator plans are frozen forecast-time proposals, not observations. Every normalized plan is
marked `evidence_status="plan_only_not_observed"` and `resolution_eligible=false`. Missing plans do
not make a cold-start forecast incomplete. If a concurrent comparison cannot be run, the plan
retains pre/post observation as a fallback while stating that attribution is not identified.
In plain language, its evidence status is **plan only, not observed**, and its sample size state is
**not estimated** until the required statistical inputs exist.

### Plan-to-Observation Linkage v1

Every proposed Comparator Plan v1 receives a deterministic, product-isolated `plan_id` derived from
its decision scope and frozen contents. A later comparator observation may explicitly name that ID;
a foreign or mismatched ID fails closed. When no ID is supplied, ACE may link only the single plan
already frozen on the same prediction. This convenience does not assert that the plan was followed.

ACE compares the planned and observed comparator type, assignment design, measurement targets,
assignment unit, eligibility criteria, minimum duration, and guardrail breaches. Caller-declared
execution deviations remain visible beside deterministic differences. The resulting state is
`aligned`, `partially_aligned`, `not_aligned`, or `not_planned`.
In plain language, an execution is **aligned, partially aligned, not aligned, or not planned**.

Alignment controls provenance, not truth. Full alignment preserves the attribution label supported
by the observed design. Missing execution details or partial alignment downgrade that label;
core design or target mismatches become `not_aligned` and receive only limited plan-supported
attribution. No alignment state independently verifies randomization or establishes causality.
Resolution records preserve the plan ID, alignment state, deviations, and effective attribution
strength while leaving the original forecast and plan unchanged.

### Measurement Ingestion v1

The existing `ace_capture` tool accepts `observation_type="forecast_measurement"` with a structured
`measurement` payload. Each sample must identify its frozen `plan_id`, measurement `run_id`, target
capability, metric and unit, intervention or comparator arm, baseline or outcome phase, numeric
value, measurement time, shared observation window, observed comparison type and design, and
evidence references. The v1 supported source is deliberately narrow: `structured_metric`.

ACE stores every valid sample as `ace.foresight.measurement-observation/v1`. A raw sample is marked
`evidence_status="raw_sample_not_effect"` and `resolution_eligible=false`; it cannot directly alter
a prediction or outcome. After each capture, ACE groups samples by product, prediction, frozen
plan, and run. The `ace.foresight.measurement-ingestion/v1` receipt lists required and missing
slots, conflicts, source support, sample counts, and the authority boundary. Product-scoped reads
are available at `GET /foresight/{product_id}/measurements` and
`GET /foresight/{product_id}/measurement-ingestions`, and both projections appear in the Living
Product Graph.

For every planned target, a complete run requires exactly one value for each cell:

```text
                 baseline    outcome
intervention       one         one
comparator         one         one
```

ACE fails closed on missing or duplicate cells, unsupported sources, absent evidence references,
foreign plans, unplanned targets or metric/unit pairs, inconsistent windows or execution metadata,
and observed comparison types or designs that differ from the frozen plan. A partial run remains
`collecting`; an ambiguous run becomes `conflicted`. Neither creates comparator evidence. Only a
complete, consistent run becomes `ingested`, at which point ACE deterministically creates the
ordinary plan-linked Comparator Observation v1 and lets the existing horizon and applicability
gates decide whether resolution is possible. Identical retries replay; conflicting request-ID
reuse is rejected.

This adapter observes; it does not operate. Its receipt explicitly states that it does not assign
cohorts, run experiments, or change rollouts. Generic `capability_quality` rows remain usable for
ordinary pre/post resolution and indicators, but cannot be promoted into comparator evidence
because they lack explicit arm and phase identity. Design labels remain caller-observed and are not
independently verified; automatic assembly therefore does not establish causality.

### Observed Comparator v1

Observed comparators are optional evidence captured after a decision; they are never required to
create a cold-start forecast. The existing `ace_capture` tool accepts
`observation_type="forecast_comparator"` with a structured `comparator` payload naming the original
decision and prediction, comparator type and design, observation window, evidence, confounders, and
one or more target measurements.

Each target supplies intervention and comparator values before and after the observation window.
ACE deterministically computes:

```text
intervention delta = intervention after - intervention before
comparator delta   = comparator after - comparator before
observed effect    = intervention delta - comparator delta
```

The result is eligible for resolution only when the design is known, measurements are complete,
targets belong to the frozen forecast, and evidence gaps are absent. Unknown or incomplete designs
are still retained and readable but cannot silently affect scoring. Randomized designs are labeled
with stronger attribution, but capture alone does not independently verify randomization or assert
causality. Matched and quasi-experimental designs are moderate, while observational designs are
limited. Recorded confounders remain visible in the final resolution.

An eligible comparator can supply observed effect deltas once the original forecast horizon is
reached and intervention applicability has been established. It does not close a valid forecast
early, does not mutate the forecast or its model-inferred no-action baseline, and does not poison
ordinary pre/post resolution when comparator evidence is absent or ineligible. Product-scoped
reads are available at `GET /foresight/{product_id}/comparators`.
Comparator payloads may also include actual assignment, eligibility, guardrail, deviation, and plan
identity details under `execution`; these are compared with the frozen plan rather than trusted as
proof that the plan was followed.

### Grounded outside-view baselines

Before a new forecast is frozen, ACE retrieves up to 200 resolved outcomes from the same product
and selects at most 12 settled analogues. Eligible cases must be scored, applicable, in a settled
resolution state, closed before retrieval, and overlap at least one forecast target. Repeated
outcomes for one prediction count once. Ranking is deterministic and exposes three features:
capability overlap, exact discipline match, and horizon similarity.

For each target capability, Outside-View Baseline v1 records the selected outcome, prediction, and
decision identities; observed deltas; similarity and feature values; weighted empirical mean;
observed range; raw and effective sample sizes; a 90% uncertainty interval; retrieval time; and
fixed limitations. Zero eligible local cases is `cold_start`; one or two is `anecdotal`; three or
more can become `provisional`. `supported` requires at least eight raw cases, effective sample size
of five, mean similarity of 0.4, complete target coverage, and an uncertainty half-width no larger
than 0.25 on the bounded delta scale. These are conservative product guardrails, not a universal
statistical-sufficiency claim. Failed retrieval is `unavailable`.

Provisional or supported reference classes show the per-target numerical difference between the
independent model projection and empirical prior. `aggregation_applied` is false: this packet
exposes disagreement but does not silently blend the two views. Cold-start and anecdotal history
never make a forecast incomplete; they widen the visible evidence gap while ACE remains useful
from the current graph, mechanisms, assumptions, and model inference.

These analogues are settled *intervention* outcomes. They provide an observational reference class,
not a causal estimate and not a no-action counterfactual. Forecast v1 therefore freezes the prose
no-action baseline as `model_inference_only`; any later observed comparator remains separate
resolution evidence and does not rewrite that label. At resolution,
ACE can compare mean absolute delta error for the model forecast and a provisional or supported
frozen outside view. The comparison is persisted with the outcome and never rewrites the forecast.
It is useful comparative evidence, but is not itself a prediction-type-specific proper score.
Prediction Score v1 supplies the implemented proper score for eligible continuous deltas.

### Prediction Scoring v1

Every new continuous-delta consequence must freeze a point estimate, lower and upper bounds, and
the coverage represented by those bounds. The current forecaster requests a central 80% predictive
interval and stores `interval_coverage=0.8`; model confidence is not reinterpreted as interval
coverage. Historical forecasts without declared coverage remain readable but abstain from proper
scoring.

At an eligible resolution, Prediction Score v1 applies the central interval score. Lower scores are
better: the score rewards narrow intervals that contain the outcome and penalizes misses according
to the declared coverage. ACE also records coverage, width, and absolute point error as diagnostics.
Cancelled, inapplicable, unresolved, missing-observation, malformed, and unsupported prediction
types remain unscored with an explicit reason.

When a provisional or supported outside view has a usable observed distribution, ACE derives a
predictive interval at the same coverage and scores both views with the same rule. Unlike interval
coverages are never pooled in product summaries. The previous bounded absolute-delta calibration
number remains available as a labeled compatibility diagnostic; it is not presented as a proper
score. Binary Brier scoring, categorical scoring, reliability curves, and validated aggregation
remain future work.

## Passed F1 target contract

Every F1-supported continuous-delta forecast must have stable identity and retain the following
information.

### Decision and applicability

- decision or candidate intervention identity;
- product or domain scope;
- responsible actor and forecast contributors;
- implementation conditions, degree of exposure, and expected start time;
- current-state baseline with observation time and provenance;
- no-action baseline and any compared alternative;
- horizon and explicit resolution deadline; and
- status of the intervention: proposed, authorized, started, partial, completed, cancelled, or
  unknown.

### Consequences

Each predicted consequence must declare:

- affected entity, metric, unit, and direction;
- magnitude as a range or probability distribution rather than unjustified precision;
- prediction type and the probability or interval coverage represented by its estimate;
- time window or lag;
- probability or confidence with its meaning made explicit;
- first-, second-, or later-order position in the consequence chain;
- proposed mechanism linking the decision to the consequence;
- supporting evidence, analogous settled cases, and provenance;
- assumptions, dependencies, and plausible confounders;
- leading indicators and evidence that would change the forecast; and
- falsification and resolution rules that can be applied without rewriting the forecast.

Mechanism edges are causal hypotheses. ACE must not present them as established causal facts unless
their evidence and assertion state justify that label.

### Observation and resolution

A resolution record must preserve:

- the original forecast unchanged;
- whether the intervention actually occurred and whether applicability conditions held;
- observed values, time window, sources, and provenance;
- resolution state: confirmed, contradicted, mixed, unresolved, invalid, or still open;
- missing evidence, measurement failures, assumption failures, and material confounders;
- forecast error computed with a scoring rule appropriate to the prediction type; and
- a bounded correction or lesson eligible for later retrieval without becoming automatic truth.

An absent observation is not a neutral outcome. A cancelled intervention is not a failed forecast.
A changed assumption is not silently scored as though the original conditions held.

## Projection and comparison

Foresight should combine two views:

- **Outside view:** reference classes, base rates, and analogous settled decision/outcome records.
- **Inside view:** the mechanisms, constraints, dependencies, and distinctive facts of the current
  case.

Credible branch diversity requires independently produced views before synthesis. A single model
response that labels three branches is not evidence of three independent forecasts. Aggregation
should expose disagreement and use relevant, sample-size-aware calibration rather than raw model
confidence or role labels alone.

Option comparison should consider expected benefit, downside and tail risk, cost, time, hard
constraints, reversibility, regret, robustness across branches, and value of additional
information. A mean capability score alone is not sufficient to recommend a path.

## Calibration and small-data learning

ACE does not need to learn environmental dynamics from raw data. It can improve data-efficiently
through settled-case retrieval, explicit mechanisms, and conservative online updating. The target
calibration hierarchy is:

```text
global prior
  -> discipline and prediction class
    -> product or private domain
      -> horizon, metric, evidence regime, and relevant contributor
```

Small samples must shrink toward a documented prior and surface uncertainty. Calibration must be
product-aware so private outcomes do not leak across products or tenants. Binary and categorical
forecasts should use proper probabilistic scores such as Brier or log score where appropriate;
numeric forecasts should evaluate error, interval coverage, and interval width. Reliability curves
must test whether stated probabilities match observed frequencies.

## Delivery sequence and ownership

1. **F1 completed:** remove ambiguous world-model language and establish this definition as the
   public authority.
2. **F1 completed:** freeze a versioned conditional forecast and resolution schema with stable
   identity and provenance.
3. **F1 completed:** capture intervention state, baselines, applicability conditions, and
   resolvable observations.
4. **F1 completed:** ground projections in analogous settled intervention cases and explicit
   consequence mechanisms;
   keep a true no-action comparator explicitly absent until it is observed, then preserve it as
   separate post-decision evidence rather than rewriting the frozen forecast.
5. **Future breadth/evidence outcome:** produce independently verified inside-view, outside-view,
   and tail-risk contributions before any aggregation claim.
6. **Future breadth/evidence outcome:** add binary/categorical scoring only when product evidence
   justifies those consequence types.
7. **I3:** make resolved-forecast retrieval and its exact effect on later reasoning inspectable.
8. **L1:** add product-aware hierarchical calibration and compare against no-foresight,
   naive/base-rate, and model-only baselines; test whether foresight improves decisions rather than
   merely changing them.

## F1 acceptance evidence

F1 advanced to `passed` when:

- public documentation consistently uses the canonical definition and does not imply a
  foundation-scale learned world model;
- a versioned forecast/resolution contract covers every required field and state above;
- prediction, observation, resolution, and later lesson remain distinct records with provenance;
- invalid, unresolved, cancelled, assumption-failed, missing-evidence, and degraded paths have
  deterministic coverage;
- intervention capture is idempotent, product-isolated, restart-durable, and linked to the original
  decision and forecast without mutating either;
- automatic indicator evidence is derived only from frozen machine-resolvable rules, while
  prose-only indicators remain visibly manual and indicator updates never rewrite forecasts;
- settled analogues are product-isolated, deterministically ranked, provenance-bearing, sparse-data
  aware, and never misrepresented as a no-action counterfactual;
- observed comparators are optional, product-isolated, idempotent, target-validated, attribution-
  labeled, horizon-gated, and unable to mutate the original forecast;
- comparator plans remain optional non-evidence, require operator confirmation, avoid fabricated
  sample-size claims, and never become resolution-eligible without a separate observation;
- linked observations fail closed on foreign plan identity and expose deterministic alignment,
  execution deviations, and downgraded effective attribution without asserting causality;
- raw measurement samples remain non-resolution evidence; ingestion requires an exact complete
  plan/target/arm/phase matrix, exposes partial and conflicting states, and has no rollout authority;
- continuous scores require frozen interval coverage, use a proper central interval score, preserve
  the legacy diagnostic separately, and explicitly abstain for unsupported semantics;
- multi-product isolation and redaction behavior are verified;
- the supported eleven-tool MCP boundary is unchanged; and
- limitations, verification evidence, and roadmap reconciliation are published.

F1 establishes an honest and testable contract. It does not prove forecast accuracy, causal
identification, automatic improvement, or beneficial material use. Those claims remain gated by
L1 evaluation evidence.
