# Agent Memory AM2 correction-node kind repair v1

## Coordinates and scope

- Exact AM2 base: `0938a63d577f817a68c61cbd8b56841c50d770e2`
- Base branch: `codex/v0.7-agent-memory-am2`
- Repair branch: `codex/v0.7-agent-memory-am2-correction-kind-fix`
- Status: isolated draft repair; not accepted, merged, released, or supported

This repair changes only the existing AM2 graph projection implementation. When a correction
candidate is first inserted during deterministic projection rebuild, its single content-free graph
node is classified as `CORRECTION`. It is not first classified as `ASSERTION` and then reinserted
under a conflicting kind.

The focused AM2 correction conformance test now rebuilds the projection and verifies one node with
the exact correction candidate identity and `CORRECTION` kind. Existing AM2 contracts, candidate
and decision identities, fixtures, receipts, authorization, persistence, graph edges, and public
claims are unchanged. This repair adds no AM3 recall, ranking, context, manifest, or use behavior.
