# R6 ace-core 0.1.3 release evidence

Date: 2026-07-23

Outcome: **passed — verified tag, GitHub Release, trusted PyPI publication, provenance, artifact
hashes, and clean public-index installation completed**

## Intended release

R6 ships `ace-core` 0.1.3 as a backward-compatible developer-preview patch release. It adds
the supported bounded I2 attributable-deliberation receipt and ships the current extension
invocation lifecycle, SDK, conformance helper, reference action, HTTP routes, and Canvas wiring as
explicitly experimental surfaces.

The supported CLI identities and exactly eleven thin MCP tools remain unchanged. The release does
not promote extension invocation to stable, claim beneficial impact for L1, establish hidden
reasoning access, or add general unattended execution authority.

## Version and compatibility scope

The release aligns these identities at `0.1.3`:

- Python distribution metadata and editable lockfile;
- `ace.__version__`;
- `ace_mcp_client.__version__`;
- engine API/health version;
- reference extension version; and
- trusted-publishing workflow default `v0.1.3`.

Python 3.12 remains the supported interpreter. Schemas v156-v157 are additive. Atrium remains
repository beta source outside the Python wheel/sdist and supported runtime.

## Release scope

Supported:

- bounded `deliberation-receipt-v1` projection through existing task/status, CLI, thin-client,
  and Living Product Graph reads;
- observable reasoning-shape selection, execution-identity contributor artifacts,
  artifact-grounded conflicts, synthesis dispositions, and explicit degraded coverage;
- existing I1 decision/correction and I3 intelligence-use receipt compatibility; and
- unchanged CLI and exactly eleven public MCP tools.

Experimental:

- authenticated `extension-invocation-v1` submission and
  `extension-invocation-receipt-v1` projection;
- deterministic capability negotiation, scoped discovery/listing, attempt history, linked retry,
  cooperative cancellation, output validation, and immutable artifact references;
- candidate Extension SDK registration handles, manifests, conformance helper, scaffold, and
  reference `product:product-check` action; and
- prospective L1 preregistration tooling with `collection_not_started` readiness state.

## Explicit non-promotion boundary

Phase 7 conditionally passed current-version stabilization. Version 0.1.3 does not establish:

- N-1 or multi-release Core/consumer compatibility;
- safe execution of untrusted extension code or independent security assessment;
- distributed task claiming, leasing, crash/partition recovery, or exactly-once external effects;
- complete extension-specific resource ceilings and operational telemetry; or
- beneficial decision impact from foresight.

These are promotion or later-outcome gates, not hidden release claims.

## Local gates

| Gate | Result |
|---|---|
| Version/package/workflow/roadmap identity | passed; distribution, import, thin client, engine, reference extension, lockfile, workflow default, README, changelog, maturity inventory, and R6 roadmap state align at 0.1.3 |
| Focused identity/I2/extension/schema/MCP/roadmap regression | `223 passed` |
| Full extension-enabled non-E2E suite | `6,661 passed, 46 skipped, 235 deselected` |
| Full zero-extension non-E2E suite | `6,651 passed, 47 skipped, 244 deselected`; explicit kernel boundary `4 passed` |
| Ruff lint and formatting | lint passed; all `1,819` Python files formatted |
| Canvas typecheck, Vitest, and production build | TypeScript passed; `291 passed`; production and naked builds passed; naked boundary `9 passed` |
| Secret, workflow, and dependency audit | staged secret scan and `actionlint` passed; `pip-audit` found no known third-party vulnerabilities and skipped only the unpublished local `ace-core==0.1.3` candidate |
| Wheel/sdist build, metadata, and archive inspection | Twine passed; wheel has 1,093 files, sdist 1,194, schema through v157, reference entry point, 17 evidence docs, one design note, and no tests, Canvas, Git state, or real `.env` |
| Clean isolated Python 3.12 wheel install | passed on Python 3.12.13; all four version identities are 0.1.3, CLI loads, exactly eleven MCP tools register, `product` entry point resolves, 156 migration files include v157, and packaged R6 evidence is present |

