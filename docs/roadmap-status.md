# Public roadmap status

Last reconciled: 2026-07-20

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
model superiority. The current entry experience is also developer-oriented: it exposes setup and
architecture before making the product-building value and first useful reasoning outcome obvious.

## Living roadmap

| ID | Phase | State | Evidence gap or dependency |
|---|---|---|---|
| R1 | Now | ready | Validate an outcome-led journey in which a product builder can understand ACE, install it, complete guided setup, recover from common failures, and reach a useful reasoning result without maintainer help or architecture knowledge on macOS and Linux |
| R2 | Now | not ready | Requires R1 findings; then cut 0.1.1 with an obvious product-builder quickstart, outcome-led entry copy, focused PyPI copy, repaired absolute links, and release-workflow maintenance |
| R3 | Now | ready | Verify supported provider routes, authentication, `ace doctor`, actionable failures, and degraded behavior |
| R4 | Now | not ready | Requires R1 and R3 to pass before publishing a product-builder golden path that starts with a recognizable decision rather than ACE internals |
| G1 | Next | candidate | Read-only projection and kernel tests exist; supported journey, failure behavior, compatibility boundary, and public evidence are incomplete |
| IA-R1 | Next | not ready | Depends on G1 passing; read-only inspection only, with no new mutation or execution authority |
| I1 | Next | not ready | Depends on stable read contracts and the developer-preview golden path |
| T1 | Next | not ready | Recovery, replay, portability, cancellation, and resource guarantees are not yet frozen |
| E1 | Next | not ready | Depends on conformance evidence and preservation of the eleven-tool boundary |
| B1 | Later | not ready | Depends on inspectable approval receipts and explicit execution authority |
| L1 | Later | not ready | Depends on stable outcome identity, provenance, and calibration evidence |
| H1 | Later | not ready | Depends on tenancy, portability, authority, and recovery guarantees |
| E2 | Later | not ready | Depends on E1 conformance and stable compatibility policy |

## Exact next dispatch

1. **Required spine — R1:** outcome-led product-builder onboarding audit. Measure comprehension,
   time to first useful reasoning result, setup interventions, failure recovery, and whether the
   journey succeeds without maintainer help or architecture knowledge.
2. **Safe parallel — R3:** provider, authentication, diagnostics, and degraded-state validation.
3. **Queued — R2:** 0.1.1 onboarding, packaging, and documentation improvements after R1 records
   observed friction and evidence.
4. **Do not start yet — R4:** product-builder golden-path demonstration until R1 and R3 pass.
5. **Do not promote yet — G1 / IA-R1:** preserve the read-only boundary; G1 remains candidate and
   IA-R1 remains dependency-closed until the missing public evidence is reconciled.

An outcome moves to `passed` only when scope, acceptance checks, evidence, limitations, roadmap
reconciliation, and downstream readiness have all been recorded. Implementation alone is
`candidate`, not `passed`.
