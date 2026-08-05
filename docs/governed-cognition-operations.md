# Governed Cognition Operations

## Signals

Monitor:

- `ace_cognition_selection_total{state}` for empty or degraded selection growth;
- `ace_cognition_candidate_dispositions_total{disposition,reason}` for unavailable dependencies,
  ambiguity, incompatibility, expiry, and budget pressure;
- `ace_cognition_selected_revisions` and `ace_cognition_level1_tokens` for ceiling drift; and
- `ace_cognition_lifecycle_total{action,status}` for failed review or rollback operations.

Alert when degraded/empty selection or lifecycle failures depart from the deployment baseline, when
`required_dependency_unavailable` appears after a package change, or when token/revision histograms
cluster at their hard ceiling. Metric labels are bounded; product, task, revision, raw exception,
prompt, and resource content are intentionally absent.

## Rollback

Disable governed product discovery to fall back to signed Core package revisions through the same
catalog; do not re-enable direct mutable selectors. For a material regression, an authorized human
posts a lifecycle `rollback` against the exact head generation and prior immutable revision. Verify
that the generation increments, fresh selection names the prior revision, the later revision remains
readable, and the selection/use receipts survive restart.

## Missing extension

Do not install a different package merely because it exports the same slug. Compare extension ID,
version, accepted contract, module/package digest, and resource manifest. Either restore the exact
compatible package or roll the affected head back/disable it. A degraded task must not be relabeled
successful cognition use.

## Backup and restore

Before schema/package rollout, take a database backup using the deployment's supported SurrealDB
backup procedure. Restore into a clean isolated database, apply schema through v171, and reconcile:

1. identity/revision/head/activation counts and hashes;
2. proposal, human review, lifecycle, import/quarantine, selection, use, and effectiveness receipts;
3. head generation and active revision per product scope;
4. current dependency/package availability; and
5. one fresh product selection/use plus a Core-only naked-kernel selection.

If reconciliation differs, keep traffic on the prior store. Never down-migrate or delete cognition
history to repair a failed rollout.

## Package compatibility evidence

Before release, build the local current/N-1/independent-consumer matrix from the exact release
worktree and the supported N-1 tag:

```bash
uv run python scripts/verify_e1_package_matrix.py \
  --n1-tag v0.2.0 \
  --output /absolute/release-evidence/e1-package-matrix-v1.json \
  --artifacts-dir /absolute/release-evidence/e1-package-artifacts-v1
```

The verifier builds current and N-1 wheels/source distributions, generates an independent consumer,
tests both mixed-artifact directions, proves the current-Core/N-1-reference adapter, proves the
N-1-Core/current-reference pre-registration refusal, checks zero-extension boot, and scans wheel
exclusions. Its receipt deliberately records `publication_provenance: not_proven_by_local_verifier`.
Release automation must separately bind the published artifact URLs and registry hashes to the
locally verified hashes; a local build is not publication evidence.

## Deployment-wide legacy inventory

Run against a quiesced upgraded database before deleting any legacy cognition table, selector,
executor, or facade. First inspect the complete bounded report without mutation:

```bash
uv run python scripts/run_governed_cognition_legacy_inventory.py \
  --deployment-id <stable-non-secret-deployment-id> \
  --output /absolute/release-evidence/legacy-inventory-dry-run-v1.json
```

Then persist and read-verify every per-row disposition:

```bash
uv run python scripts/run_governed_cognition_legacy_inventory.py \
  --deployment-id <stable-non-secret-deployment-id> \
  --persist \
  --output /absolute/release-evidence/legacy-inventory-persisted-v1.json
```

Dry-run and persisted receipts must have the same `deployment_id`, `schema_head`, and
`receipt_set_hash`; `total_receipts` must equal `verified_persisted_count`. Retain every mapped,
historical, or quarantined receipt. The command
paginates every declared source, fails rather than truncating at its row ceiling, covers orphaned
and null-product rows, and refuses to overwrite an existing evidence file unless the operator uses
the explicit replacement flag. Rerun after any source-table change.

## Independent security review handoff

Build the fixed-scope evidence bundle:

```bash
uv run python scripts/build_e1_security_review_bundle.py \
  --output /absolute/review/e1-security-review-bundle-v1.json
```

Send the bundle and
`docs/evidence/governed-cognition-independent-security-review-template-v1.md` to a reviewer who did
not implement the workstream. The reviewer must bind their record to the bundle hash, resolve or
explicitly accept every finding, and issue a verifiable verdict. The generated bundle always says
`pending_independent_review`; changing that field is not a valid sign-off.
