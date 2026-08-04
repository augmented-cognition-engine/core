# ACE State Engine TP8 scale, stability, and Core-boundary evidence v1

Status: **TP8 implementation and single-node scale packet complete; K1 ready; K2 and K3 candidate**

TP8 closes the architectural scale packet before v0.2 release hardening. It is not a release,
deployment, distributed-systems, real-world causal-accuracy, beneficial-impact, or general
world-model claim. The trial used only deterministic synthetic/public-safe material, disposable
local SurrealKV stores, loopback networking, and no paid or hosted provider.

Subsequent decision (2026-08-04): the later
[K1-K3 readiness audit](state-engine-k1-k3-readiness-v1.md) closes the bounded pre-R7 requirements
recorded here and advances K2 and K3 to `ready`. This TP8 record retains its point-in-time candidate
decisions and measurements unchanged.

The frozen manifest is
[`state_engine_tp8_scale_stability_v1.json`](../../evaluations/fixtures/state_engine_tp8_scale_stability_v1.json),
the summarized machine result is
[`state_engine_tp8_scale_stability_v1.json`](../../evaluations/results/state_engine_tp8_scale_stability_v1.json),
the raw outputs are in
[`state_engine_tp8_raw`](../../evaluations/results/state_engine_tp8_raw), and the separate readiness
receipt is [`state_engine_tp8_readiness_v1.json`](../../evaluations/results/state_engine_tp8_readiness_v1.json).
The frozen manifest file SHA-256 is
`2a1551aa49abe8aec332a27ac7b62ede64a362d32a666fbbcc0dac005643d47e`; the summarized result is
`253abc29a565d3f4cc8d54eef88718a462262452b36ce937dac8e5875b43be56`; the readiness receipt is
`922a5e212a25300984ebe1a2b0525ca529c165cfae16fe02779d916b85f53fda`; and the compatibility
matrix is `8935ce2b7e4b466e9f7e62d3b3b0772ee307565a1b312ae0dfb88dfdb78a874b`.

## Preconditions and production journeys

The existing dirty worktree, schema head, TP0–TP7 contracts, migrations, evaluators, runtime paths,
and evidence were inspected and preserved before scale work. TP6 and TP7 initially had a real gap:
the services and evaluators existed, but terminal production task execution did not own the complete
rollout, bounded reasoning injection, I3 use, promotion, and later-use sequence. TP8 scale work was
paused while that gap was repaired.

The ordinary durable task path now carries exact runtime coordinates from authenticated extension
preparation through a predeclared task identity. Terminal task execution runs and persists the
`ConsequenceRolloutService`, injects bounded `[SE-N]` consequences as untrusted context, persists the
actual I3 reasoning-use receipt, applies the authority-gated TP7 disposition, writes accepted
material into the existing `insight` memory plane, and records later promoted-memory use. The real
acceptance journey then restarts SurrealDB, resolves evidence in a fresh invocation, retrieves the
promoted conclusion, applies an I1 correction/supersession, restarts again, and returns only the
corrected authoritative memory while preserving prior lineage. A matched control remains explicit,
and beneficial impact remains unsupported.

The production journey is verified by
`test_tp6_rollout_reasoning_use_and_reconciliation_survive_restart`; it is not evaluator-only or a
service-only unit test.

## Frozen benchmark

The manifest was frozen before the clean scale execution. Its identities are:

- generator seed `8042026`;
- raw dataset SHA-256 `c58e36030f3835b71e82268e13b2f5d753ee6fb530a860b4075eb1ccd9cbcad8`;
- manifest-set SHA-256 `2e7c8b0a37fa6a7e7062c2cf077af7adfda41b6e83822b99a20f29fad498d2eb`;
- 63 manifests, 2,360 bounded items, 200,000 claims, and 236,000 semantic records;
- 2,000 sources, 5,000 entities, 5,000 aliases, 2,000 events, 2,000 participants, and 20,000 relations;
- 2,000 corrections, 4,000 contradictions, 10,000 unknown-time records, and 5,000 negative controls;
- frozen reference peak 34,000 claims/day and required sustained target 68,000 claims/day; and
- zero bulk-ingestion or deterministic State Engine provider calls, tokens, retries, or cost.

Reference environment: Apple MacBook Pro Mac15,6, Apple M3 Pro with 11 CPU cores and 18 GB unified
memory; macOS 26.6 build 25G72; SurrealDB 3.2.1 aarch64 with SurrealKV; CPython 3.12.13; uv 0.11.14;
local internal SSD; one database process and one single-connection benchmark client over loopback.
No distributed or multi-writer guarantee was tested.

