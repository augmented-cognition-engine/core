# GC1 — public governed-cognition builder surface (v1)

**Status:** public surface passed; GC1 remains active  
**Date:** 2026-08-09  
**Outcome:** GC1, supported governed-cognition builder journey

## Claim

The public `ace-core==0.4.2` distribution exposes a supported builder workflow for teaching,
inspecting, governing, materially using, and retiring reusable cognition through the existing
authenticated application boundary. This record proves the public package and CLI surface. It does
not claim that the full external-consumer, restart, and failure-control journey has passed.

## Public release identity

| Component | Public identity | Release |
|---|---|---|
| Core + Intelligence | `ace-core==0.4.2` | [GitHub](https://github.com/augmented-cognition-engine/core/releases/tag/v0.4.2) · [PyPI](https://pypi.org/project/ace-core/0.4.2/) |

The release tag resolves to commit `b5d490569e1d9b829d607790cbee03c1266aa4fe`. The
[trusted publication run](https://github.com/augmented-cognition-engine/core/actions/runs/31340444871)
validated the exact tag-to-package version, built and checked both distributions, and published to
PyPI using trusted identity. The public artifacts are:

- wheel `ace_core-0.4.2-py3-none-any.whl`, SHA-256
  `d5f2f3f9280f7b019fa1d4e90a11747bf36d19d08852cde092127160d38767b0`;
- sdist `ace_core-0.4.2.tar.gz`, SHA-256
  `a8816b7c64029b6fcb082d24e9ad9d1b254d200e1c5d5cebd578cd1fe083a9e8`.

## Fresh public-index verification

A new Python 3.12 virtual environment installed `ace-core==0.4.2` from PyPI after refreshing the
public package index. It had no source checkout or locally built wheel on its import path.

The installed distribution and all three runtime identities agreed:

```text
distribution  ace.__version__  ace_mcp_client.__version__  core VERSION
0.4.2         0.4.2            0.4.2                       0.4.2
```

The installed `ace cognition --help` command exposed the supported operations:

```text
diff
head
inspect
lifecycle
review
revision
selection
teach
use
use-receipt
```

The release-candidate verification before publication also passed:

- 30 focused release, cognition, roadmap, and evidence tests;
- 7,389 Core tests, with 48 expected skips and 247 excluded end-to-end tests;
- 7,377 zero-extension tests, with 48 expected skips and 259 extension-dependent exclusions;
- four kernel-boundary tests;
- Ruff lint and format checks;
- wheel and sdist build; and
- an isolated install of the built wheel with the same version and CLI-surface result.

GitHub CI independently passed lint, security, Canvas, Core, zero-extension, and Docker gates on
the release pull request before merge.

## Boundary result

- The CLI is a thin builder experience over the existing authenticated cognition API.
- Core still owns authority, immutable proposals and revisions, active heads, review receipts,
  selection and use receipts, lifecycle transitions, and persistence.
- The command reports cognition use only when a completed fresh task has matching non-empty
  selection and use revision identities plus a material-use hash.
- The public release does not add model-write authority, a second cognition model, or a twelfth MCP
  tool.

## Remaining GC1 gate

GC1 remains `active`. An external consumer must still run the supported public interface against a
real deployment and prove, across an operator restart:

1. a sourced proposal is not selectable before human disposition;
2. an authorized human can inspect the semantic change and approve the exact proposal;
3. a later invocation materially uses the exact approved revision with complete attribution;
4. the revision and active head survive restart unchanged;
5. authorized retirement is durable; and
6. a subsequent required use fails because the cognition is retired, not because of a network or
   unrelated runtime failure.

The independent Market Intelligence repository owns that consumer packet. Passing it is required
before GC1 can advance to `passed`.

## Reconciliation decision

The 0.4.2 public builder-surface dependency advances from local candidate to public and verified.
GC1 does not advance: its external-consumer, restart, and failure-control dependencies remain open.
