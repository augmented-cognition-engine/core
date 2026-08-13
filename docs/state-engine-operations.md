# State Engine operations and recovery

This runbook covers the supported ACE 0.2.0 / schema v168 single-node topology: local or
operator-managed SurrealDB with SurrealKV, one ACE API/worker deployment, bounded ingestion clients,
and optional external read-only source bodies. Use only disposable or backed-up environments when
rehearsing failures. K1-K3 are `passed` only for this bounded topology and the published
product-journey evidence; the v168 release boundary remains the operational contract.

## Release and health identity

Confirm that the distribution, API, worker, reference extension, Compose image label, and thin MCP
client all report `0.2.0` before material work. The public thin MCP registration must contain exactly
eleven tools. In a source deployment:

```bash
uv run ace doctor
curl --fail http://127.0.0.1:3000/health/live
curl --fail http://127.0.0.1:3000/health/ready
curl --fail http://127.0.0.1:37778/health
```

`/health/live` proves only that the API event loop is alive. Readiness and worker health carry the
database/queue state needed for operations; neither endpoint establishes semantic correctness.

## Operating limits

- 200 records per ingestion item, 200 items per manifest, and manifest chunk size at most 50.
- 200 candidate records, 50 returned candidates, 20 evidence-pack records, and 8 runtime evidence
  records within 2,400 characters.
- 8 rollout branches, steps, and transitions; 20 promotion retrieval results.
- The reference trial covered 200,000 claims and 236,000 initial semantic records on an M3 Pro with
  18 GB memory and a 2 GiB initial-store budget.
- Bulk ingestion is synchronous and provider-free. A terminal batch receipt means semantic and index
  work for that bounded manifest committed; no per-claim synthesis queue is expected.
- Distributed ordering, multi-writer conflict throughput, multi-region failover, and arbitrary
  historical migration interruption are not supported by this evidence.

## Before ingestion or migration

1. Record the ACE version, schema head, SurrealDB version, adapter ID/version, product, manifest hash,
   dataset/content digests, expected family counts, storage free space, and recovery budgets.
2. Take a database export before migration or material ingestion and verify that the export is
   non-empty. Keep the store and export outside any cleanup target.
3. Run the schema installer to the declared head, then run it a second time. The second run must
   apply zero files and validate the same head.
4. Run the benchmark `freeze-check` before material load. Never edit thresholds or expected counts to
   match a result.
5. Verify that product scope is authenticated Core input and that external content digests match
   adapter proposals.

The supported public-release predecessor is 0.1.4 at schema v160. Take and verify a backup before
upgrading, then run the ordinary schema installer through v168 twice; the second run must apply zero
files. Current-head partial application is resumable. Arbitrary interruption inside historical
pre-v142 files is not supported; restore the pre-migration backup rather than skipping statements.

## Normal ingestion

Run the packaged TP8 runner against an explicit disposable endpoint. `prepare` installs the focused
State Engine schema for a disposable benchmark; production deployments use the complete
`scripts/schema_apply.py` installer. `load`, `counts`, `sustained`, `planes`, `state-planes`, and
`adapter-compare` write JSON when `--output` is supplied.

Monitor manifest index/identity, committed claim position, item and record dispositions, manifest
duration, batch receipt identity, semantic family counts, lineage count, storage growth, failures,
and provider usage. Any returned database error, count mismatch, conflicting stable identity,
failed item, or missing terminal receipt is red. Do not infer success from process exit alone.

## Client, adapter, or database interruption

1. Stop submitting new manifests and retain the exact manifest set and last terminal batch receipt.
2. For database loss, restart the same store in a fresh process and wait for successful authenticated
   health before resuming. Do not remove lock or store files manually.
3. Run `counts` and compare every semantic family, item receipt, batch receipt, and supersession edge
   with the last committed boundary.
4. Replay the last known committed manifest. Its identity must be unchanged, it must report replay,
   and semantic counts must not grow.
