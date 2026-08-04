# R7 ace-core 0.2.0 release-candidate readiness

Status: **local release-candidate gates passed; draft PR and CI reconciliation pending; publication not authorized**

R7 reconciles the complete TP0-TP8 and K1-K3 State Engine work into an inspectable `ace-core`
0.2.0 candidate. This record is intentionally not a release closeout. It may become a candidate
authorization packet after the pushed branch, a draft pull request, and available CI have been
recorded. R7 cannot become `passed` until a separately
authorized merge, `v0.2.0` tag, GitHub Release, trusted PyPI publication, provenance, matching
artifact hashes, and fresh public-index installation have all been verified.

## Authoritative starting state

R7 began from public `origin/main` commit `2fc4fe603aec7f1709a7acfc480dcf0307684d3e` on branch
`codex/release-0.2.0`, with the complete preserved State Engine worktree moved from
`codex/release-0.1.4`. The public main tree and the old branch base tree were identical before the
move; no v0.1.4 work was lost or reset.

Authoritative GitHub and PyPI checks corrected stale roadmap prose: v0.1.4 was publicly released on
2026-07-30 from public main. The non-draft GitHub Release and PyPI project both exist. Public PyPI
0.1.4 hashes are:

- wheel: `3de9c8e9920cd9d5fd5a12bd8c97beba8b949697c0fd7ff63d7ec95b6f823386`;
- sdist: `8149c0d556cf9df0efa0815ecdcd596318e99aa0e3d6cc0256d347c0a95c9571`.

The roadmap checkpoint incorrectly named 0.1.3 as current and is corrected by R7. The historical
0.1.4 changelog remains a real shipped release entry rather than being folded into 0.2.0.

## Intended v0.2.0 scope and support boundary

The candidate adds supported domain-neutral State Engine v1 contracts for bounded ingestion,
grounded temporal evidence, candidate/evidence packs, reviewed belief projection, reviewed
transition hypotheses, labeled action/no-action consequence rollouts and reconciliation, I3
reasoning-use receipts, authority-gated promotion/correction lineage, and single-node lifecycle and
operations receipts.

The supported measured topology is one ACE API/worker deployment, one SurrealDB/SurrealKV database,
and bounded synchronous adapter clients. Core owns authenticated product scope, stable identity,
validation, transactions, replay, and receipts. Connectors, extraction prompts/models and policy,
source mappings, and domain ontology remain extension-owned. Source/model content has no product,
task, tool, mutation, review, causal, or promotion authority.

The reference `evidence-query` and `promotion-review` task actions exercise the real production task
and extension-invocation routers but remain on the explicitly experimental HTTP surface. They do
not add a stable CLI/MCP command. The supported thin HTTP-backed MCP client remains exactly eleven
tools. The pre-existing broad in-process engine MCP command is a compatibility/internal surface,
not a second supported public client or a second State Engine.

## Integrated architecture audit

The candidate production path is reachable as:

```text
bounded adapter ingestion
-> grounded evidence and exact terminal receipts
-> candidate receipt and frozen evidence pack
-> reviewed as-of belief projection
-> challenged/reviewed transition revision
-> action/no-action rollout and labeled simulation context
-> durable task execution
-> I3 reasoning-use receipt
-> promotion proposal and authenticated authority receipt
-> existing insight memory plane
-> real restart and fresh retrieval
-> correction and append-only supersession
```

The real database restart acceptance
`test_tp6_rollout_reasoning_use_and_reconciliation_survive_restart` proves this chain through the
production task and extension-invocation routers; the capability is not evaluator-only. The
integrated audit also confirmed:

- grounded source records do not enter reviewed belief or memory merely because an extractor/model
  emitted them;
- item/batch success is persisted only with semantic work; retryable failure and dead letter remain
  visible;
- unknown, provisional, contested, rejected, degraded, failed, expired, invalidated, and superseded
  meanings remain distinct and inspectable;
