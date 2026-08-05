# ace-core 0.3.1 Productized State release evidence

Status: **release candidate; trusted publication and public-index verification pending**

Date: 2026-08-05

## Intended release

ace-core 0.3.1 completes the Productized State promise for the 0.3.x release line. A builder can
install ACE and a compatible extension, discover its bounded Product State adapter, ingest product
context under authenticated Core-owned scope, inspect composed state and provenance, make and
correct a decision, restart the runtime, and observe the exact correction materially influence a
later decision.

The patch preserves the package and import identities, supported Python 3.12 runtime, schema head
v171, existing CLI identities, and exactly eleven thin MCP tools. It adds one focused `ace state`
command group and two authenticated HTTP reads/writes without granting models or source content
product-scope, review, promotion, or execution authority.

## Release scope

- Product State adapter discovery and ingestion through the trusted extension boundary.
- Canonical authenticated product scope with no legacy default-product fallback and fail-closed
  rejection of cross-product adapter output.
- The `ace state capabilities`, `ingest`, `invoke`, `correct`, and `inspect` builder journey.
- Read-only Living Product Graph projection of allowlisted State Engine and I1–I3 receipt families.
- The provider-free Fjord Operations example, frozen journey, public guide, evidence, and bounded
  capability-maturity statement.
- Version alignment for the distribution, imports, thin client, engine, reference extension,
  container metadata, lockfile, and trusted-publishing default.

## Frozen engineering evidence

The implementation merged through [PR #51](https://github.com/augmented-cognition-engine/core/pull/51)
at merge commit `927b5a367991b13c547aa6b412cdad1624ac2a0c`. Its exact head
`6aee6b5ef9263adf55e4c16c36369665a11e9448` passed all six official CI jobs in
[run 31036206760](https://github.com/augmented-cognition-engine/core/actions/runs/31036206760): lint,
the fast gate, naked kernel, Canvas, security audit, and Docker build with health-endpoint
verification.

The frozen [`productized-state-public-journey-v1`](productized-state-journey-v1.md) acceptance
passed authenticated ingestion and exact replay, complete scoped inspection, schema-zero v171 and
v168→v171 upgrade, real database/API/worker restarts, interruption/retry behavior, decision and
correction lineage, and exact later material use with zero provider calls. The machine receipt binds
config SHA-256 `7916f0f7566e74a9b1981210e3e710ceb5876e9874369ed18f9abc8c1c1cdbd3`, corpus SHA-256
`85907acc8ad5b9a73d2d7551ced98d1bb26d4b9ea51a189d262675cb5ff9ea28`, and acceptance SHA-256
`023dd9147e2f97227be12a7ad8bc13e3266389ca59cbe3c9c32063b67949f83c`.

## Release-candidate gates

Before publication, the exact release candidate must pass:

- package/import/client/engine/reference-extension/container/lock/workflow identity checks;
- focused Product State, authenticated scope, Living Product Graph, extension conformance, and
  frozen-journey tests;
- the complete extension-enabled and naked-kernel non-E2E suites;
- Ruff lint and format, dependency audit, secret scan, whitespace, JSON, and archive checks;
- deterministic current/v0.3.0 and mixed wheel/source-distribution compatibility;
- clean wheel installation with version, CLI, eleven-tool, schema, documentation, and naked-loading
  probes; and
- official pull-request CI for the exact candidate commit.

The GitHub Release must name an exact `v0.3.1` tag whose package version matches. The pinned trusted
workflow must build and publish the distributions. Registry files must match the release-commit
matrix artifacts, and a fresh environment must install `ace-core==0.3.1` from the public index and
repeat the supported identity probes before PS1 or issue #2 can be closed.

## Security and support boundary

PR #51 hardened the new write boundary so a missing or malformed token product and any adapter
output outside the authenticated product fail before persistence. Official security audit and the
focused cross-product, malformed-scope, foreign-read, and exact-replay tests passed for that head.
The v0.3.0 independent AI review is historical evidence for the inherited E1 trusted-extension
boundary; it is not represented as independent certification of the changed 0.3.1 artifact.

The supported claim remains one database, one API/worker deployment, synchronous adapters, trusted
installed Python extensions executing in process, and fictional public-safe evidence. It does not
establish hostile-code isolation, distributed ordering, multi-writer or multi-region guarantees,
general real-world causal correctness, autonomous learning, a general world model, or beneficial
impact.

## Publication decision

Publication remains fail-closed until every candidate gate above passes for one exact commit. This
record will be reconciled after publication with the immutable release commit and tree, tag,
workflow run, package-matrix receipt, GitHub/PyPI URLs and hashes, and clean public-install receipt.
