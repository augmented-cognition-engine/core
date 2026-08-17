# Code Intelligence installed-wheel acceptance v3

Date: 2026-08-14 (America/Los_Angeles; final receipts were emitted after 00:00 UTC on 2026-08-15)

Disposition: **accepted for the bounded product-isolated, checkout-free installation claim**

This is the first installed-wheel receipt for the settled Code Intelligence source after the
installed-solution/provider composition, exact Keep/tBTC local-index binding, pinned upstream
license, and journey product-isolation/header-authentication hardening. It supersedes neither the
immutable [v1](code-intelligence-installed-wheel-acceptance-v1.md) nor
[v2](code-intelligence-installed-wheel-acceptance-v2.md) receipt; each remains evidence only for
its exact earlier wheel.

Issue #194 remains open. This local candidate is not a release, publication, deployed service, or
full public acceptance journey.

## Exact pre-evidence source stage and artifact

The accepted artifact is:

- path: `/tmp/ace-code-clean-wheel-final-v3-20260814/ace_core-1.0.3-py3-none-any.whl`;
- size: 8,548,027 bytes;
- SHA-256: `9bb5305ae898fb0732b637d8803ebabaf98e968ded2f54296555193a10328bc8`;
- distribution identity: `ace-core==1.0.3`; and
- wheel tag: `py3-none-any`.

The final input was copied from the dirty current-source candidate at base commit
`d73906b5a7e0923be66f8f070df15b52e88bc25f` into
`/tmp/ace-wheel-v3-product-isolated-final.Sgl3ps/source`. The copy included current tracked and
untracked source while excluding `.git`, `.venv`, `build`, `dist`, `node_modules`, Python/tool
caches, uv caches, `*.egg-info`, coverage output, and the not-yet-created v3 evidence file.

Before build, all 3,171 staged regular files matched the workspace byte-for-byte. The 336,068-byte
sorted SHA-256 manifest is
`/tmp/ace-wheel-v3-product-isolated-final.Sgl3ps/prebuild-manifest.txt`, SHA-256
`a455255945b13ede428ceb98e64bf718cf7573c09c954fc23ee850c126686072`.
After every installed-only gate, checksum-aware dry-run reconciliation found no file difference
between the staged input and the workspace; its only output was the stage root directory timestamp.

Representative release-critical source fingerprints were:

| Source | SHA-256 |
|---|---|
| `core/engine/api/code_intelligence.py` | `20b38c9cea026b32ca9e1784c5b78af63711358b77786cc01ae95ddd7845deec` |
| `core/engine/api/main.py` | `e84c7d852c409723bb93c5c516f3f5548090e76ece950e1ab7f3dd8a50dcd6e4` |
| `core/engine/core/auth.py` | `c3fab653d6814ce79cae2a9e2454ba46dc1346c514f5ee90ffaa10abf04af205` |
| `core/engine/core/config.py` | `b89980266e9a6b7e4ce3f6701346671e23cee7bc2391542d0ebb52b55d162e21` |
| `core/engine/core/intelligence_resource_plane.py` | `86326a7b3fb27d72419b56aae39713d6b5f08a4706919b93692d04156c951070` |
| `core/engine/extensions/loader.py` | `6f6a0727715c4c41daf070e71953ea8a5028bb971b403b2a41d2838ddb4b0b75` |
| `core/engine/extensions/registry.py` | `ffdcfe9e662ea85e0c9383c72912ee53a56e5c13f33cfbdc29d6f467cc4435de` |
| `core/engine/code_intelligence/solution.py` | `572e44970f31226a3978635739b85af93176d77a17d1d203c45553d5b03aff24` |
| `core/engine/code_intelligence/incident_source.py` | `0e7188b8abb7a7b8e9454d955639b44770de545e0d7c25782f589a6961877dc0` |
| `core/engine/code_intelligence/incident_index_binding.py` | `5ea4f2ac7db692bb315c1787a759bcb862ad1ac117245a33a16beddf4ca14f7a` |
| `core/ui/canvas/src/app/solutions/code/register.tsx` | `3965da0d7ebd3328cca2013fed8ec260e0b086a86f4399dc9dae548999f5cdd2` |
| `core/ui/canvas/src/app/ext/registry.tsx` | `a3794d5821a1a2a5b96cbf42b85eea771c51a0f42dcf587f14d3afb8ac5cb1ec` |
| `core/ui/canvas/src/app/ext/defaults/KernelNav.tsx` | `523b68ddfc8c0d6ffd3825a3b6daffeb9e40441d3ce23d50de1500aca35698a2` |
| `core/ui/canvas/src/main.tsx` | `2212224c9f5a269ffdfde18bad6dab5e521119f4ca342785438d7b986e284c84` |
| `NOTICE` | `40472ca5548eca6eba30e8ef85427a19e9cbdf1554115db0fb9b9938911c51f3` |
| `LICENSE.keep-network-tbtc-9651d53-MIT` | `59f67a2ea030f1fcbfd4f5ffd0aae8b65f66954e5aa0fdd5b745c4ac9eba6fb9` |

