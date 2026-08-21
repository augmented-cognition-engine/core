# PI13 WS2 local candidate evidence v1

- Date: 2026-08-20
- Baseline: `origin/main` / `e9a53ae63d209a266dc8a5156b1afcd5c939dd08`
- Disposition: **reviewed and freshly verified local candidate; owner disposition pending; not landed**
- Scope: WS2 and the corresponding WS0 J3 motion only. This record does not claim a public
  release acceptance run or an ACE 1.2 acceptance pass.

## Candidate composition

WS2 adds two exact production API routes:

- `POST /v1/intelligence/builds/connect/preview`
- `POST /v1/intelligence/builds/connect/authorize`

Preview is lexical and side-effect free. It resolves the exact installed onboarding profile,
planner, Pack, source group, and mapping declarations, but it does not touch the filesystem,
clock, network, or database. Its result states `local`, `read_only`, no network capture, and no
write request. Authorize accepts only literal `authorized: true`; missing or false consent is
rejected by transport validation before the provider can be resolved or invoked.

After consent, the production `ace.source.snapshot/v1alpha1` provider is invoked once for the
exact previewed root and include/exclude scope. The existing PI2 adapters return local
Markdown/PDF/CSV/JSON acquisitions. WS2 binds those acquisitions to exact recorded-source
selection contracts, adds explicit `LOCAL` acquisition admission to the existing
recorded-source boundary, and atomically appends the preview, authorization, captures, and
result through the existing immutable-record store. Exact replay performs no second source
read. A reviewed selection reference can be reopened only for the same product and actor and
bound into the existing Intelligence build-plan review; admission/execution of that reviewed
plan remains WS3.

The host interprets installed source-mapping modules only through a public application helper;
generic Core imports no `ace.intelligence` bounded-context module. The new Core file is listed
as an exact host adapter without weakening the public-Core boundary rule.

Defect #259 is fixed by comparing the setup response with `len(LOCAL_OWNER_GRANTS)` instead of a
hard-coded count. Defect #260 remains carried to WS3. WS2 adds no connector catalog, remote
source, collaboration, hostile-adapter isolation, restore-from-export, or ACE 1.3 behavior.

Claude Code CLI performed the bounded WS2 implementation and final boundary correction in
workstream-specific prompts. Every resulting change was inspected and composed here. The CLI
was usable; the previously observed decommissioned-project stale hook did not block this work.
Claude was not used as approval authority.

## Fresh installed-artifact composition

The final tree built fresh wheels for Core, all six local adapter/provider distributions, the
Personal pack, and the Personal bundle. Only those nine wheels and their declared dependencies
were installed into a new bare Python 3.12 environment outside the checkout. A memory-only
SurrealDB 3.2.3 container with no volume received the schema from the installed Core wheel and
validated schema version 179.

The installed API composition then performed preview, authorize, exact authorize replay, and
build-plan preparation against the real API and durable store. All four calls returned 200.
The result was:

```json
{
  "authorization_id": "local_source_connect_authorization:afb4d7eb26a43f8477dcab9b0ad7afe7",
  "capture_id": "local_source_connect_capture:0f5c091caf5c4341c32aaa2188731ca8",
  "plan_id": "intelligence_build_plan:cf4962588b9e1abeeb6517f8a44ffdea",
  "preview_id": "local_source_connect_preview:3da2783c42f7707be2b9129b70886a58",
  "replay_exact": true,
  "review_bound": true,
  "selection_id": "recorded_source_selection:8160babf314847167320f5e0aaad0b29"
}
```

One preliminary composition invocation intentionally set `ACE_DISABLE_EXTENSIONS=1` and
therefore failed closed before reading a source because the installed Personal planner was
suppressed. The corrected production-composition invocation used normal installed entry-point
discovery and produced the result above.

Final wheel digests:

| Distribution | SHA-256 |
|---|---|
| `ace-core==1.2.2` | `8226fee4d28cfda54b2a985bd28631b10e00620fdc366eda28061bb54cf2305e` |
| `ace-local-source-normalizers==0.1.0` | `b0db8335c061a640dba20bf336baf93f387ba4080c8683e83e25344a665a3085` |
| `ace-local-markdown-source==0.1.0` | `cc55b1d13edddf9d5da96547432798c2b74f57b02190bdfb9ddc0c1be9e8d701` |
| `ace-local-pdf-source==0.1.0` | `5231238f4e0f0ac85c73c2c0af41e7c4ded3ecad905f2a344a4f475910bdbaec` |
| `ace-local-csv-source==0.1.0` | `36be9334f2ea55427862885ee457e91a155c33d536e8a4c47b0de229ec95468e` |
| `ace-local-json-source==0.1.0` | `05c1bdc43b26a3b73bb7a728db42b2d1ca75fc837a64b063cdfb7c80f93eea95` |
| `ace-local-source-snapshot==0.1.0` | `7cb40fe8668519c894ddd6093d5d7c19f25e6fb0f4bf7cb0069eb809025f2c4e` |
| `ace-personal-intelligence-pack==0.1.0` | `012d897e42841bca5e23e61410c8efa05b24683784c7e466c49f306ca1f1a888` |
| `ace-personal-intelligence-bundle==0.1.0` | `d39716201fdecfa32e945af14d73c68ffa44e828847cfe756047738087e5157f` |

