# I2 attributable deliberation and synthesis evidence

Date: 2026-07-22

Outcome: **I2 passed**

## Frozen claim and boundary

ACE can expose a versioned, bounded receipt showing why it selected a reasoning shape, which
execution units contributed final position artifacts, which artifact-grounded conflicts mattered,
and how synthesis dispositioned each position and its evidence.

This is inspectable attribution, not access to hidden reasoning. The contract does not expose
chain-of-thought, prompts, model scratchpads, private reasoning tokens, tool transcripts, or
unrestricted contributor output. It does not claim the final decision is correct, causal,
beneficial, or higher quality because multiple contributors participated.

## Frozen `deliberation-receipt-v1` contract

The receipt is an additive task-backed projection over existing orchestration and task identities.
Schema v156 adds one optional `task.deliberation_receipt` field; it adds no table, endpoint, public
MCP tool, write operation, or execution authority.

The receipt contains:

- `selection`: the selected reasoning shape and mode, a fixed allowlist of bounded observable
  classification/dispatch signals, and bounded selection reasons;
- `contributors`: stable execution and contribution identities, phase, concise position or
  recommendation, assumptions, evidence IDs, confidence, gaps, execution status, duration, and a
  completeness receipt;
- `conflicts`: only conflicts that name at least two existing contribution artifacts plus a
  decision-relevant issue; roles and generated persona labels cannot create attribution or
  disagreement credit;
- `synthesis`: accepted, rejected, contested, and decision-bounding dispositions that copy the
  referenced position and distinguish contributor evidence from synthesis evidence;
- `coverage`: expected/observed/missing contributors, failures, timeouts, tainted phases, partial
  coverage, and degraded synthesis; and
- route, continuity, explicit no-execution authority, completeness, and limitations.

Generated calls may append one fenced `ace-attribution` JSON block to their ordinary final answer.
The adapter strips that block from user-facing prose, allowlists only final-artifact fields, bounds
and redacts them, and stores the projection. Malformed or absent blocks do not fail the task: the
receipt uses a bounded final-output projection where possible, names every missing structured
field, and remains degraded. Streaming, legacy, unknown-version, foreign-product, partial, failed,
and interrupted paths never reconstruct facts from prose or internal logs.

## Supported paths and implementation

The existing `POST /tasks` / `GET /tasks/{id}` API path persists and normalizes the receipt. The
same value is returned by existing thin-client `ace_task` / `ace_status` calls and the read-only
Living Product Graph task projection. The supported CLI keeps its existing command and adds an
explicit inspection flag:

```bash
uv run ace run --show-deliberation "Should the cancellation policy move to general rollout?"
```

The default result display remains backward-compatible. No twelfth MCP tool was added; all eleven
registered names and the thin client's engine-import prohibition remain unchanged.

Implementation is intentionally concentrated in:

- `core/engine/product/deliberation.py` for parsing, building, normalizing, redaction, lineage, and
  degraded-state rules;
- existing orchestration patterns and provider shells for execution-phase labels and bounded final
  artifacts;
- existing task/status and Living Product Graph projections for authenticated reads;
- schema v156 for additive persistence; and
- the existing CLI `run` command for opt-in rendering.

## Frozen public-data demonstration

The deterministic scenario uses the public UCI Online Retail II dataset context, DOI
`10.24432/C5F88Q`. The decision is whether a cancellation-policy rollout should remain staged or
move to general availability. Evidence IDs distinguish the public dataset and its documented
C-prefixed cancellation convention from derived metrics and a declared operational constraint.

The checksum-frozen input is
`evaluations/fixtures/i2_attributable_deliberation_v1.json` (14,726 bytes, SHA-256
`3bfaca0e695b7e342856aee66de9f2c24e7483571adbf75fb0e9dae8ab6b0943`). The generated receipt
matrix is `evaluations/results/i2_attributable_deliberation_v1.json` (36,438 bytes, SHA-256
`6a2e1742adbcdbbd899e8848a6ff5460860ca5231d7506b3e8e419cf7ac76cd5`) with a compact Markdown
report beside it.

