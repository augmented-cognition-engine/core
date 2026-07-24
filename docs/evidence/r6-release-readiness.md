# R6 ace-core 0.1.3 release readiness

Date: 2026-07-23

Outcome: **candidate — local release gates passed; public release gates pending**

## Intended release

R6 packages `ace-core` 0.1.3 as a backward-compatible developer-preview patch release. It adds
the supported bounded I2 attributable-deliberation receipt and ships the current extension
invocation lifecycle, SDK, conformance helper, reference action, HTTP routes, and Canvas wiring as
explicitly experimental surfaces.

The supported CLI identities and exactly eleven thin MCP tools remain unchanged. The release does
not promote extension invocation to stable, claim beneficial impact for L1, establish hidden
reasoning access, or add general unattended execution authority.

## Version and compatibility scope

The candidate aligns these identities at `0.1.3`:

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

## Candidate verification

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

These are local candidate hashes only. The trusted-publishing artifacts will be rebuilt from the
verified tag and independently compared with PyPI after publication.

## Public release gates

Promotion to `passed` requires:

1. a reviewed release-preparation PR and green PR CI;
2. a verified merge commit on `main` with all six merged-main CI jobs green;
3. an annotated `v0.1.3` tag resolving to that exact commit;
4. a published GitHub Release triggering the trusted PyPI workflow;
5. successful tag/package-version validation and distribution checks;
6. matching GitHub/PyPI artifact SHA-256 digests and verified PyPI attestations; and
7. a cache-free public-index install confirming version identities, CLI, schema v157, reference
   extension discovery, and exactly eleven MCP tools.

No artifact has been published at candidate preparation time.
