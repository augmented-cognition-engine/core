# ACE 0.7 stable Domain Pack Core contract candidate

**Status:** candidate, local. This record closes only the Core implementation packet frozen by
PR #99. It does not close issue #39, E2, SI3, or the 0.7.0 release, and it does not claim the
required independent World Intelligence and Market Intelligence installed-artifact falsification.

**Kickoff base:** `f667b12ecf75a7a5c4e6e7d5aea6950db8976919` over released `main` at
`492b99667b0a119234d4a8af26e448254c0a6abd`.

## Implemented boundary

The candidate promotes the existing v1alpha1 substrate through an additive stable layer:

- distributed JSON Schemas for the stable manifest, every accepted module contract, compilation
  evidence, golden fixtures, receipts, and an installed schema index;
- explicit `supported`, `deprecated`, `migration_required`, and `rejected` negotiation against
  compiler/runtime contract ranges;
- stable, bounded, path-specific diagnostic codes and messages;
- stable compiled Pack IR plus exact compatibility and compilation result identities;
- a public `ace.testing.run_domain_pack_conformance` helper that requires no model provider,
  network, database, registry, persistence, or clock read;
- deterministic golden Observation transition evaluation through the existing ontology,
  numeric/categorical detector, Signal routing, persona, and synthesis-template machinery;
- exact conformance receipts binding Pack IR, compiler/runtime contracts, compilation evidence,
  fixture material, expected outcomes, actual outcomes, diagnostics, and pass/fail state;
- deterministic co-installation validation with pack-identifier collision refusal; and
- stable activation refusal for missing, failed, stale, forged, mismatched, or compilation-divergent
  conformance evidence before Core can create durable live state.

The activation contract continues to store only opaque receipt references. It does not add domain
resource identifiers or product nouns to Core receipts. The v1alpha1 compilation path retains its
historical Pack IR identities and exact-equality compiler/runtime behavior.

## Failure controls

Focused tests cover unsupported and migration-required versions, incompatible ranges, duplicate
and drifted bytes, imperative fields, executable/network/extension/action capability escalation,
authority escalation, module and pack identifier collisions, divergent golden identity, failed
golden outcomes, and missing/stale/mismatched activation evidence. Existing compiler suites retain
coverage for undeclared/missing/oversized/cyclic resources, duplicate JSON keys, unknown modules,
cross-module references, source mapping bounds, and typed detector/runtime behavior.

The stable policy in `docs/domain-pack-contracts.md` defines the current window, accepted module
versions, additive/migration-required/breaking classifications, the 180-day plus one-minor-line
deprecation floor, offline migration and audit preservation, and the prohibition on silent host
rewrites.

## Verification

The following local evidence was reproduced from the isolated worktree:

- focused Intelligence, package-data, eleven-tool, and naked-kernel selection: 440 passed, 12
  skipped;
- complete `tests/intelligence`: 420 passed, 12 skipped;
- broad non-E2E/naked-kernel run: 7,295 passed, 243 skipped, 261 deselected; four sandbox-blocked
  loopback cases passed when rerun with loopback permission;
- the remaining three broad-suite failures are pre-existing worktree-topology failures in
  `grounded_state/baseline.py`, which treats the worktree `.git` pointer file as a directory;
- kernel boundary: 4 passed;
- Ruff, secret scan, and whitespace checks passed; and
- a wheel built locally, contained every schema and the public conformance helper, installed into
  a fresh temporary environment, imported `ace` only from that environment, and emitted this
  provider-free receipt:

```json
{
  "pack_digest": "sha256:a61ab084f6a73540bd5248696d0c5f3956abe78dadb6f7069b792b1a70280bf5",
  "receipt_digest": "sha256:56ac516a6b0aa9540f2c5e87e27070e597e07fa96c0fb9c3fedd10a0ab32e42c",
  "receipt_id": "pack_conformance:56ac516a6b0aa9540f2c5e87e27070e5",
  "status": "passed"
}
```

The two-directory test also reproduces byte-identical Pack IR, compilation evidence, and
conformance receipt JSON from separately materialized manifest and fixture files.

## Scope and remaining gate

No World or Market repository was edited. No connector SDK, connector execution, extension
sandbox, telemetry, heterogeneous-evidence expansion, registry, marketplace UI, package release,
or release tag is included. The MCP surface remains exactly eleven tools and naked-kernel startup
remains intact.

The next independent gate belongs in the consumer repositories: World and Market must build their
own inert packs, run the installed helper unchanged, and record exact Core plus consumer artifact
identities. Only failures that reduce to a domain-neutral contract/compiler/conformance/runtime
requirement return to Core.