The build command was:

```text
/Users/eamirian/.codex/worktrees/17ae/ace-core/.venv/bin/python \
  -m build --wheel --no-isolation \
  --outdir /tmp/ace-wheel-v3-product-isolated-final.Sgl3ps/wheel
```

The v3 evidence file and the three living index updates were intentionally written only after the
artifact passed. They are not inside the wheel and are the only expected post-stage documentation
changes. The artifact is therefore an exact **pre-evidence/current-source candidate**, not a
self-containing receipt.

## Wheel integrity, package data, license, and assets

The exact wheel passed its ZIP CRC scan. All 1,665 hashed entries in the 1,666-row `RECORD` matched
the declared URL-safe SHA-256 and size; the only unhashed row was `RECORD` itself. Forty-two
release-critical Code/API/host/verifier/static files matched the staged source byte-for-byte.

The wheel contains every current Code Intelligence module, both immutable fixtures, all five Code
verification scripts, and this installed extension declaration:

```text
[ace.extensions]
code-intelligence = core.engine.code_intelligence.solution:CodeIntelligenceSolution
```

The exact pinned Keep/tBTC MIT license is packaged at
`ace_core-1.0.3.dist-info/licenses/LICENSE.keep-network-tbtc-9651d53-MIT`: 1,053 bytes, SHA-256
`59f67a2ea030f1fcbfd4f5ffd0aae8b65f66954e5aa0fdd5b745c4ac9eba6fb9`. Packaged `NOTICE`,
SHA-256 `40472ca5548eca6eba30e8ef85427a19e9cbdf1554115db0fb9b9938911c51f3`, maps the exact
`DepositRedemption.sol` revision and `Copyright (c) 2020 Keep SEZC.` to that license.

The packaged Atrium asset set exactly matched the stage and contained no prior hashed JS/CSS:

| Asset | Bytes | SHA-256 |
|---|---:|---|
| `CodeIntelligenceOS-BLs4_Nxp.js` | 12,698 | `c57a059829f5026baab1fb55c699ee1ba0d125aad620800fe30c8ff4da9b3b12` |
| `index-DAs0KUGN.js` | 1,744,728 | `fdbd0731eb3537cb0d1bd5612a5bac08b26562157cfd05b684b4b7764485daa7` |
| `index-DLk1D7jZ.css` | 217,926 | `0f05d1c7c19d67cae5e6d70060cb334f124c081ab94261f05cd77422e46da9f1` |
| `spline-sans-latin-ext-wght-normal-DGzmlScV.woff2` | 21,112 | `2c2e7ddfe8d6b0b445d29f0f73a8fe8fe2893d5c561fbe98644eda47a9a20f7f` |
| `spline-sans-latin-wght-normal-DI10v4rJ.woff2` | 57,984 | `64513365c2d82a4ba56470e830577247342ffbf54ed8dc8df011957db5d65a9e` |
| `spline-sans-mono-latin-ext-wght-normal-Dh0aNLWd.woff2` | 20,816 | `0ca9a3989044d1f9b4da1f303cea3c3091f5cb02fe54da04fd51fceaf676ecf9` |
| `spline-sans-mono-latin-wght-normal-DlaB5ohX.woff2` | 36,476 | `46b7dcafe3e51dbe87be1bafaac3fed7646db1fe0a146647a6ffce3699f2752d` |

`index.html` names the exact entry JS/CSS; the entry bundle names the exact lazy Code chunk and
contains the installed `/atrium/code` route/navigation contribution. The lazy chunk preserves the
Code Intelligence surface. This is package inspection, not a browser-driven receipt.

