# B1A governed action execution candidate evidence (v1)

**Status:** candidate, merged to `main`; independent-adapter and released-artifact evidence pending

**Date:** 2026-08-09

**Outcome:** first bounded B1 action-execution primitive for ACE 0.5.0 Reasoning into Action

## Claim

The candidate adds a domain-neutral public contract and replay-first service that binds one
authenticated `ActionIntent` to one immutable Core Decision, one effect-free adapter plan, one exact
governed authorization, a durable pre-effect admission, and an honest terminal result. Applications
and trusted extensions supply the adapter; Core contains no domain action or built-in writable tool.

This record does not pass T1 or B1 and does not authorize an ACE 0.5.0 release. It does not establish
cross-process or distributed exactly-once effects, remote workers, container equivalence, automatic
compensation, arbitrary shell execution, complete SHIP promotion, or unrestricted autonomy.

## Source and artifact identity

The candidate was built on branch `codex/b1a-governed-action-execution` from Core main commit
`43bfa1d6e489708f53f19f9117e620fb4bde0fff`. Public review and final-head verification completed in
[pull request #76](https://github.com/augmented-cognition-engine/core/pull/76):

- final reviewed head: `0414f54e7986a761dca246151589b47fe17a903d`;
- squash merge on `main`: `1c415823337dd14e6d8fc5278ff07baf8ba395fa`; and
- final-head CI run: [31361130777](https://github.com/augmented-cognition-engine/core/actions/runs/31361130777).

The release identity remains pending.

The locally built wheel retained the unreleased base version `ace-core==0.4.4`:

```text
ace_core-0.4.4-py3-none-any.whl
SHA-256 5b752c77a30012ac2c0b809c551d620dfdd967f897470d749dedc989a72ba2c1
```

The wheel version is not a new release claim.

## Contract result

The implementation and focused tests establish:

- the Decision must explicitly authorize the same action type for the same named actor;
- an adapter can only prepare a bounded plan using the exact artifact selected by Core's governed
  operation binding;
- credential-shaped parameter and evidence metadata keys fail contract validation;
- Core authorization and immutable admission complete before adapter execution begins;
- exact and concurrent duplicate calls converge without a second prepare or effect;
- reuse of one action key with different immutable material fails closed;
- successful, failed, partial, timed-out, cancelled, and restart-orphaned executions have distinct
  terminal dispositions and effect certainty;
- adapter exception text is not exposed as public failure material; and
- a prior admission with no terminal receipt is never implicitly re-executed and becomes
  `degraded/effect_unknown`.

The frozen ownership and exclusion rules are in the
[B1A work packet](../design/b1a-governed-action-execution-work-packet-v1.md).

## Verification

Focused action lifecycle verification:

```text
14 passed in 0.48s
```

Related Core authorization, contract-boundary, naked-kernel, roadmap, and evidence verification:

```text
66 passed in 1.94s
```

Full non-e2e repository regression with extensions disabled:

```text
7413 passed, 50 skipped, 260 deselected in 180.39s
```

Naked-kernel boundary rerun:

```text
4 passed in 0.90s
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

The local wheel and declared dependencies were installed into a new Python 3.12 environment. A
probe executed from `/private/tmp`, imported the module from `site-packages`, reached the public
service export, and constructed an exact successful terminal result:

```json
{
  "contract": "ace.core.action-result/v1alpha1",
  "disposition": "succeeded",
  "effect_state": "confirmed",
  "result_id": "action_result:512485ccda35bd4352ea85ec2dfd4b37",
  "service_exported": "GovernedActionExecutionService"
}
```

This is an isolated installed-wheel import/contract probe, not a public-index or side-effect journey.

## Remaining closeout gate

B1A remains a candidate until an independently packaged trusted adapter proves the same contract
without importing host internals and a later released artifact reproduces the bounded journey.
[B1B durable restart evidence](b1b-durable-action-restart-candidate-v1.md) now binds supported host
composition, strict database replay, and fresh-process admission/orphan reconciliation. Public review,
final-head CI, and merge reconciliation are complete. A later packet must still add explicit action
review and repair/promotion, container portability evidence, and the remaining T1 topology guarantees
before T1, B1, or 0.5.0 can pass.
