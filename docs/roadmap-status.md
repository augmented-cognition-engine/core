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
| G1 | Next | passed | [`g1-living-product-graph-evidence.md`](g1-living-product-graph-evidence.md) records the frozen contract, supported `ace landscape` journey, deterministic replay, accepted/provisional/contested/rejected behavior, bounded failures, restart parity, strict read-only authority, and [green acceptance CI](https://github.com/augmented-cognition-engine/core/actions/runs/29872552736) |
| IA-R1 | Next | passed | [Read-only product-map evidence](ia-r1-product-map.md) and [green branch CI](https://github.com/augmented-cognition-engine/core/actions/runs/29889892587) record the six-question operator hierarchy, strict GET-only boundary, visible uncertainty/failures, local verification, and roadmap closeout |
| I1 | Next | passed | [`decision-correction-receipts.md`](decision-correction-receipts.md) records stable identities, complete decision context, all four dispositions, correction supersession/invalidation/contestation/expiry, authorization, isolation, redaction, explicit provenance gaps, and schema-zero-to-v145 restart continuity |
| I2 | Next | ready | I1 identities and read contracts have passed; attributable perspective selection, bounded contributor positions, disagreement, synthesis lineage, and honest partial/degraded behavior may start without exposing hidden chain-of-thought |
| I3 | Next | ready | I1 identities and R3 route evidence have passed; inspectable retained-intelligence states and exact decision effects may start while preserving null, harmful, stale, contested, failure, and degraded cases |
| F1 | Next | passed | [`f1-foresight-evidence.md`](f1-foresight-evidence.md) records the bounded continuous-delta v1 contract, real structured-measurement-to-comparator-to-resolution API/database scenario, restart-safe replay, cold-start behavior, proper scoring, limitations, and exact eleven-tool preservation through schema v154 |
| T1 | Next | not ready | Recovery, replay, portability, cancellation, and resource guarantees are not yet frozen |
| E1 | Next | not ready | Depends on conformance evidence and preservation of the eleven-tool boundary |
| F2 | Later | not ready | Broader consequence types and independently verified design evidence require L1 evidence or demonstrated user need; they do not keep F1 open |
| B1 | Later | not ready | Depends on inspectable approval receipts and explicit execution authority |
| L1 | Later | not ready | F1 is passed; L1 now depends on I3 material-use evidence, sample-size-aware reliability, explicit null/harmful/degraded influence, and comparison against no-foresight, naive/base-rate, and model-only controls |
| H1 | Later | not ready | Depends on tenancy, portability, authority, and recovery guarantees |
| E2 | Later | not ready | Depends on E1 conformance and stable compatibility policy; native telemetry sources belong to this adapter lane |

I1 passed through structured task decisions, authenticated human dispositions, and linked
correction observations exposed through the existing status/capture/load contracts. The disposable
real-API restart proof preserves the same decision, correction, provenance, lifecycle, and typed
relationship identities across fresh processes. Production API startup owns schema-zero-to-v145
replay on the supported SurrealDB 3.1.4 pin and 3.2.1; unknown future receipt versions degrade
without being reinterpreted as v1. Persistence remains identity-continuity evidence, not evidence
that a decision or correction is correct or beneficial.

## Exact next dispatch

1. **Completed — R2:** keep the 0.1.1 release evidence, PyPI package, GitHub Release, and living
   roadmap links intact; R2 passed on 2026-07-21.
2. **Completed — R3:** preserve the supported provider/auth matrix, redacted live Claude and
   Codex/GPT evidence, deterministic degraded-state coverage, and exact eleven-tool boundary.
3. **Completed — R4:** preserve the frozen scenario, sanitized accepted replay, restart/material-use
   assertions, provider provenance, failure matrix, and exact eleven-tool boundary.
4. **Completed — G1:** preserve the versioned `ace landscape` contract, deterministic evidence,
   visible uncertainty, and strict read-only boundary established by the G1 closeout.
5. **Completed — IA-R1:** preserve the verified `/landscape` hierarchy, visible uncertainty and
   provenance, bounded failures, and strict read-only boundary established by the IA-R1 closeout.
6. **Completed — I1:** preserve stable decision/correction identities, structured human
   dispositions, lifecycle and provenance evidence, restart continuity, and the no-execution
   boundary.
7. **Ready, parallel bounded lanes — I2 / I3:** I2 may add attributable deliberation and synthesis
   receipts without hidden chain-of-thought; I3 may add inspectable retained-intelligence use and
   exact decision effects. Keep their contracts and evidence separate.
8. **Completed — F1:** preserve the canonical definition, continuous-delta v1 scope, additive
   v146-v154 contracts, real measurement-to-resolution restart evidence, limitations, and exact
   eleven-tool boundary. Do not reopen F1 for forecast breadth or adapters.
9. **Next value proof — I3 then L1:** make resolved-forecast retrieval and exact decision effects
   inspectable, then compare ACE foresight with no-foresight, naive/base-rate, and model-only
   controls. I2 may proceed as a separate parallel attributable-deliberation lane.

An outcome moves to `passed` only when scope, acceptance checks, evidence, limitations, roadmap
reconciliation, and downstream readiness have all been recorded. Implementation alone is
`candidate`, not `passed`.