5. For adapter failure, verify that no green receipt exists for the unsubmitted/failed boundary.
   Restore the adapter, verify external digests again, and resume at the exact manifest index.
6. For client loss, start a fresh client with the same frozen manifest set. Receipt-derived replay is
   authoritative; local cursor state is not.
7. Reconcile exact final counts and record recovery time, failures, retries, backlog, and storage.

A failed child write must leave neither semantic children nor a green item receipt. If it does,
quarantine the product and stop; do not continue or manufacture a receipt.

## Migration interruption

Current strict migrations must be additive/fail-closed and safe when a client stops after any
completed statement but before the schema-version receipt advances. Restart the ordinary installer;
it must reapply the current migration, validate the head, and then apply zero files on a second run.

Historical pre-v142 migrations are not guaranteed statement-idempotent. TP8 deliberately interrupted
v014 and the resume failed closed on an already existing table. For that case, stop, retain logs,
restore the pre-migration backup into a clean store, and rerun schema zero without interruption. Do
not weaken legacy error handling or skip statements manually.

## Backup and restore

For the supported single-user recovery path, use ACE's packaged wrapper rather than replaying a raw
SurrealDB full export directly:

```bash
python -m core.engine.cli.commands.recovery backup ./ace-backup.surql
python -m core.engine.cli.commands.recovery restore ./ace-backup.surql \
  --target-namespace ace_restore \
  --target-database ace_restore
```

`backup` refuses to overwrite either output, serializes every SurrealDB table record with the native
CLI, and writes `ace-backup.surql.manifest.json` with the ACE version, Surreal CLI version, schema
head, byte count, and SHA-256 digest. `restore` verifies that manifest and checksum, requires an
explicit database with no definitions, rebuilds the exact recorded packaged ACE schema, removes
migration seed rows, imports the native record snapshot, and checks the restored schema head.
Pause ACE ingestion and other writers while `backup` runs so the recovery point has one explicit
operational boundary.

The packaged schema is deliberately authoritative. Historical migrations can leave valid runtime
indexes that reference retired fields; SurrealDB can export those generated definitions but then
reject the same definitions during a clean import. ACE therefore retains SurrealDB's native record
serialization while rebuilding definitions from the exact matching package. A schema-version
mismatch fails before the destination is changed. Any failure after schema preparation makes the
destination partial; discard that destination and retry with a new empty database.

This is runnable database recovery, not data portability. It does **not** include `.env`, provider or
connector credentials, external secret stores, or external source bodies that were never persisted
in SurrealDB. Back those up through their owning systems. Restore into a clean disposable store
first. Then verify:

- exact semantic-family, item, batch, and lineage counts;
- lifecycle and authoritative promotion states;
- evidence-pack, belief, transition, rollout, reasoning-use, and promotion receipt identities;
- replay of a known manifest without semantic growth; and
- fresh retrieval of the current promoted/corrected memory.

TP8's reference export was 520,154,734 bytes, restored in 28.97 seconds, and reconciled 220,000
post-sustained claims plus all receipts and lineage. Those numbers are reference evidence, not a
universal service-level objective.

## Product archival and reactivation

Archive through `StateEngineOperationsService`; never delete State Engine rows directly. An archived
product rejects ingestion and retrieval while its append-only lifecycle receipt remains inspectable.
Reactivation requires a new authoritative receipt linked to the prior state. Physical deletion and
cascading cleanup are not part of the supported TP8 lifecycle.

## Escalation conditions

Stop and retain the store, manifests, export, receipts, and logs when any of these occur: count
growth on replay, cross-product results, identity conflict for different material, simulated state
in an observation/belief response, raw claim in memory without accepted promotion, missing or green
receipt after a failed transaction, schema version advanced after a failed migration, restored
identity mismatch, provider activity on a declared no-call path, or a frozen budget violation.

The [TP8 evidence record](evidence/state-engine-tp8-scale-stability-v1.md) contains the reference
measurements and preserved negative results.
