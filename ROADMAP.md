# ACE public roadmap

This roadmap is the public view of work planned for ACE. It describes outcomes rather than
internal release operations, commercial plans, customer work, or security-sensitive details.
Priorities may change as maintainers learn from users and contributors.

## Current release checkpoint

`ace-core` 0.1.0 is published on PyPI and GitHub. The release, package artifacts, trusted
publishing path, and a clean public-index wheel installation have been verified. The onboarding
gate is proven in clean macOS and Linux proxy trials. The reproducible product-builder golden path
now also shows a public evidence-backed decision, inspectable reasoning, a retained human
correction, real runtime restart, and material later use through the supported CLI and eleven-tool
MCP boundary. I3 now adds a versioned receipt that distinguishes retrieval, injection, reflection,
and exact structured decision effects without presenting material influence as beneficial impact.
I2 now has a locally accepted candidate receipt for observable routing, bounded contributor
artifacts, artifact-grounded disagreement, synthesis lineage, and degraded coverage;
authoritative branch CI remains its final promotion gate.

Roadmap outcome states are used strictly:

- **ready** — authorized and able to start;
- **active** — currently being executed;
- **candidate** — implementation exists, but evidence or reconciliation is incomplete;
- **not ready** — a dependency or acceptance gate remains;
- **passed** — outcome, verification evidence, limitations, and roadmap reconciliation are complete;
- **superseded** — replaced by an accepted newer outcome.

## Now — effortless product onboarding

- Publish and validate the `ace-core` 0.1.x Python distribution while preserving the `ace`
  import and CLI identities.
- Lead with the product outcomes ACE enables—better product context, reasoning, decisions,
  evidence, and learning—before introducing its architecture or developer surface.
- Make installation, authentication, provider setup, `ace doctor`, and the first useful journey
  guided and reliable for new users on macOS and Linux.
- Provide one obvious path from “what is ACE?” to a meaningful result, with progressive
  disclosure for the CLI, thin 11-tool MCP contract, self-hosting, and extension internals.
- Improve setup guidance, diagnostics, failure recovery, security reporting, and contributor
  onboarding from observed first-use friction.
- Protect the kernel/extension boundary and keep model-provider routes replaceable.

| ID | State | Public outcome | Dependency / acceptance evidence |
|---|---|---|---|
| R0 | passed | Publish `ace-core` 0.1.0 through a credential-free release path | GitHub Release, PyPI release, successful OIDC workflow, and public-index install verified |
| R1 | passed | Make first use effortless and outcome-led for product builders, not only developers | [Clean-trial evidence](docs/r1-onboarding-evidence.md): isolated macOS and Linux journeys both reached useful recommendations without maintainer help or architecture knowledge; intentional recovery and `ace doctor` passed |
| R2 | passed | Ship a focused 0.1.1 onboarding, packaging, and documentation release | [Release evidence](docs/r2-release-evidence.md): clean macOS/Linux installs, artifacts, required PR/main CI, `v0.1.1`, trusted PyPI publication, GitHub Release, and a fresh public-index install all passed against verified main commit `1662eaa` |
| R3 | passed | Validate provider setup, authentication, diagnostics, and degraded behavior | [Provider validation evidence](docs/r3-provider-validation.md): supported matrix, deterministic degraded-state coverage, live Claude and GPT subscription routes, honest effort reporting, and green current-main CI |
| R4 | passed | Publish a reproducible, product-builder golden-path demonstration | [Golden-path evidence](docs/product-builder-golden-path.md): a checksum-frozen public product decision completed through the supported Codex subscription route, persisted a binding human correction across a real service restart, materially changed a fresh later experiment, retained inspectable provenance, and recorded failures and portability limits without widening the eleven-tool boundary |
| R5 | passed | Ship the backward-compatible ace-core 0.1.2 inspectability and foresight release | [0.1.2 release evidence](docs/r5-release-readiness.md) records aligned metadata, clean artifacts and isolated install, full regressions, schema v155 restart/Compose health, verified main/tag identity, GitHub Release, trusted PyPI publication, cryptographic provenance, matching archive hashes, and a clean public-index install |

