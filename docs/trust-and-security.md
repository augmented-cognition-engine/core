# Trust, security, and governance boundaries

These are product and implementation invariants enforced by contract validation and architecture tests. They supplement—not replace—the [security policy](../SECURITY.md), [manifesto](../MANIFESTO.md), and [capability-maturity boundary](capability-maturity.md).

## Security and governance invariants

These are enforced by contract validation and architecture tests, not by convention.

**Authority**
- Every LIVE effect requires a resolved authority grant and a committed domain activation. Prepared
  analysis grants no authority under any circumstance.
- Authority-use receipts are single-use and cannot be reused across admissions.
- Capability use is bound to exact artifact identity, so a capability granted for one artifact does
  not carry to another.
- Models may propose. Models cannot approve, activate, roll back, expire, supersede, retire, or
  grant execution authority.

**State**
- All durable writes go through Core's immutable-record port as atomic append-only transactions.
  There is no persistence path around it.
- Governed-state heads carry preconditions that are **rechecked inside the commit**; a stale head
  fails the transaction rather than racing it.
- Identity and material hashes are derived from canonical JSON. Supplying a mismatched
  `storage_id`, `material_hash`, or `request_hash` is a validation error.
- Replay is exact: the same transaction key with the same material returns the same receipt; the
  same key with different material raises a replay conflict.

**Acquisition**
- Source acquisition fails closed on scope, URI, redirect, DNS/IP-rebinding, payload-size, digest,
  replay, timing, and authority violations. HTTPS URIs are validated exactly and IP literals are
  checked against non-public ranges.
- **ACE does not browse.** There is no automatic or arbitrary web access. A connector may fetch only
  one exact resolved source definition, and only through the bounded registry the host constructed.

**Packs and connectors**
- Domain Packs are inert data. The compiler rejects executable-shaped fields and refuses mappings
  that touch host-owned envelope fields.
- Connectors register in a constructor-supplied registry keyed by exact artifact identity. There is
  no dynamic entry-point loading for LIVE source connectors.
- The naked kernel (`ACE_DISABLE_EXTENSIONS=1`) boots and composes no LIVE service. `make
  test-naked-kernel` is that boundary in CI form.

Report vulnerabilities per
[SECURITY.md](https://github.com/augmented-cognition-engine/core/blob/main/SECURITY.md).

---
