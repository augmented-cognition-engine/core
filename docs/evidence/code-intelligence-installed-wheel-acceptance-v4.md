# Code Intelligence installed-wheel acceptance v4

Date: 2026-08-14 (America/Los_Angeles; acceptance completed after 00:00 UTC on 2026-08-15)

Disposition: **accepted for the bounded checkout-free installation and material-use replay claim**

This receipt covers the first installed wheel after the calibrated MCP and REST impact packet and
the durable local material-use evidence packet. It preserves the immutable
[v1](code-intelligence-installed-wheel-acceptance-v1.md),
[v2](code-intelligence-installed-wheel-acceptance-v2.md), and
[v3](code-intelligence-installed-wheel-acceptance-v3.md) receipts as point-in-time evidence for
their exact earlier artifacts.

Issue #194 remains open. This candidate is not a release, publication, deployment, production
grant, or full public acceptance journey.

## Exact pre-evidence source and wheel

The accepted artifact is:

- path: `/tmp/ace-code-wheel-v4.SbJGNb/wheel/ace_core-1.0.3-py3-none-any.whl`;
- size: 8,557,773 bytes;
- SHA-256: `164ffc8ccaa35e591eb8e248740edf930b28f4a247a636aa593def08c1fb58d0`;
- distribution identity: `ace-core==1.0.3`; and
- wheel tag: `py3-none-any`.

The input was copied from the dirty current-source candidate at base commit
`d73906b5a7e0923be66f8f070df15b52e88bc25f` to
`/tmp/ace-code-wheel-v4.SbJGNb/source`. The stage excluded Git metadata, virtual environments,
dependency/build output, and tool caches. Its 3,175-file, 336,578-byte sorted SHA-256 manifest is
`/tmp/ace-code-wheel-v4.SbJGNb/prebuild-manifest.txt`, SHA-256
`fd0c131f24ec1a500d1b08fe2cb04a4217c66e24302144145a7e49098df58c0c`.
The captured porcelain Git-status receipt is SHA-256
`395ce0e7e1cf159f796e8e1c2e06416952bf8a837f8d29aa19d2d27478e51655`.

Immediately before this v4 receipt was written, a separately copied current tree produced the
same 3,175-line manifest and an empty checksum-aware drift diff. This file and the living-index
edits below are therefore the only intentional post-stage changes. The wheel is an exact
**pre-evidence/current-source candidate**, not a self-containing receipt.

Representative changed-source fingerprints are:

| Source | SHA-256 |
|---|---|
| `core/engine/mcp/tools.py` | `6e3a86c71d0b5008530d1652f67a7620325019b37056e84c0583afd08e5b3dbc` |
| `core/engine/mcp/server.py` | `ca7c403a0e21dae513a9d5afc84f866aa2b2ecb17bce18001d4a650ca0e92b2e` |
| `core/engine/api/graph_traverse.py` | `ccf15f0a5580534eb65829292b9ef6c8f06b5c96d4d9311f6c3f6820ffda45a8` |
| `core/engine/code_intelligence/contracts.py` | `bfb9378ed7d0e09c94247fdd85de19306125ccd7c95796fde8078b7765478ea8` |
| `core/engine/code_intelligence/handoff.py` | `59a10d21bed42b1a14a9a6553684d4e583ef43dd4f92be5c173af5ee055e4800` |
| `scripts/verify_code_intelligence_return.py` | `812bfb4b3cd641fe675ae5c34c5294339136a9090663053a29c5b94ff1eb283f` |

