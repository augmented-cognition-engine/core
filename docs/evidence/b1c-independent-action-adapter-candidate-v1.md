# B1C independent action adapter candidate evidence (v1)

**Status:** candidate, merged to `main`; released-artifact evidence pending

**Date:** 2026-08-10

**Outcome:** first independently packaged trusted adapter over the public governed-action contract

## Claim

The candidate adds `ace-reference-workspace-action` as a separately buildable distribution. It
imports only the public `ace.core` contract, is excluded from the Core package configuration, and
is never dynamically discovered. A host must construct it with an approved workspace and register
its exact immutable artifact identity.

Its single effect is deliberately small and observable: create one absent file below that
workspace. The implementation refuses overwrite, traversal, symlinked parents, missing parents,
ambiguous inputs, broad filesystem access, network access, and command execution. Directory-relative
no-follow opens close the validation-to-open symlink window. Preparation is effect-free; exclusive
creation happens only during execution.

This is a candidate boundary record. It is not a published package, general tool framework,
untrusted-plugin sandbox, distributed execution guarantee, or completion of B1/T1/0.5.0.

## Candidate identity

- branch: `codex/b1c-independent-action-adapter`;
- final reviewed head: `494b8d9b28cdfc10f0e5bb0980944ada1c05b033`;
- squash merge on `main`: `496b14dc21ad098952597cbbe7db86641d7702e8`;
- successful final-head GitHub Actions run:
  [31400684983](https://github.com/augmented-cognition-engine/core/actions/runs/31400684983); and
- release identity: pending.

## Current verification

Focused source-distribution and Core-host checks:

```text
45 passed, 1 skipped in 1.21s
```

That combined run covers B1A execution, B1B composition/restart, B1C adapter conformance and
packaging, and roadmap/evidence/package integrity. The B1C-only source checks passed `11` tests.

Full non-e2e repository regression with extensions disabled:

```text
7420 passed, 50 skipped, 260 deselected in 194.57s
```

Naked-kernel boundary:

```text
4 passed in 0.97s
```

Repository-wide Ruff checks over the new distribution, formatting checks, and `git diff --check`
passed. The first sandboxed full run could not bind an existing test-only localhost port; the same
unchanged suite passed outside that network sandbox. This was an execution-environment restriction,
not an ignored test or product failure.

## Independent wheel and effect probe

The two wheels were built separately:

| Artifact | SHA-256 |
|---|---|
| `ace_core-0.4.4-py3-none-any.whl` | `d3e58c22f1516b503926cdeb0546330270e67f177c7b635894016bb0f525e100` |
| `ace_reference_workspace_action-0.1.0-py3-none-any.whl` | `32c95470b751dbe0e0954d1a9daae636d7b69587c954d16ee56a4a5de25ae4dd` |

Archive inspection found no `ace_reference_workspace_action` or adapter-source path in the Core
wheel. The adapter wheel contains only its two package modules and distribution metadata.

A new Python 3.12 environment installed both candidate wheels from local paths. Because the
adapter intentionally declares the future release floor `ace-core>=0.5.0`, the unreleased 0.4.4
Core candidate and adapter were installed without dependency resolution and the minimal public
contract dependency was installed separately. From `/private/tmp`, outside both source and build
trees, the probe imported Core and adapter modules from `site-packages`, prepared the exact action,
created `exports/proof.md`, and observed:

```json
{"adapter_module":"ace_reference_workspace_action.adapter","core_module":"ace.core.action_execution","disposition":"succeeded","effect_state":"confirmed","content":"# Installed B1C proof\n"}
```

This is isolated local-wheel evidence, not a PyPI or ACE 0.5.0 release claim.

## Public review and final-head CI

[Pull request #80](https://github.com/augmented-cognition-engine/core/pull/80) preserved the adapter
boundary and merged only after the refreshed final head passed all six repository gates:

- Lint;
- Tests (fast gate);
- Naked kernel (zero extensions);
- Canvas (core/ui/canvas);
- Security Audit; and
- Docker Build.

The first run and one rerun of the original B1C head each failed one pre-existing orchestration
test that inferred concurrency from an absolute sub-300-millisecond wall-clock threshold. B1C did
not touch that code; the same test passed repeatedly in isolation. The baseline repair was isolated
in [pull request #81](https://github.com/augmented-cognition-engine/core/pull/81): it replaced the
timing guess with a deterministic overlapping-execution assertion, passed all six gates, and merged
as `fd57abb881f59075f9b730b807039b17c460f5fa`. B1C then merged current `main`, passed its focused
72-test integration slice locally, and passed all six gates on the exact final reviewed head above.
No product behavior or B1C adapter material changed in the CI repair.

## Remaining closeout gate

B1C remains a candidate until released-artifact evidence exists. Public review, final-head CI,
merge reconciliation, local wheel isolation, and a real create-only installed-wheel effect are
complete. B1 additionally requires explicit action review, repair, and promotion. T1
portability/topology and the complete context-to-action-to-updated-state release journey also remain
before ACE 0.5.0 can pass.
