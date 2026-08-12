# Agent Memory AM0 threat model and control traceability v1

**Status:** contract-level controls and acceptance mapping; runtime mitigation remains milestone-scoped
**Date:** 2026-08-11
**Fixture:** [`agent_memory_am0_contract_v1.json`](../../evaluations/fixtures/agent_memory_am0_contract_v1.json)

## Claim boundary

This record shows that AM0 freezes fail-closed contracts, ownership, ports, and executable fixtures
for the listed threats. It does not claim that AM1-AM9 runtime paths, SurrealDB projections,
connectors, caches, monitors, or erasure jobs already implement those controls. A passing AM0 test
proves the contract boundary only.

## Control-to-test traceability

| Threat | AM0 control | Executable evidence | Runtime owner / residual work |
|---|---|---|---|
| Memory poisoning and repeated claims | Captured/model material remains `proposed`; repetition cannot mint grants, approval, confidence, or accepted state | `test_repetition_and_prompt_text_cannot_mint_instruction_authority`; `test_model_output_remains_a_proposal_without_reconciliation_authority` | AM2 reconciliation and AM5 governed evolution must preserve this boundary in storage and feedback loops |
| Prompt injection | Instruction-policy assertions require the same resolved product-scoped authority and approval as any accepted assertion; source text is inert | `test_repetition_and_prompt_text_cannot_mint_instruction_authority`; `test_accepted_assertion_requires_exact_product_scoped_approval_and_grant` | AM1 adapters and AM3 context composition must keep source text outside the authenticated policy channel |
| Scope laundering | Core scope is strict, deterministic, host supplied, and rejects captured extra authority fields | `test_scope_is_deterministic_and_rejects_content_supplied_authority_fields`; `test_trace_negative_cases_fail_closed_or_remain_explicitly_degraded` | AM1 admission must ignore payload-claimed product, principal, session, visibility, and retention values |
| Cross-product or cross-principal leakage | Exact product-scoped grants/approvals are required; Candidate Receipts bind the opaque Core authorization-filter receipt and lifecycle snapshot used before ranking; product-scoped reads do not disclose foreign records | `test_accepted_assertion_requires_exact_product_scoped_approval_and_grant`; `test_product_scope_is_required_to_reopen_a_record`; repeat/later-session product trace | AM3 retrieval, graph traversal, and every cache/index adapter must implement and verify those pre-ranking receipts |
| Identity collision or divergent replay | IDs derive from exact canonical material; exact replay is stable and conflicting material cannot silently replace it | `test_source_span_identity_is_deterministic_and_content_derived`; `test_existing_core_store_preserves_exact_agent_memory_replay` | AM1 must add adapter-normalization and divergent-coordinate fixtures across at least two source adapters |
| Unknown-value fabrication | Knowledge/world time and unavailable spans use explicit tagged forms; fabricated clock or locator values fail validation | `test_unknown_times_stay_unknown_and_cannot_carry_fabricated_values`; `test_unavailable_span_is_explicit_instead_of_inventing_a_locator` | AM1/AM2 adapters must never default missing canonical time to ingestion time or `now` |
| Graph contamination | Semantic assertions, reconciliation, reflection, consolidation, and rank changes remain reviewable proposals; projection ports are rebuildable and non-authoritative | `test_reconciliation_is_a_proposal_with_evidence_not_a_state_mutation`; `test_evolution_output_is_only_a_reviewable_proposal`; import-boundary suite | AM2/AM3 must preserve epistemic state on nodes/edges and filter before traversal |
| Stale reuse or stale cache | Candidate Receipts disclose degraded signals/omissions; the frozen trace rejects stale cache reuse and selects the authorized correction | `test_repeat_briefing_trace_preserves_correction_manifest_and_i3_lineage`; product-trace degraded-receipt case | AM3 must key and revalidate cache dependencies for source, authority, policy, index, correction, and time revisions |
| Self-reinforcement | Retrieval and feedback do not activate belief or rank policy; feedback creates only an evolution proposal | `test_later_session_continuity_and_feedback_remain_scoped_and_proposal_only`; `test_evolution_output_is_only_a_reviewable_proposal` | AM5 activation requires governed review; AM6 must run matched controls and preserve negative outcomes |
| Partial write and indeterminate retry | Append-only transactions are atomic and idempotent; indeterminate failures forbid blind retry and require an exact durable-receipt lookup reference | `test_existing_core_store_preserves_exact_agent_memory_replay`; `test_atomic_failure_leaves_no_partial_agent_memory_records`; `test_indeterminate_port_failure_forbids_blind_retry_and_requires_receipt_lookup` | AM2 SurrealDB adapter must implement durable receipt lookup and post-timeout recovery conformance |
| Lifecycle bypass | Lifecycle is append-only, supersession preserves history, and erasure confirmation requires a complete dependency proof | `test_lifecycle_supersession_is_append_only_and_erasure_needs_dependency_proof`; product trace correction chain | AM3 filters restricted/expired/erased material before ranking; AM4 supplies runtime lifecycle operations |
| Incomplete erasure | Core proof is content-free and requires exact equality between enumerated and removed dependencies | `test_erasure_proof_is_content_free_and_requires_complete_dependency_removal` | AM4 must enumerate bodies, assertions, edges, embeddings, summaries, caches, exports, and rebuild paths |
| Backend coupling | Contracts import no SurrealDB, `RecordID`, host, extension, HTTP, or MCP implementation | `test_agent_memory_contracts_are_provider_host_and_extension_free`; `test_naked_contract_import_composes_no_engine_host_or_extension` | AM9 requires a complete second-backend conformance run before any portability claim |
| False material-use or benefit claim | Candidate Receipt proves retrieval only; lineage references existing Context Manifest and exact I3 receipt identities without duplicate use flags | `test_candidate_receipt_links_to_existing_manifest_and_i3_without_redefining_use`; `test_repeat_briefing_trace_preserves_correction_manifest_and_i3_lineage` | AM3/AM6 must produce matched controls and may claim benefit only through separately authorized evaluation evidence |

## Fail-closed boundary

AM0 blocks closeout if a contract permits content-supplied authority, implicit current time, unknown
required versions, selected current use of a known superseded assertion in the frozen trace, a
decision claim without an exact I3 receipt, database types in public contracts, or a public MCP
inventory other than eleven tools.
