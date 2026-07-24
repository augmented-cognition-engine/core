# R5 ace-core 0.1.2 release evidence

Date: 2026-07-22

Outcome: **passed — verified tag, GitHub Release, trusted PyPI publication, provenance, artifact
hashes, and clean public-index installation completed**

## Intended release

R5 ships `ace-core` 0.1.2 as a backward-compatible developer-preview patch release. It keeps
the supported CLI, import package, extension entry point, and exactly eleven thin MCP tools stable
while packaging the completed G1, I1, and I3 inspectability work and the R3-supported Codex
subscription route.

The release notes distinguish supported additions from experimental engine work. F1 continuous-
delta foresight, bounded/adaptive routing, and the L1 evaluator ship as experimental source. L1's
negative public-data probe remains `benefit_not_established`; 0.1.2 does not claim beneficial
impact, unlock F2, or add autonomous execution authority.

## Version and compatibility scope

The release aligns these identities at `0.1.2`:

- Python distribution metadata;
- `ace.__version__`;
- `ace_mcp_client.__version__`;
- engine API/health version;
- Codex app-server client identity;
- reference extension version;
- editable lockfile package identity; and
- trusted-publishing workflow default `v0.1.2`.

Schemas v143-v155 are additive. The package remains Python 3.12-only. Atrium/Canvas source remains
repository beta and outside the wheel/sdist. The complete self-hosted Compose journey still uses a
source checkout for pinned runtime assets.

## Release scope

Supported:

- authenticated read-only Living Product Graph landscape;
- I1 decision/correction identities, dispositions, lifecycle, provenance, and restart continuity;
- I3 intelligence-use receipts with exact structured decision deltas;
- explicit Codex ChatGPT-subscription provider selection and diagnostics;
- bounded public task execution/resource receipts; and
- unchanged CLI and eleven-tool MCP boundary.

Experimental:

- F1 graph-grounded continuous-delta foresight and its measurement/resolution contracts;
- bounded interactive and advisory adaptive reasoning routes;
- broader foresight HTTP and Canvas projections; and
- the L1 sample-aware evaluator and preserved negative probe.

## Local gates

| Gate | Candidate result |
|---|---|
| Version/package/provider/roadmap identity | `62 passed` after the Docker CLI-package guard was added |
| L1/F1/I3 focused regression | `164 passed` |
| Full zero-extension non-E2E suite | `6568 passed, 47 skipped, 242 deselected` |
| Full extension-enabled non-E2E suite | `6576 passed, 46 skipped, 235 deselected` on the release-gate rerun |
| Ruff lint and formatting | lint passed; all `1804` Python files formatted |
| Canvas typecheck, Vitest, production build | TypeScript/Vite build passed; `288 passed` (existing large-chunk warning retained) |
| Security and workflow audit | secret scan and `actionlint` passed; no known third-party vulnerabilities after updating the disposable environment's `pip` to 26.1.2 |
| Wheel and sdist build/metadata/archive inspection | Twine and payload inspection passed; no tests, Canvas UI, Git state, caches, or real `.env` files shipped |
| Clean isolated wheel install | Python 3.12 install passed outside the checkout; CLI, version identities, eleven MCP tools, schema v155, I3 module, and installed docs verified |
| Schema-zero-to-v155 API restart | restart/kernel scope `5 passed`; Compose applied `154` migration files and validated schema v155 |
| Docker image/Compose health | non-root image probe passed; isolated Compose `/health/live`, `/health/ready`, and `/health` returned 200 with version 0.1.2 |

The extension-enabled suite's first attempt produced one SurrealDB failed-transaction result in
`test_confirmed_erase_removes_row_and_writes_log` after 6,575 other tests passed. The exact test
then passed alone, its complete 11-test forget sequence passed, and the full 6,576-test release-gate
rerun passed. No product-code retry or suppression was added; the transient observation remains
recorded here for CI comparison.

The candidate-stage `pip-audit` necessarily skipped the then-unpublished
`ace-core==0.1.2` distribution itself while auditing its installed third-party dependency set.

## Public release gates

Completed on 2026-07-22:

- release scope merged through [PR #23](https://github.com/augmented-cognition-engine/core/pull/23)
  and the recovered provider-runtime work through
  [PR #24](https://github.com/augmented-cognition-engine/core/pull/24);
- verified release commit
  [`d9e8baffd70b95821af751612bac6c499a81ab8f`](https://github.com/augmented-cognition-engine/core/commit/d9e8baffd70b95821af751612bac6c499a81ab8f)
  matched `origin/main`, with [all six merged-main CI jobs](https://github.com/augmented-cognition-engine/core/actions/runs/29966719164)
  green;
- annotated tag [`v0.1.2`](https://github.com/augmented-cognition-engine/core/tree/v0.1.2)
  resolves to that exact verified commit;
- [GitHub Release](https://github.com/augmented-cognition-engine/core/releases/tag/v0.1.2)
  published and triggered the
  [trusted-publishing workflow](https://github.com/augmented-cognition-engine/core/actions/runs/29967200238);
- the workflow validated tag/package-version equality, built and checked both distributions, and
  published [ace-core 0.1.2 on PyPI](https://pypi.org/project/ace-core/0.1.2/);
- downloaded workflow artifacts matched PyPI's SHA-256 digests exactly:
  - `ace_core-0.1.2-py3-none-any.whl` —
    `63379684a46f5ecac461b0900dbfd88f632895d5aa2c45a02add26b957d85a85`;
  - `ace_core-0.1.2.tar.gz` —
    `e2e2e2bef7da0997735552d3cc9c705f67c80872491943ef6813498ec6e69109`;
- `pypi-attestations verify pypi` cryptographically verified both public distributions against
  `https://github.com/augmented-cognition-engine/core`; and
- a cache-free public-index installation in a fresh Python 3.12.13 environment confirmed
  distribution/import/thin-client version `0.1.2`, a working `ace --help`, and the exact eleven
  public MCP tools.

Trusted publishing emitted GitHub's known Node.js 20 deprecation warnings for the v4 artifact
actions, which GitHub ran on Node.js 24. The clean install also reported normalized invalid
version specifiers from transitive upstream package metadata. Neither warning changed the built
artifacts, provenance result, installed ACE identity, or public contract verification.
