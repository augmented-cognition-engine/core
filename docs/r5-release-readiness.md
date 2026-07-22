# R5 ace-core 0.1.2 release-candidate readiness

Date: 2026-07-22

Outcome: **candidate — all local release gates passed; external release gates remain; nothing published**

## Intended release

R5 prepares `ace-core` 0.1.2 as a backward-compatible developer-preview patch release. It keeps
the supported CLI, import package, extension entry point, and exactly eleven thin MCP tools stable
while packaging the completed G1, I1, and I3 inspectability work and the R3-supported Codex
subscription route.

The release notes distinguish supported additions from experimental engine work. F1 continuous-
delta foresight, bounded/adaptive routing, and the L1 evaluator ship as experimental source. L1's
negative public-data probe remains `benefit_not_established`; 0.1.2 does not claim beneficial
impact, unlock F2, or add autonomous execution authority.

## Version and compatibility scope

The candidate aligns these identities at `0.1.2`:

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

## Candidate scope

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

Local artifact hashes belong in the release handoff rather than this packaged document: embedding
an archive's digest inside a document contained by that archive would make the digest
self-referential. Maintainers must rebuild from the reviewed release commit and record those
resulting release hashes; local candidate hashes are not publication attestations. `pip-audit`
necessarily skipped the unpublished `ace-core==0.1.2` distribution itself while auditing its
installed third-party dependency set.

## Non-local release gates

R5 cannot move to `passed` until maintainers intentionally complete the external release process:

1. review and commit the exact candidate scope;
2. open and merge a release PR with required CI green;
3. verify merged-main CI and the release commit;
4. create tag `v0.1.2` on that verified commit;
5. publish the GitHub Release and allow trusted PyPI publishing;
6. verify attestations and archive hashes; and
7. install `ace-core==0.1.2` from the public index in a clean Python 3.12 environment.

No commit, branch, PR, tag, push, GitHub Release, or PyPI publication is part of this local
readiness packet.
