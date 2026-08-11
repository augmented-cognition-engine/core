# Platform P2G owner-governed monitoring — candidate evidence v1

**Status:** candidate, local

**Date:** 2026-08-11

**Consumer requests:** `WI-CR-007`, `WI-CR-008`

## Result

The candidate adds the smallest domain-neutral platform surface needed to turn an inert Monitor,
PersonaBinding, and Subscription into a user-owned, append-only sensing intent. It does not add a
scheduler or source connector. Every transition and sensing window starts from an explicit
authenticated owner request and commits through Core's existing `ImmutableRecordStore` port. The
first lifecycle transaction atomically appends one stable intent anchor, one append-once sequence
slot, and its create receipt. Later transitions append one sequence slot plus one receipt; sensing
windows append one receipt each.

`WI-CR-007` is implemented locally by `MonitoringLifecycleService` and exact request/receipt
contracts. `WI-CR-008` is implemented locally by `SensingWindowService` and exact
request/evaluation/receipt contracts. The requests remain open for the World consumer until this
surface is reviewed, merged, released, installed from the public artifact, and replayed there.

## Frozen public surface

| Surface | Invariant |
|---|---|
| `MonitoringLifecycleAnchorV1Alpha1` | Gives one owner and exact target a stable append-once logical lifecycle identity. |
| `MonitoringLifecycleRevisionV1Alpha1` | Gives each lifecycle sequence one append-once slot so competing transitions cannot branch from the same prior receipt. |
| `MonitoringLifecycleRequestV1Alpha1` | Binds one authenticated actor, product, exact target, exact PersonaBinding, action, sequence, prior receipt, and request time. |
| `MonitoringLifecycleReceiptV1Alpha1` | Records create, pause, resume, or revoke as an immutable content-derived transition. |
| `MonitoringLifecycleService` | Requires the authenticated actor to equal the PersonaBinding principal, preserves target/pack/activation/product scope, enforces exact sequence and replay, and makes revocation terminal. |
| `SensingWindowRequestV1Alpha1` | Requires an explicit authenticated request and positive bounded interval with exact current Monitor and Subscription lifecycle receipts. |
| `SensingWindowEvaluationV1Alpha1` | Carries exact acquisition requests, source transactions, accepted/replayed resources, routed resources, material kind, and one disposition. |
| `SensingWindowReceiptV1Alpha1` | Records the exact lifecycle states and routed-or-suppressed result; authority flags are literal false. |
| `SensingWindowService` | Reopens both lifecycle receipts, checks owner/product/target scope, enforces zero acquisition while paused or revoked, and appends or exactly replays one receipt. |

All identities use existing ACE alpha canonical hashing. The stable lifecycle anchor prevents a
second create chain for the same exact target and owner, including after terminal revocation. Each
sequence slot prevents divergent branches even when they use different transition keys. Stable
transition and window keys are product-scoped transaction keys: an exact retry reopens the prior
result, while changed material under the same key fails as a replay conflict. Service
reconstruction over the same store reopens the exact receipt and transaction.

## Accepted lifecycle

```text
absent --create--> active or paused
active --pause--> paused
paused --resume--> active
active|paused --revoke--> revoked (terminal)
```

Monitor initial state follows its existing enabled/disabled disposition. A Subscription begins
active. Monitor and Subscription targets both retain one exact PersonaBinding owner across the
chain. No request can infer ownership from a credential, persona, subject, source, or publisher.

## Sensing-window guards

- Active Monitor + active Subscription may route material change or record exact
  `no_material_change` suppression over replayed material.
- Correction material requires accepted material, a routed result, and visible correction status.
- Paused Monitor records `owner_paused`; revoked Monitor records `monitor_revoked`.
- Paused Subscription records `subscription_paused`; revoked Subscription records
  `subscription_revoked`.
- Every lifecycle-guarded result requires zero acquisition requests, zero source transactions,
  zero accepted/replayed resources, and zero routed resources.
- A window must cite the latest exact Monitor and Subscription lifecycle receipts available at its
  start time; an older active receipt cannot bypass an already-recorded pause or revocation.

The receipt's `scheduler_authority`, `delivery_authority`, and `external_action_authority` fields
are literal `false`. The service performs no source acquisition and cannot invoke a connector.

## Fail-closed coverage

The focused suite covers:

- exact append and replay after service reconstruction;
- changed material under a stable transition or window key;
- competing lifecycle transitions under different keys at the same sequence;
- a principal different from the bound owner;
- skipped or crossed lifecycle sequence and prior receipt;
- resume after terminal revocation;
- a second create chain after terminal revocation;
- active material routing and exact no-change suppression;
- acquisition attempted while paused;
- sensing after Subscription revocation;
- stale active lifecycle references after pause;
- correction suppression or hidden correction status;
- malformed time windows and smuggled scheduler authority.

## Verification

- Focused P2G plus adjacent public-contract tests: `31 passed`.
- Complete Intelligence suite: `404 passed, 2 skipped`.
- Release-equivalent repository set: `7,456 passed`, `50 skipped`, `260 deselected`:
  - the clean naked-kernel run excluding two runner-sensitive files passed `7,447` tests;
  - the historical baseline file passed `7` tests when pointed at the primary checkout's real Git
    control directory because that historical helper assumes `.git` is a directory rather than a
    linked-worktree pointer file;
  - the database embedding-reconciler file passed `2` tests in isolation after its first full-run
    teardown encountered a transient SurrealDB write conflict;
  - the explicit naked-kernel boundary passed `4` tests and is also included in the clean run.
- Source and wheel artifacts built successfully. Local candidate hashes:
  - wheel: `b2698f333b283ced6a14cc717997e160e2e438b0c20cdd69e83ca093152e18c0`;
  - sdist: `29bd439778543473876352bd6390f32eb18fe7d3d59a1c354fa64402e6ef3d1b`.
- A checkout-free Python 3.12 environment installed the wheel and imported `ace` only from
  `site-packages`. It reproduced lifecycle anchor
  `monitoring_intent:7999a6454ca3fdbaf6f1d72f6ce0b5d7`, pause receipt
  `monitoring_lifecycle:5306c8b397e2c6d75a600187e412457f`, sensing receipt
  `sensing_window:328b43f39539986ce05e4d27333e26fc`, `owner_paused` zero-acquisition
  suppression, false authority flags, and exact fresh-service replay over nine immutable records,
  including the append-once anchor and lifecycle sequence slots.

These are local candidate artifacts, not released publication evidence. Review, merge, versioning,
public artifact publication, and independent World consumer replay remain open.

## Explicit limits

This candidate does not schedule a window, read a source, register or discover a connector,
deliver a notification, publish a Brief, persuade a user, create a Decision or Outcome, invoke an
action adapter, or advance SI1–SI4. It is additive to the 0.5.0 public surface and does not change
existing one-shot PREPARED or LIVE flows when no monitoring request is supplied.
