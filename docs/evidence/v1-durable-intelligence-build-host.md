# Durable Intelligence build host — v1 acceptance evidence

## Scope

This packet closes one bounded Core composition gap on base
`7e75feea1c1f757a8a32f6c729e486ec2e933e2f`. An authorized Intelligence
build can now recover its exact active Builder bootstrap from the same
product-scoped durable record store, reload the exact canonical activation,
resolve the exact installed compiled Pack, and receive fresh invocation-scoped
recorded-source and prepared-derivation ports.

The recorded-source port also resolves a requested subject binding only when
the binding and entity type are declared by the exact committed Pack. The
caller supplies no activation coordinates and receives no raw activation or
binding object.

## Fail-closed boundary

- No matching active Builder bootstrap or no exact installed Pack keeps both
  optional ports unavailable.
- Malformed correlated activation material, more than one exact candidate,
  changed approval/session material, product drift, or Pack/activation drift
  fails the composition request explicitly.
- The host reuses the authorized build's product-fenced immutable-record port,
  existing activation authority, and current runtime-use resolver. It does not
  create a global setter, cached authority decision, alternate store, or
  fixture identity.
- Composition performs no new approval or grant resolution. Prepared
  derivation retains its existing requirement to resolve the current build
  grant when derivation is invoked.

## Durable restart proof

`tests/intelligence/test_intelligence_build_host_restart.py` starts a
disposable SurrealKV service, applies the supported schema, persists the full
Watch/Brief-to-active-Builder chain and canonical activation, and discovers the
matching compiled Pack from an inert installed distribution. It then composes
both ports, stops the database process, reopens the same database in a fresh
runtime, rediscovers the Pack, and recomposes distinct port instances with the
same exact activation binding and a fresh runtime-use resolver. The proof also
checks same-store reuse, product fencing, and absence of additional approval or
grant calls.

## Verification

- Focused build-host, subject binding, prepared derivation, HTTP boundary, and
  host-service tests: **24 passed**.
- Public Core, naked-kernel, exact-eleven, installed-Pack, executor registry,
  package identity/policy, and Intelligence schema boundaries: **68 passed**.
- Disposable-Surreal process restart/reopen proof: **1 passed**.
- Ruff and `git diff --check`: passed.

## Exclusions

This packet does not implement Brief or cognition behavior, token scopes,
owner bootstrap, UI, domain logic, MCP, connectors, providers, collaboration,
release, tag, or publication work. It does not widen the eleven-tool public
surface and does not make external connector secrets durable or portable.
