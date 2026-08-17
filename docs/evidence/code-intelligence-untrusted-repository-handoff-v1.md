# Code Intelligence — Untrusted Repository Handoff v1 — Bounded Release Evidence Record

Status: CANDIDATE — focused and stacked verification passed; independent review and clean installed-artifact verification remain release gates. The prose began as a Sonnet draft produced from a sanitized interface-only workspace; the implementation owner then reconciled it against the candidate and recorded only observed results below.

## 1. Scope

Target module: `core.engine.code_intelligence.untrusted_handoff`

In scope, exactly:

- `prepare_untrusted_repository_handoff(repository, workspace_root, *, repository_ref, query, target_path, receiver_ref, read_prefixes, read_paths=(), write_paths, policy=None) -> PreparedUntrustedRepositoryHandoff`
- `validate_untrusted_repository_return(packet, raw_return, *, validated_at=None) -> UntrustedRepositoryReturnReceiptV1Alpha1`
- Public frozen Pydantic models and stable ID properties:
  - `UntrustedRepositoryPolicyV1Alpha1`; `.policy_id`
  - `ControllerRepositoryScopeV1Alpha1(repository_ref, query, target_path, receiver_ref, read_prefixes, read_paths=(), write_paths)`; `.scope_id`
  - `UntrustedRepositoryMaterialDecisionV1Alpha1(path, git_blob_id, body_digest, byte_count, disposition, reason, recognized_secret_categories=(), body_exposed=False)`
  - `UntrustedRepositoryMaterialReceiptV1Alpha1`; `.receipt_id`
  - `UntrustedRepositoryEvidenceRoleV1Alpha1`
  - `UntrustedRepositoryHandoffV1Alpha1`; `.packet_id`
  - frozen dataclass `PreparedUntrustedRepositoryHandoff(packet, workspace_root)`
  - `UntrustedRepositoryReturnReceiptV1Alpha1`; `.receipt_id` excludes `validated_at`
- Existing public contracts consumed, unmodified:
  - `CodingAgentReturnV1Alpha1(receiver_ref, handoff_id, index_id, lens_id, manifest_id, disposition, summary, consumed_block_ids, changed_paths=(), verification_refs=(), uncertainties=(), submitted_at, claims_source_authority=False, claims_reasoning_authority=False, claims_delivery_authority=False, claims_effect_authority=False)`; `.model_dump_json()`, `.return_id`
  - Packet access surface: `packet.journey.handoff.blocks`, `.journey.handoff.receipt`, `.journey.lens.index`, `.controller_scope`, `.material_receipt.decisions`, `.permitted_write_paths`, `.delivered_read_paths`, source/filtered revisions and trees, base IDs

Out of scope: anything not named above, including any internal implementation not exposed by this public interface.

## 2. Invariants

1. Prepare delivers only immutable tracked Git HEAD blobs. Before admission, source cleanliness is proven from exact HEAD/index path-mode-blob identity plus bounded lstat-only mode, size, mtime, ctime, and untracked inventory checks; source working-tree bodies are never opened.
2. Scopes are canonical POSIX paths; write paths are exact (no globbing/expansion); all bounds below are fixed.
3. Prepare creates a clean, deterministic filtered repository at the supplied empty `workspace_root`; evidence files are materialized read-only, writable files are materialized writable.
4. Excluded categories: generated/vendor/cache paths, unsupported file types, binary/NUL content, invalid UTF-8/control-containing content, Git LFS pointers, symlinks/submodules/special modes. If an excluded path is required as a write path or as the target path, preparation blocks (fails closed) rather than silently omitting it.
5. Recognized secret material triggers whole-file exclusion; if the excluded file is required, preparation blocks. Receipts never contain secret values or file bodies.
6. Handoff bodies carry `content_role='untrusted_repository_evidence'` and cannot supply instructions or alter scope — they are evidence, not control input.
7. Return validation enforces a strict byte ceiling before strict UTF-8/JSON decoding, then applies the existing `CodingAgentReturnV1Alpha1` contract; consumed block IDs must be exact and ordered against the handoff; changed paths must be a subset of the permitted write paths.
8. No source-repository or return-payload code executes. The existing trusted Journey runs in a short-lived helper process with an allowlisted environment and a strict bounded JSON request/response.
9. The exact public MCP compatibility count remains 11 for this interface.

## 3. Limits (exact public constants)