The 7,404-byte integrity result is
`/tmp/ace-wheel-v3-product-isolated-final.Sgl3ps/wheel-integrity.json`, SHA-256
`a037665fe555a5199966a60bca22ab969e09eea2c0a0fee4a6fb4f63c40400f7`.

## Offline installation and checkout isolation

A fresh CPython 3.12.13 environment was created at
`/tmp/ace-code-wheel-v3-acceptance-20260814/venv`. Installation used only the exact local wheel and
the existing local uv cache:

```text
/Users/eamirian/.local/bin/uv pip install \
  --python /tmp/ace-code-wheel-v3-acceptance-20260814/venv/bin/python \
  --offline \
  /tmp/ace-code-clean-wheel-final-v3-20260814/ace_core-1.0.3-py3-none-any.whl
```

The resolver installed 157 packages including ACE. `pip check` returned
`No broken requirements found.` The sorted 158-line, 3,200-byte `pip freeze --all` has SHA-256
`fd5de4b2c0ed951992537ba43f1221c134842989b63a3a604fb4bc06a739022d`. Installed `ace --help`
loaded successfully.

All runtime probes ran from `/tmp` with `PYTHONPATH` removed, `PYTHONNOUSERSITE=1`, and Python
isolated mode. The source checkout was absent from `sys.path`. The installed origins were:

- `ace`: `/tmp/ace-code-wheel-v3-acceptance-20260814/venv/lib/python3.12/site-packages/ace/__init__.py`;
- Code Intelligence: `/tmp/ace-code-wheel-v3-acceptance-20260814/venv/lib/python3.12/site-packages/core/engine/code_intelligence/__init__.py`;
- Code API: `/tmp/ace-code-wheel-v3-acceptance-20260814/venv/lib/python3.12/site-packages/core/engine/api/code_intelligence.py`; and
- resource host: `/tmp/ace-code-wheel-v3-acceptance-20260814/venv/lib/python3.12/site-packages/core/engine/core/intelligence_resource_plane.py`.

macOS may canonicalize `/tmp` as `/private/tmp`; both paths name the same installed environment.

## Installed API, product isolation, and header authentication

The installed OpenAPI schema contains:

- `/v1/code-intelligence/journey`: `200`, `401`, `403`, `409`, `422`, `503`;
- `/v1/code-intelligence/admissions`: `200`, `401`, `403`, `409`, `422`, `503`; and
- `/v1/intelligence/resources/query`: `200`, `422`, with
  `IntelligenceResourcePageV1Alpha1` as its success model.

The journey retains `context_bodies_exposed=false`, `repository_read_only=true`,
`product_history_write=false`, `local_cache_may_write=true`, and
`index_store_provider_free=true`. Admission retains `source_body_count=0`,
`context_bodies_exposed=false`, and `local_cache_may_write=true`.

The new installed product-isolation boundary passed exactly:

| Journey gate | Installed result |
|---|---|
| Default configuration | repository root `""`; product ref `""`; inspection disabled |
| Missing repository configuration | `503`, `Code Intelligence repository inspection is not configured.` |
| Missing product configuration | `503`, `Code Intelligence product inspection is not configured.` |
| Verified token without product | `401`, `Verified token lacks product scope`, Bearer challenge |
| Product mismatch | `403`, repository inspection unavailable for that product |
| Valid query-string JWT | `401`, `Not authenticated`, Bearer challenge |

All five denials occurred before `CodeIntelligenceJourney` construction or local-cache-store
initialization, and the disposable cache path remained absent. The separate admission endpoint also
rejected a valid query-string JWT with `401` before its runtime initialized. This proves the early
installed boundary; it is not a successful journey, governed append, or deployed HTTP receipt.

The 4,404-byte installed result is
`/tmp/ace-code-wheel-v3-acceptance-20260814/installed-probe.json`, SHA-256
`fc46c9eb7e2a60425f25f885089f665a086013dce7333528d8af9faff68a2579`.

## Installed solution/provider composition and neutral surfaces

Normal installed discovery produced one Code-owned provider manifest:

```text
extension_id=code-intelligence
extension_version=1.0.3
provider_name=atrium-code-lens
supported_kinds=[semantic_revision]
```

An empty `semantic_revision` query completed without degradation. A synthetic broken optional
provider degraded only its claimed `semantic_revision` kind to one opaque reason; an unrelated
`agent` query remained complete and the provider exception text did not escape.