Phase 7 already recorded current-source Core/consumer conformance, real restart persistence, clean
Core and Marketing packages, naked-kernel behavior, and wired browser acceptance. R6 repeats the
release-critical package and contract gates against the versioned candidate.

The first full extension-enabled run reported two Layer 5 recency-tier failures caused by
50–100 ms production deadlines leaking into semantic live-database tests. Direct production-path
probes completed full concurrent tier loads in 1.75–10.36 ms with the composite index and healthy
pool. The tests now use isolated semantic deadlines while separate assertions pin the production
defaults, deterministic index plan, and explicit timeout degradation; the focused module passed
35 tests and the authoritative full rerun passed all 6,661 selected tests.

During the first zero-extension run, a concurrent user-owned documentation reorganization moved
point-in-time records into `docs/evidence/` while the suite was reading the old path. The completed
refactor preserves the evidence, updates package data and durable links, makes `ROADMAP.md` the
operational authority, and passed focused contract checks. The authoritative settled-tree naked
rerun passed all 6,651 selected tests.

Candidate artifact SHA-256 values:

- `ace_core-0.1.3-py3-none-any.whl` —
  `72b057713727e352a4a2aca6a37bcb049b2c067e23e0b3200995cba7f84d4636`;
- `ace_core-0.1.3.tar.gz` —
  `6fbad095bcabc7d016b2a5f3b60b0183dbe676eade3070235550a790d596dfc2`.

These local candidate hashes differ from the trusted-publishing rebuild recorded below because
the candidate preceded final evidence-only wording and Python archives also include build
metadata. Both builds were independently inspected, and the workflow artifacts match PyPI
exactly.

## Public release gates

Completed on 2026-07-23:

- release preparation merged through [PR #32](https://github.com/augmented-cognition-engine/core/pull/32)
  after [all six PR CI jobs](https://github.com/augmented-cognition-engine/core/actions/runs/30065307192)
  passed;
- verified release commit
  [`6e7d28b864b591cad473572e38ffdc7dc28a86de`](https://github.com/augmented-cognition-engine/core/commit/6e7d28b864b591cad473572e38ffdc7dc28a86de)
  matched `origin/main`, with
  [all six merged-main CI jobs](https://github.com/augmented-cognition-engine/core/actions/runs/30065533622)
  green;
- annotated tag [`v0.1.3`](https://github.com/augmented-cognition-engine/core/tree/v0.1.3)
  resolves to that exact verified commit;
- [GitHub Release](https://github.com/augmented-cognition-engine/core/releases/tag/v0.1.3)
  published and triggered the
  [trusted-publishing workflow](https://github.com/augmented-cognition-engine/core/actions/runs/30065775723);
- the workflow validated tag/package-version equality, built and checked both distributions, and
  published [ace-core 0.1.3 on PyPI](https://pypi.org/project/ace-core/0.1.3/);
- downloaded workflow artifacts matched PyPI's SHA-256 digests exactly:
  - `ace_core-0.1.3-py3-none-any.whl` —
    `963353a66942956d20e50f2c2aa6707476ca749511bf10a986d1e706ffd326c7`;
  - `ace_core-0.1.3.tar.gz` —
    `bedc2b3b9b2a83d2768082d91ed42b67c87dd389d789fb65800bb5752ec12846`;
- `pypi-attestations verify pypi` cryptographically verified both public distributions against
  `https://github.com/augmented-cognition-engine/core`; and
- a cache-free public-index installation in a fresh Python 3.12.13 environment confirmed all five
  distribution/import/thin-client/engine/reference-extension version identities at `0.1.3`, a
  working `ace --help`, exactly eleven MCP tools, the `product` extension entry point, 156 schema
  files through v157, and the packaged R6 evidence record.

The clean install reported normalized invalid version specifiers from transitive upstream package
metadata. The warning did not change resolution, the installed ACE identity, or any public
contract verification.
