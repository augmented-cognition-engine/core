# Code Intelligence installed-wheel acceptance v2

Date: 2026-08-14

Disposition: **accepted for the bounded integrated checkout-free installation claim**

This receipt supersedes v1 only for the later source-landed Code Intelligence surface. The immutable
[v1 receipt](code-intelligence-installed-wheel-acceptance-v1.md) remains the point-in-time record for
its own earlier wheel and must not be reinterpreted as admission evidence.

## Exact artifact and clean build input

The accepted artifact is:

- path: `/tmp/ace-code-clean-wheel-final-v2-20260814/ace_core-1.0.3-py3-none-any.whl`;
- size: 8,501,851 bytes;
- SHA-256: `11ff168945c31c1322bd6f45290f2b0609ff5a77b364ce72c4795999c2f5b164`;
- distribution identity: `ace-core==1.0.3`; and
- wheel tag: `py3-none-any`.

The final build input was a new copy at `/tmp/ace-wheel-v2-final-build.OMegkI/source`. The copy
excluded `.git`, `.venv`, `build`, `dist`, `node_modules`, Python/tool caches, uv caches, and
`*.egg-info`. A pre-build scan found none of those directories. The wheel was then built from that
copy with:

```text
/Users/eamirian/.codex/worktrees/17ae/ace-core/.venv/bin/python \
  -m build --wheel --no-isolation \
  --outdir /tmp/ace-wheel-v2-final-build.OMegkI/wheel
```

The shared source gate had already reconfirmed 172 backend tests, the Atrium component/TypeScript/
production-build gate, Ruff, JSON validation, and diff checks after the final mechanical formatting.
An earlier pre-format v2 candidate was invalidated and is not evidence for this receipt.

## Wheel integrity and Atrium assets

The exact accepted wheel passed its ZIP CRC scan. All 1,655 hashed entries in the 1,656-row
`RECORD` matched both the declared URL-safe SHA-256 and size. The sole unhashed row was `RECORD`
itself.

The installed Atrium asset directory exactly matched the final source asset directory and contained
only:

- `index-CuSni149.js`;
- `index-DLk1D7jZ.css`;
- `spline-sans-latin-ext-wght-normal-DGzmlScV.woff2`;
- `spline-sans-latin-wght-normal-DI10v4rJ.woff2`;
- `spline-sans-mono-latin-ext-wght-normal-Dh0aNLWd.woff2`; and
- `spline-sans-mono-latin-wght-normal-DlaB5ohX.woff2`.

The packaged `index.html` referenced the exact JS and CSS names above. No superseded hashed JS or
CSS bundle was present.

## Offline installation and checkout isolation

A fresh CPython 3.12.13 environment was created at
`/tmp/ace-code-wheel-v2-acceptance-20260814/venv`. Installation used only the exact local wheel and
the existing local uv cache:

```text
uv pip install \
  --python /tmp/ace-code-wheel-v2-acceptance-20260814/venv/bin/python \
  --offline \
  /tmp/ace-code-clean-wheel-final-v2-20260814/ace_core-1.0.3-py3-none-any.whl
```

The offline resolver installed 157 packages including ACE. `pip check` returned
`No broken requirements found.` The sorted 158-line `pip freeze --all` was 3,200 bytes with
SHA-256 `bc7f0da39183794a4c6b911d71def7d3e9883cb3c0443c871c3406139e37e13d`.

All runtime probes ran from `/tmp` with `PYTHONPATH` removed, `PYTHONNOUSERSITE=1`, and Python
isolated mode. The checkout was absent from `sys.path`. `ace`, Code Intelligence, and the continuity
verifier resolved only from the temporary environment's `site-packages`. The installed `ace --help`
command loaded successfully.

## Installed API and authentication surface

An OpenAPI-only probe supplied a disposable JWT secret and disabled extensions. It did not run the
application lifespan or connect to a database. The installed schema contained authenticated POST
operations for:

- `/v1/code-intelligence/journey` with responses `200`, `401`, `409`, `422`, and `503`;
- `/v1/code-intelligence/admissions` with responses `200`, `401`, `403`, `409`, `422`, and `503`;
  and
- `/v1/intelligence/resources/query`, whose `200` response references
  `IntelligenceResourcePageV1Alpha1` and whose generated responses are `200` and `422`.

The journey response froze these literal effects:

