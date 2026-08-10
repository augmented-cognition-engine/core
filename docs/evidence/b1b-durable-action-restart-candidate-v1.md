# B1B durable action restart candidate evidence (v1)

**Status:** candidate, merged to `main`; independent-adapter and released-artifact evidence pending

**Date:** 2026-08-09

**Outcome:** supported host composition and fresh-process durable replay for governed action

## Claim

The candidate adds the first sanctioned host boundary for B1 action adapters. Applications name
trusted adapters explicitly, Core resolves one complete immutable artifact identity, and the
composed service persists through the existing domain-neutral immutable-record port. No adapter is
discovered dynamically and no Domain Pack receives imperative control flow.

The candidate also corrects strict replay decoding for Decision, admission, and terminal payloads
reopened from database JSON. A real SurrealDB journey now admits an action, executes its adapter,
simulates process loss before terminal commit, and starts a fresh Python process. The fresh process
does not authorize, prepare, or execute the adapter again; it records `degraded/effect_unknown` with
`runtime_restarted`. A third client instance replays that exact terminal receipt.

This is application-process restart evidence over a durable database. It does not claim a database
server restart, distributed exactly-once effects, or safe automatic retry after uncertain effects.

## Source and artifact identity

The candidate was reviewed and verified in
[pull request #78](https://github.com/augmented-cognition-engine/core/pull/78):

- final reviewed head: `716171f4a1cf4613578df7c211a5acfce51ff3d7`;
- squash merge on `main`: `e824151230f98bae5b563bc06131e605a2d386fe`; and
- final-head CI run: [31363773057](https://github.com/augmented-cognition-engine/core/actions/runs/31363773057).

The release identity remains pending.

## Current verification

Focused action, host-composition, and real-restart verification:

```text
18 passed in 1.52s
```

The integration case used the repository's real SurrealDB fixture and a separate Python process.

Full non-e2e repository regression with extensions disabled:

```text
7417 passed, 50 skipped, 260 deselected in 183.45s
```

Naked-kernel boundary rerun:

```text
4 passed in 0.97s
```

Roadmap, public-positioning, and evidence-index integrity:

```text
18 passed in 0.36s
```

Repository-wide Ruff checks, format checks, and `git diff --check` passed.

Final-head CI completed successfully on the exact reviewed head. All six repository gates passed:

- Lint;
- Tests (fast gate);
- Naked kernel (zero extensions);
- Canvas (core/ui/canvas);
- Security Audit; and
- Docker Build.

## Isolated wheel probe

The local candidate wheel retained the unreleased base version `ace-core==0.4.4`:

```text
ace_core-0.4.4-py3-none-any.whl
SHA-256 21f79bdfb8f96441b46516148b457c72152979016f20bdef04784a03faa0ec76
```

The wheel and declared dependencies were installed into a new Python 3.12 environment. From
outside the source tree, the probe imported the supported host module from `site-packages`, built
the exact registry, resolved only the registered artifact, and reached the SurrealDB builder. The
wheel version is not a new release claim.

## Remaining closeout gate

B1B remains a candidate pending released-artifact reproduction. Local acceptance, isolated-wheel
host composition, public review, final-head CI, and merge reconciliation are complete. B1 still
additionally requires an independently packaged trusted adapter plus explicit action review, repair,
and promotion behavior. T1 portability/topology and released-artifact closeout also remain before
ACE 0.5.0 can pass.