## Scale and per-plane results

| Plane | Result | Frozen limit | Outcome |
|---|---:|---:|---|
| Initial claims | 200,000 | at least 200,000 | pass |
| Initial semantic records | 236,000 exact | 236,000 | pass |
| Initial receipts | 2,360 item / 63 batch | exact | pass |
| Supersession edges | 2,000 | exact | pass |
| Lowest unique-load process rate | 659.038 claims/s | at least 20 claims/s | pass |
| Largest observed manifest p95 | 4,079.167 ms | at most 120,000 ms | pass |
| Sustained sample | 20,000 in 20.194 s | 20,000 exact | pass |
| Sustained rate | 990.410 claims/s; 85,571,384/day equivalent | at least 68,000/day | pass |
| Candidate retrieval | 6.532 ms median; 14.189 ms p95 | p95 at most 1,000 ms | pass |
| Evidence query plus pack | 14.443 ms median; 16.510 ms p95 | p95 at most 1,500 ms | pass |
| Belief projection | 7.493 ms | at most 2,000 ms | pass |
| Transition resolution | 10.815 ms | at most 2,000 ms | pass |
| Consequence rollout | 13.131 ms | at most 3,000 ms | pass |
| I3 reasoning-use persistence | 9.071 ms | separately reported | pass |
| Initial store | 826,015,744 bytes | at most 2,147,483,648 bytes | pass |
| Provider use | 0 calls, 0 tokens, 0 retries, $0 | zero | pass |

Source, entity, relation, lineage, and index work is committed inside the bounded ingestion-item and
manifest path. It does not enqueue an asynchronous per-claim synthesis job. Consequently the
ingestion backlog is zero at each terminal receipt; association lag is included in manifest
latency, not hidden behind an aggregate queue number. Task reasoning, promotion, and fresh retrieval
pass one deterministic provider-free production journey, but do not yet constitute p95 scale
samples; this is why K3 remains `candidate`.

Unknown, contested, rejected, stale, invalidated, and superseded meanings remain distinct. Candidate
and evidence queries returned zero foreign-product material. Simulation tables and identities are
separate from evidence and belief tables, with zero simulated-as-observed violations. Raw claims do
not enter memory without an accepted TP7 receipt. Source text is rendered inside an explicit
untrusted-data envelope and cannot select product, system, task, tool, secret, mutation, review, or
promotion authority.

## Interruption, replay, backup, and migration

The clean initial load was interrupted at the frozen points:

- SurrealDB was terminated after claim 40,000. A fresh database process was available in about 11
  seconds, below the 15-second budget. Exact boundary replay took 20.689 ms and counts remained
  40,000 claims with no duplicate semantic rows.
- The adapter was made unavailable before claim 120,000. The committed boundary remained 116,000;
  no green receipt was issued for the unavailable submission, and a fresh client resumed exactly.
- The client was hard-stopped at claim 160,000 with exit 143. A fresh client completed the load to
  exact final counts.
- A forced child-write failure inside one ingestion-item transaction left neither child rows nor a
  green item receipt.

The 520,154,734-byte export completed in about five seconds. Import into a clean store completed in
28.97 seconds. After the 20,000-claim sustained sample the restored database reconciled exactly to
220,000 claims, 256,000 semantic records, 2,560 item receipts, 68 batch receipts, and 2,000 lineage
edges. The same previously committed manifest replayed with the same identity in 27.901 ms.

Schema-zero applied 167 migration files through v168 in 21.66 seconds, reported 110 audited legacy
compatibility events, validated the required schema, and applied zero files on the second run. The
supported v0.1.x upgrade from v157 applied v158–v168, retained a sentinel record, and validated v168.

A deterministic current-head migration trial built an exact v167 predecessor with production
migration functions, committed 8 of 53 additive v168 statements, hard-stopped the client without
advancing the schema-version receipt, and resumed with the ordinary production installer. It
validated v168, then applied zero files on a second run. An intentionally harsher schema-zero stop
inside historical v014 did not resume: v014 predates strict, statement-idempotent migration policy
and failed closed on an already existing table. That negative result is preserved as a documented
limit; arbitrary interruption inside historical pre-v142 files is not supported.

## Adapter and compatibility evidence

The same-database adapter and a read-only external filesystem content input each submitted the same
ten SHA-256-verified public-safe source bodies through the Core ingestion boundary. Core stable IDs
were identical 10/10, the external delivery was recognized as ten exact duplicates, batch receipts
remained distinct, and product, identity, query, lifecycle, and replay semantics did not change.
This proves external source-body portability, not externalization of Core receipts or identities.