## Next — durable product partnership

- Make product context, decisions, evidence, corrections, and outcomes easier to inspect.
- Give decisions and human corrections stable identity, provenance, authority, disposition, and
  typed relationships that survive restart.
- Make problem classification, perspective selection, bounded contributor positions,
  disagreement, and synthesis attributable without exposing hidden chain-of-thought.
- Show when retained intelligence was retrieved, injected, reflected, and materially changed a
  later decision—including null, stale, contested, harmful, and degraded cases.
- Strengthen long-running task recovery, replay, portability, and resource reporting.
- Turn Atrium research into a clearer read-only view of ACE state before adding new write or
  execution authority.
- Preserve the passed graph-grounded calibrated-foresight contract while keeping broader
  consequence-learning claims gated by comparative evidence.
- Expand extension examples and conformance tests without widening the public MCP contract.

| ID | State | Public outcome | Dependency / acceptance evidence |
|---|---|---|---|
| G1 | passed | Promote the read-only Living Product Graph projection into a supported inspectable journey | [`ace landscape`](docs/living-product-graph.md), [reproducible G1 evidence](docs/g1-living-product-graph-evidence.md), and [green acceptance CI](https://github.com/augmented-cognition-engine/core/actions/runs/29872552736) prove the versioned, bounded, deterministic, assertion-backed read contract and strict read-only boundary |
| IA-R1 | passed | Define the read-only information architecture for inspecting ACE state | [`/landscape`](docs/ia-r1-product-map.md), [reconciled IA-R1 evidence](docs/ia-r1-product-map.md), and [green branch CI](https://github.com/augmented-cognition-engine/core/actions/runs/29889892587) establish the six-question operator hierarchy, visible provenance and uncertainty, bounded failures, stable identity, and strict no-write/no-execution authority |
| I1 | passed | Make decisions, evidence, dissent, uncertainty, corrections, approval receipts, and outcomes easier to inspect | [Decision and correction receipt evidence](docs/decision-correction-receipts.md) proves stable identities, complete decision context, all four human dispositions, correction supersession/invalidation/contestation/expiry, authorization, isolation, redaction, explicit provenance gaps, and restart continuity through the existing eleven-tool boundary |
| I2 | candidate | Make deliberation and synthesis attributable without exposing hidden chain-of-thought | [I2 candidate evidence](docs/i2-attributable-deliberation-evidence.md) records the frozen receipt, public-data four-path matrix, artifact-grounded conflict and synthesis lineage, real restart continuity, failure/redaction/isolation behavior, and unchanged eleven-tool boundary; final-head branch CI remains required for `passed` |
| I3 | passed | Make retained-intelligence use and its decision effect inspectable | [I3 closeout evidence](docs/i3-intelligence-use-evidence.md) proves the bounded `intelligence-use-receipt-v1` projection, exact I1 field deltas, matched live Codex route, real restart/fresh-client continuity, null/stale/contested/harmful/mismatch/failure behavior, and unchanged eleven-tool boundary |
| F1 | passed | Freeze the honest, conditional contract for graph-grounded calibrated foresight | [F1 closeout evidence](docs/f1-foresight-evidence.md) proves the continuous-delta v1 forecast-to-observation-to-resolution loop through additive schema v154, including cold start, settled analogues, optional planning/comparators, structured measurement ingestion, proper interval scoring, real API/database restart continuity, explicit non-causal limitations, and the unchanged eleven-tool boundary |
| T1 | not ready | Strengthen durable task recovery, replay, portability, cancellation semantics, and resource reporting | Requires explicit single-process versus distributed guarantees and failure evidence |
| E1 | not ready | Expand extension examples and conformance coverage | Must preserve the kernel boundary and exactly eleven public MCP tools |

I1 passed through the existing task/status/capture/load paths with versioned task-backed decision
receipts and linked correction provenance. API-owned schema-zero-to-v145 bootstrap and restart
pass on the supported SurrealDB 3.1.4 pin and 3.2.1; mixed future receipt versions degrade without
v1 reinterpretation. This outcome makes no correctness, benefit, I2, I3, or execution-authority
claim.

I3 passed through the existing task/status and Living Product Graph read paths. Runtime use without
a control remains retrieved/injected/reflected with an explicit unknown comparison; only an
isolated, valid, relevant, reflected item with an exact matched comparison can become
decision-material. I3 makes no beneficial-impact or L1 claim.

I2 is candidate through the same existing task/status and Living Product Graph reads plus opt-in
CLI rendering. Complete means required bounded artifacts and executions are present, not that the
synthesis is correct or beneficial. Missing structured artifacts, contributors, failures,
timeouts, tainted phases, and incomplete lineage remain degraded; final promotion requires green
authoritative branch CI.

## Later — build, ship, and learn

**ACE provides graph-grounded, calibrated foresight.** It projects conditional consequences of
decisions, exposes the mechanisms and uncertainty behind them, observes what actually happens,
and uses resolved forecasts to improve later reasoning. The intended system is a bounded,
inspectable consequence model over a product or domain—not a foundation-scale learned model of the
physical world. F1 freezes the contract; L1 must prove that resolved forecasts materially and
beneficially inform later reasoning.

- Carry approved decisions through attributable implementation, review, repair, and promotion.
- Connect predicted outcomes to observed results so corrections can improve later reasoning.
- Support secure collaboration and managed operation without making the hosted service the
  owner of a user's durable intelligence.
- Grow a provider-neutral ecosystem of extensions and execution adapters.

| ID | State | Public outcome | Dependency / acceptance evidence |
|---|---|---|---|
| F2 | not ready | Broaden consequence types and independently verified design evidence where product evidence justifies the added complexity | Requires L1 evidence or demonstrated user need; may include binary/categorical scoring, verified assignment/randomization provenance, and independently produced forecast contributions without reopening F1 |
| B1 | not ready | Carry approved decisions through attributable implementation, review, repair, and promotion | Requires I1 approval receipts and explicit execution authority |
| L1 | candidate | Use resolved conditional forecasts to improve later reasoning and decision quality | [Initial L1 evidence gate](docs/l1-foresight-impact-evidence.md) implements a bounded sample-aware all-controls evaluator, but the checksum-frozen public-data probe did not beat persistence, its cluster intervals include zero, model-only evidence is absent, and intervention/confounder attribution is unsupported; beneficial impact is not established |
| H1 | not ready | Support secure collaboration and managed operation without transferring ownership of durable intelligence | Requires tenancy, portability, authority, and recovery guarantees |
| E2 | not ready | Grow the provider-neutral extension, telemetry, and execution-adapter ecosystem | Requires E1 conformance and stable compatibility policy; native telemetry sources belong here rather than in F1 |

## Follow and contribute

Follow the live [ACE Public Roadmap](https://github.com/orgs/augmented-cognition-engine/projects/1)
for current Now/Next/Later status. This file preserves the versioned outcome definitions and
public planning principles; repository issues carry discussion and acceptance evidence for
individual outcomes.

[`docs/roadmap-status.md`](docs/roadmap-status.md) records the latest reconciled evidence snapshot,
dependencies, and exact next dispatch. The GitHub Project is the live operational view; neither
strategy prose nor an unverified implementation claim advances an outcome to `passed`.

The I1–I3 outcomes are reasoning-product infrastructure, not demonstration scaffolding. A demo may
reveal or exercise these gaps, but recording needs do not define their acceptance criteria or pull
them ahead of the onboarding and compatibility spine. Frozen scenarios, raw-model controls,
scorecards, video renderers, and recording automation remain evaluation/communication tooling
unless they independently satisfy a supported user outcome.

Public roadmap issues should state the user outcome, scope, acceptance evidence, dependencies,
and maturity impact. They must not contain credentials, vulnerability details, customer
information, private agreements, or unpublished business and release plans.

L1 is candidate rather than passed. Its first leakage-bounded retrospective probe preserves the
negative result: rolling resolved forecasts were slightly worse than last-observation persistence,
the apparent base-rate improvement was not cluster-robust, and observational source data could not
identify intervention benefit. Passing L1 requires new preregistered outcome evidence against every
required control; it cannot be achieved by relabeling this probe or selecting only its favorable
comparison.
