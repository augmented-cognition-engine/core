# PI13 WS1 local candidate evidence v1

- Date: 2026-08-20
- Baseline: `origin/main` / `e9a53ae63d209a266dc8a5156b1afcd5c939dd08`
- Disposition: **reviewed and freshly verified local candidate; owner disposition pending; not landed**
- Scope: WS1 and the corresponding WS0 J3 motion only. This record does not claim a public
  release acceptance run or an ACE 1.2 acceptance pass.

## Candidate composition

WS1 adds a domain-neutral `SourceSnapshotRequestV1Alpha1` and `SourceSnapshotProvider` port for
the exact `source_snapshot` / `ace.source.snapshot/v1alpha1` capability contract. The request
describes one exact already-authorized absolute root and sorted include/exclude scope. It carries
no grant or reusable authority. Registration revalidates the provider's exact capability
artifact identity.

The production host registry discovers only `ace.source_snapshot_providers`, loads once,
rejects duplicate implementations and ambiguous capability/contract claims, rolls back on
failure, preserves a cached discovery error, and refuses identity drift after registration.
`ACE_DISABLE_EXTENSIONS=1` keeps the naked kernel empty.

The new `ace-local-source-snapshot` wheel registers `local_source_snapshot` and composes the
existing governed `acquire_local_folder` port with the PI2 Markdown/PDF/CSV/JSON normalizer
chain. It adds no traversal, source admission, connector catalog, remote-source, RAG/search, or
Personal product logic. Its normalizer seam shapes the existing `SourceUnit` records into
explicit JSON-serializable dictionaries; unsupported formats remain inventoried as unsupported.

Exact candidate identities:

- provider artifact: `local_source_snapshot==0.1.0`
- provider source digest:
  `sha256:b8251c69a13b9b6dbb7f09e4a124f30d5b23ad5da3249bdc6c9568c01e838010`
- provider wheel digest:
  `sha256:6d13e389b9ba5636bc3e81fbcc05ef87b76d396be1fedab22e5d9a8e1b537f68`
- rebuilt Core wheel digest:
  `sha256:966bed2c78ace54d3d52720525cb8380a9ed3cc8c95687b24cc9a69a1bc16f5a`
- Personal bundle manifest:
  `solution_bundle_manifest:71eedae43f911811a5b4a3abb89cfeb4`

Claude Code CLI performed the bounded implementation and the installed-metadata correction in
workstream-specific prompts. Every resulting diff was inspected here. The CLI was usable; the
previously observed decommissioned-project stale hook did not block this work. Claude was not
used as approval authority.

## Fresh installed-artifact run

The candidate built fresh wheels for Core, all local adapters including the new provider, the
Personal pack, and the Personal bundle. Only those wheels and their declared dependencies were
installed into a new bare Python 3.12 environment outside the checkout. A memory-only
SurrealDB 3.2.3 container with no volume received the schema from the installed Core wheel and
validated schema version 179. The final gate invocation used the runner installed inside that
same rebuilt Core wheel.

The first fresh run found that existing extension loading had prepended the same site-packages
path already present, causing `importlib.metadata` to enumerate one exact pack dist-info twice.
The WS0 runner now collapses only identical canonical-name plus identical resolved-dist-info
entries before calling the unchanged fail-closed installed-pack resolver. Distinct paths remain
distinct and therefore still surface ambiguity. Focused regression tests cover both cases.

The strict runner exited 1 and emitted every J1-J10 row in order:

| Step | Result | Candidate evidence or blocker |
|---|---|---|
| J1 Install | PASS | Fresh distributions including `ace-local-source-snapshot`; schema 179; four fixtures; exactly eleven MCP tools; deterministic stub invoked |
| J2 Choose | PASS | Installed Personal profile and production planner resolve to the exact Personal pack |
| J3 Connect | FAIL, snapshot portion verified | Provider entry point loads; exact artifact validates; pack requirement is bound in a prepared, unpersisted activation spec; Connect API routes and executor remain absent |
| J4 Inventory | BLOCKED | No connected inventory exists before WS2/WS3 |
| J5 First Brief | BLOCKED | No admitted corpus exists before WS2/WS3 |
| J6 Change | BLOCKED | No watched source or prior Brief exists before WS5 |
| J7 Ask | PARTIAL | Ask route exists; connected cited-answer path remains unavailable |
| J8 Correct | PARTIAL | Correction route exists; real claim re-derivation remains unavailable |
| J9 Restart | BLOCKED | Connected source/Brief/correction state does not exist yet |
| J10 Own | BLOCKED | Corpus-derived intelligence does not exist yet |

J3's exact remaining blocker is `F5-F10:missing_connect_routes_executor`. Its activation evidence
is `activation_spec:dbeb6d53a90ebee3f49ab0854ae557ff`. The authority bindings used for this
pure preparation probe are deterministic structural fixtures only; they were not resolved,
committed, persisted, or used to read a source.

Final report digests:

- JSON: `80bfef18153db48e18c2a8bec0d373d1ad101c3a10b740d7c8c5fa13c6e22a5f`
- Markdown: `06dbaf6ec4a66b4181ec063b0de4214072d16e075b5ac6cd650564faa499f8db`

## Installed provider invocation

An independent invocation resolved the provider through the production registry, constructed
request `source_snapshot_request:510a8b49ee45d090d657ebbeb27d6af6`, and took a snapshot of a
disposable copy of the four-format WS0 corpus. Exact source hashes before and after were equal.
All four files were acquired with explicit structured units:

| Source | Byte digest | Units |
|---|---|---:|
| `notes/vault.md` | `sha256:56ec441935b8aadf1ee74687a46b546bd03a8a3f2452ccd63f84f3641133d5bc` | 1 |
| `sample.csv` | `sha256:64cbc8cf50346d067f5d13c2d866d9e13c126ec69cbea14f8865c02a57160d97` | 3 |
| `sample.json` | `sha256:d141371d9e4b2ad6b7a1fda347ad2eb3f98e216cbf07c4253e4a4823863f8913` | 10 |
| `sample.pdf` | `sha256:ac61c22b62868f01208b46a459c702ba738a571496a41d28810379e1b06845d5` | 1 |

This invocation proves the provider and PI2 adapter composition is read-only. Consent and grant
resolution still belong to WS2 and were deliberately not simulated as a production API claim.

## Verification

- 161 focused adapter, normalizer, acquisition, mapping, provider, registry, bundle, and WS0
  tests passed together using isolated multi-package import mode.
- 14 public-Core and naked-kernel boundary tests passed.
- Ruff check and format check passed for all WS1 and touched WS0 Python files.
- The full non-E2E/no-extension backend run produced 9,203 passes, 52 skips, 300 deselections,
  and the same three existing `tests/test_graph_context.py` expectation failures documented by
  WS0. That file passed 26/26 with `EMBEDDING_PROVIDER=none`. WS1 does not edit retrieval/search.
- The installed-artifact run validated the exact eleven-tool MCP boundary.
- No API or Atrium/Canvas code changed in WS1, so browser, narrow-layout, accessibility, and
  production UI-build checks remain proportionately deferred to their API/UI workstreams.
- No commit, merge, push, GitHub write, tag, package publish, or release occurred. The exact
  disposable SurrealDB container was removed; generated local build directories were removed
  and are recoverable by rebuilding.

## Limitations and next gate

WS1 moves only the snapshot-binding portion of J3. It does not provide consent-before-read,
recorded-source admission, Connect APIs, the Builder executor, citations, watching/re-ingest,
or Atrium journey wiring. Separate-worktree success is not public release acceptance. The next
human-only gate is owner disposition of this WS1 candidate; WS2 has not started.