A separate fresh process with `ACE_DISABLE_EXTENSIONS=1` installed no provider and returned exactly
`degraded_reason:unsupported-semantic_revision`. Its 204-byte result is
`installed-probe-disabled.json`, SHA-256
`53a479b14a301abcc20767a2a51a344dbe9d2ff112ba9bf70295dd6289ccddd5`.

The MCP inventory remained exactly 11 tools: `ace_start`, `ace_load`, `ace_capture`, `ace_task`,
`ace_status`, `ace_capture_idea`, `ace_search`, `ace_briefing`, `ace_impact`, `ace_history`, and
`ace_related`. The public resource vocabulary remained exactly 24 neutral kinds and contains no
Code-domain repository/file/service/module/symbol/feature/test/API/ownership/ADR/incident/
dependency/architecture noun.

## Installed fresh-process continuity

The installed verifier ran as:

```text
/tmp/ace-code-wheel-v3-acceptance-20260814/venv/bin/python -I \
  -m scripts.verify_code_index_continuity \
  --work-root /tmp/ace-code-wheel-v3-acceptance-20260814/continuity-work \
  --output /tmp/ace-code-wheel-v3-acceptance-20260814/continuity-result.json
```

The 2,878-byte result has SHA-256
`9af1b145cfd3847412c3482d7a636a06a50a1a7b82ab6f24b9203da5d0786158` and `accepted=true`.

| Check | Result |
|---|---|
| Initial scan | 3 files, 3 functions, 2 imports; generation 1 |
| Generation-1 index | `code_index:1240b7baff4f75712dc99e98630ae6e6` |
| Generation-1 snapshot | `code_index_snapshot:76274cedbfbce4b57283aa073708ce57` |
| Fresh-process reopen | exact snapshot; full rescan and provider invocation forbidden |
| Incremental change | exact `pkg/service.py`; one file updated, two symbols added |
| Generation-2 index | `code_index:ea327c8f15b6dd079e1d7d60a2adbdbe` |
| Generation-2 snapshot | `code_index_snapshot:3277e547b0965e00c282a820af31a9d3` |
| History | exact parent ID/digest; both immutable snapshots readable |
| Authority | provider-neutral; all source/reasoning/delivery/execution/effect authority false |

## Installed incident projection and exact local-index binding

The installed verifier ran against the preserved clean sparse tBTC checkout:

```text
/tmp/ace-code-wheel-v3-acceptance-20260814/venv/bin/python -I \
  -m scripts.verify_code_incident_local_index_binding \
  --repository /tmp/ace-tbtc-binding.aLmMuk \
  --output /tmp/ace-code-wheel-v3-acceptance-20260814/incident-local-index-binding.json
```

The checkout was still clean at revision `9651d53a443b3d2470e13ee1db0ecae60be8b246`, with tracked
blob `e7e16d77c32fd23437320cede83c07db75e6f5e8` at
`solidity/contracts/deposit/DepositRedemption.sol`. The current-time body-free receipt is 3,835
bytes, SHA-256 `06dfcfbbd3128df216c12af8850bdc0b411b2dedcd36d668c161536e2e093fe6`.
Its exact index remains `code_exact_local_index:87e0b1c57680f97df417e0c7ac132846`; its timestamp-bound
snapshot is `code_exact_local_snapshot:0ff2e4930fffc6c3589ce6f49fb2af0a`; and its binding receipt
is `code_incident_local_index_binding:1c21678337609ff1db6ca838131fb96a`.

A second installed-only fixed-time adversarial probe produced exactly one
`affected_code_snapshot` relation, three evidence records, and two explicit omissions. It proved:

- same-time capture/receipt determinism;
- stable content index/artifact identities but timestamp-bound snapshot identities;
- paired source forgery rejection;
- forged receipt rejection;
- 1999/2099 cross-wired timestamp rejection;
- mutually shifted but structurally valid timestamp rejection at paired validation;
- exact 17,849-byte code artifact SHA-256
  `22ce6fd7f78e97423a495273bbea89d7d185b12318b3dd0da6449b38acbaf330`;
- `body_included=false`, `semantic_scope=none`, and no dependency/impact inference; and
- all source, reasoning, change, approval, delivery, execution, and effect authority false.