| Constant | Value |
|---|---|
| `UNTRUSTED_TREE_ENTRY_LIMIT` | 20000 |
| `UNTRUSTED_CANDIDATE_FILE_LIMIT` | 2000 |
| `UNTRUSTED_CANDIDATE_TOTAL_BYTES_LIMIT` | 33554432 |
| `UNTRUSTED_BLOB_BYTES_LIMIT` | 500000 |
| `UNTRUSTED_PATH_BYTES_LIMIT` | 1024 |
| `UNTRUSTED_PATH_DEPTH_LIMIT` | 32 |
| `UNTRUSTED_PATH_SEGMENT_BYTES_LIMIT` | 255 |
| `UNTRUSTED_CONTEXT_FILE_LIMIT` | 8 |
| `UNTRUSTED_CONTEXT_BYTES_LIMIT` | 24000 |
| `UNTRUSTED_RETURN_JSON_BYTES_LIMIT` | 131072 |

All limits are fixed and public; no runtime override is exposed by this interface.

## 4. Ownership

One owner per draft target, as specified:

| Draft target | Owner responsibility |
|---|---|
| `verify_code_intelligence_untrusted_handoff.py` | Deterministic local fixture verifier: sorted, body-free JSON output; no provider/network/DB access |
| `test_code_intelligence_untrusted_handoff.py` | Pytest matrix derived from the public behavior contract |
| `code-intelligence-untrusted-repository-handoff-v1.md` | This evidence record |

Each target has exactly one named owner file; no shared or overlapping ownership is defined by this record.

## 5. Secret policy

- Recognized secret material causes whole-file exclusion at prepare time.
- If a file carrying recognized secret material is required (as a write path or as the target path), preparation blocks rather than proceeding with a partial or redacted copy.
- `UntrustedRepositoryMaterialDecisionV1Alpha1` records `recognized_secret_categories` and `body_exposed` flags, but never the underlying secret value.
- Receipts (`UntrustedRepositoryMaterialReceiptV1Alpha1`, decisions) never contain values or file bodies — only path, blob ID, digest, byte count, disposition, reason, and category/exposure metadata.

## 6. Deterministic workspace

- Source delivery reads are restricted to immutable, clean, tracked Git HEAD blobs.
- Source cleanliness uses exact HEAD/index identity and lstat-only metadata/inventory checks; working-tree bodies are not opened. Missing or mismatched index stat evidence rejects conservatively.
- Prepare materializes a clean, deterministic filtered repository at the caller-supplied empty `workspace_root`.
- Evidence files are written read-only in the workspace; permitted write-path files are written writable.
- The existing Journey executes only in an isolated `python -I` helper whose environment disables global/system Git config and attributes, empties HOME/XDG/TMP, fixes locale/time/hash inputs, omits inherited credential/proxy/provider variables, and returns strict bounded JSON with an asserted module origin.
- Given the same source HEAD, scope, and policy, workspace construction is deterministic.

## 7. Evidence roles

- `UntrustedRepositoryEvidenceRoleV1Alpha1` labels handoff bodies as evidence and binds both the admitted whole-file digest and the exact delivered block digest.
- Labeled content role: `content_role='untrusted_repository_evidence'`.
- Evidence-labeled content cannot supply instructions to the receiver and cannot alter the controller-defined scope (`ControllerRepositoryScopeV1Alpha1`). It is inert with respect to control flow.

## 8. Strict return

- `validate_untrusted_repository_return` enforces `UNTRUSTED_RETURN_JSON_BYTES_LIMIT` (131072 bytes) as a hard ceiling on `raw_return` before any decoding is attempted.
- Decoding is strict UTF-8, then strict JSON; malformed input at either stage is rejected.
- The decoded payload is then validated against the existing `CodingAgentReturnV1Alpha1` contract.
- `consumed_block_ids` must exactly and in-order equal the handoff's blocks.
- `changed_paths` must be a subset of `permitted_write_paths` from the packet's controller scope.
- Output is `UntrustedRepositoryReturnReceiptV1Alpha1`; it records the actual settled base receipt identity, while its replay-stable outer `.receipt_id` excludes validation-time/base-receipt volatility and remains bound to the exact packet and returned material identities.

## 9. No persistence

- Neither `prepare_untrusted_repository_handoff` nor `validate_untrusted_repository_return` persists state beyond the caller-supplied `workspace_root`, and neither executes any code from the source repository or the return payload. Preparation executes only the installed trusted Journey helper described above.
- No database, network, or external provider I/O is part of this interface's contract.

## 10. Exact-11 expectation

- The public MCP compatibility count for this interface is expected to remain exactly **11** after this change.
- This expectation is a release gate: any deviation (increase or decrease) in the public MCP-exposed count must be treated as a contract change requiring explicit re-review, not a passive update to this record.

