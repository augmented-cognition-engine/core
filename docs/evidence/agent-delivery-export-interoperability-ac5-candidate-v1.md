# AC5 delivery, export, and interoperability candidate evidence v1

- Date: 2026-08-12
- Combined base: `37dd899c7a5b54c0f6a01f5691da95f992f31c4d`
- Candidate branch: `codex/v0.7-agent-delivery-export-interoperability`
- Status: clean verified local candidate; publication topology review pending

## Candidate claim

The candidate adds provider-neutral, separately authorized delivery, administrative export, and
external-effect operations on top of exact AC3 prepared handoffs and exact AC4 governed participant
state. Current runtime capability/grant/configuration, destination, and policy heads are revalidated
after preparation and immediately before send/effect.

The combined-base merge has exact AC3 and AC4 parents. PR #110 remains the AC3 review authority and
PR #111 remains the AC4 review authority; no source branch was rewritten.

## Deterministic adapter and failure evidence

The provider-free digest-mailbox adapter proves delivery acknowledgment, duplicate detection,
delivery/effect lookup, and portable export without network I/O. Focused fixtures cover
stale/revoked/foreign authority and policy state, destination/payload/ack drift, timeout, rejection,
partial, duplicate, cancellation, indeterminate results, conclusive lookup-before-retry,
crash/reopen lookup, unsupported protocol, ineligible external agent, omission/redaction,
retention/erasure dependencies, and checksum validation.

## Verification record

| Check | Result |
|---|---|
| Focused AC5 contracts, convergence, host policy, restart and adapter suite | 22 passed |
| AC1–AC5, runtime-use/TOCTOU, action/effect/restart, export/retry and package targeted gates | 214 passed, 2 skipped |
| Exact eleven-tool MCP, naked-kernel, package and public-boundary gate | 48 passed |
| Full non-E2E/non-extension gate in the exact locked worktree environment | 7,634 passed, 50 skipped, 261 deselected; two unrelated concurrent database cleanup conflicts |
| Exact isolated rerun of both database-conflict cases | 2 passed |
| Repository Ruff, scoped format, lock and diff checks | passed |
| Secret scan over every AC5-owned path | passed |
| Scoped Domain/AM1 scan | no domain dependency; no AM1 import or contract |
| Scoped authority/effect scan | reviewed; only explicit separation, false authority flags, and lookup-before-retry paths |

## Installed-wheel reproduction

- Wheel: `ace_core-0.6.0-py3-none-any.whl`
- SHA-256: `ce0d1fa780db75e72061d56b0da842fe8d0a25beb75a0fe29215b0d17a11abf7`
- Wheel inventory contains every AC5 Core/Application/Intelligence/host module, the public reference adapter, and the AC5 fixture.
- Two fresh checkout-free target installs loaded the packaged fixture and independently reproduced:
  - destination definition: `destination_definition:e9ec26762a97cf89960e4d9bcf7ff7ff`;
  - destination revision: `destination_revision:375a1975d1f76845416f959e5d6b73c3`;
  - external-agent protocol: `external_agent_protocol:609ed2ab84ea45e6ef72e4a4a770fd36`;
  - 24 frozen conformance cases; and
  - `reference_digest_mailbox` as the installed provider-free adapter identity.

The final AC5 commit, remote branch, draft PR, and publication topology are recorded only after the
control-tower base/diff gate confirms that AC4 review provenance will remain unambiguous.

## AC6 entry dependencies

- Landing order that preserves independent AC4 review provenance.
- Production durable host registrations for destination revision/policy/configuration heads.
- Provider-specific adapters outside Core, with host-private credential resolution and their own conformance.
- Operational reconciliation ownership for long-lived indeterminate external effects.
- Product/UI/API surfaces only after separate authorization; none are implied by this candidate.
