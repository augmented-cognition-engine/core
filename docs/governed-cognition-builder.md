# Governed cognition builder journey

ACE keeps reusable reasoning under an explicit lifecycle:

```text
teach → propose → inspect → approve → use → measure → revise or retire
```

The `ace cognition` commands are a thin product interface over ACE's authenticated governed-
cognition HTTP routes. They do not add model write authority, bypass review, or create another
cognition representation. Run `ace login` first. Approval and lifecycle commands require the
human operator credential described in the
[operations guide](governed-cognition-operations.md#review-authority-credential).

## 1. Teach from accepted work

Start with a completed task whose output and receipts are worth reusing. Teaching creates a sourced,
non-selectable proposal; it does not activate anything.

```bash
ace cognition teach task:SOURCE \
  --stable-key market_signal_review \
  --name "Market Signal Review" \
  --description "Review a market signal with explicit counterevidence." \
  --intent "Reuse an accepted market-intelligence reasoning pattern."
```

The response contains the content-addressed proposal and its semantic diff. Save the
`proposal.proposal_id`.

## 2. Inspect before disposition

```bash
ace cognition inspect cognition_proposal:PROPOSAL
ace cognition diff cognition_proposal:PROPOSAL
```

Inspection is read-only. The diff binds the proposed material to its base revision, when one exists.

## 3. Approve, reject, or request changes

The supported interactive route remains human-only: an authenticated human with
`cognition-review` authority can disposition a proposal. A separately provisioned headless
SERVICE may use only the sibling delegated two-stage route described in the
[operations guide](governed-cognition-operations.md#headless-service-provisioning). That exception
does not change this command, its contracts, or its human authority checks.
`--review-request-id` is a caller-stable idempotency identity, and
`--expected-generation` prevents a stale review from replacing a newer head.

```bash
ace cognition review cognition_proposal:PROPOSAL \
  --review-request-id review:market-signal-v1 \
  --disposition approve \
  --rationale "The semantic change and provenance are acceptable." \
  --expected-generation 0
```

Approval atomically creates an immutable revision and a product-scoped active head. Rejection and
requested changes remain durable but never become selectable.

## 4. Require material use in a fresh task

```bash
ace cognition use market_signal_review \
  "Re-evaluate this new market signal and identify counterevidence."
```

This command succeeds only when the fresh task completes and returns matching non-empty selection
and use receipts with a material-use hash. An unavailable, rejected, disabled, expired, retired, or
selected-but-unused revision fails closed instead of being reported as successful cognition use.

Inspect exact attribution independently:

```bash
ace cognition selection cognition_selection:RECEIPT
ace cognition use-receipt cognition_use:RECEIPT
ace cognition revision cognition_revision:REVISION
ace cognition head cognition_head:HEAD
```

## 5. Govern the active head

Lifecycle changes require the same explicit human authority and an exact expected generation.
Delegated services cannot roll back, reactivate, disable, expire, or retire cognition.

```bash
ace cognition lifecycle cognition_head:HEAD \
  --review-request-id review:retire-market-signal-v1 \
  --action retire \
  --rationale "This reasoning pattern is no longer eligible for selection." \
  --expected-generation 1
```

Supported actions are `rollback`, `reactivate`, `disable`, `expire`, and `retire`. Rollback and
reactivation can name `--target-revision`; reactivation can also name a timezone-aware
`--expires-at`. No lifecycle action deletes proposal, revision, review, selection, or use history.

## Boundary

This interface is product-scoped and uses the same public task and cognition APIs as external
consumers. It does not prove the complete GC1 outcome by itself. GC1 still requires a public-
artifact journey covering revision, restart, failure controls, and external-consumer reproduction.