- `contract = ace.code-intelligence.atrium-journey-response/v1alpha1`;
- `context_bodies_exposed = false`;
- `repository_read_only = true`;
- `product_history_write = false`;
- `local_cache_may_write = true`; and
- `index_store_provider_free = true`.

The admission response froze:

- `contract = ace.code-intelligence.atrium-code-lens-admission-response/v1alpha1`;
- `source_body_count = 0`;
- `context_bodies_exposed = false`; and
- `local_cache_may_write = true`.

A safe in-process probe created a valid query-string JWT and sent it to the header-only admission
route. The result was `401`, `{"detail":"Not authenticated"}`, and `WWW-Authenticate: Bearer`.
The admission runtime sentinel was not initialized, the configured repository was not read, and no
local index directory was created. This proves early query-token rejection, not a deployed
admission or database transaction.

## Installed continuity acceptance

The installed continuity verifier ran as:

```text
/tmp/ace-code-wheel-v2-acceptance-20260814/venv/bin/python -I \
  -m scripts.verify_code_index_continuity \
  --work-root /tmp/ace-code-wheel-v2-acceptance-20260814/continuity-work \
  --output /tmp/ace-code-wheel-v2-acceptance-20260814/continuity-result.json
```

The 2,878-byte result had SHA-256
`c7e5d1068788b831dc7f6f1f30268d223be73e3785d320e1d2032fd4828fd3ad` and reported
`accepted: true`.

| Check | Installed-wheel result |
|---|---|
| Initial capture | 3 files, 3 functions, 2 imports; generation 1 |
| Generation-1 index | `code_index:bee27e9d5e54f340c9c8c1cdde5396be` |
| Generation-1 snapshot | `code_index_snapshot:92f34aabd08dbc679aebcc4cb792adc1` |
| Fresh-process reopen | Exact generation-1 snapshot; full rescan and provider invocation forbidden |
| Incremental input | Exact changed set `pkg/service.py`; 1 file updated and 2 symbols added |
| Generation-2 index | `code_index:15916ceecca931c589f2ad7ff38f1120` |
| Generation-2 snapshot | `code_index_snapshot:5c23a74d880d1d00801488748a81d89a` |
| Parent and history | Exact parent ID/digest; both immutable snapshots readable; old digest unchanged |
| Authority | Provider-neutral; no source, reasoning, delivery, execution, or effect authority |

## Installed incident, MCP, and neutral resource surfaces

The wheel and `RECORD` contain the incident projector, canonical-source host seam, packaged fixture,
and explicit fixture verifier. The installed fixture is 11,212 bytes with SHA-256
`12ceffefa5e9bf56c3f3b6a66537a834f1c08376321654737191e1d44d9cd09e`.

Installed-only projection produced one `affected_code_snapshot` relation, three evidence records,
and two explicit omissions. Paired source-envelope validation passed. A mutually consistent forged
standalone snapshot lineage remained structurally parseable, while the mandatory paired validator
rejected it. The literals remained `source_snapshot_revalidation_required = true` and
`self_authenticates_source_snapshot = false`.

The thin MCP inventory remained exactly 11 tools: `ace_start`, `ace_load`, `ace_capture`,
`ace_task`, `ace_status`, `ace_capture_idea`, `ace_search`, `ace_briefing`, `ace_impact`,
`ace_history`, and `ace_related`.

The shared public Intelligence resource vocabulary remained exactly 24 generic kinds, included
`semantic_revision`, and introduced no Code-domain noun token such as repository, file, service,
module, symbol, feature, test, API, ownership, ADR, incident, dependency, or architecture.

## Reproduction boundary and non-claims

This is an exact checkout-free **local-cache installation** receipt for one macOS/Python 3.12
environment and the wheel hash above. It is not a public-index install, a trusted-publication
receipt, a second-operating-system matrix, or a lockfile-hermetic dependency proof.

The acceptance does not claim:

- a live or deployed SurrealDB connection, migration, append, replay, backup, rollback, or recovery;
- a successful governed admission, production grant decision, or deployed HTTP receipt;
- a browser-driven Atrium journey or deployed static-site receipt;
- model-provider execution, network retrieval, or provider availability;
- live public-index download or artifact publication;
- live incident acquisition, live incident composition, or an ACE incident;
- coding-agent delivery, change, effect, outcome, or material-use authority; or
- languages/topologies beyond the declared bounded Python, local, single-repository profile.

No artifact was published, no v1 evidence was modified, and no implementation file was changed by
this acceptance lane.
