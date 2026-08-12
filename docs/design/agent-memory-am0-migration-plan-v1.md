# Agent Memory AM0 isolated migration and verification plan v1

**Status:** final integrated migration candidate verified; draft PR authorized, merge and release prohibited
**Date:** 2026-08-11
**Preserved source worktree:** `/private/tmp/ace-agent-memory-am0` on `codex/agent-memory-am0`
**Verification worktree:** `/private/tmp/ace-agent-memory-am0-final-verification`
**Verification branch:** `codex/agent-memory-am0-final-verification`
**Exact integrated base:** `10bbed620291ac5f552c3313dd37580938a5b9d7` (`feat(intelligence): bind watch brief activation handoff`, draft PR #105)

## Guardrails

- Do not stage, commit, push, publish, or open a pull request without a later explicit instruction.
- Do not alter the large preserved source checkout or include any of its non-AM0 changes.
- Do not mix AM0 into Core PR #99 or a branch associated with that work.
- Recreate only the recorded AM0 migration set on the control-tower-authorized integrated commit;
  shared Intelligence Builder, Connect/Map, Watch/Brief, Domain Activation, and Agent Composition
  files remain owned by their respective lanes.
- Treat Meta-Intelligence only as a cross-cutting capability name, never as a package, fourth layer, or dependency direction.
- Preserve the public dependency direction: Core → Intelligence → Domain.
- Frame ACE publicly as the Intelligence Builder and, at the complete platform boundary, the
  Intelligence Operating System: “ACE, the Intelligence Builder. Build intelligence, not
  infrastructure.” Do not frame ACE as a reasoning engine.
- Keep cognition broad and internal—memory, learning, planning, and reasoning—and keep Agent Memory
  largely invisible to users.
- Bound AM0 product evidence to a contract-and-receipt trace for source continuity, repeated
  briefing refreshes, later-session onboarding continuity, corrections, preferences, and feedback.
  Do not implement an onboarding agent, connector, ontology mapper, briefing generator, monitor
  scheduler, or UI in AM0.

## Ownership freeze

Core owns only:

- memory identity and authenticated scope;
- exact source coordinates;
- ledger, knowledge, and world time;
- append-only lifecycle;
- authority bindings;
- opaque immutable records and receipts; and
- content-free erasure dependency proof.

Intelligence owns:

- semantic memory families and epistemic state;
- reconciliation and evolution proposals;
- `AgentMemoryQuery`;
- ranking-signal contributions;
- candidate records and receipts;
- graph projection, semantic query, selection, and context-composition ports; and
- linkage to existing Context Manifest and I3 receipt identities.

The memory-context lineage contract must not repeat eligibility, authorization, selection, injection, reflection, decision-material, or benefit claims. It references the existing `ace.context.manifest/v1` and `intelligence-use-receipt-v1` artifacts that own those claims.

## AM0-only migration set

Only the following paths may be carried into the isolated worktree during this slice:

```text
ace/core/agent_memory.py
ace/core/agent_memory_bridges.py
ace/core/agent_memory_ports.py
ace/core/__init__.py
ace/intelligence/contracts/agent_memory.py
ace/intelligence/contracts/__init__.py
tests/agent_memory/test_contracts.py
tests/agent_memory/test_contract_roundtrip.py
tests/agent_memory/test_bridge_mappings.py
tests/agent_memory/test_boundaries.py
tests/agent_memory/test_port_conformance.py
tests/agent_memory/test_product_trace.py
evaluations/fixtures/agent_memory_am0_contract_v1.json
docs/design/agent-memory-roadmap.md
docs/design/agent-memory-charter-audit-v1.md
docs/design/agent-memory-am0-work-packet-v1.md
docs/design/agent-memory-am0-migration-plan-v1.md
docs/design/agent-memory-am0-threat-model-v1.md
docs/design/agent-memory-am0-closeout-audit-v1.md
docs/design/agent-memory-am1-work-packet-v1.md
evaluations/fixtures/agent_memory_am1_session_normalization_v1.json
```

The Core and Intelligence-contract package initializers contain only AM0 public-export additions
required by the existing contract-boundary suite. No release metadata, migration, generated
artifact, existing test, or existing runtime path is part of the migration set.

## Migration sequence

1. Finalize ownership corrections only in the isolated AM0 migration set without staging them.
2. Verify that every migration-set file is additive and that no target path already differs on the base.
3. Recreate only the migration-set files in the isolated worktree.
4. Confirm isolated `git status --short` lists exactly the migration set and no other changes.
5. Run focused formatting and tests in the isolated worktree.
6. Run existing architecture/kernel/MCP boundary tests against the isolated worktree.
7. Run the supported naked-kernel lane with extensions disabled if the focused boundary suite passes.
8. Record results and any pre-existing failures without changing release maturity.
9. Stop before staging or committing and report the exact diff/status and verification evidence.

## Verification commands

Focused formatting:

```text
uv run ruff check ace/core/agent_memory.py ace/core/agent_memory_ports.py ace/intelligence/contracts/agent_memory.py tests/agent_memory
```

Focused AM0 tests:

```text
uv run pytest tests/agent_memory -q --tb=short
```

Existing boundary checks:

```text
uv run pytest tests/test_kernel_boundary.py tests/test_public_core_boundaries.py tests/intelligence/test_contract_boundaries.py tests/extensions/test_naked_kernel.py -q --tb=short
```

Naked-kernel regression lane:

```text
ACE_DISABLE_EXTENSIONS=1 uv run pytest -m "not e2e and not requires_extensions" -q --tb=short
```

The public MCP inventory assertion must remain exactly eleven tools. Unknown required contract versions and memory families must fail closed. The isolated diff must contain no SurrealDB driver, `RecordID`, HTTP host, extension, Domain Pack, or Meta-Intelligence-package dependency in Core contracts.

## Publication hold

Successful local verification does not authorize staging, committing, pushing, a pull request, release-metadata changes, or a capability-maturity claim. Publication begins only after an explicit review of the isolated status/diff and a separate instruction naming the intended destination.

## Verification result

Final integrated run on 2026-08-11 in
`/private/tmp/ace-agent-memory-am0-final-verification`:

| Check | Result |
|---|---|
| Repository Ruff lint plus AM0 formatter check | Passed |
| Focused AM0 suite | 47 passed |
| Existing Core, Intelligence-contract, naked-kernel, MCP, and package-identity boundary suite | 37 passed, 1 expected skip (built-in extensions deliberately absent) |
| Supported full extension-disabled non-e2e lane, including linked-worktree tests | 7,591 passed, 50 skipped, 261 marker-deselected |
| Literal all-marker repository suite | 7,799 passed, 49 skipped; 51 failures and 3 setup errors confined to legacy live-LLM/E2E, stale database-schema, and missing optional-report-dependency lanes; no AM0 failure |
| PR #104 linked-worktree source-revision regression | Passed in the supported full lane; no path exclusion |
| Wheel build and two checkout-free target-directory imports | Passed; wheel SHA-256 `f6494d80f4487f4d8f3b8f1ae0f61395a8e90a0db78c3e01af75dbea7d113f05` |
| Lock consistency and whitespace checks | Passed |
| Frozen Intelligence Builder trace | Passed: first briefing, correction, refreshed briefing, later-session continuity, governed feedback proposal, and fail-closed controls |
| AM0 threat control traceability | Recorded with executable tests and explicit AM1-AM9 residual owners |

The first supported-full run reported one SurrealDB cleanup transaction conflict after 7,591 tests
passed. The exact test passed immediately in isolation, and the complete supported gate then passed
on rerun. PR #104's linked-worktree fix is present and green; no linked-worktree failure is an Agent
Memory limitation.

The literal all-marker run intentionally includes legacy tests outside the repository's supported
Core gate. Its failures require live provider behavior, legacy database state/schema, optional PDF
dependencies, or other E2E environment assumptions. None imports or exercises an AM0 module.

Both the preserved source worktree and the final verification worktree remain unstaged and
uncommitted. No branch was pushed and no package was published.

## Clean rebase and handoff plan

The control tower supplied exact integrated commit
`10bbed620291ac5f552c3313dd37580938a5b9d7`, and the recorded sequence was executed:

1. preserved `/private/tmp/ace-agent-memory-am0` unchanged as the source-of-record worktree and
   record hashes for every AM0 migration-set file;
2. created a second isolated verification worktree and branch from the exact supplied integrated
   commit; do not rebase, clean, stage, or commit the preserved source worktree;
3. recreated only the AM0 migration set in that verification worktree and compared every resulting
   file hash or reviewed conflict to the source-of-record set;
4. resolved only genuine contract/package-initializer collisions. Shared README, roadmap,
   manifesto, architecture, release, Domain Activation, Watch/Brief, and Agent Composition files
   under their owning lanes;
5. verified the exact landed Context Manifest and I3 identities, the 0.7D proposal/preview identities,
   the 0.7E activation-plan/revision/receipt coordinates, and the 0.7G task-composition naming seam
   without importing their runtime implementations into Agent Memory;
6. reran focused Ruff, the AM0 suite, existing Core/Intelligence/naked-kernel/MCP boundaries, the
   full extension-disabled non-e2e lane, and installed-wheel import/serialization checks if the
   integrated stack requires them;
7. stopped for separate staging/commit/push/PR authorization after recording the exact worktree,
   branch, base, diff, file hashes, checks, and collision resolution.

The only shared-file collisions were additive exports in `ace/core/__init__.py` and
`ace/intelligence/contracts/__init__.py`. The accepted
`ace.application.domain-activation-commit-reference/v1alpha2` seam is retained only through a
Core-owned exact historical-lineage reference containing the referenced contract, opaque committed
record reference, and full material digest. It is fixed to `authority_stage=historical_reference`
and `live_authority=false`; it is neither an AM0 dependency nor an AM1 authority contract.