- simulation tables/identities and reasoning context remain separate from observations and beliefs;
- promotion forbids model authority and requires exact evidence/task/use lineage plus human or
  exact allow-listed deterministic authority;
- caller/source payload cannot override authenticated product scope;
- Core imports no OLC or other domain extension; extensions import Core, and the naked kernel runs
  with extensions disabled;
- exact material IDs, replay conflicts, restart continuity, I3 use, and correction lineage are
  preserved; and
- promotion reuses the existing `insight` plane and I3 contract rather than creating duplicate
  memory or receipt systems.

Two bounded release-test defects were corrected during R7. The historical TP0 baseline test now
allows only release identity/revision drift when replayed outside its frozen reference commit, and
the reference extension unit test explicitly supplies and verifies the new product-lifecycle check.
Neither correction changes State Engine semantics or retained benchmark results.

## Version identity matrix

| Surface | Candidate identity |
|---|---|
| Python distribution / `pyproject.toml` | `ace-core` 0.2.0 |
| `ace.__version__` | 0.2.0 |
| `ace_mcp_client.__version__` | 0.2.0 |
| engine / FastAPI / health | 0.2.0 |
| reference extension | 0.2.0 |
| root editable lock entry | 0.2.0 |
| publish workflow default | `v0.2.0` with tag/package equality guard |
| Docker build arg / OCI labels / Compose service labels | 0.2.0 |
| Python | `>=3.12,<3.13` |
| schema head | v168 |

The lockfile was regenerated with `uv lock`; its only candidate identity change is the root
`ace-core` editable entry from 0.1.4 to 0.2.0. Unrelated dependency versions were not replaced.

## Scale and readiness evidence retained

TP8's expensive frozen 200,000-claim scale/recovery run and the follow-on K1-K3 readiness audit
precede R7. Their immutable release inputs and results are retained:

- TP8 manifest: `2a1551aa49abe8aec332a27ac7b62ede64a362d32a666fbbcc0dac005643d47e`;
- TP8 frozen raw dataset: `c58e36030f3835b71e82268e13b2f5d753ee6fb530a860b4075eb1ccd9cbcad8`;
- TP8 frozen 63-manifest set: `2e7c8b0a37fa6a7e7062c2cf077af7adfda41b6e83822b99a20f29fad498d2eb`;
- TP8 summarized result: `253abc29a565d3f4cc8d54eef88718a462262452b36ce937dac8e5875b43be56`;
- TP8 readiness receipt: `922a5e212a25300984ebe1a2b0525ca529c165cfae16fe02779d916b85f53fda`;
- TP8 compatibility result: `8935ce2b7e4b466e9f7e62d3b3b0772ee307565a1b312ae0dfb88dfdb78a874b`;
- K1-K3 frozen target: `0818b3b8acfd86051bd13ff1e6111748d42a78a617133bd13e75d40a7e55df00`;
- K1/K2/K3 raw result hashes:
  `ff781718d0f81bf8e540d33d07694aa9c66d7d5ec443a1377044074e5afa618b`,
  `159a01b17549cf53c1ea424612654a60760ad29d659e13b1b8b83c25a1515700`, and
  `3e104d732d4f56f42fefeee32c31ccfcdca8466bbbcc440c64d9b58a779d564c`;
- K1-K3 canonical machine receipt:
  `6d6c582f8d2e007fe74dfc5d52c312c7b8ee3cd924432152265d96e3ab5b9c99`;
- K1-K3 outcome hash:
  `6ebfb55ae0b4bc007ba63a7c0ca2974c8caa4aed2f8cc62d505678076f84735f`.

The retained database held 220,000 claims and 256,000 semantic records after the sustained sample.
K2 recorded 40/40 exact cases and replays, 35 required abstentions, and 8.924 ms transition p95.
K3 recorded 5/5 fresh-process journeys, 81.799 ms task p95, 42.534 ms promotion p95, 11.214 ms
retrieval p95, and 2.186 seconds maximum restart.

