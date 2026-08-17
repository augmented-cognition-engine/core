# Code Intelligence installed-wheel acceptance v1

Date: 2026-08-14

Disposition: **accepted for the bounded checkout-free packaging and continuity claim**

## Exact artifact and environment

The acceptance installed this wheel as the only ACE artifact:

- path: `/tmp/ace-code-clean-wheel-final-20260814/ace_core-1.0.3-py3-none-any.whl`;
- size: 8,473,367 bytes;
- SHA-256: `0b399c00f36458aedf10f1f83a7e5a60fecc166011ea791f2106ffc7045c3edb`;
- distribution identity: `ace-core==1.0.3`; and
- interpreter: CPython 3.12.7.

The wheel ZIP passed its CRC scan. All 1,650 hashed entries in its 1,651-row `RECORD` matched their
declared hash and size; the unhashed row was `RECORD` itself.

A new environment was created at `/tmp/ace-wheel-acceptance.4kzMid/venv`. The installer ran in
offline mode and resolved ACE plus 156 dependencies from the existing local uv cache. It made no
network request. `pip check` reported `No broken requirements found.` The sorted 158-line installed
freeze, including environment bootstrap packages, had SHA-256
`0d3d2c25baf7d4459a6b4e072f0b900a341726c4f2fac1755cedc02a9d713106`.

## Checkout isolation

All probes ran from the temporary acceptance directory with `PYTHONPATH` removed,
`PYTHONNOUSERSITE=1`, and Python isolated mode where applicable. The source checkout was absent from
`sys.path`.

Resolved modules were:

- `ace`: `/private/tmp/ace-wheel-acceptance.4kzMid/venv/lib/python3.12/site-packages/ace/__init__.py`;
- Code Intelligence: `/private/tmp/ace-wheel-acceptance.4kzMid/venv/lib/python3.12/site-packages/core/engine/code_intelligence/__init__.py`; and
- continuity verifier: `/private/tmp/ace-wheel-acceptance.4kzMid/venv/lib/python3.12/site-packages/scripts/verify_code_index_continuity.py`.

No probe imported implementation code from the repository checkout.

## Installed continuity acceptance

The installed verifier ran in a fresh isolated Python process:

```text
python -I -m scripts.verify_code_index_continuity \
  --work-root /tmp/ace-wheel-acceptance.4kzMid/continuity-work \
  --output /tmp/ace-wheel-acceptance.4kzMid/continuity-result.json
```

The result reported `accepted: true`. Its exact output file was 2,878 bytes with SHA-256
`7d90ca685250da1766da1dfed3a523f91117c5844730aa55d99f26413caa3265`.

| Check | Installed-wheel result |
|---|---|
| Initial phase-one capture | 3 files, 3 symbols, 2 imports; generation 1 |
| Generation-1 index | `code_index:498a5170e82e23edae4dac6725c842d7` |
| Generation-1 snapshot | `code_index_snapshot:c780fb6814ea0139671aba0e73ece04a` |
| Fresh-process reopen | Passed with full rescan and provider invocation explicitly forbidden |
| Provider environment | Absent |
| Incremental change | Exact changed set `pkg/service.py`; 2 symbols added; generation 2 |
| Generation-2 index | `code_index:a6a78f384b30ef37d9ce5c8b2e1cec21` |
| Generation-2 snapshot | `code_index_snapshot:c7165491ea33892490057abc8c38add2` |
| Parent linkage | Generation 2 names the exact generation-1 snapshot ID and digest |
| Immutable history | Two snapshots; old digest unchanged; old snapshot readable; old symbol absent and new symbol present as expected |
| Authority | Provider-neutral; source, reasoning, execution, delivery, and effect authority all false |

## Installed public-surface checks

The installed artifact also passed these bounded checks:

- the CLI loaded and rendered `ace --help`;
- OpenAPI contained authenticated `POST /v1/code-intelligence/journey` and the governed
  `/v1/intelligence/resources/query` path;
- the shared resource plane retained exactly 24 generic kinds, included `semantic_revision`, and
  introduced no Code-named generic kind;
- the Code-specific `contributor` kind and governed Code-lens projection reader imported;
- the thin MCP inventory remained exactly these eleven tools: `ace_briefing`, `ace_capture`,
  `ace_capture_idea`, `ace_history`, `ace_impact`, `ace_load`, `ace_related`, `ace_search`,
  `ace_start`, `ace_status`, and `ace_task`; and
- installed Atrium `index.html` referenced `index-CuSni149.js` and `index-DLk1D7jZ.css`, and both
  hashed assets were present in the installed package.

The API import correctly failed closed without a JWT secret. The OpenAPI-only probe supplied a
disposable acceptance secret and disabled extensions; it supplied no database or model-provider
credential and performed no external effect.

## Reproduction boundary and non-claims

This is a checkout-free **local-cache installation** acceptance for the exact wheel above. It is
not a clean public-index download, a lockfile-hermetic dependency proof, or an installation on a
second operating system. Reproduction requires that exact wheel plus a compatible Python 3.12
environment and locally available dependency artifacts (or separately authorized network access).

The acceptance does not claim:

- live database startup, migration, backup, or recovery;
- a browser-driven Atrium journey;
- a connected real repository outside the verifier's disposable fixture;
- provider execution, LSP/compiler coverage, or languages beyond the declared Python profile;
- governed live admission of a lens revision; or
- coding-agent delivery, effect, outcome, or material-use authority.

No artifact was published and no implementation file was changed by this lane.
