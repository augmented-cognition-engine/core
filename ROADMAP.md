# ACE public roadmap

This roadmap is the public view of work planned for ACE. It describes outcomes rather than
internal release operations, commercial plans, customer work, or security-sensitive details.
Priorities may change as maintainers learn from users and contributors.

## Current release checkpoint

`ace-core` 0.2.0 is published on PyPI and GitHub from verified main commit `6c0638a`. The release
adds the product-scoped State Engine contract from bounded ingestion and grounded evidence through
belief projection, reviewed transitions, action/no-action rollouts, later-outcome reconciliation,
I3 reasoning-use receipts, and authority-gated promotion/correction lineage. It preserves the
supported CLI and exactly eleven thin MCP tools, upgrades the public v0.1.4 schema head from v160
to v168 through restart-safe migrations, and publishes the bounded single-node scale and readiness
evidence without claiming distributed operation, autonomous learning, causal accuracy, or
beneficial impact. The reproducible product-builder golden path continues to demonstrate a public
evidence-backed decision, retained human correction, real runtime restart, and material later use.

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
| R1 | passed | Make first use effortless and outcome-led for product builders, not only developers | [Clean-trial evidence](docs/evidence/r1-onboarding-evidence.md): isolated macOS and Linux journeys both reached useful recommendations without maintainer help or architecture knowledge; intentional recovery and `ace doctor` passed |
| R2 | passed | Ship a focused 0.1.1 onboarding, packaging, and documentation release | [Release evidence](docs/evidence/r2-release-evidence.md): clean macOS/Linux installs, artifacts, required PR/main CI, `v0.1.1`, trusted PyPI publication, GitHub Release, and a fresh public-index install all passed against verified main commit `1662eaa` |
| R3 | passed | Validate provider setup, authentication, diagnostics, and degraded behavior | [Provider validation evidence](docs/evidence/r3-provider-validation.md): supported matrix, deterministic degraded-state coverage, live Claude and GPT subscription routes, honest effort reporting, and green current-main CI |
| R4 | passed | Publish a reproducible, product-builder golden-path demonstration | [Golden-path evidence](docs/product-builder-golden-path.md): a checksum-frozen public product decision completed through the supported Codex subscription route, persisted a binding human correction across a real service restart, materially changed a fresh later experiment, retained inspectable provenance, and recorded failures and portability limits without widening the eleven-tool boundary |
| R5 | passed | Ship the backward-compatible ace-core 0.1.2 inspectability and foresight release | [0.1.2 release evidence](docs/evidence/r5-release-readiness.md) records aligned metadata, clean artifacts and isolated install, full regressions, schema v155 restart/Compose health, verified main/tag identity, GitHub Release, trusted PyPI publication, cryptographic provenance, matching archive hashes, and a clean public-index install |
| R6 | passed | Ship the backward-compatible ace-core 0.1.3 attributable-deliberation and experimental extension-invocation release | [0.1.3 release evidence](docs/evidence/r6-release-readiness.md) records the supported/experimental boundary, full local regressions, verified release commit and tag, green PR/main CI, trusted PyPI publication, matching artifact hashes, provenance, and clean public-index verification |
| R7 | passed | Reconcile and publish the ace-core 0.2.0 State Engine release | [R7 release evidence](docs/evidence/r7-release-readiness.md) records the integrated architecture audit, version/support boundary, v168 upgrade and operations checks, full regressions, retained scale hashes, verified merge/tag identity, green PR and merged-main CI, GitHub Release, trusted PyPI publication, matching workflow/public hashes, cryptographic provenance, and fresh public-index installation |

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
| G1 | passed | Promote the read-only Living Product Graph projection into a supported inspectable journey | [`ace landscape`](docs/living-product-graph.md), [reproducible G1 evidence](docs/evidence/g1-living-product-graph-evidence.md), and [green acceptance CI](https://github.com/augmented-cognition-engine/core/actions/runs/29872552736) prove the versioned, bounded, deterministic, assertion-backed read contract and strict read-only boundary |
| IA-R1 | passed | Define the read-only information architecture for inspecting ACE state | [`/landscape`](docs/evidence/ia-r1-product-map.md), [reconciled IA-R1 evidence](docs/evidence/ia-r1-product-map.md), and [green branch CI](https://github.com/augmented-cognition-engine/core/actions/runs/29889892587) establish the six-question operator hierarchy, visible provenance and uncertainty, bounded failures, stable identity, and strict no-write/no-execution authority |
| I1 | passed | Make decisions, evidence, dissent, uncertainty, corrections, approval receipts, and outcomes easier to inspect | [Decision and correction receipt evidence](docs/decision-correction-receipts.md) proves stable identities, complete decision context, all four human dispositions, correction supersession/invalidation/contestation/expiry, authorization, isolation, redaction, explicit provenance gaps, and restart continuity through the existing eleven-tool boundary |
| I2 | passed | Make deliberation and synthesis attributable without exposing hidden chain-of-thought | [I2 closeout evidence](docs/evidence/i2-attributable-deliberation-evidence.md) and [green branch CI](https://github.com/augmented-cognition-engine/core/actions/runs/29976761503) prove the frozen receipt, public-data four-path matrix, artifact-grounded conflict and synthesis lineage, real restart continuity, failure/redaction/isolation behavior, and unchanged eleven-tool boundary |
| I3 | passed | Make retained-intelligence use and its decision effect inspectable | [I3 closeout evidence](docs/evidence/i3-intelligence-use-evidence.md) proves the bounded `intelligence-use-receipt-v1` projection, exact I1 field deltas, matched live Codex route, real restart/fresh-client continuity, null/stale/contested/harmful/mismatch/failure behavior, and unchanged eleven-tool boundary |
| F1 | passed | Freeze the honest, conditional contract for graph-grounded calibrated foresight | [F1 closeout evidence](docs/evidence/f1-foresight-evidence.md) proves the continuous-delta v1 forecast-to-observation-to-resolution loop through additive schema v154, including cold start, settled analogues, optional planning/comparators, structured measurement ingestion, proper interval scoring, real API/database restart continuity, explicit non-causal limitations, and the unchanged eleven-tool boundary |
| T1 | not ready | Strengthen durable task recovery, replay, portability, cancellation semantics, and resource reporting | [State Engine TP1](docs/evidence/state-engine-tp1-reliable-memory-lifecycle-v1.md) closes reliable observation claiming/recovery; T1 still requires task cancellation, portability, resource reporting, and explicit single-process versus distributed guarantees |
| E1 | passed | Govern reusable cognition through one inspectable lifecycle without widening model authority | [E1 release evidence](docs/evidence/e1-governed-cognition-release-v1.md) binds the canonical E1-A–G implementation to ace-core 0.3.0, the exact current/N-1 and mixed-package matrix, public PyPI artifacts, a fresh public install, deployment inventory, an independent Claude Fable 5 AI security acceptance, and release-owner countersignature. The pass remains limited to trusted in-process extensions and is not a human penetration-test or certification claim |

I1 passed through the existing task/status/capture/load paths with versioned task-backed decision
receipts and linked correction provenance. API-owned schema-zero-to-v145 bootstrap and restart
pass on the supported SurrealDB 3.1.4 pin and 3.2.1; mixed future receipt versions degrade without
v1 reinterpretation. This outcome makes no correctness, benefit, I2, I3, or execution-authority
claim.

I3 passed through the existing task/status and Living Product Graph read paths. Runtime use without
a control remains retrieved/injected/reflected with an explicit unknown comparison; only an
isolated, valid, relevant, reflected item with an exact matched comparison can become
decision-material. I3 makes no beneficial-impact or L1 claim.

I2 passed through the same existing task/status and Living Product Graph reads plus opt-in CLI
rendering. Complete means required bounded artifacts and executions are present, not that the
synthesis is correct or beneficial. Missing structured artifacts, contributors, failures,
timeouts, tainted phases, and incomplete lineage remain degraded.

## Later — build, ship, and learn

**ACE provides graph-grounded, calibrated foresight.** It projects conditional consequences of
decisions, exposes the mechanisms and uncertainty behind them, observes what actually happens,
and uses resolved forecasts to improve later reasoning. The intended system is a bounded,
inspectable consequence model over a product or domain—not a foundation-scale learned model of the
physical world. F1 freezes the contract; L1 must prove that resolved forecasts materially and
beneficially inform later reasoning.

- Carry approved decisions through attributable implementation, review, repair, and promotion.
- Connect predicted outcomes to observed results so corrections can improve later reasoning.
- Build a product-scoped State Engine over large knowledge bases: temporal
  epistemic state, inspectable dynamics hypotheses, and reconciled consequence simulation without
  turning every claim into durable cognitive memory or claiming a general learned world model.
- Support secure collaboration and managed operation without making the hosted service the
  owner of a user's durable intelligence.
- Grow a provider-neutral ecosystem of extensions and execution adapters.

| ID | State | Public outcome | Dependency / acceptance evidence |
|---|---|---|---|
| F2 | not ready | Broaden consequence types and independently verified design evidence where product evidence justifies the added complexity | Requires L1 evidence or demonstrated user need; may include binary/categorical scoring, verified assignment/randomization provenance, and independently produced forecast contributions without reopening F1 |
| B1 | not ready | Carry approved decisions through attributable implementation, review, repair, and promotion | Requires I1 approval receipts and explicit execution authority |
| L1 | candidate | Use resolved conditional forecasts to improve later reasoning and decision quality | [L1 evidence gate](docs/evidence/l1-foresight-impact-evidence.md) preserves the negative public-data probe and freezes a tamper-evident prospective all-controls protocol; the executed readiness receipt is `collection_not_started`, so beneficial impact is not established |
| K1 | ready | Maintain grounded temporal state over large product-scoped knowledge bases | [State Engine K1-K3 readiness](docs/evidence/state-engine-k1-k3-readiness-v1.md) revalidates the frozen TP8 identities and boundary against the retained 220,000-claim/256,000-semantic-record store; TP8 supplies the named single-node interruption, replay, backup/restore, migration, isolation, ingestion, and query evidence |
| K2 | ready | Model inspectable world dynamics and state-transition hypotheses | The [frozen K1-K3 audit](docs/evidence/state-engine-k1-k3-readiness-v1.md) repeats all eight TP5 domains five times beside the large corpus: 40/40 exact cases and replays, 35 required abstentions, five predeclared calibrations, 8.924 ms p95, and zero unsupported acceptances, provenance failures, isolation leaks, or provider use |
| K3 | ready | Simulate, compare, and reconcile consequences of possible actions | The [frozen K1-K3 audit](docs/evidence/state-engine-k1-k3-readiness-v1.md) passes 5/5 repeated database/API/worker/thin-client journeys with matched outcome reconciliation, durable task identity, correction/supersession, exact later material use, 81.799 ms task / 42.534 ms promotion / 11.214 ms retrieval p95, 2.186 s maximum restart, and zero degraded, isolation, semantic-separation, retry, or provider failures |
| H1 | not ready | Support secure collaboration and managed operation without transferring ownership of durable intelligence | Requires tenancy, portability, authority, and recovery guarantees |
| E2 | not ready | Grow the provider-neutral extension, telemetry, and execution-adapter ecosystem | Requires E1 conformance and stable compatibility policy; native telemetry sources belong here rather than in F1 |

K1–K3 name a grounded epistemic-state and consequence capability. They do not claim a general
learned world model, latent physical simulator, or current F1 capability.

TP8 closes the single-node scale, recovery, portability, and Core-boundary packet. The subsequent
[bounded readiness audit](evaluations/results/state_engine_k1_k3_readiness_v1.md) closes its explicit
pre-R7 matrix and repeated-process requirements and advances K1, K2, and K3 to `ready`. R7 is
unblocked but was not started or authorized by that audit. These decisions do not advance L1
beneficial-impact readiness, T1, B1, E1, or ACE v0.2.0 release readiness and make no general
world-model, real-world causal-accuracy, calibrated-forecasting, or beneficial-impact claim.

## Follow and contribute

Follow the live [ACE Public Roadmap](https://github.com/orgs/augmented-cognition-engine/projects/1)
for current Now/Next/Later status. This file preserves the versioned outcome definitions and
public planning principles; repository issues carry discussion and acceptance evidence for
individual outcomes.

The GitHub Project is the live operational view; neither strategy prose nor an unverified
implementation claim advances an outcome to `passed`. Point-in-time verification records remain
available in the [evidence archive](docs/evidence/README.md).

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
comparison. The prospective v1 protocol is now frozen, but its `collection_not_started` receipt is
readiness evidence only and does not advance L1.
