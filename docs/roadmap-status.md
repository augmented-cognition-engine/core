# Public roadmap status

Last reconciled: 2026-07-21

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
| IA-R1 | Next | candidate | [Read-only product-map evidence](ia-r1-product-map.md) records the six-question operator hierarchy, strict GET-only boundary, visible uncertainty/failures, local verification, and remaining branch/final-head/main CI closeout |
| I1 | Next | ready | G1's stable read contract and R4's developer-preview golden path have passed; inspectability work may start without adding execution authority, after the smaller IA-R1 operator-view slice is framed |
| T1 | Next | not ready | Recovery, replay, portability, cancellation, and resource guarantees are not yet frozen |
| E1 | Next | not ready | Depends on conformance evidence and preservation of the eleven-tool boundary |
| B1 | Later | not ready | Depends on inspectable approval receipts and explicit execution authority |
| L1 | Later | not ready | Depends on stable outcome identity, provenance, and calibration evidence |
| H1 | Later | not ready | Depends on tenancy, portability, authority, and recovery guarantees |
| E2 | Later | not ready | Depends on E1 conformance and stable compatibility policy |

## Exact next dispatch

1. **Completed — R2:** keep the 0.1.1 release evidence, PyPI package, GitHub Release, and living
   roadmap links intact; R2 passed on 2026-07-21.
2. **Completed — R3:** preserve the supported provider/auth matrix, redacted live Claude and
   Codex/GPT evidence, deterministic degraded-state coverage, and exact eleven-tool boundary.
3. **Completed — R4:** preserve the frozen scenario, sanitized accepted replay, restart/material-use
   assertions, provider provenance, failure matrix, and exact eleven-tool boundary.
4. **Completed — G1:** preserve the versioned `ace landscape` contract, deterministic evidence,
   visible uncertainty, and strict read-only boundary established by the G1 closeout.
5. **Candidate — IA-R1:** preserve the locally verified `/landscape` hierarchy and strict
   read-only boundary; require green branch, final-head, and merged-main CI before moving the
   outcome to passed.
6. **Ready, sequence after IA-R1 — I1:** both stated dependencies now pass, but keep the next slice
   thin: establish the read-only operator information architecture before expanding approval-
   receipt or outcome inspection behavior.

An outcome moves to `passed` only when scope, acceptance checks, evidence, limitations, roadmap
reconciliation, and downstream readiness have all been recorded. Implementation alone is
`candidate`, not `passed`.
