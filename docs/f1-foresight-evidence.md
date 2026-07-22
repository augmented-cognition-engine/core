# F1 graph-grounded calibrated foresight closeout evidence

Date: 2026-07-22

Outcome: **F1 passed**

## Claim and boundary

ACE provides graph-grounded, calibrated foresight. It projects conditional consequences of
decisions, exposes the mechanisms and uncertainty behind them, observes what actually happens,
and uses resolved forecasts to improve later reasoning.

F1 establishes the honest, inspectable foundation for that claim. It does not establish that ACE
is a foundation-scale learned world model, that a captured design is causal, that forecasts are
generally accurate, or that foresight beneficially improves decisions. The last claim belongs to
L1 comparative evaluation.

F1 v1 proper scoring is deliberately scoped to continuous numeric deltas with declared predictive
interval coverage. Binary and categorical scoring are not silently approximated; those consequence
types remain outside the passed v1 scoring scope.

## Implemented contract

The additive v146-v154 schema preserves separate, versioned records for:

- conditional forecasts and immutable consequence mechanisms;
- interventions, applicability, exposure, indicators, and falsification evidence;
- product-local outside-view reference classes with explicit cold-start maturity;
- comparator plans that remain advisory non-evidence;
- plan/execution alignment and deviations without causal claims;
- raw structured metric samples that remain non-resolution evidence;
- fail-closed measurement ingestion receipts;
- observed comparator effects using transparent difference-in-differences;
- horizon-gated resolutions and bounded lessons; and
- continuous Prediction Score v1 interval scores and diagnostics.

The supported public boundary remains the existing CLI and exactly eleven thin MCP tools.

## Real service acceptance scenario

`tests/test_i1_restart_persistence.py` starts a disposable SurrealKV database and production API,
uses an authenticated thin client, stops the API, and starts a fresh API process against the same
store. Its deterministic fixture makes no model calls.

The F1 closeout path performs the following through real persistence and API boundaries:

1. Freeze a continuous forecast with point delta `0.10`, central 80% interval `[0.00, 0.20]`,
   mechanism, assumptions, dependencies, confounders, evidence, applicability, falsification,
   current-state/no-action baselines, and a matched-holdout comparator plan.
2. Capture a completed, applicable intervention while the forecast remains before its horizon.
3. Advance only the fixture forecast's creation time so the declared 30-day horizon is due.
4. Capture four explicit `structured_metric` samples incrementally: intervention baseline/outcome
   `0.50/0.70` and comparator baseline/outcome `0.50/0.55`.
5. Observe three `collecting` receipts. The fourth sample creates one plan-linked Comparator
   Observation v1 and computes `(0.70 - 0.50) - (0.55 - 0.50) = 0.15`.
6. Resolve the forecast through the normal horizon/applicability gate, retain the original
   forecast, and produce an eligible continuous Prediction Score v1 result.
7. Restart the API, read the four raw samples, ingestion receipt, aligned comparator, and resolved
   outcome, then replay the fourth sample and receive the same durable identities.

Raw samples remain `resolution_eligible=false`; the derived comparator is the separate eligible
evidence record. The receipt explicitly grants no cohort assignment, experiment operation, or
rollout-changing authority.

## Acceptance reconciliation

| F1 acceptance requirement | Evidence |
|---|---|
| Canonical, non-world-model definition | Consistency checks across README, roadmap, architecture, and foresight documentation |
| Stable forecast and resolution contracts | Versioned Forecast v1 and Resolution v1 projections through v154 |
| Distinct prediction, observation, resolution, and lesson provenance | Contract tests, reconciler tests, Living Product Graph projection, and real service scenario |
| Invalid, unresolved, cancelled, failed-applicability, missing-evidence, and degraded paths | Deterministic contract and reconciler failure-state tests |
| Idempotent, isolated, restart-durable intervention evidence | API/unit coverage plus disposable database/API restart proof |
| Machine-resolvable versus manual indicators | Indicator contract/evaluator tests; prose-only indicators remain manual |
| Sparse, product-local settled analogues | Outside-view ranking, cold-start, maturity, provenance, and isolation tests |
| Optional observed comparators | Target validation, design labels, horizon gating, immutable forecast, and difference-in-differences tests |
| Advisory comparator planning | Plan-only evidence state, no fabricated sample size, stable product-isolated identity |
| Plan/execution linkage | Foreign-plan rejection, deterministic alignment/deviation states, attribution downgrade, no causal claim |
| Fail-closed measurement ingestion | Partial, duplicate-slot, inconsistent-metadata, unsupported-source, foreign-plan, closed-prediction, and real assembly coverage |
| Proper continuous scoring | Declared-coverage central interval score, abstention, diagnostics, and resolved real scenario |
| Isolation and redaction | Product-isolated plan/outside-view/observation tests and bounded credential-redaction projections |
| Eleven-tool boundary | Kernel/MCP boundary checks report exactly eleven public tools |

## Verification record

- Focused foresight, API, MCP, and kernel regression: `188 passed`.
- Schema migration, splitter, and kernel checks: `25 passed`.
- Disposable SurrealDB/API restart scenario including F1 ingestion and resolution: `1 passed`.
- Canvas production build: passed.
- Full non-E2E repository run at closeout: `6525 passed`, `47 skipped`, `242 deselected`.
- The full run retained 21 pre-existing unrelated failures: 20 provider-selection expectations and
  one roadmap-lane expectation. Focused F1 verification is green.
- Ruff, schema hygiene, diff hygiene, and exact MCP tool-count checks: passed; tool count `11`.

## Deferred work

F1 is not kept open for unbounded breadth. Deferred work is routed by purpose:

- independently verified assignment/randomization and additional consequence types belong to a
  future evidence-quality/breadth outcome, contingent on demonstrated need;
- native telemetry sources belong to the extension and adapter ecosystem;
- reliability curves, hierarchical calibration, null/harmful influence, and comparison against
  no-foresight, naive/base-rate, and model-only controls belong to L1; and
- attributable retrieval and exact later decision effects belong to I3.

The next existential milestone is L1: prove that resolved foresight beneficially improves later
reasoning rather than merely changing it.
