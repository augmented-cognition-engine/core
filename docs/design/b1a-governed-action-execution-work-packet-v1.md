# B1A governed action execution work packet (v1)

Status: **active candidate for ACE 0.5.0; does not complete T1 or B1**

## Objective

Establish the first domain-neutral writable-action seam: an authenticated principal can bind one
approved Decision to one exact extension- or application-owned adapter plan, durably admit that
plan before effects begin, and receive an immutable terminal receipt that never represents denied,
failed, partial, timed-out, cancelled, or restart-uncertain work as successful.

## Ownership

Core owns contract validation, exact identity, Decision linkage, authorization verification,
pre-effect admission, immutable receipts, replay, timeout/cancellation classification, product
scope, and failure semantics. A trusted application or extension owns the adapter implementation,
target resolution, before/after evidence, domain arguments, and actual side effect. Domain Packs
remain declarative and contain no imperative control flow.

## Frozen flow

1. Validate an opaque `ActionIntent` linked to one immutable Core Decision whose disposition
   explicitly authorizes the same action type.
2. Ask the selected adapter to prepare an exact, effect-free plan containing target identity,
   declared side effects, required permissions, before evidence, and a bounded timeout.
3. Resolve one Core governed-action authorization over the exact prepared-plan identity.
4. Append the admission transaction before invoking the adapter.
5. Execute once in the current process and append one terminal receipt.
6. Replay an exact terminal result without invoking the adapter again. If a prior runtime admitted
   the action but left no terminal receipt, append an honest `degraded/effect_unknown` terminal
   record and refuse implicit re-execution.

## Acceptance

- no adapter execution occurs before durable admission and exact authorization;
- duplicate requests replay one immutable result;
- reused action keys with different material fail closed;
- product, principal, Decision, adapter artifact, action type, and state-head scope are exact;
- denial, adapter failure, partial effect, timeout, cooperative cancellation, and restart orphaning
  have distinct non-success terminal dispositions;
- before/after evidence is bounded, content-addressed metadata and never secret material;
- extension removal leaves Core receipts readable and does not move adapter logic into Core; and
- the naked kernel starts with zero action adapters.

## Explicit exclusions

B1A does not establish distributed exactly-once effects, cross-process locking, remote workers,
container equivalence, automatic compensation, arbitrary shell execution, unattended autonomy,
promotion through every SHIP gate, or released-artifact acceptance. Those remain later 0.5.0
packets. Passing B1A alone changes neither T1 nor B1 to passed.
