# Code Intelligence incident admission boundary v1

**Status:** local, non-live Slice 5 candidate assembled at
`/private/tmp/ace-code-slice5.d05bf` on top of the accepted Slices 1-4 parent
(base revision `d05bf099977a975721cea787b41069ea0c383147`); independently
reviewable implementation candidate, not wired into the live repository
journey, not staged, committed, pushed, or published, and carries no
dependency/impact/causality/authority claim.

**Milestone:** ACE Core 1.1 Code Intelligence (#194)

**Recorded:** 2026-08-14; candidate verification rerun 2026-08-16

## Decision

The ACE repository itself still does not contain an honest canonical ACE incident or postmortem
source. A separately researched, immutable, MIT-licensed Keep/tBTC report now supplies the first
bounded public acceptance source. The independent projector emits exactly one
`affected_code_snapshot` relation declared by that report and explicitly omits a timeline-only
section that repeats the runtime error but declares no code coordinate. Generic errors, failed
verification, comments, lexical similarity, and Git proximity remain inadmissible incident
evidence.

This remains an admission boundary, not an incident ontology or provider policy for Core. The Code
contract and projector live in `core.engine.code_intelligence.incidents`; the only import of the
neutral public Core source contract is the narrow host seam
`core.engine.code_intelligence.incident_source`. The packet is not composed into
`CodeIntelligenceJourney`, Atrium, the API, MCP, or coding-agent handoff yet.

## Repository audit and exact evidence anchors

The audit covered repository filenames and tracked content containing `incident`, `postmortem`,
`post-mortem`, `outage`, `root cause`, and failure-record terms; the relevant schemas and readers;
and Git history messages across local refs. It found no tracked canonical incident/postmortem record
and no matching history record. The concrete near-matches establish why the gap cannot be filled by
inference:

| Candidate | Exact repository evidence | Admission decision |
| --- | --- | --- |
| In-memory error buffer | [`core/engine/core/error_buffer.py`](../../core/engine/core/error_buffer.py#L1-L6) calls the buffer lightweight on-call visibility and explicitly says it is not persistent audit logging. Its fields are exception telemetry (`timestamp`, `cid`, `source`, `error_type`, `message`, optional context), not incident identity, status, impact, declared code coordinates, or an immutable source receipt ([lines 21-54](../../core/engine/core/error_buffer.py#L21-L54)). | Reject as an incident source. An exception occurrence does not establish an incident. |
| Failure memory table | [`core/schema/v067_failure_memory.surql`](../../core/schema/v067_failure_memory.surql#L1-L17) defines Reflexion-style memory for failed or partial VerificationGate gaps. The writer only admits non-clean verification verdicts with gaps and stores task summary, gaps, verdict, confidence, and repeat status ([`executor.py` lines 234-283](../../core/engine/orchestration/executor.py#L234-L283)). | Reject as an incident source. A quality/verification failure is not an operational incident or postmortem. |
| Tests, synthetic outage data, and comments | These materials exist to reproduce behavior or exercise failure handling. They lack an acquisition receipt and canonical incident identity, and their prose is not a declared source-to-code relation. | Keep as test or regression evidence only. Never project an incident from them. |
| Current Code Intelligence contract | `CodeArtifactKind` reserves the `incident` kind ([`contracts.py` lines 47-59](../../core/engine/code_intelligence/contracts.py#L47-L59)), but no current journey path constructs such a node. The journey explicitly records that no declared incident source is connected ([`journey.py` lines 302-307](../../core/engine/code_intelligence/journey.py#L302-L307)). | Preserve the explicit omission. A reserved vocabulary value is not evidence that an incident exists. |

## Existing neutral seam to reuse

No new source-acquisition mechanism is required in Core.

[`CanonicalSourceSnapshotV1Alpha1`](../../ace/core/source.py#L244-L262) already binds a source
definition, URI, canonical payload and digest, source/event/observation clocks, locator, acquisition
mode, and acquisition receipt without implied authority. Its validation derives the immutable
snapshot identity from exact material and rejects payload or identity mismatch
([lines 313-367](../../ace/core/source.py#L313-L367)).

The governed ingress seam already passes a closed, credential-free, exact adapter request with
bounded payload size and an exact adapter artifact
([`SourceAdapterCaptureRequestV1Alpha1`](../../ace/intelligence/contracts/source_acquisition.py#L155-L223)).
Its inert result binds the request, URI, payload digest, locator, clocks, network safeguards, and
content-derived capture identity while carrying no authority
([`CapturedSourceMaterialV1Alpha1` lines 226-285](../../ace/intelligence/contracts/source_acquisition.py#L226-L285)).

The implemented host seam reads the packaged fixture from a fixed package resource, reconstructs
and validates `CanonicalSourceSnapshotV1Alpha1` even when handed a caller-created model copy, then
narrows it into the Code-owned `IncidentSourceEnvelopeV1Alpha1`. The envelope independently
requires Core-canonical JSON spelling, reconstructs the snapshot identity from all canonical
material, and exact-binds the source definition, report URI, source/event clocks, locator, mode,
and receipt. Its `acquisition_mode = prepared_fixture` and deterministic local
`acquisition_receipt_ref`/digest identify only local prepared-fixture construction. They do **not**
prove a live external fetch, governed adapter delivery, freshness, or source authority. A later
live source-specific adapter may use the governed ingress seam, but provider names, severity
taxonomies, escalation policy, and incident workflow nouns still must not move into Core.

## Bounded provider-neutral projection contract

The implemented `IncidentToCodeProjectionV1Alpha1` binds:

- the `source_snapshot_ref`/digest pair and exact frozen `acquisition_receipt_ref`/digest carried
  from the neutral prepared source snapshot;
- the report commit, Git blob, whole-report SHA-256, publication clock, exact source spans, and UTC
  incident clocks;
- the separately verified code revision, path, symbol, line span, Git blob, whole-file SHA-256, and
  exact span digest;
- one source-declared `affected_code_snapshot` relation whose evidence binds report line 45 and code
  lines 326–355;
- deterministic incident, coordinate, evidence, relation, and projection identities;
- explicit omissions for the coordinate-free timeline and separately discussed historical change;
- literal provider-neutral/read-only declarations, prepared-fixture disclosure, live-fetch and
  governed-delivery negatives, and source/reasoning/change/approval/delivery/execution/effect
  authority negatives.

The relation describes only what the captured source declares; it does not prove causal truth. The
report separately discusses revision `71361a51c220536d82681f1ab77ed640836329ce` under “How The Code
Landed.” The packet records that reference only as non-projected context. It never calls it causal,
never emits `introduced_by`, and never conflates it with the affected source snapshot
`9651d53a443b3d2470e13ee1db0ecae60be8b246`.

The projector revalidates the narrowed source envelope, canonical payload digest, frozen fixture
schema, qualified report identity, URLs, title, licenses, clocks, spans, non-projected context, and
the separate code artifact/span identity. It also revalidates deserialized projection graphs:
content-derived IDs, unique bounded collections, exact source/target/evidence/omission cross-links,
and internal snapshot-reference consistency must close before the result is structurally accepted.
A standalone projection is structurally self-validating but is not source-authenticating: it
declares `source_snapshot_revalidation_required = true` and
`self_authenticates_source_snapshot = false`. Callers must use
`validate_incident_projection_against_source` with the strictly validated source envelope before
using snapshot lineage; that paired check rejects a mutually consistent forged snapshot ref/digest
and evidence chain. A separate
[local-index binding candidate](code-intelligence-incident-local-index-binding-v1.md) now closes the
exact public coordinate against a clean revision-pinned checkout while preserving Solidity as
inventory-only. Live-journey composition remains a later, separately reviewed step.

## Required immutable public acceptance fixture

The packaged fixture is
[`tbtc_deposit_pause_2020_v1.json`](../../core/engine/code_intelligence/fixtures/tbtc_deposit_pause_2020_v1.json).
It freezes the following independently verified material:

| Material | Immutable evidence |
| --- | --- |
| Report | [`keep-network/tbtc-website@083c6216…`](https://github.com/keep-network/tbtc-website/blob/083c62168e470e466e9d701fb48242eef254d7b5/src/pages/news/2020-05-21-details-of-the-tbtc-deposit-pause-on-may-18-2020.md), Git blob `693535acb820c7b8347c4e1bf3bccc81414b01c8`, 20,336 bytes, raw SHA-256 `9f105c2a56cae01b16e27625dee1b6c2d32a5f9dae71225bb0c0fb4a659a6a72` |
| Declared affected-code snapshot | [`keep-network/tbtc@9651d53…/solidity/contracts/deposit/DepositRedemption.sol#L326-L355`](https://github.com/keep-network/tbtc/blob/9651d53a443b3d2470e13ee1db0ecae60be8b246/solidity/contracts/deposit/DepositRedemption.sol#L326-L355), symbol `redemptionTransactionChecks`, Git blob `e7e16d77c32fd23437320cede83c07db75e6f5e8`, 17,849 bytes, raw whole-file SHA-256 `22ce6fd7f78e97423a495273bbea89d7d185b12318b3dd0da6449b38acbaf330` |
| Report license | [MIT at the report revision](https://github.com/keep-network/tbtc-website/blob/083c62168e470e466e9d701fb48242eef254d7b5/LICENSE), blob `4ed19fdb…`, 1,054 bytes, SHA-256 `be587dab…`, `Copyright (c) 2020 Keep SEZC.` |
| Code license | [MIT at the code revision](https://github.com/keep-network/tbtc/blob/9651d53a443b3d2470e13ee1db0ecae60be8b246/LICENSE), blob `80a1ed24…`, 1,053 bytes, SHA-256 `59f67a2e…`, `Copyright (c) 2020 Keep SEZC.` |

The fixture must contain at least two independently checkable records or sections:

1. Report line 45 declares the exact revision/path/symbol/line coordinate above.
2. Report lines 21–39 are a timeline-only negative. They include the same runtime error text but no
   repository coordinate.

Only the first produces the typed edge. The second produces
`no_source_declared_code_coordinate`; lexical matching is explicitly false as a causality basis.

The fixture is package data in the source tree and installed wheel. It is immutable test evidence,
not a claim that ACE fetched or admitted a live current incident source.

## Fail-closed acceptance cases

[`tests/test_code_intelligence_incidents.py`](../../tests/test_code_intelligence_incidents.py)
independently demonstrates:

- tampered or non-canonical payload spelling, snapshot ref/digest, source definition, locator,
  acquisition receipt ref/digest, or canonical snapshot model copy is rejected;
- missing or malformed incident identity or source locator is rejected;
- a repository mismatch, revision mismatch, absolute/traversal path, missing path, or missing named
  symbol creates no edge and records the exact rejection;
- duplicate identical material is deterministic and idempotent, while one identity naming
  conflicting material is rejected;
- a generic `error_buffer` entry and a `failure_memory` row cannot validate as incident input;
- test text, comments, stack traces, and model-written root-cause prose cannot create an incident
  node or code edge without the canonical incident source chain;
- undeclared relations and lexical-only matches create no edge;
- incident-count, coordinate-count, payload, and output bounds are enforced before projection;
- repeated projection of exact material preserves deterministic projection and evidence identities;
- package-resource access retains the fixture and its verified report/code digests;
- self-consistent forged report/code excerpts, cross-host URLs, and recomputed digests are rejected;
- deserialized output with forged IDs, evidence URIs, cross-links, omission refs, duplicates, or
  collection-bound violations is rejected;
- a mutually consistent forged snapshot lineage is rejected by mandatory paired source
  revalidation; the standalone output contract explicitly does not claim to authenticate it;
- live acquisition is refused by this prepared-fixture seam.

Fresh-process/live repository-index revalidation and degraded runtime composition are intentionally
deferred because this packet is not wired into the live journey.

## Authority and product-boundary negatives

Every projection and handoff must declare:

- `provider_neutral = true`;
- `read_only = true`;
- `source_authority = false`;
- `reasoning_authority = false`;
- `change_authority = false`;
- `approval_authority = false`;
- `delivery_authority = false`;
- `execution_authority = false`;
- `effect_authority = false`;
- source, index, and repository revalidation are required before later use.

The adapter reports captured source material; it does not decide incident truth. The projector
reports declared source-to-code connections; it does not decide root cause, remediation priority,
safe deletion, ownership, deployment, or effect. A coding agent receiving the projection gains no
permission to edit, execute, deliver, or claim effect.

## Verification and next dispatch

Local verification on 2026-08-14 (reviewed source, prior to Slice 5 assembly):

- `49 passed in 0.79s` in the focused incident packet;
- `83 passed in 9.02s` across the incident packet, existing Code journey, ownership, snapshot-store,
  and public-Core boundary suites.

Local candidate verification rerun on 2026-08-16 against this assembled Slice 5 candidate
(`/private/tmp/ace-code-slice5.d05bf`):

- `76 passed` in the focused incident + public-Core-boundary lane
  (`tests/test_code_intelligence_incidents.py`, `tests/test_code_intelligence_incident_index_binding.py`,
  `tests/test_public_core_boundaries.py`);
- `533 passed` in the full settled Slices 1-4 19-file stacked lane plus the two incident test files
  (466 of those are the unchanged parent tests, individually reconfirmed by running the 19-file lane
  alone);
- Ruff check and `ruff format --check` passed clean on all 9 Python files in the Slice 5 packet;
  `git diff --check` clean on every tracked modification and every new file;
- [`scripts/verify_code_incident_local_index_binding.py`](../../scripts/verify_code_incident_local_index_binding.py)
  ran fully offline against the retained clean pinned checkout `/tmp/ace-tbtc-binding.aLmMuk`
  (`HEAD` = `9651d53a443b3d2470e13ee1db0ecae60be8b246`, working tree clean) and produced a receipt with
  `semantic_scope = "none"` and every authority flag `false`;
- a fresh wheel was built from a disposable copy of this candidate and installed offline into a
  fresh Python 3.12 target outside the checkout; importing only from installed `site-packages`,
  installed-only acceptance passed 23/23 checks covering module and entry-point origins, the exact
  11-tool surface, the explicit-network verifier's `--help`, no-argument-default, and unknown-flag
  offline paths, one exact `affected_code_snapshot` relation and its two explicit omissions, paired
  source and pinned local-index validation, `semantic_scope = "none"`, and three rejected tamper
  attempts (forged projection digest, wrong repository path, forged receipt `semantic_scope`);
- the exact wheel identity used for this installed-only acceptance pass (byte count, SHA-256, and
  per-entry `RECORD` verification) is not reproduced here: a packaged design note cannot truthfully
  embed the hash of the wheel that contains it without self-reference, so that identity is recorded
  only in the external local acceptance receipt/logs for this run, not in this file;
- [`scripts/verify_code_incident_fixture.py`](../../scripts/verify_code_incident_fixture.py) was
  **not** deliberately rerun as accepted acceptance evidence for this candidate: the script gates its
  four revision-pinned `raw.githubusercontent.com` reads behind an explicit `--allow-network` CLI
  opt-in (`--help` and the no-argument default both exit without touching the network), and that
  opt-in was not exercised for this candidate. Its historical 2026-08-14 result above is carried only
  as prior context from an earlier, accidental invocation before this gate existed — it is not a claim
  about this candidate, and remote verification was not rerun here.

These are local pre-publication verification results for this specific, non-live candidate. They
prove artifact identity, packaging, and deterministic prepared-fixture execution for this checkout;
they are not a clean-release build receipt, live source acquisition receipt, governed adapter
delivery receipt, or live Atrium journey result, and this candidate has not been staged, committed,
pushed, or published.

1. Review this packet independently before changing the existing live-journey omission.
2. Independently review the separate exact local-index binding candidate and retain its explicit
   Solidity semantic/dependency/impact negatives; do not silently treat the external code as
   ACE-local or Python-profile code.
3. Only after that review, compose bounded incident nodes/edges and omissions into Atrium and the
   coding-agent handoff. Preserve every authority negative and revalidate source/index identity.