## 11. Verification table

Observed candidate evidence: the repaired focused prevention suite passed **78 tests**; the settled stacked Code Intelligence, API, graph, snapshot/resource-plane, public-boundary, kernel, and MCP suites passed **255 tests** with four pre-existing short-key warnings; the deterministic source verifier passed with exact public MCP count **11**, zero provider/network/persistence calls, zero host-Git-customization markers, and three negative-return checks. Two fresh verifier processes emitted byte-identical JSON. Independent review remains mandatory rather than being inferred from implementation text.

| # | Verification item | Method | Result |
|---|---|---|---|
| 1 | Prepare rejects dirty/staged/deleted/untracked source state through HEAD/index identity plus lstat-only metadata/inventory checks without opening working-tree bodies | `test_code_intelligence_untrusted_handoff.py` | pass |
| 2 | Prepare delivers only immutable tracked Git HEAD blobs; isolated Journey ignores repository/host Git filter, diff, fsmonitor, credential, hook, template, and provider/proxy environment customization | focused tests + source verifier | pass |
| 3 | Canonical POSIX scope normalization and exact (non-glob) write paths | focused tests | pass |
| 4 | All 10 public limit constants fixed at stated exact values | focused tests + source verifier | pass |
| 5 | Deterministic filtered workspace construction at supplied empty `workspace_root` | source verifier | pass |
| 6 | Evidence files materialized read-only; write-path files materialized writable | focused tests | pass |
| 7 | Generated/vendor/cache/unsupported/binary/NUL/invalid-UTF-8/control/LF-or-CRLF-LFS/symlink/submodule/special-mode exclusion | focused tests | pass for candidate fixtures |
| 8 | Preparation blocks when an excluded path is required as write/target path, without reading generated/vendor bodies | focused tests | pass |
| 9 | Recognized-secret whole-file exclusion; blocks when secret file or controller/return metadata is required | focused tests + source verifier | pass for recognized fixtures |
| 10 | Receipts never contain recognized secret values or file bodies | focused tests + source verifier | pass for recognized fixtures |
| 11 | Handoff bodies labeled `content_role='untrusted_repository_evidence'` | focused tests | pass |
| 12 | Evidence-labeled content cannot alter controller scope or authority flags | focused tests | pass |
| 13 | Return payload rejected above 131072 bytes before decode | focused tests + source verifier | pass |
| 14 | Return payload requires strict UTF-8 then strict JSON decoding | focused tests | pass |
| 15 | `consumed_block_ids` equals the exact ordered handoff blocks | focused tests | pass |
| 16 | `changed_paths` is a subset of `permitted_write_paths` | focused tests + source verifier | pass |
| 17 | No persistence beyond `workspace_root`; no source/return execution | dependency inspection + source verifier | pass for bounded verifier |
| 18 | Actual settled base receipt is recorded while outer return `.receipt_id` is stable across validation time | focused replay test | pass |
| 19 | Stable IDs replay across exact serialization, fresh workspace paths, and byte-identical clones | focused replay/cross-clone tests + verifier replay | pass |
| 20 | Exact public MCP compatibility count remains 11 | focused test + source verifier + stacked suite | pass |

## 12. Explicit nonclaims

This record makes no claim beyond the authored interface. Specifically, it does **not** claim:

1. That recognized secret patterns are exhaustive.
2. That there is a semantic prompt-injection detector or any universal resistance to prompt injection.
3. That any cryptographic isolation is provided between controller and untrusted material.
4. That any automatic admission of untrusted material or return content occurs.
5. That any authority (source, reasoning, delivery, or effect) is granted by this interface — `claims_source_authority`, `claims_reasoning_authority`, `claims_delivery_authority`, and `claims_effect_authority` on `CodingAgentReturnV1Alpha1` default to `False` and are not asserted by this record.
6. That this record constitutes production or deployment evidence of any kind.

## 13. Independent-review gate

This record is bounded and non-final. Release is blocked until all of the following hold:

- Every row in the verification table (Section 11) has been executed against real fixtures by `verify_code_intelligence_untrusted_handoff.py` and/or `test_code_intelligence_untrusted_handoff.py`, and its result updated from `pending` to an actual pass/fail outcome.
- The verification run and this record are reviewed by an owner independent of whoever drafted this record and independent of whoever authored the implementation.
- The exact-11 MCP compatibility count (Section 10) is independently re-counted and confirmed, not merely re-asserted.
- No verification item is marked passing based on this record's own restatement of the contract; passing requires actual execution evidence.

Until this gate passes, this document is candidate evidence, not release acceptance.