## WS0 journey movement

The strict runner exited 1 and emitted every J1-J10 row in order:

| Step | Result | Candidate evidence or blocker |
|---|---|---|
| J1 Install | PASS | Fresh distributions; schema 179; four fixture kinds; exactly eleven MCP tools; deterministic stub invoked; #259 fixed, #260 remains carried |
| J2 Choose | PASS | Installed Personal profile and production planner resolve to the exact Personal pack |
| J3 Connect | **PASS** | Installed snapshot provider binding; exact preview/authorize routes; explicit local/read-only/no-network/no-write preview; missing/false consent rejected with zero provider calls |
| J4 Inventory | BLOCKED | WS3 has not admitted the reviewed capture into a production Builder inventory |
| J5 First Brief | BLOCKED | WS3/WS4 have not produced a real corpus Brief |
| J6 Change | BLOCKED | No watched source or prior Brief exists before WS5 |
| J7 Ask | PARTIAL | Ask route exists; connected cited-answer path remains unavailable |
| J8 Correct | PARTIAL | Correction route exists; real claim re-derivation remains unavailable |
| J9 Restart | BLOCKED | Connected source/Brief/correction state is not yet complete |
| J10 Own | BLOCKED | Corpus-derived intelligence is not yet complete |

The executor entry-point group is deliberately visible as absent in J3 evidence but does not
gate WS2's Connect step; it is the frozen WS3 scope and blocks J4/J5. `all_pass` remains false.

Final report digests:

- JSON: `8e0dd533d81a1ccecb36aa6e5fb69ea8fc18a5e6b3a348604510bc734f758d06`
- Markdown: `7d05d0774d9c96b16fb4626af9bbd6bf369461dc788a759ea1192fed0418e430`

## Verification

- 264 focused WS0–WS2 Core, API, host, persistence/replay, recorded-source admission, setup,
  registry, and public-boundary tests passed on the final tree.
- 43 local Markdown/PDF/CSV/JSON/normalizer/provider adapter tests passed in isolated
  multi-package import mode.
- 120 final Connect/API/plan/public-boundary tests passed together after the last boundary
  correction; the kernel boundary suite passed 4/4.
- Ruff check and format check passed for all changed WS0–WS2 Python files.
- The full non-E2E/no-extension backend run produced 9,325 passes, 52 skips, 300 deselections,
  and five failures. The erase failure passed immediately in isolation. Three graph-context
  expectations still observed `a.py`/`b.py` records in the shared semantic store and failed
  identically from a pristine `origin/main` archive; WS2 does not edit release-critical
  RAG/search. The extension-disabled kernel-start test also failed identically from pristine
  `origin/main`. Six earlier loopback-denied tests passed 6/6 when rerun with loopback access.
- The installed-artifact run exercised exact consent-before-read, exact durable JSON replay,
  product/actor scope, and exact reviewed-selection binding. The clean-context run itself found
  and drove the fix for strict tuple replay after a real JSON round trip.
- The installed WS0 gate validated the exact eleven-tool MCP boundary and intentionally exited
  1 because J4–J10 are not all complete.
- No Atrium/Canvas production file changed in WS2. Desktop/narrow browser and accessibility
  checks remain proportionately deferred to WS6; the production Core wheel and API composition
  were exercised here.
- No commit, merge, push, GitHub write, tag, package publish, or release occurred. The exact
  disposable in-memory SurrealDB container was removed and is not recoverable; its data was
  test-only. Local wheels/reports under `/tmp` remain rebuildable evidence artifacts.

## Limitations and next gate

WS2 moves J3 to pass. It does not install the `ace.intelligence_builders` executor, populate the
production inventory, create a Brief, map citations to source spans, watch/re-ingest changes,
re-derive corrected claims, or mount the Atrium journey. Separate-worktree success is not public
release acceptance. The next human-only gate is owner disposition of this WS2 candidate; WS3
must not begin before that disposition.
