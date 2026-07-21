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
model superiority. R1 now provides an outcome-led entry path, while the clean trials remain an
AI-operated proxy rather than independent human usability validation.

## Living roadmap

| ID | Phase | State | Evidence gap or dependency |
|---|---|---|---|
| R1 | Now | passed | [2026-07-21 clean-trial evidence](r1-onboarding-evidence.md): isolated macOS and Linux journeys both reached useful recommendations without maintainer help or architecture knowledge; intentional recovery and `ace doctor` passed |
| R2 | Now | passed | [0.1.1 release evidence](r2-release-evidence.md) records clean macOS/Linux installs, artifacts, required PR/main CI, `v0.1.1`, trusted PyPI publication, GitHub Release, and a fresh public-index install against verified main commit `1662eaa` |
| R3 | Now | candidate | Frozen provider/auth matrix, structured diagnostics, deterministic degraded states, a live Codex/GPT smoke, and pre-update CI are recorded in [`r3-provider-validation.md`](r3-provider-validation.md); an authorized live Claude smoke and final CI against current main remain required before `passed` |
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

1. **Completed — R2:** keep the 0.1.1 release evidence, PyPI package, GitHub Release, and living
   roadmap links intact; R2 passed on 2026-07-21.
2. **Active — R3:** complete one authorized Claude live smoke, final branch CI, and redacted
   evidence reconciliation; deterministic implementation and the Codex/GPT route are candidate-ready.
3. **Do not start yet — R4:** product-builder golden-path demonstration until R3 also passes.
4. **Do not promote yet — G1 / IA-R1:** preserve the read-only boundary; G1 remains candidate and
   IA-R1 remains dependency-closed until the missing public evidence is reconciled.

An outcome moves to `passed` only when scope, acceptance checks, evidence, limitations, roadmap
reconciliation, and downstream readiness have all been recorded. Implementation alone is
`candidate`, not `passed`.
