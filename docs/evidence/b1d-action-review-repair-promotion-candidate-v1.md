# B1D action review, repair, and promotion candidate evidence (v1)

Date: 2026-08-10

Status: **merged candidate; released-artifact acceptance pending**

**Outcome:** the B1 action boundary now has durable exact-material human review before an effect,
separate post-effect verification, explicit linked repair, and separate promotion without changing
the B1A admission or terminal receipt contracts.

## Exact reviewed identity

- Pull request: [Core #83](https://github.com/augmented-cognition-engine/core/pull/83)
- Reviewed head: `2250d89d4453c136b58910962a325ed184fe269a`
- Squash merge on `main`: `00fb08a1ef8371268b9d459ca1b46370d77ddd0b`
- CI run: [31406339822](https://github.com/augmented-cognition-engine/core/actions/runs/31406339822)

All six final-head jobs passed: Lint, Tests (fast gate), Naked kernel (zero extensions), Security
Audit, Canvas, and Docker Build. The PR had no unresolved review comments or requested changes and
was mergeable at the exact tested head.

## Contract proved

The public `GovernedActionReviewService` composes over the existing executor and immutable-record
store. Preparation remains effect-free. The durable review embeds the complete intent, prepared
plan, and Core policy authorization. This binds the target, adapter identity, permissions, declared
side effects, before evidence, reversibility, timeout, and governed-state preconditions to one
authenticated human approve/reject decision.

An approved review can be reloaded by key after service reconstruction and executed without asking
the adapter to prepare another plan. The unchanged B1A executor still appends admission before the
adapter effect and an honest terminal afterward. Rejection never reaches admission. A changed
review under the same stable key conflicts instead of replacing the human judgment.

Verification, repair, and promotion are distinct immutable facts:

- only a confirmed successful terminal can be marked verified;
- a repair requires `repair_required`, known effect state, explicit rationale, and a successor with
  a different action key;
- unknown effects cannot enter repair because another attempt could duplicate an effect that may
  already have happened; and
- success does not promote itself—promotion or rejection requires a separate authenticated human
  receipt over the exact verification.

These records do not perform effects. The explicitly supplied trusted adapter remains the only
effect boundary. Domain Packs remain declarative.

## Verification

Focused verification at the committed head passed `42` tests covering action contracts, host
composition, real-database restart, the independently packaged reference adapter, public Core
boundaries, and evidence-index integrity.

The complete non-e2e, non-extension-required suite was then reproduced from the exact commit in a
normal Git clone:

```text
7429 passed, 50 skipped, 260 deselected
```

The naked-kernel boundary separately passed `4` tests. Lint and formatting passed for every changed
Python file.

The first complete run was intentionally attempted in a linked Git worktree. It reached `7426`
passes but three pre-existing runtime-baseline tests failed because their read-only revision helper
assumes `.git` is a directory; a linked worktree uses a `.git` pointer file. No B1D test failed. The
exact committed head was copied through Git object transfer into a normal clone, where all `7429`
tests passed. The unrelated worktree-topology defect was not hidden inside this packet.

## Durable restart proof

The SurrealDB integration journey:

1. prepares and authorizes an exact plan;
2. persists an approved human review;
3. reconstructs the host service and store;
4. reloads the review by stable key from database JSON;
5. executes the stored plan once without a second adapter preparation;
6. persists the exact terminal, verification, and promotion lineage; and
7. confirms the adapter saw one prepare and one effect.

Unit-level negative cases additionally prove rejected and expired reviews, review replay conflict,
late review after admission, verification-before-promotion, unknown-effect repair refusal, and
fresh repair identity.

## Independent artifact probe

Core and the B1C reference adapter built as separate wheels and imported together from a clean
environment outside the checkout:

- Core `ace_core-0.4.4-py3-none-any.whl`:
  `sha256:5825f626901d3594470a3d84c90ad8edf15b619b80c769e71cd5e50e7d526daa`
- Adapter `ace_reference_workspace_action-0.1.0-py3-none-any.whl`:
  `sha256:fb7fcbec99df77959de18b2aa391bb43646a8cdca1aa96da5b83360c4f757cd0`

The external probe imported the public review, verification, repair, and promotion contracts and
service plus the separately packaged adapter. The adapter intentionally declares
`ace-core>=0.5.0,<0.6`, while this unreleased candidate wheel still reports `0.4.4`; therefore the
paired local probe installed Core first and the local adapter without dependency re-resolution.
This preserves the honest future release floor. It is not public-index or released-0.5.0 evidence.

## Remaining release boundary

B1D does not provide compensation, rollback, cross-process locking, distributed exactly-once
effects, remote execution, arbitrary filesystem access, untrusted-code sandboxing, or automatic
publication. T1 portability/topology closeout, the public Decision-to-reviewed-action journey, and
released-artifact reproduction remain required before T1, B1, or ACE 0.5.0 can pass.

See the [B1D work packet](../design/b1d-action-review-repair-promotion-work-packet-v1.md).
