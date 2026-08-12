# AC4 agent onboarding and governance candidate evidence v1

- Date: 2026-08-12
- Candidate base: `26fa78dda31db1041f5bf0d838ede0916f0749af`
- Candidate branch: `codex/v0.7-agent-onboarding-governance`
- Status: clean implementation candidate

## Candidate claim

The candidate supplies additive, provider-neutral contracts and application services for explicit
agent onboarding and governance. It preserves frozen AC1 identities, reuses Core governed state and
authority resolution, maintains five separate current heads, and makes activation a no-effect,
non-reusable eligibility receipt.

## Frozen conformance cases

- deterministic service;
- model agent;
- adversarial definition;
- stale approval;
- widened binding;
- revoked grant;
- incompatible protocol; and
- retired principal.

## Verification record

| Check | Result |
|---|---|
| AC4 focused lifecycle suite | 20 passed |
| AC1, governed cognition, governed state targeted regression | 86 passed |
| Naked-kernel, package identity, and exact eleven-tool MCP selection | 42 passed, 1 skipped |
| Dedicated kernel boundary | 4 passed |
| Full extension-disabled gate | 7,574 passed, 50 skipped, 261 deselected |
| Ruff, format, lock, diff and secret scans | passed |
| Scoped domain-noun scan | no production or fixture matches |
| Scoped authority scan | reviewed; matches state explicit separation/denial only |

## Installed-wheel reproduction

- Wheel: `ace_core-0.6.0-py3-none-any.whl`
- The final wheel SHA-256 is recorded in the draft-PR handoff rather than inside this packaged
  evidence file, avoiding self-referential artifact metadata.
- Two fresh environments installed the wheel plus declared dependencies from outside the checkout.
- Both loaded the packaged AC4 fixture and reproduced byte-identical coordinates:
  - governance: `agent_governance:831a77b46762ef056216d57e5538f26e`;
  - registration snapshot: `agent_principal:b4568931bf31999e2dffcaa6a9b673d8`;
  - initial lifecycle revision: `agent_principal_lifecycle_revision:c0808b3037db2714cd0e0ae1947f6856`; and
  - Core commit receipt: `governed_state_commit:6bb0f79c39568341998a80cde64bcbae`.
- Both reopened a fresh service over the committed stores and recovered the exact lifecycle head plus
  its `lifecycle_revision` and `governed_state_commit_receipt` audit records.
- Wheel inventory contains all three AC4 modules and the AC4 fixture, with no tests, environment
  files, credential payloads, or AC4 provider SDK additions.

The final broad run and dedicated kernel rerun were clean. An earlier pre-hardening run encountered
one unrelated SurrealDB cleanup write conflict in `test_atomic_capture_write`; its fixed test records
were explicitly cleaned and the isolated test passed before the clean final run above.

## Limitations and downstream handoff

The candidate does not execute an agent, grant authority, expose a new API/MCP tool, deliver or
export content, interoperate with an external agent, or migrate legacy compatibility participants.
AC5 consumes the exact activation and compatibility-replacement receipts described in the work
packet, but must independently resolve all current heads and runtime authority before use.
