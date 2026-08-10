# B1B durable action restart and host composition work packet (v1)

**Status:** frozen acceptance packet

**Date:** 2026-08-09

**Parent outcome:** B1 — approved decisions can produce bounded, attributable action

## Purpose

B1A froze the public action contracts and replay-first service. B1B proves that boundary through
the supported host and durable backend rather than only an in-memory store. It closes the risk that
database JSON, process restart, or adapter discovery changes exact admission and terminal material.

## Ownership

Core owns exact action identities, Decision linkage, authorization, pre-effect admission, immutable
terminal receipts, replay classification, and persistence through `ImmutableRecordStore`.

The host owns an explicit registry of trusted action adapters and constructs the Core service with
the selected governed operation binding and durable store. Registration is exact and constructor
only: no entry-point discovery, import hook, version fallback, or prefix matching is allowed.

The trusted adapter owns effect-free planning, target resolution, the actual bounded effect, and
after-effect evidence. Domain Packs remain declarative and cannot register or execute adapters.

## Acceptance

1. A supported host builder resolves only the complete immutable adapter artifact identity.
2. Duplicate registration, wrong contracts, and missing exact adapters fail closed.
3. The supported durable path uses Core's SurrealDB `ImmutableRecordStore` adapter.
4. Strict Decision, admission, and terminal contracts reopen correctly from database JSON.
5. A real admission is committed before the adapter effect begins.
6. If the effect completes but the terminal append is interrupted, a fresh OS process reloads the
   admission and persists `degraded/effect_unknown` with `runtime_restarted`.
7. The fresh process performs no authorization, preparation, or adapter effect.
8. A later client instance replays the exact terminal material written by the fresh process.
9. Existing denial, timeout, cancellation, partial-effect, duplicate, and replay behavior remains
   unchanged.

## Required evidence

- focused B1A/B1B contract and composition tests;
- real SurrealDB persistence with a fresh Python process;
- full extensions-disabled regression and naked-kernel verification;
- final-head CI and exact merge reconciliation; and
- isolated installed-wheel import of the supported host composition module.

## Explicit exclusions

B1B does not provide a built-in writable adapter, dynamic package discovery, distributed locks,
cross-process exactly-once effects, compensation, remote execution, container equivalence, action
review/repair/promotion, or an independently released adapter package. It does not complete T1, B1,
or authorize an ACE 0.5.0 release by itself.