The build used the repository's CPython 3.12 environment with `python -m build --wheel
--no-isolation`. No network dependency resolution was used.

## Wheel integrity, package data, license, and assets

The wheel passed its ZIP CRC scan. All 1,666 hashed entries in the 1,667-row `RECORD` matched the
declared URL-safe SHA-256 and size; the only unhashed entry was `RECORD` itself. Nineteen
release-critical Code/API/MCP/verifier files matched the staged source byte-for-byte.

The installed extension entry point remains exactly:

```text
[ace.extensions]
code-intelligence = core.engine.code_intelligence.solution:CodeIntelligenceSolution
```

The exact pinned Keep/tBTC MIT license remains 1,053 bytes with SHA-256
`59f67a2ea030f1fcbfd4f5ffd0aae8b65f66954e5aa0fdd5b745c4ac9eba6fb9`. Packaged `NOTICE`,
SHA-256 `40472ca5548eca6eba30e8ef85427a19e9cbdf1554115db0fb9b9938911c51f3`, retains the exact
Keep SEZC/revision/path/license mapping.

The 17 packaged Atrium static files exactly matched the stage. No orphaned v1 bundle remained.
The current entry assets were:

| Asset | Bytes | SHA-256 |
|---|---:|---|
| `index.html` | 847 | `f5742cf808391bbb5ad96d77a7af5f101ea59040ba042d402e4889ab332747c3` |
| `assets/CodeIntelligenceOS-BLs4_Nxp.js` | 12,698 | `c57a059829f5026baab1fb55c699ee1ba0d125aad620800fe30c8ff4da9b3b12` |
| `assets/index-DAs0KUGN.js` | 1,744,728 | `fdbd0731eb3537cb0d1bd5612a5bac08b26562157cfd05b684b4b7764485daa7` |
| `assets/index-DLk1D7jZ.css` | 217,926 | `0f05d1c7c19d67cae5e6d70060cb334f124c081ab94261f05cd77422e46da9f1` |

`index.html` names the exact current JS/CSS and the entry bundle names the exact lazy Code chunk.
This is package inspection, not browser acceptance. The complete integrity receipt is 6,748 bytes,
SHA-256 `eb46bb35d0b0fab663b7cefd43126dc3847ad078df1f8491fcea2e7f2a22129e`.

## Fresh offline CPython 3.12 installation

The exact wheel was installed offline into a fresh CPython 3.12.13 environment at
`/tmp/ace-code-wheel-v4.SbJGNb/venv` using only the local wheel and existing local package cache.
The resolver installed 157 packages including ACE. `pip==26.2.1` was then seeded from the same
offline cache so the exact `python -m pip check` gate could run; it returned
`No broken requirements found.`

The final 158-line, 3,192-byte `pip freeze --all` receipt has SHA-256
`62522ef5588a3c4dd490ae689a822ce94a231abec364ac7db4d1b804cc14d9fe`.
Installed `ace --help` loaded successfully.

Every runtime probe ran from `/tmp` with `PYTHONPATH` removed, `PYTHONNOUSERSITE=1`, and Python
isolated mode. The source checkout was absent from `sys.path`; all ACE, Code API, resource host,
MCP, REST impact, and return-verifier origins were under the fresh environment's `site-packages`.

## Installed API, authentication, and solution/provider composition

Installed OpenAPI retained the exact Code journey and admission response sets (`200`, `401`, `403`,
`409`, `422`, `503`) and the neutral resource-query response (`200`, `422`). The journey remained
read-only, body-free to Atrium, product-history-write negative, local-cache-write explicit, and
provider-free at the index boundary. Admission remained source-body-count zero.

With inspection disabled by default, the installed boundary passed:

| Gate | Result |
|---|---|
| Missing repository configuration | `503` before journey/cache construction |
| Missing product configuration | `503` before journey/cache construction |
| Verified token without product scope | `401` with Bearer challenge |
| Product mismatch | `403` before repository/cache access |
| Query-string journey JWT | `401`; header-only authentication retained |
| Query-string admission JWT | `401`; admission runtime not initialized |

Normal installed discovery produced the exact `code-intelligence` / `1.0.3` /
`atrium-code-lens` provider for `semantic_revision`, and that query completed without degradation.
A broken optional provider degraded only its claimed kind without leaking its exception or poisoning
an unrelated `agent` query. With `ACE_DISABLE_EXTENSIONS=1`, no provider was installed and the kind
returned exactly `degraded_reason:unsupported-semantic_revision`.

The MCP inventory remained exactly 11 tools. The resource vocabulary remained exactly 24 neutral
kinds and contains none of the Code-domain repository/file/service/module/symbol/feature/test/API/
ownership/ADR/incident/dependency/architecture nouns. The installed probe is SHA-256
`de5f759bab74ba5ee370f7c5004af94360ac3e1dce9a9192abadc6cea7111022`; the disabled-process
probe is SHA-256 `53a479b14a301abcc20767a2a51a344dbe9d2ff112ba9bf70295dd6289ccddd5`.

## Installed continuity and incident boundaries

The installed fresh-process continuity verifier passed generation 1 capture, exact rescan-free and
provider-free reopen, one-file incremental generation 2, parent linkage, and immutable historical
readability. Generation 1 used index `code_index:9731397e7880391173a90033e527b293` and snapshot
`code_index_snapshot:31c60ac8f4a12149a326fe7ff5798970`; generation 2 used index
`code_index:2ad87e8576f629e76be3f57f6cc97327` and snapshot
`code_index_snapshot:75e9de3627b21b9cdc4ee18619a8ff58`. Its 2,878-byte receipt has SHA-256
`d60b7855cf8474ab9ec85fe0b18903eb2b8513921ae554d1415cbb2a48b43594`.

The exact local-index verifier passed against the clean tBTC checkout at revision
`9651d53a443b3d2470e13ee1db0ecae60be8b246`, tracked blob
`e7e16d77c32fd23437320cede83c07db75e6f5e8`, and exact `DepositRedemption.sol` coordinate. Its
current-time receipt is SHA-256 `e594164d0c7c40ee1203e30b8afc62d0815699dd0fcaff887906879358a060e6`.

A separate fixed-time installed adversarial probe produced exactly one source-declared
`affected_code_snapshot` relation, three evidence records, and two omissions. It rejected paired
source forgery, receipt forgery, cross-wired 1999/2099 timestamps, and a mutually shifted timestamp
forgery. It retained the stable content index
`code_exact_local_index:87e0b1c57680f97df417e0c7ac132846`, exact 17,849-byte artifact SHA-256
`22ce6fd7f78e97423a495273bbea89d7d185b12318b3dd0da6449b38acbaf330`, `body_included=false`,
`semantic_scope=none`, and no dependency or impact inference. All authority flags were false. The
fixed-time receipt is SHA-256 `d3c8b3a53251e6a730226826bd00dfdc8e8570ebaa52e2027df8d976ac2e957b`.

Live source acquisition was unavailable in the restricted acceptance environment and contributes
no evidence. This gate covers only the exact bundled source and paired clean local checkout.

## Installed impact calibration

The installed MCP and REST implementations were exercised independently with zero and one observed
direct static importer. Every result retained `safe_to_delete=false` and
`deletion_safety=not_assessed`.

| Surface | Evidence basis | Zero importer wording | One importer wording |
|---|---|---|---|
| MCP | `direct_static_importers` | `NO DIRECT STATIC IMPORTERS OBSERVED`; deletion safety not assessed | `IMPACT OBSERVED` |
| REST | `direct_static_importers_and_cochange` | `NO DIRECT STATIC IMPORTERS OBSERVED`; deletion safety not assessed | `IMPACT OBSERVED`; deletion safety not assessed |

Neither structured summary nor MCP rendering claimed `SAFE` or `BREAKING`. Both exposed dynamic
import/runtime/reflection/generated-code/external-consumer uncertainty. The 6,958-byte installed
impact receipt has SHA-256 `998d1a69043d9898fb1e7faedeefc82ff1692358a0d442d48b28f3b6348b26b2`.
These mocked graph rows prove response calibration, not real downstream effect or deletion safety.

## Durable material-use archive and installed return boundary

The source-stage material-use receipt is 9,601 bytes, SHA-256
`9c5fdb78e7081865ef0e4ead53a16a1931282824e9639ab4e3a1cf7a27aa4393`, with receipt reference
`code_intelligence_material_use:ace_impact-static-import-calibration-v1`. Its durable archive is
58,505 bytes, SHA-256 `fffafe306c6cc078a178b76920f74f7712386b2029067f92161e3d6dcfe58681`.
All five declared archive members matched their exact byte counts and hashes, including the original
return receipt SHA-256 `c92d390f25d0bb3ebd0d67177cca46af3c1dd4f4c2f6a6aa78d8db7f4b3d33cd`.

The wheel packages the return contract and verifier, not the evidence archive. After extracting the
source-stage archive, the installed verifier revalidated the exact pre-change handoff and return:

- return ID: `coding_agent_return:1ecd53df9e5aed75ab71626ba2efc370`;
- handoff ID: `coding_agent_handoff:cdf20e1b0abc4ef97351803ae5a81041`;
- index ID: `code_index:3ab54b8a720b2ba056a364a8fb4925c1`;
- lens ID: `atrium_code_lens:968d98fc5a8e1091abd99823d7808c27`; and
- manifest ID: `code_context_manifest:e5211e1608efeb1a0cfb2237468650ba`.

The fresh replay receipt is time-bound and therefore intentionally has a new receipt identity. Its
4,432-byte output has SHA-256 `220effa532165118328370c534c77fc705408cd23e90338419a908255998c10d`.
It retained `chain_validated=true`, every authority flag false, execution-boundary revalidation
required, and the archived warning that three manifest blocks were not reported consumed.

An installed adversarial gate enforced the 131,072-byte pre-parse cap; summary, item-count, and
item-length bounds; extra-field rejection; false-only source/reasoning/delivery/effect claims; and
fail-closed handoff-ID, unknown-block, and out-of-scope-path validation. Its 931-byte result has
SHA-256 `3539a06934552f46d588a76b3c8a17c5bd876dc3377ea42f25d79b2c7ff33a93`.
This is a validation boundary, not sandboxing or trust isolation for a coding agent.

## Regression and governance checks

The exact staged-source matrix passed **267 tests** with four known short-test-HMAC warnings. It
covered Code API/journey/resource/continuity/incident/ownership/return/snapshot/solution behavior,
graph and MCP behavior, extension atomicity, naked kernel, and public Core boundaries. Ruff lint and
format checks passed for the touched Code/impact/return surfaces, and `git diff --check` was clean.

Before living-record edits, v1-v3 remained byte-for-byte unchanged:

| Receipt | SHA-256 |
|---|---|
| v1 | `284005cde84c9d232b4307b2574eda3e9890f042ce387a2a586b50e5ec153b53` |
| v2 | `4bdb7bcb3ccea59e130d9fd77e1a0ea2e62978010ec7ed2c7a1a7323d522691e` |
| v3 | `4b3cb2d4a772eb4682b19fe94c2f9011a84ec77dbc3359f8538a762fe1aec2ef` |

## Boundary and non-claims

This exact local receipt does not claim:

- a commit, pull request update, public-index install, signed publication, GitHub Release, or #194
  closeout;
- a deployed HTTP service, successful production journey/admission, production grant, shared
  database, browser-driven Atrium session, or externally delivered change;
- causal benefit, user/business outcome, production effect, safe deletion, or universal impact
  reasoning;
- live incident acquisition, ACE incident ownership, causality/root cause, Solidity semantics,
  dependency inference, or downstream impact from the isolated Solidity coordinate;
- model-provider trust isolation, reasoning authority, delivery authority, or effect authority;
- a second operating system, universal language support, automatic watcher, or multi-repository
  topology; or
- 1.3 compatibility, migration, update notification/UX, backup, rollback, or recovery acceptance.

The supported semantic profile remains Python/local/single-repository. The exact Solidity exercise
is a separate source-coordinate inventory profile. No artifact was committed, pushed, published, or
deployed.