R7 revalidates the frozen identities and affected code. The full 200,000-claim load is rerun only if
candidate changes touch benchmark-affecting production paths after the retained measurement.
Release-only version, documentation, workflow, container-label, inventory, and test-harness changes
do not invalidate the retained scale execution.

## Migration and operations boundary

The public predecessor is v0.1.4 at schema v160. Migrations v161-v168 are additive and establish
truthful synthesis outcomes, observation leases, grounded temporal evidence, belief projection,
transition dynamics, consequence rollouts, promotion/correction, and operational lifecycle. R7 must
record schema-zero through v168, v160-to-v168 upgrade with retained sentinel data, second-run
idempotency, current-head partial-interruption resume, database/API/worker/client restart, and
Compose health before candidate authorization. The isolated R7 runs completed as follows:

- schema zero applied 167 migration files through v168, validated every required runtime table,
  and recorded 110 audited historical compatibility events;
- the second ordinary installer invocation started at v168, applied zero files, and validated
  v168 again;
- an isolated database was constructed through the exact public v0.1.4 head v160 (159 files), a
  sentinel value was inserted, and the ordinary installer applied exactly v161-v168; the sentinel
  and v168 schema receipt both survived;
- a separate v167 database committed the first 8 of 53 v168 statements before the client was
  terminated with the version receipt still at v167; the ordinary installer then reapplied the
  single v168 file, validated v168, and failed neither open nor partially green; and
- the retained TP8 backup/restore receipt remains 520,154,734 bytes, under 5 seconds to back up,
  28.97 seconds to restore, with all 256,000 semantic records, 2,560 item receipts, 68 batch
  receipts, 2,000 supersession edges, and known replay identity preserved.

Arbitrary interruption inside historical pre-v142 migrations is not supported. The published v014
negative result failed closed; the recovery is restore from a verified pre-migration backup and
ordinary schema replay, not skipped statements or weakened validation.

## Verification ledger

The local release-critical verification completed with the following results:

| Gate | Result |
|---|---|
| Integrated focused State Engine unit/contract lane | 157 passed; database/socket-only cases rerun separately |
| Real TP2-TP7 database/restart lane | 17 passed in 96.39 s |
| R7 version, package, N-1, extension, TP0 checks | 28 passed in 10.80 s |
| Updated unit regressions | 16 passed in 0.78 s |
| Full extension-enabled non-E2E | 6,855 passed, 46 skipped, 246 deselected in 479.73 s |
| Full extension-disabled non-E2E | 6,842 passed, 47 skipped, 258 deselected in 554.31 s |
| Naked-kernel boundary | 4 passed in 1.51 s |
| Focused real DB/API restart State Engine E2E | 12 passed, 6 deselected in 148.89 s |
| Migration lint/splitter/safety/failure lane | 43 passed in 0.67 s |
| Schema zero / idempotency / public-v160 upgrade / interrupted v168 | passed as itemized above |
| Frozen TP8 input | 63 manifests; raw dataset and manifest-set hashes matched |
| Frozen K1-K3 target | passed; 5 K2 and 5 K3 repetitions remain predeclared |
| Canvas typecheck | passed (`tsc --noEmit`) |
| Canvas tests | 291 passed across 32 files |
| Canvas production and naked builds | both passed; naked build also passed 9 zero-extension guards |
| Ruff lint / repository format | passed; 1,878 files already formatted |
| Workflow validation | `actionlint` passed |
| Whitespace/error diff | `git diff --check` passed |
| Dependency audit | initially found four current advisories; patched floors now report no known vulnerabilities |
| Dependency consistency | `pip check` reports no broken requirements |
| License inventory | 192 installed distributions; zero unknown licenses |
| Linux locked image | 0.2.0 identities, non-root UID 1000, 11 tools, reference extension, v168, and exclusions passed |
| Compose | schema migration exited 0; SurrealDB, API, and worker healthy; API ready reports 0.2.0 |
| Staged secret scan | passed across all intentional candidate commit groups |
| Checkout-free corpus/package regression | 119 passed in 3.03 s after the clean-wheel blocker fix |
| Worker watcher/startup regression | 34 passed in 1.21 s; real threaded file activity remained healthy |
| Clean wheel State Engine journey | fresh v168 schema plus belief/transition/action-no-action rollout/I3 receipt completed with zero provider calls and zero simulated-as-observed violations |

