# PI13 WS0 local candidate evidence v1

- Date: 2026-08-20
- Baseline: `origin/main` / `e9a53ae63d209a266dc8a5156b1afcd5c939dd08`
- Disposition: **locally verified candidate; intentionally failing; not landed**
- Scope: WS0 only. This record does not claim a public release acceptance run or an ACE 1.2
  acceptance pass.

## Composition exercised

The candidate built the Core, Personal pack and bundle, all four local-source adapter wheels,
and the shared local-source normalizer wheel. It installed only those wheels and their declared
dependencies into a new bare Python 3.12 virtual environment outside the checkout. It started a
memory-only SurrealDB 3.2.3 container with no volume, applied the schema from the installed Core
artifact, and validated schema version 179 before invoking the strict journey gate.

The gate imported `ace`, `core.engine.api.main`, `scripts.schema_apply`, and
`ace_mcp_client.server` from the bare environment's `site-packages`; it rejected checkout-local
imports. The PDF fixture was independently read with `pypdf` and extracted `PI13 fixture`.

## Exact J1–J10 result

The strict runner exited 1, as required for a non-passing journey. It emitted all ten rows in
order; no later row was omitted.

| Step | Result | Candidate evidence or blocker |
|---|---|---|
| J1 Install | PASS | Distributions present; schema 179; Markdown/PDF/CSV/JSON fixtures; exactly eleven MCP tools; deterministic stub invoked |
| J2 Choose | PASS | Installed Personal profile found; production planner registry resolves it to `personal_intelligence` |
| J3 Connect | FAIL | No `ace.intelligence_builders` executor, connect route, or production snapshot binding |
| J4 Inventory | BLOCKED | No connected sources exist |
| J5 First Brief | BLOCKED | No admitted corpus exists |
| J6 Change | BLOCKED | No watched source or prior Brief exists |
| J7 Ask | PARTIAL | Ask route exists; a connected cited-answer path does not |
| J8 Correct | PARTIAL | Correction route exists; a real claim cannot yet be re-derived |
| J9 Restart | BLOCKED | The scoped run-3 pass is not re-claimed without connected journey state |
| J10 Own | BLOCKED | The scoped run-3 pass is not re-claimed without corpus-derived intelligence |

Counts: PASS 2, FAIL 1, BLOCKED 5, PARTIAL 2. `all_pass` is false.

## Verification

- 70 focused and existing Personal journey/package tests passed together.
- The broad non-E2E/no-extension run produced 9,177 passes, 52 skips, and three failures in
  existing `tests/test_graph_context.py` expectations. Those tests mock
  `core.engine.graph.context.pool`, while the existing semantic enhancement queries through
  `core.engine.search.semantic.pool`; local graph rows were therefore appended. The graph-context
  file passed 26/26 under the supported `EMBEDDING_PROVIDER=none` test setting. WS0 does not edit
  or suppress that release-critical retrieval/search behavior.
- Ruff check and Ruff format check passed for the WS0 runner and tests.
- The CI contract test confirms a job-level allowed failure, strict unmasked runner step,
  outside-checkout venv, built-wheel installation, pinned memory-only SurrealDB, installed schema
  application, always-uploaded reports, and cleanup.
- The exact eleven-tool MCP boundary passed in the installed-artifact run.
- The candidate changes no production application module and does not touch retrieval/search
  behavior.

Report digests:

- JSON: `0e03f9c2f2dcaffa8fa37d30de6aea36fa9b4eb44017cbce700c1c5d8272ab8b`
- Markdown: `7778ea49d79c8a04bb7ee1a4f5d5652890ac4e45016b630d60d1f53561146dd9`

## Limitations and next gate

This was a maintainer-side, clean-environment-style composition run in a dedicated worktree. The
CI job has not been landed or executed by GitHub, so this is not public-artifact release
acceptance. J7 and J8 establish route presence and the honest unavailable frontier, not complete
positive journeys. J9 and J10 intentionally remain blocked rather than inheriting run 3's scoped
passes. The next human-only gate is disposition of this reviewed WS0 candidate.

## 2026-08-21 continuation — the lane now walks the journey from installed artifacts

WS0 no longer reports static J4/J5 rows. The gate drives the public route sequence in-process against the
installed wheels and the ephemeral SurrealDB: `/auth/token`, `/auth/local-owner/bootstrap`, Connect
preview/authorize over the fixture corpus through the installed snapshot provider, `/prepare`, `/bind`,
`/bootstrap/local-first-run`, `/session/associate`, the seven `/builder/...` progression routes,
`/activation-plan/prepare|approve|activate`, `/start`, and `resources/query`. J4 is computed from the real
resource page (source-health, entity, and observation counts plus Markdown locators) and J5 from the
Brief's cited claims and whether each citation resolves to an admitted Markdown observation. Every step
that stops early is named exactly in the blocker.

