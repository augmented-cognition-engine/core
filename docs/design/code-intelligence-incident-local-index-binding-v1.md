# Code Intelligence incident local-index binding v1

**Status:** local, non-live Slice 5 candidate assembled at
`/private/tmp/ace-code-slice5.d05bf` on top of the accepted Slices 1-4 parent
(base revision `d05bf099977a975721cea787b41069ea0c383147`); independently
reviewable implementation candidate, not wired into the live journey, not
staged, committed, pushed, or published.

**Milestone:** ACE Core 1.1 Code Intelligence (#194)

**Recorded:** 2026-08-14; candidate verification rerun 2026-08-16

## Decision

Bind the independently reviewed Keep/tBTC incident projection to one exact, clean, local checkout
of the report-declared affected code revision before any Atrium, API, MCP, journey, or coding-agent
composition. The binding inventories one Solidity file and one source-declared symbol span. It does
not parse Solidity, construct dependency edges, infer downstream impact, or claim causality.

The existing Code Intelligence repository index is intentionally not widened for this packet.
`RepositoryIndexIdentityV1Alpha1`, the phase-one graph, and the durable snapshot store identify the
supported profile as `python-local-static-v1`; Solidity is not in that semantic language matrix.
Treating the public `.sol` coordinate as though it had Python-equivalent dependency or impact
coverage would be an unsupported claim. This separate Code-owned profile is therefore
`exact-source-coordinate-inventory-v1`, with `observed_languages = ("solidity",)` and
`semantic_languages = ()`.

No incident nouns or product policy move into public Core. The existing neutral source snapshot is
only an input to the Code-owned incident projector and paired validator. The local index, snapshot,
and binding receipt remain under `core.engine.code_intelligence`.

## Exact admitted coordinate

The only accepted target is:

| Field | Exact value |
| --- | --- |
| Repository | `https://github.com/keep-network/tbtc` |
| Revision | `9651d53a443b3d2470e13ee1db0ecae60be8b246` |
| Path | `solidity/contracts/deposit/DepositRedemption.sol` |
| Symbol | `redemptionTransactionChecks` |
| Lines | 326–355, 1-based inclusive |
| Git blob | `e7e16d77c32fd23437320cede83c07db75e6f5e8` |
| Raw bytes | 17,849 |
| Whole-file SHA-256 | `22ce6fd7f78e97423a495273bbea89d7d185b12318b3dd0da6449b38acbaf330` |
| Span SHA-256 | `8dcc8a65e144e04de894826c9b7777430570265f175198a0b687d6652c50d172` |

The span convention is UTF-8 `splitlines()`, 1-based inclusive selection, joined by literal `\n`,
with no terminal newline in the span digest. The packaged `.b64` resource decodes to the exact raw
source bytes because the upstream file itself has no terminal newline. The exact upstream MIT
license is distributed through
[`LICENSE.keep-network-tbtc-9651d53-MIT`](../../LICENSE.keep-network-tbtc-9651d53-MIT):
Git blob `80a1ed24975b0263f29157a7bc788d9e30ab2adf`, 1,053 bytes, raw SHA-256
`59f67a2ea030f1fcbfd4f5ffd0aae8b65f66954e5aa0fdd5b745c4ac9eba6fb9`. It is included by the
standard project `license-files` metadata and accompanied by the Keep SEZC/MIT entry in `NOTICE`,
so wheels preserve the upstream permission notice alongside ACE's own license. The existing
incident fixture also records the immutable raw URL and license anchor. Packaging these bytes does
not imply a live fetch or governed adapter delivery.

## Contract and revalidation boundary

[`incident_index_binding.py`](../../core/engine/code_intelligence/incident_index_binding.py)
provides four body-free contracts:

- `ExactCoordinateArtifactV1Alpha1` records the exact path, language, symbol, line bounds, byte
  count, whole-file digest, Git blob, and span digest without source contents;
- `ExactLocalRepositoryIndexV1Alpha1` records the canonical repository URL, exact revision, clean
  tree, isolated inventory profile, topology, and observed/semantic language matrices. Its ID and
  digest are stable content identities and intentionally exclude `generated_at`;
- `ExactLocalRepositorySnapshotV1Alpha1` closes the index, artifact, and exact UTC capture time
  while declaring that repository revalidation is required and semantic/dependency/impact analysis
  did not occur. `index.generated_at` must equal `captured_at`, and both timestamps participate in
  the snapshot ID/digest;
- `IncidentLocalIndexBindingReceiptV1Alpha1` closes the validated source snapshot, incident
  projection, relation, coordinate, artifact, index, and repository-snapshot identities and
  digests. It includes no report or source body.

Capture reads the exact Git identity before file inspection and again after the tracked blob,
whole-file bytes, decoded span, and symbol declaration are checked. The identities must be equal,
so a HEAD, dirty-state, or remote mutation observed between those samples fails closed. The
snapshot remains explicitly revalidation-required because no local filesystem read can prevent a
concurrent change after its final sample. Capture rejects
more than one remote or remote URL, credentials or non-GitHub URL aliases, a different worktree
root, wrong revision, dirty/untracked content, missing/untracked/non-regular files, symlinks,
traversal, path escape, size overflow, a mismatched Git blob or digest, non-UTF-8 content, absent or
ambiguous symbol declarations, and incorrect span bounds or bytes.

The content-level index and artifact IDs remain stable when the same bytes are captured again. The
snapshot and binding receipt are intentionally capture-specific: shifting a mutually consistent
pair of timestamps changes the snapshot ID/digest and invalidates an earlier receipt, while a
cross-wired `generated_at`/`captured_at` pair is schema-invalid. This preserves deduplication at the
content layer without allowing capture-time provenance to be rewritten under a stable receipt.

Binding first calls `validate_incident_projection_against_source`; a structurally valid standalone
projection cannot establish source authenticity. It then re-scans the current checkout and closes
the exact projection coordinate against the local snapshot. Restart or deserialization callers
must use `validate_incident_local_index_binding` with the receipt, validated source envelope,
projection, snapshot, and current repository path. That paired validator repeats both source and
repository checks and the projection-to-snapshot crosswire predicate. Mutually consistent forged
snapshot/receipt inputs cannot be promoted into a valid binding.

The receipt is structurally body-free but does not self-authenticate the repository snapshot:
`repository_revalidation_required = true` and
`self_authenticates_repository_snapshot = false`. It is valid only while the exact local checkout
and the paired source chain still revalidate.

## Semantic and authority negatives

The snapshot and receipt make these limitations machine-readable:

- `semantic_analysis_performed = false` on the repository snapshot;
- `semantic_scope = "none"` on the binding receipt;
- `dependency_inference_performed = false`;
- `impact_inference_performed = false`;
- `body_included = false`;
- `provider_neutral = true` and `read_only = true`; and
- source, reasoning, change, approval, delivery, execution, and effect authority are all false.

The incident relation remains exactly `affected_code_snapshot`. It is not `introduced_by`, root
cause, remediation, downstream impact, or proof of causality. Revision `71361a51…`, separately
discussed by the report, is not the local index target and is not projected as a cause.

## Fail-closed acceptance

[`test_code_intelligence_incident_index_binding.py`](../../tests/test_code_intelligence_incident_index_binding.py)
covers the exact happy path, stable content identities, time-bound snapshot/receipt identities,
1999/2099 cross-wired timestamps, mutually shifted timestamp tampering, JSON restart,
body and authority negatives, wrong repository URL/revision/dirty state, a late Git-identity race,
missing files, changed bytes, symlinks, traversal, missing symbols, changed spans, unpaired source
lineage, cross-wired snapshots and receipts, schema-impossible semantic/impact claims, and packaged
artifact identity. Tests use a byte-exact synthetic Git checkout with only the Git identity seam
controlled; a separate acceptance run uses the real pinned upstream checkout.

## Candidate verification (2026-08-16)

Local candidate verification against this assembled Slice 5 candidate
(`/private/tmp/ace-code-slice5.d05bf`):

- `tests/test_code_intelligence_incident_index_binding.py` passed as part of a 76-test focused lane
  and a 533-test full stacked lane (466 unchanged parent tests + this packet's 67 incident tests);
- [`scripts/verify_code_incident_local_index_binding.py`](../../scripts/verify_code_incident_local_index_binding.py)
  ran fully offline (no network import) against the retained clean pinned checkout
  `/tmp/ace-tbtc-binding.aLmMuk`, confirmed `HEAD` = `9651d53a443b3d2470e13ee1db0ecae60be8b246` with a
  clean working tree, and produced a receipt with `semantic_scope = "none"`,
  `dependency_inference_performed = false`, `impact_inference_performed = false`, and every authority
  flag `false`;
- a wheel built from a disposable copy of this candidate was installed offline into a fresh Python
  3.12 environment outside the checkout; importing only from installed `site-packages`, installed-only
  acceptance passed 23/23 checks covering module and entry-point origins, the exact 11-tool surface,
  the explicit-network verifier's `--help`, no-argument-default, and unknown-flag offline paths, one
  exact `affected_code_snapshot` relation and its two explicit omissions, paired source and pinned
  local-index validation, `semantic_scope = "none"`, and three rejected tamper attempts (forged
  projection digest, wrong repository path, forged receipt `semantic_scope`), each raising
  `IncidentProjectionError` / `IncidentIndexBindingError`;
- the exact wheel identity used for this installed-only acceptance pass (byte count, SHA-256, and
  per-entry `RECORD` verification) is not reproduced here: a packaged design note cannot truthfully
  embed the hash of the wheel that contains it without self-reference, so that identity is recorded
  only in the external local acceptance receipt/logs for this run, not in this file.

This candidate did not use network access for local-index binding verification. It is a local,
non-live result for this checkout only; it is not a clean-release build receipt and not a live
Atrium/API/MCP journey result.

## Integration stop boundary and next dispatch

This packet does not change the existing live journey's `incident_source_unconnected` omission. It
does not add an API route, Atrium node, MCP tool, handoff block, database record, checkout manager,
network adapter, Solidity parser, or generalized external-repository index.

After independent review, the next dispatch may compose this validated external incident binding
into the bounded Code lens and handoff. That dispatch must retain the original source omissions,
repeat paired source and repository revalidation at use time, describe Solidity as exact coordinate
inventory only, and preserve every authority negative.