The exact primary commands were:

```bash
.venv/bin/pytest -m "not e2e" -q --tb=short
ACE_DISABLE_EXTENSIONS=1 .venv/bin/pytest -m "not e2e and not requires_extensions" -q --tb=short
ACE_DISABLE_EXTENSIONS=1 .venv/bin/pytest tests/test_kernel_boundary.py -q --tb=short
.venv/bin/pytest tests/test_grounded_state_ingestion.py tests/test_observation_lease_restart.py \
  tests/test_synthesis_outcome_restart.py tests/test_i1_restart_persistence.py \
  -m e2e -q --tb=short
.venv/bin/pytest tests/test_schema_apply.py tests/test_schema_apply_fail_closed.py \
  tests/test_schema_migration_errors.py tests/test_schema_migration_lint.py \
  tests/test_schema_splitter.py tests/test_migration_safety.py -q --tb=short
.venv/bin/python scripts/run_state_engine_tp8.py freeze-check
.venv/bin/python scripts/run_state_engine_readiness.py freeze-check
.venv/bin/ruff check .
.venv/bin/ruff format --check .
actionlint
.venv/bin/pip-audit --progress-spinner off
.venv/bin/python -m pip check
git diff --check
```

Canvas verification ran `npx tsc --noEmit`, `npx vitest run --reporter=basic`,
`npx vite build`, and `npm run build:naked` after `npm ci`. Linux verification used a clean
`docker build --no-cache --build-arg ACE_VERSION=0.2.0 -t ace-core:0.2.0-rc .`; the resulting
546,075,407-byte final image is
`sha256:6d92045b5aec0d452c2c287c4303d79e87e27ef71e22a3043ad9553e1018d1df`.
The isolated Compose project used reserved loopback ports; its one-shot migration exited 0 and its
database, API, and worker all reached healthy state. After verification, the explicitly scoped
Compose project and its disposable test volume were removed; no candidate image was pushed.

## Artifact and clean-install ledger

The candidate artifacts were built twice from exact source commit
`34486ab7b857a8bf1b3315fe795491c7a133a3ac` with `SOURCE_DATE_EPOCH=1785882129`. Both builds were
byte-identical:

| Artifact | Bytes | SHA-256 |
|---|---:|---|
| `ace_core-0.2.0.tar.gz` | 3,552,533 | `e85b4d78e9bbe462a0122679c8292ac825895e72394abb906068411440476230` |
| `ace_core-0.2.0-py3-none-any.whl` | 4,090,374 | `37300ed17333de13e670941f4ece8514f4d76976af205edc526883eeece926d2` |

The corrected source archive has 1,318 entries and the wheel 1,214. Both contain schema v168, the
packaged 40-case frozen State Engine corpus, the TP8 runner, R7 evidence, operations documentation,
LICENSE, NOTICE, and the declared entry points. Neither contains tests, Git data, `.env`, caches,
local databases, logs, or the excluded K1-K3 raw directory.

An isolated Python 3.12.13 macOS arm64 environment installed the wheel without a checkout and
reported 157 compatible distributions and zero unknown licenses. All distribution/module/extension
identities were 0.2.0, the `product` reference extension was discoverable, the public MCP surface
was exactly eleven tools, ordinary and extension-disabled CLI startup passed, and the packaged
frozen corpus loaded 40 cases from site-packages. The packaged schema installer applied all 167
migration files to a fresh namespace and validated v168. The packaged State Engine smoke then
persisted belief, reviewed transition, action/no-action rollout, and I3 reasoning-use identities
over the retained 200,000-claim scale boundary with zero provider calls and no observed/simulated
meaning violation. Clean-wheel API `/health/ready` and worker `/health` both returned 0.2.0 healthy;
the worker remained healthy after real watchdog-thread file activity and shut down cleanly.

