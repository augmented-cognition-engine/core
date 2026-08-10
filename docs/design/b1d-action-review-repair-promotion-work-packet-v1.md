# B1D action review, repair, and promotion work packet (v1)

Status: **active candidate for ACE 0.5.0; does not complete T1 or B1**

Date: 2026-08-10

## Outcome

Add the missing human-governance span around B1 action execution without changing the durable B1A
admission and terminal contracts: exact plan review before an effect, explicit post-effect
verification, linked repair instead of silent retry, and a separate adoption decision after
verification.

## Frozen lifecycle

```text
approved Decision
→ effect-free prepared plan + Core policy authorization
→ durable exact-material human review
→ approved plan admitted and executed
→ honest terminal result
→ durable human verification
→ explicit linked repair request or separate promotion decision
```

Policy authorization and human review are different authorities. Review embeds the complete intent,
prepared plan, and authorization, including target, permissions, declared side effects, before
evidence, reversibility, timeout, adapter identity, and governed-state preconditions. Execution
reuses that exact material; it does not ask the adapter to produce a fresh target after approval.
A changed plan is different material and requires a fresh stable review key.

Rejection persists an immutable receipt and cannot admit or execute the action. A terminal result is
not automatically promoted. A confirmed successful result requires a separate verification receipt
and then a separate promotion receipt. A repair request requires a `repair_required` verification,
a distinct successor action key, an explicit human rationale, and known effect state. Unknown effects
are categorically ineligible for automatic or requested repair because another attempt could duplicate
an effect that already happened.

## Ownership boundary

Core owns receipt schemas, identity, product fencing, exact replay, authority binding, persistence,
and lifecycle eligibility. The trusted adapter still owns target resolution and the effect. An
application supplies authenticated human decisions and explicitly composes the adapter and services.
Domain Packs remain inert configuration and cannot review, execute, repair, or promote anything.

Review, verification, repair, and promotion records are governance facts. They never write the
target, compensate an effect, or publish an artifact by themselves. The existing executor remains
the only effect-admission boundary, preserving all B1A–B1C receipt identities and replay behavior.

## Acceptance

- exact approved material executes once and replays without re-preparation or re-execution;
- exact review survives service reconstruction before execution;
- rejection, divergent review replay, changed material, expired/cross-product reviewers, and
  non-durable receipts fail closed before effects;
- verification cannot call a failed, partial, cancelled, degraded, or unknown-effect result verified;
- repair cannot reuse the original action key or proceed from unknown effect state;
- promotion cannot precede successful verification and does not happen implicitly on success;
- lifecycle receipts survive durable database JSON and retain exact lineage; and
- focused, full non-e2e, naked-kernel, lint, formatting, documentation-integrity, and independent
  wheel checks pass.

## Non-claims and next boundary

B1D does not provide compensation, rollback, distributed locks, remote execution, arbitrary
filesystem access, untrusted-plugin sandboxing, automatic publication, or released-artifact
acceptance. It does not make a Domain Pack executable and does not complete T1 or B1. T1 still needs
its portability/topology closeout, and the complete 0.5.0 journey still needs released artifacts and
one public Decision-to-reviewed-action-to-promoted-output proof.
