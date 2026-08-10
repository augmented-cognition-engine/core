# B1C independent action adapter candidate evidence (v1)

**Status:** candidate; public review, merge, and released-artifact evidence pending

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
- reviewed head: pending;
- merge identity: pending;
- GitHub Actions run: pending; and
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

This is isolated local-wheel evidence, not a PyPI or ACE 0.5.0 release claim. Public review,
final-head CI, and merge reconciliation remain to be added.

## Remaining closeout gate

B1C remains a candidate until public review, final-head CI, merge reconciliation, and released
artifact evidence exist. B1 additionally requires explicit action review, repair, and promotion.
T1 portability/topology and the complete context-to-action-to-updated-state release journey also
remain before ACE 0.5.0 can pass.