| Path | Observable result |
|---|---|
| Independent | One complete execution artifact bounds the final result; no synthesis is portrayed |
| Pipeline | Definition, measurement, and policy artifacts are dispositioned with one artifact-grounded conflict |
| Team | One usable artifact, one timeout, one failure, one missing contributor, a tainted synthesis phase, and partial coverage remain visibly degraded |
| Adversarial | Four execution artifacts yield two material conflicts and exactly one accepted, rejected, contested, and bounding disposition |

The adversarial synthesis keeps the rollout staged. It accepts the repeat-purchase guardrail,
rejects cancellation-only rollout, preserves the no-causal-claim position as contested pending a
controlled evaluation, and uses manual-review capacity only to bound exposure. Every disposition
retains its contributor position and evidence IDs.

Reproduce the zero-model-call matrix:

```bash
uv run python scripts/verify_i2_deliberation.py
```

Observed summary: four receipts, reasoning shapes `adversarial`, `independent`, `pipeline`, and
`team`; three complete, one deliberately degraded; three artifact-grounded conflicts; zero model
calls; exactly eleven public MCP tools.

## Failure and degraded-state matrix

| Case | Required behavior | Evidence |
|---|---|---|
| Missing structured artifact | Bounded projection only; missing assumptions/evidence/confidence named | Unit and runtime projection tests |
| Malformed attribution JSON | Strip metadata block; retain parse failure; never expose unapproved fields | Parser contract tests |
| Persona/role-only input | Reject as attribution identity | Role-only adversarial test |
| Conflict without two artifact identities | Omit conflict and degrade lineage | Builder validation tests |
| Missing contributor | Partial coverage with stable missing slot | Frozen team case |
| Provider timeout | Timed-out contribution retained; synthesis cannot be complete | Frozen team case |
| Provider failure | Failed contribution and redacted error retained | Frozen team case |
| Tainted phase | Named in coverage and degrades synthesis | Frozen team case |
| Partial synthesis lineage | Unresolved contribution IDs remain explicit | Frozen team/runtime tests |
| Unknown future receipt | Empty degraded v1 view; no reinterpretation | Compatibility test |
| Foreign-product stored receipt | Empty product-local degraded view; no foreign artifact leakage | Product-isolation test |
| Legacy task | Empty degraded projection; no prose reconstruction | Task normalization tests |
| Runtime interruption/restart | Existing task runtime marks incomplete work degraded | Existing async task recovery tests |

Common credential forms are redacted in positions, gaps, evidence, synthesis reasons, and errors.
The public task projection still omits original private task text, user/runtime coordinates, and
retained-intelligence payloads.

## Persistence and restart evidence

`tests/test_i1_restart_persistence.py` starts a disposable SurrealKV database and production
uvicorn API, creates authenticated tasks through the thin client, stops the API, starts a fresh API
process against the same store, and reads through a fresh client. Production startup replays
schema zero through v156.

The deterministic fixture makes zero model calls and persists one complete independent I2
artifact. Before and after restart, the receipt ID, task/product identity, contribution identity,
selection reason, evidence ID `test:i2:restart`, coverage, and completeness are identical. The same
journey simultaneously preserves the existing I1 decision/correction and I3 intelligence-use
receipts. Observed result: `1 passed in 30.79s`.

Persistence proves receipt and relationship continuity only. It does not prove that the
contributor or synthesis is correct.

## Compatibility, authorization, and authority evidence

- Existing task submission and status responses retain `async-receipt-v1`; the I2 field is
  additive and normalized beside `decision-receipt-v1` and `intelligence-use-receipt-v1`.
- Existing task ownership checks derive product scope from authentication and return not-found for
  foreign tasks. Stored foreign-product I2 receipts fail closed without projecting artifacts.
- Schema v156 defines one optional field and performs no update, delete, or legacy rewrite.
- The thin adapter remains pure HTTP and registers exactly eleven tools.
- The receipt is a read-only projection. It cannot dispatch work, change a decision, disposition a
  correction, resolve a conflict, invoke an extension, or grant tool permission.
- Provider-shell changes only request and parse bounded final metadata; they add no tools or
  permissions. Existing execution authority is unchanged.