The frozen compatibility matrix passed the current reference extension, the 0.1.3 N−1 task-action
envelope against Core 0.1.4, extension failure without Core corruption, extension-disabled naked
kernel, exact eleven-tool thin MCP client, and package boundary. The exact fresh-database/API/thin-
client restart acceptance passed at schema v168 in 31.84 seconds. Two distinct worker process IDs
then started against the retained full-schema v168 store, reported healthy worker v0.1.4, and shut
down cleanly. Core has no dependency on the OLC adapter, another domain extension, or a source-
specific ontology.

## Preliminary failures and legitimate corrections

Preliminary failures were retained rather than overwritten:

1. The first disposable load used growing bulk preflight scans and exposed both unacceptable latency
   growth and a typed-product comparison defect that rejected valid rows. The failed store remains at
   `/private/tmp/ace-tp8-benchmark-dLIBel`. Direct record preloads, indexed coordinate reconciliation,
   real item transactions, and typed comparison corrected the implementation; frozen thresholds did
   not change.
2. The first large-corpus plane run produced 1,952.053 ms candidate p95, 2,073.160 ms evidence-pack
   p95, and zero selected pack items because the chosen `as_of` preceded ACE creation time. After the
   timestamp correction, candidate p95 was still 1,302.377 ms and failed the frozen 1,000 ms target.
   A source-scoped compound index and bounded query projection produced the final 14.189 ms p95. All
   three raw results remain published.
3. The first post-optimization production journey omitted ACE creation times for candidates from all
   but the final record table because of one table-variable defect. The full journey caught it; the
   lookup was corrected and the complete restart/reconciliation journey passed.
4. Arbitrary interruption in legacy v014 failed closed, as described above. Only the supported
   current-head migration interruption is classified as resumable.

No benchmark threshold, dataset hash, expected count, provider budget, or pass criterion was loosened
after any result.

## Readiness and remaining packet

K1 is `ready` for the declared single-node capability: scale, exact replay, provenance and temporal
meaning, disagreement and unknowns, deterministic projection, restart/recovery, query latency, and
product isolation all have measured passing evidence.

K2 is `candidate`. Its bounded frozen mechanism/challenge/review/revision/calibration matrix passes,
and transition persistence was measured while the 200,000-claim database was active, but a broad
domain matrix has not been repeated at scale. K3 is `candidate`: the complete real task and later-use
journey passes, but it is a single deterministic acceptance rather than repeated fresh-process
large-corpus task, promotion, and retrieval measurements.

The smallest pre-R7 packet is therefore bounded: repeat the frozen TP5 domain matrix against the
large corpus with per-domain challenge and calibration measurements, then run repeated fresh
API/worker/client K3 journeys and publish task, promotion, restart, and later-retrieval p95s. Neither
packet may claim causal accuracy, calibrated forecasting, autonomous learning, beneficial impact,
or general world-model intelligence.

## Verification summary

- Focused TP8 plus complete grounded-state persistence/runtime file: 19 passed in 92.86 seconds.
- Production regression plus structured-decision compatibility after the final fix: 2 passed in
  17.99 seconds.
- Naked kernel, package boundary, and exact eleven-tool client: 32 passed in 2.29 seconds.
- Complete extension-disabled non-E2E run before its one compatibility fix: 6,834 passed, 47 skipped,
  258 deselected, one failure, and 28 warnings in 522.25 seconds. The failure was the established
  structured-decision query-text assertion; the exact assertion and production journey passed after
  correction. The final clean rerun passed 6,835 tests, skipped 47, deselected 258, retained 28
  warnings, and took 533.22 seconds; the chained kernel-boundary run passed 4 tests in 1.36 seconds.
- Complete focused TP0–TP8 regression: 144 passed in 100.04 seconds.
- Schema, migration, and TP8 lane: 41 passed in 12.52 seconds.
- Fresh database, API, and thin-client restart at schema v168: 1 passed in 31.84 seconds. Its first
  explicit TP8 run failed only because the acceptance still expected the prior v167 head; the
  process had correctly migrated to v168, the expectation was reconciled, and the exact test passed.
- Fresh worker restart: two separate worker PIDs reached healthy v0.1.4 against the retained v168
  database and both completed graceful shutdown.
- Full-repository Ruff lint passed; the format check reported all 1,873 files already formatted;
  repository whitespace validation passed.

The repository has no configured static type-checker command. Contract typing is exercised through
Pydantic validation and the focused/full test lanes; no unexecuted mypy, pyright, or `ty` command is
claimed.

No commit, push, pull request, publication, deployment, tag, release, reset, or worktree cleanup was
performed.