WS0's provider is deterministic but never injected: `scripts/pi13_ws0_stub_provider.py` serves the OpenAI
chat-completions wire shape on loopback and is published through `OPENAI_COMPAT_BASE_URL`, so `get_llm()`
selects the production `OpenAICompatProvider`. Its answers are pure functions of the trusted context in
each prompt, so it cannot introduce material the host did not already admit. The fixture corpus gained a
second Markdown note because the source-scope bridge requires at least two exact captures; PDF, CSV, and
JSON mapping remain WS4.

Running the lane surfaced three defects invisible to in-memory tests, each repaired test-first: a
non-idempotent `sys.path` insert in `scripts/schema_apply` that made every installed distribution
enumerate twice; an installed-Pack resolver that read one twice-enumerated dist-info as two ambiguous
Packs; and recorded-source admission replay validating durable payloads strictly when SurrealDB returns
them as JSON. Two composition corrections followed: the cognition resolver accepts the build's own
product-scoped record-store fence over the configured store, and the OpenAI-compatible provider records
per-call usage into the in-process accumulator (without it, governed structured calls fail closed for
missing telemetry).

The walk now reaches `ACTIVE` and executes recorded-source admission under real authority. It stops in
canonical Brief assembly with `Brief citations must be available by the Brief as_of cutoff`: a citation's
`retrieved_at` is the admission commit, while the initial-corpus Brief's `as_of` is the corpus validity
cut derived from the captures' `observed_at`, which is necessarily earlier. J4 and J5 do not pass; the
options and the owner decision are recorded in the tracker's current gate. Nothing was committed, merged,
pushed, tagged, published, or released.

## 2026-08-21 — J4 and J5 pass from installed artifacts

The owner resolved the Brief-time conflict by separating the two bitemporal axes in `BriefV1Alpha1`:
valid-time leakage stays `source_as_of <= as_of`; transaction-time leakage becomes
`retrieved_at <= generated_at` (the contract's own availability field). The prior rule compared an
ingestion instant against a validity cut, which required evidence to be ingested before the moment it
describes and so refused every orientation over a historical corpus.

One further defect of the already-familiar class surfaced and was fixed test-first: the resource-plane
reader's `_decode_recorded_acquisition` and `_decode_recorded_snapshot` validated durable payloads
strictly, degrading `source_health` with `invalid-recorded-source-readiness`. That mattered beyond a
missing count: `source_health` is the only projected surface binding an admitted snapshot to the exact
`source_uri` that was authorized and read, so the gate resolves Markdown provenance through it —
`source_health.source_snapshot_ref` is precisely the `source_ref` that an Observation and a Brief citation
both carry. J4 now reads the resource plane as the owner would, rather than trusting the build's own page.

Exact result, reproduced twice over freshly built wheels, a bare venv outside the checkout, and an
ephemeral memory-only SurrealDB at schema v179:

| Step | Result | Evidence |
|---|---|---|
| J1 Install | PASS | Distributions, schema 179, four fixture kinds, exactly eleven MCP tools |
| J2 Choose | PASS | Installed Personal profile and planner resolve to the pack |
| J3 Connect | PASS | Installed snapshot binding, both exact Connect routes, consent-before-read with zero provider calls |
| **J4 Inventory** | **PASS** | `source_health=2 entity=2 observation=2`; page complete with no degraded reasons; every observation resolves to `notes/vault.md` or `notes/second.md` |
| **J5 First Brief** | **PASS** | `briefs=1 cited_claims=3 uncited_claims=0 unresolved_citations=0`; citations resolve to both admitted Markdown sources |
| J6 Change | BLOCKED | No watched source or prior Brief revision (WS5) |
| J7 Ask | PARTIAL | Route present; connected cited answers not yet exercised |
| J8 Correct | PARTIAL | Route present; real claim re-derivation is WS5 |
| J9 Restart / J10 Own | BLOCKED | Scoped claims not re-established at this frontier |

The lane executes the full public sequence from installed artifacts: `/auth/token`,
`/auth/local-owner/bootstrap`, Connect preview/authorize over the fixture corpus through the installed
snapshot provider, `/prepare`, `/bind`, `/bootstrap/local-first-run`, `/session/associate`, the seven
`/builder/...` progression routes, `/activation-plan/prepare|approve|activate` (session reaches `ACTIVE`),
`/start`, and `resources/query`. Its provider is deterministic but never injected: the loopback stub is
published through `OPENAI_COMPAT_BASE_URL` so `get_llm()` selects the production `OpenAICompatProvider`.

Core wheel `ace_core-1.2.2` sha256 `def4b5a08b250db4c8e956ca20e31eaff25152f03b36fb98058b411407c6af29`;
the Personal pack, bundle, and six local adapter/provider wheels were built in the same pass.

This is candidate evidence for WS0 and WS3 only. It is not a public release acceptance: the amended gate
still requires a clean-context run reporting J1–J10 end to end, maintainer cross-check concurrence, and
the four-record reconciliation. WS4 has not started, and nothing was committed, merged, pushed, tagged,
published, or released.