## Verification record

| Gate | Result |
|---|---|
| Focused I1/I2/I3, task/API, orchestration, MCP, migration, and kernel regression | **134 passed** |
| Deterministic I2 matrix plus task/API/orchestration compatibility | **92 passed** |
| Final I2 fail-closed, task, planner/executor, orchestration, MCP, migration, and kernel regression | **151 passed** |
| Real schema-zero-to-v156 database/API restart and fresh-client receipt continuity | **1 passed** |
| Full extension-enabled non-E2E suite | **6,591 passed, 46 skipped, 235 deselected** |
| Full zero-extension non-E2E suite | **6,583 passed, 47 skipped, 242 deselected** |
| Ruff repository check | **passed** |
| Ruff repository format check | **passed after formatting three touched files** |
| actionlint | **passed**, actionlint 1.7.12 |
| Final wheel and sdist build/inventory | **passed**; v156, I2 implementation, fixture, results, verifier, and evidence are present in both artifacts |
| Exact naked-kernel / eleven-tool boundary | **passed** in focused and full zero-extension runs |
| Roadmap reconciliation contracts | **17 passed** |
| Authoritative candidate-head branch CI | **passed**: [run 29976761503](https://github.com/augmented-cognition-engine/core/actions/runs/29976761503) — Lint, Security Audit, Canvas, fast tests, naked kernel, and Docker Build |

Commands executed from the repository root:

```bash
uv run python scripts/verify_i2_deliberation.py \
  --fixture evaluations/fixtures/i2_attributable_deliberation_v1.json --write
uv run pytest tests/test_i2_deliberation.py tests/test_task_public_contract.py \
  tests/test_orchestration_patterns.py tests/test_orchestration_dispatcher.py \
  tests/test_dispatch_planner.py tests/test_executor.py tests/test_runtime_executor.py \
  tests/test_mcp_specs.py tests/test_mcp_tools.py tests/test_kernel_boundary.py \
  tests/test_schema_migration_lint.py tests/test_schema_migration_errors.py \
  tests/test_migration_safety.py -q --tb=short
uv run pytest tests/test_i1_restart_persistence.py -q --tb=short
uv run pytest -m "not e2e" -q --tb=short
ACE_DISABLE_EXTENSIONS=1 uv run pytest -m "not e2e and not requires_extensions" -q --tb=short
uv run ruff check .
uv run ruff format --check .
actionlint
uv run pytest tests/test_roadmap.py tests/test_roadmap_staleness.py \
  tests/test_roadmap_reconciler.py tests/test_roadmap_generator.py \
  tests/test_ace_roadmap_tool.py -q --tb=short
uv build --out-dir /tmp/ace-i2-dist
```

The suites emitted only existing dependency/deprecation and asynchronous-mock warnings; no I2
test failed. The ready [pull request #26](https://github.com/augmented-cognition-engine/core/pull/26)
is the stable final-head reconciliation and merge record.

## Explicit limitations

- A structured final artifact is model-generated evidence, not hidden reasoning or proof of why a
  model internally produced an answer.
- Selection reasons explain observable routing policy; they do not claim causal access to model
  cognition.
- Conflict lineage records declared incompatibility among bounded artifacts; it does not establish
  which side is true.
- A complete receipt means required fields and executions are present, not that coverage was
  exhaustive or the synthesis was correct.
- The public demonstration is deterministic and makes zero model calls. It proves contract
  behavior and portability, not provider quality or real-world decision benefit.
- The runtime is still a single-process preview. Distributed recovery and replay guarantees remain
  T1 work.
- I2 adds no claims about I3 material retained-intelligence influence, L1 beneficial impact, F1
  forecast accuracy, B1 execution, or access to private reasoning.

## Work-packet reconciliation

The implementation, local acceptance evidence, compatibility checks, persistence proof, public
scenario, limitations, roadmap reconciliation, and authoritative candidate-head branch CI are
complete on `codex/i2-attributable-deliberation`. I2 is `passed`. Pull request #26 remains the
stable final-head and merge record; any attributable reconciliation or main-branch failure reopens
the outcome rather than weakening a gate.