The CLI doctor also failed honestly in two non-ready situations. With no configuration it reported
`invalid_configuration`, unreachable API, absent authentication, and 11/11 MCP registration. With
the local database/API/auth configured, database, schema v168, API, authentication, policy, and MCP
were green, while the model route remained `configured_unverified`; no fake or billable live
provider call was made. This is a declared external-provider readiness boundary, not a concealed
green result.

No artifact has been uploaded to PyPI or attached to a public GitHub Release.

## Preliminary failures and preserved exclusions

TP8 and K1-K3 preliminary product/harness failures remain described in their historical records;
no threshold or expected outcome was loosened. R7 also preserves but deliberately excludes
`evaluations/results/state_engine_k1_k3_raw/`: 198 files containing host-specific absolute paths,
large superseded trials, and process/store logs. It remains in the local worktree and is neither
deleted nor staged. The complete canonical machine receipt, readable report, final raw hashes, and
failure summary are included instead. Ignored `.env`, virtual environments, caches, local database
stores, credentials, and Git metadata are not release inputs.

R7 preflight found and corrected five release blockers without weakening a gate:

- the first source archive included the locally preserved K1-K3 raw directory; `MANIFEST.in` now
  prunes it and the archive regression enforces the exclusion;
- the same raw directory was eligible for the local Docker context; `.dockerignore` now excludes it
  and Linux image inspection proves it absent;
- the first current dependency audit found PYSEC-2026-3545/3546/3547 in `aiohttp` 3.14.1 and
  PYSEC-2026-3552 in `cryptography` 49.0.0. Base safety floors are now 3.14.3 and 50.0.0, the lock
  and locked container install use those versions, and the repeated audit is clean;
- the first isolated wheel journey found that the TP8 runner referenced a test-only TP0 corpus
  intentionally excluded from artifacts; an identical canonical corpus is now packaged under the
  grounded-state runtime, defaults resolve there, and the package regression prevents drift; and
- the first isolated worker startup exposed watchdog callbacks scheduling on a thread without an
  event loop; callbacks now marshal debounce work to the lifespan's owning loop, with both a
  threaded regression and a real installed-wheel filesystem-activity smoke.

The Dockerfile also now consumes the frozen lock with `uv sync --frozen --no-dev --no-editable`
instead of resolving a new environment independently during every image build.

The 1.1 MB canonical K1-K3 machine receipt is an intentional release evidence file: it retains all
40 K2 cases and five K3 repetitions. The large-file hook has one path-specific exception for it;
the independent staged secret scan still inspects the file. Raw TP8 result files are small,
public-safe, and separately subject to final staged review.

## Source, branch, PR, CI, and remaining blockers

- release branch: `codex/release-0.2.0`;
- exact artifact/source commit: `34486ab7b857a8bf1b3315fe795491c7a133a3ac`;
- local commit series: `acbfe756199d6e45db244473a8dc3b93840b9051`,
  `8cc16c2b71d909e850235d273624e2edccad8aa8`,
  `539ff2e1749115c78eb63fc959fb5a95475a6afe`,
  `a11c018eb5177a7727b17a6e717427f412eb3109`, and
  `34486ab7b857a8bf1b3315fe795491c7a133a3ac`;
- draft PR: **pending**;
- CI: **pending pushed candidate**;
- artifact identities and clean install: **passed locally as recorded above**;
- publication authorization: **not requested and not granted**.

The local release-candidate verdict is `candidate`. The overall R7 verdict remains not-passed until
the pushed branch, draft PR, and available CI result are reconciled here; publication remains under
the separate authorization boundary below.

## Publication boundary

R7 authorizes no public release action. A separate explicit authorization is required before
marking the PR ready, merging, creating `v0.2.0`, publishing a GitHub Release, triggering trusted
PyPI publication, deploying, or announcing launch. The exact proposed merged commit, tag, release
notes, artifact identities, CI state, and remaining risks must accompany that request.