That 1,794-byte result is `installed-incident-probe.json`, SHA-256
`d3c8b3a53251e6a730226826bd00dfdc8e8570ebaa52e2027df8d976ac2e957b`.
The differing fixed-time and current-time snapshot/receipt identities are expected: capture time is
part of snapshot and receipt identity while content index/artifact IDs remain stable.

## Verifier fingerprints and reproducibility

The temporary integrity verifier was 6,108 bytes, SHA-256
`dac0c2e09361898a87f437e340d6b0b756df8e7a8d16fcc13dbab6ebaede01be`. The installed API/resource
probe was 17,839 bytes, SHA-256
`500b08d0b436b0091d24b85f645a97891a47e2fed8ed824132b6c13a3cae4b9d`. The installed incident
probe was 7,258 bytes, SHA-256
`efbb4eb119ad7be0ab29ea7e2b65067932e2b8a0215b80f122d6f7ae1671861b`.
They are temporary local acceptance harnesses, not shipped APIs.

Their exact invocations were:

```text
/Users/eamirian/.codex/worktrees/17ae/ace-core/.venv/bin/python \
  /tmp/ace-wheel-v3-product-isolated-final.Sgl3ps/verify_wheel.py \
  /tmp/ace-code-clean-wheel-final-v3-20260814/ace_core-1.0.3-py3-none-any.whl \
  /tmp/ace-wheel-v3-product-isolated-final.Sgl3ps/source \
  /tmp/ace-wheel-v3-product-isolated-final.Sgl3ps/wheel-integrity.json

env -u PYTHONPATH \
  -u CODE_INTELLIGENCE_REPOSITORY_ROOT \
  -u CODE_INTELLIGENCE_PRODUCT_REF \
  PYTHONNOUSERSITE=1 \
  JWT_SECRET=installed-v3-disposable-secret-only \
  /tmp/ace-code-wheel-v3-acceptance-20260814/venv/bin/python -I \
  /tmp/ace-code-wheel-v3-acceptance-20260814/installed_probe.py

env -u PYTHONPATH \
  -u CODE_INTELLIGENCE_REPOSITORY_ROOT \
  -u CODE_INTELLIGENCE_PRODUCT_REF \
  PYTHONNOUSERSITE=1 \
  JWT_SECRET=installed-v3-disposable-secret-only \
  ACE_DISABLE_EXTENSIONS=1 \
  /tmp/ace-code-wheel-v3-acceptance-20260814/venv/bin/python -I \
  /tmp/ace-code-wheel-v3-acceptance-20260814/installed_probe.py --disabled

env -u PYTHONPATH PYTHONNOUSERSITE=1 \
  JWT_SECRET=installed-v3-disposable-secret-only \
  /tmp/ace-code-wheel-v3-acceptance-20260814/venv/bin/python -I \
  /tmp/ace-code-wheel-v3-acceptance-20260814/installed_incident_probe.py \
  /tmp/ace-tbtc-binding.aLmMuk
```

`JWT_SECRET` above was a disposable local signing value used only to construct valid rejection
tokens. No provider credential or production secret was used. `pip check`, CLI, origin, and freeze
probes used the same installed interpreter from `/tmp`, isolated from the checkout.

## Boundary and non-claims

This is an exact checkout-free local installation receipt for one macOS/CPython 3.12.13 environment
and one wheel hash. It does not claim:

- a public-index install, signed/trusted publication, GitHub Release, or release promotion;
- a second operating system, universal language support, or dependency-lock hermeticity;
- a successful repository journey, browser-driven Atrium session, or deployed static site;
- a deployed HTTP service, live/shared/production database, production grant decision, or governed
  admission append;
- online/replicated backup, formal restore/recovery, rollback, migration, or 1.3 update UX;
- model-provider execution, availability, retrieval, reasoning, delivery, effects, or material use;
- live incident acquisition, an ACE incident, causality/root cause, Solidity semantics, dependency
  inference, or downstream impact reasoning; or
- automatic watching, multi-repository topology, or any profile beyond Python/local/single-repository
  semantic analysis plus the explicitly separate one-coordinate Solidity inventory.

No artifact was published, no commit or push was made, and the immutable v1/v2 evidence files were
not modified. The pre-product-isolation wheel, stage, and probe tree were permanently removed and
contribute no evidence to this receipt.
