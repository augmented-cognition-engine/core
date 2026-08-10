# T1A durable cancellation work packet

Status: **active candidate for ACE 0.5.0; does not complete T1 or B1**

## Outcome

Establish the first bounded control primitive for Reasoning into Action: an authenticated owner can
request cancellation of an extension invocation that explicitly declared cancellation support, and
ACE records one durable, truthful terminal result without presenting cancelled work as successful.

This packet promotes no general or distributed cancellation claim. It hardens the existing
experimental extension-invocation seam so the larger 0.5.0 action journey can build on an honest
lifecycle primitive instead of creating a second task system.

## Ownership boundary

- **Core owns** task identity, product/user/workspace access, the cancellation state transition,
  durable task and extension receipts, interruption of the local execution coroutine, and restart
  reconciliation.
- **The extension owns** whether an action advertises cooperative cancellation support. It does not
  mutate Core lifecycle state.
- **The domain application owns** the user experience and domain reason for stopping work. It does
  not gain direct execution or persistence authority.
- **External effect adapters remain out of scope.** Cancelling ACE orchestration is not proof that a
  remote system reversed or stopped an effect.

## Frozen invariants

1. Cancellation is available only when the accepted capability declared
   `cancellation_supported=true` and included the `cancel` lifecycle operation.
2. Product, user, and workspace ownership are checked before the cancellation request reaches the
   Core task lifecycle.
3. Core persists `requested` before interrupting the local execution coroutine.
4. A cooperative local stop becomes `status=cancelled`, `cancellation.state=acknowledged`, and
   `execution.usable_output=false`.
5. If execution already reached a terminal state, Core records
   `completed_before_cancellation` without rewriting that terminal result.
6. If the owning process is unavailable, Core fails visibly as `degraded` with
   `process_stopped_during_cancellation`; it does not claim successful cancellation.
7. The first terminal cancellation fact is immutable for repeated requests. Actor, reason, and
   timestamps are not rewritten by a later caller.
8. Concurrent requests for the same task serialize through one in-process transition.
9. Runtime restart reconciliation rebuilds the public extension receipt from the reconciled task
   facts, so a stale `running` projection cannot survive beside a terminal degraded task.
10. Cancellation receipts expose bounded lifecycle facts, not hidden reasoning, private execution
    coordinates, credentials, or a claim that external effects were reversed.

## Acceptance matrix

| Case | Required observable result |
|---|---|
| Capability does not support cancellation | `409 cancellation_unavailable`; execution lifecycle is not called |
| Active local invocation | `requested → acknowledged`; task is `cancelled`; output is unusable |
| Completed/cancelled/degraded terminal invocation | Existing result remains terminal; first cancellation fact is preserved |
| Execution-completion race | Core rechecks durable state and reports the fact that won; no false cancelled/success projection |
| Missing owning process | Task becomes visibly `degraded` with an interrupted, unusable execution receipt |
| Restart with pending cancellation | Durable task and public extension receipt both reconcile to the stopped-process result |
| Wrong product, user, or workspace | Not found; no cancellation state is written |
| Duplicate or concurrent request | One lifecycle transition; subsequent response returns the same durable fact |

## Explicit exclusions

- distributed worker signalling or portable in-flight execution;
- exactly-once execution or transaction replay;
- remote API, browser, infrastructure, payment, messaging, or filesystem effect cancellation;
- compensation, rollback, revocation, timeout budgets, or partial-effect repair;
- unrestricted autonomy or a model-originated right to execute or cancel work;
- a supported general `/tasks/{id}/cancel` contract outside negotiated extension actions.

Those remain later T1/B1 packets and must be proved through the complete 0.5.0 journey.

## Closeout gate

T1A may be marked passed only when focused lifecycle and extension API tests, naked-kernel tests,
the required repository checks, an installed-artifact restart journey, limitations, evidence, and
roadmap reconciliation are complete. Passing T1A changes neither T1 nor B1 to passed.
