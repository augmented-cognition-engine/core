# Public roadmap status

Last reconciled: 2026-07-22

The live operational view is the
[ACE Public Roadmap](https://github.com/orgs/augmented-cognition-engine/projects/1), organized as
Now, Next, and Later. [`ROADMAP.md`](../ROADMAP.md) preserves the versioned outcome definitions,
IDs, dependencies, and public planning principles. Internal commercial work, customer material,
credentials, and security-sensitive detail are intentionally excluded.

## Release evidence

| Outcome | State | Evidence |
|---|---|---|
| R0 — `ace-core` 0.1.0 public release | passed | [GitHub Release](https://github.com/augmented-cognition-engine/core/releases/tag/v0.1.0), [PyPI](https://pypi.org/project/ace-core/0.1.0/), [OIDC publication run](https://github.com/augmented-cognition-engine/core/actions/runs/29789939142), clean public-index wheel install and `import ace` version check |

Known release limitations remain explicit: ACE 0.1.x supports Python 3.12; the supported public
interaction boundary is the CLI and exactly eleven thin MCP tools; Atrium and the broader engine
surfaces remain experimental; and the existing signature evidence does not establish general
model superiority. R1 provides an outcome-led entry path and R4 provides a reproducible durable
decision journey, while the clean trials remain an AI-operated proxy rather than independent human
usability validation. R4's second-provider check was unavailable because the accepted replay host
did not have the Claude CLI installed; the canonical Codex subscription run remains authoritative.

## Living roadmap

| ID | Phase | State | Evidence gap or dependency |
|---|---|---|---|
| R1 | Now | passed | [2026-07-21 clean-trial evidence](r1-onboarding-evidence.md): isolated macOS and Linux journeys both reached useful recommendations without maintainer help or architecture knowledge; intentional recovery and `ace doctor` passed |
| R2 | Now | passed | [0.1.1 release evidence](r2-release-evidence.md) records clean macOS/Linux installs, artifacts, required PR/main CI, `v0.1.1`, trusted PyPI publication, GitHub Release, and a fresh public-index install against verified main commit `1662eaa` |
| R3 | Now | passed | [`r3-provider-validation.md`](r3-provider-validation.md) records the frozen provider/auth matrix, structured diagnostics, deterministic degraded states, live Claude and Codex/GPT subscription smokes, honest effort limits, and green current-main CI |
| R4 | Now | passed | [Product-builder golden-path evidence](product-builder-golden-path.md) records a checksum-frozen public scenario, live Codex/GPT route, zero-intelligence clean start, inspectable multi-perspective reasoning, decision and correction capture, real service restart, fresh-invocation material reuse, bounded failures, exact eleven-tool preservation, and explicit portability and usability limitations |
| R5 | Now | passed | [`r5-release-readiness.md`](r5-release-readiness.md) records the backward-compatible 0.1.2 scope, passed local gates, verified main/tag identity, GitHub Release, trusted PyPI publication, cryptographic provenance, matching archive hashes, and a clean public-index install |
| G1 | Next | passed | [`g1-living-product-graph-evidence.md`](g1-living-product-graph-evidence.md) records the frozen contract, supported `ace landscape` journey, deterministic replay, accepted/provisional/contested/rejected behavior, bounded failures, restart parity, strict read-only authority, and [green acceptance CI](https://github.com/augmented-cognition-engine/core/actions/runs/29872552736) |
| IA-R1 | Next | passed | [Read-only product-map evidence](ia-r1-product-map.md) and [green branch CI](https://github.com/augmented-cognition-engine/core/actions/runs/29889892587) record the six-question operator hierarchy, strict GET-only boundary, visible uncertainty/failures, local verification, and roadmap closeout |
| I1 | Next | passed | [`decision-correction-receipts.md`](decision-correction-receipts.md) records stable identities, complete decision context, all four dispositions, correction supersession/invalidation/contestation/expiry, authorization, isolation, redaction, explicit provenance gaps, and schema-zero-to-v145 restart continuity |
| I2 | Next | passed | [`i2-attributable-deliberation-evidence.md`](i2-attributable-deliberation-evidence.md) and [green branch CI](https://github.com/augmented-cognition-engine/core/actions/runs/29976761503) record the frozen v1 receipt, public-data independent/pipeline/team/adversarial matrix, artifact-grounded conflict and synthesis lineage, real schema-zero-to-v156 restart continuity, failure/redaction/isolation behavior, and exact eleven-tool preservation |
| I3 | Next | passed | [`i3-intelligence-use-evidence.md`](i3-intelligence-use-evidence.md) records the bounded task/graph receipt, exact I1 decision deltas, matched live Codex route, real restart/fresh-client material continuity, null/stale/invalidated/contested/harmful/mismatch/failure matrix, and exact eleven-tool preservation through schema v155 |
| F1 | Next | passed | [`f1-foresight-evidence.md`](f1-foresight-evidence.md) records the bounded continuous-delta v1 contract, real structured-measurement-to-comparator-to-resolution API/database scenario, restart-safe replay, cold-start behavior, proper scoring, limitations, and exact eleven-tool preservation through schema v154 |
| T1 | Next | not ready | Recovery, replay, portability, cancellation, and resource guarantees are not yet frozen |
| E1 | Next | not ready | The [`extension-invocation-v1` evidence](extension-invocation-contract.md) freezes the experimental durable bridge, fail-closed reference accounting, and linked restart attempts; packaged-example/version-skew conformance evidence and eleven-tool preservation are still required |
| F2 | Later | not ready | Broader consequence types and independently verified design evidence require L1 evidence or demonstrated user need; they do not keep F1 open |
| B1 | Later | not ready | Depends on inspectable approval receipts and explicit execution authority |
| L1 | Later | candidate | [`l1-foresight-impact-evidence.md`](l1-foresight-impact-evidence.md) records the bounded all-controls evaluator and checksum-frozen 72-case public-data probe; benefit is not established because persistence slightly outperformed ACE, eight-cluster intervals include zero, matched model-only evidence is absent, and intervention/confounder attribution is unsupported |
| H1 | Later | not ready | Depends on tenancy, portability, authority, and recovery guarantees |
| E2 | Later | not ready | Depends on E1 conformance and stable compatibility policy; native telemetry sources belong to this adapter lane |

I1 passed through structured task decisions, authenticated human dispositions, and linked
correction observations exposed through the existing status/capture/load contracts. The disposable
real-API restart proof preserves the same decision, correction, provenance, lifecycle, and typed
relationship identities across fresh processes. Production API startup owns schema-zero-to-v145
replay on the supported SurrealDB 3.1.4 pin and 3.2.1; unknown future receipt versions degrade
without being reinterpreted as v1. Persistence remains identity-continuity evidence, not evidence
that a decision or correction is correct or beneficial.

I3 passed through `intelligence-use-receipt-v1` on the existing task/status and Living Product
Graph read surfaces. The receipt retains per-item source/receiver identity, route and comparison
metrics, exact changed and unchanged I1 fields, and explicit reasons for every unearned evidence
state. Material influence remains distinct from beneficial impact, which is still unsupported
without L1 outcome evidence.

I2 passed through `deliberation-receipt-v1` on the same task/status and Living Product Graph reads
plus opt-in CLI rendering. Attribution is based on execution identities and bounded final
artifacts, never persona labels or hidden reasoning. Missing, failed, timed-out, tainted, partial,
foreign, and future-version cases fail closed.

## Exact next dispatch

1. **Completed — R5:** preserve the 0.1.2 supported/experimental boundary, verified tag and release
   commit, trusted publication evidence, artifact hashes, provenance verification, and clean
   public-index installation; R5 passed on 2026-07-22.
2. **Completed — R2:** keep the 0.1.1 release evidence, PyPI package, GitHub Release, and living
   roadmap links intact; R2 passed on 2026-07-21.
3. **Completed — R3:** preserve the supported provider/auth matrix, redacted live Claude and
   Codex/GPT evidence, deterministic degraded-state coverage, and exact eleven-tool boundary.
4. **Completed — R4:** preserve the frozen scenario, sanitized accepted replay, restart/material-use
   assertions, provider provenance, failure matrix, and exact eleven-tool boundary.
5. **Completed — G1:** preserve the versioned `ace landscape` contract, deterministic evidence,
   visible uncertainty, and strict read-only boundary established by the G1 closeout.
6. **Completed — IA-R1:** preserve the verified `/landscape` hierarchy, visible uncertainty and
   provenance, bounded failures, and strict read-only boundary established by the IA-R1 closeout.
7. **Completed — I1:** preserve stable decision/correction identities, structured human
   dispositions, lifecycle and provenance evidence, restart continuity, and the no-execution
   boundary.
8. **Completed — I2:** preserve the frozen bounded receipt, execution-identity attribution,
   artifact-grounded conflict, synthesis dispositions, degraded coverage, restart evidence, green
   branch CI, and exact eleven-tool boundary. Keep I2 distinct from claims of correctness, benefit,
   causality, or hidden-reasoning access.
9. **Completed — F1:** preserve the canonical definition, continuous-delta v1 scope, additive
   v146-v154 contracts, real measurement-to-resolution restart evidence, limitations, and exact
   eleven-tool boundary. Do not reopen F1 for forecast breadth or adapters.
10. **Candidate evidence gate — L1:** preserve the negative public-data result and collect a new
   preregistered, independently timed outcome cohort with verified attribution. Do not run or select
   a model-only comparison as a substitute for the failed persistence gate; eventual promotion
   requires favorable cluster-adjusted evidence against every declared control.

An outcome moves to `passed` only when scope, acceptance checks, evidence, limitations, roadmap
reconciliation, and downstream readiness have all been recorded. Implementation alone is
`candidate`, not `passed`.
