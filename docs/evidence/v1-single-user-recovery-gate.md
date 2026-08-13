# ACE v1 single-user recovery gate

**Status:** passed on 2026-08-13

**Base:** Core `main` at `0948db68af3f3915132baed35b40549e305a35ea`

**Topology:** one disposable SurrealDB 3.2.1 SurrealKV store, one product, fresh application service
instances, no model or external network calls

## Promise tested

A single operator can persist the domain-neutral Connect → Map → Watch → Brief Builder chain, stop
the database process, reopen the exact chain through fresh services, append a later immutable
`activation_pending` revision, back up the complete ACE database record state, restore into a clean
database, and reopen the same resource page. Database recovery stays distinct from product-scoped
portability and makes no claim that connector credentials or external source bodies are included.

## Reproduction

```bash
pytest tests/intelligence/test_builder_database_recovery.py -q --tb=short
pytest tests/test_database_recovery.py \
  tests/intelligence/test_intelligence_builder_connect.py \
  tests/intelligence/test_ontology_agent_map.py \
  tests/intelligence/test_briefing_agent_first_brief.py \
  tests/intelligence/test_intelligence_builder_resource_projection.py \
  -q --tb=short
```

Observed result:

- real restart/append/backup/restore after final restack: `1 passed in 77.02s`;
- focused contracts and failure controls: `34 passed`;
- final restacked focused recovery plus public/kernel boundary gate: `82 passed, 2 skipped`;
- a built `ace_core-0.8.2` wheel contains both recovery modules, and the extracted wheel exposes
  `python -m core.engine.cli.commands.recovery --help` with bounded `backup` and `restore` commands;
- Ruff lint and format checks passed for every changed Python file.

The pre-restack broad non-E2E Core run at base
`7142804e2e3479c8fdbbd062614803300fb7fb4e` reached `7897 passed, 50 skipped, 262 deselected`. It reported one
transient SurrealDB transaction conflict that passed on immediate isolated rerun, plus
`test_real_database_fresh_process_orphans_admission_without_reexecuting`, whose child-process import
fails from a linked worktree. The latter reproduces at exact unmodified base
`7142804e2e3479c8fdbbd062614803300fb7fb4e`; it is not introduced by this recovery lane.

## Exact assertions

1. The first persisted page is complete and ends at `first_briefing_ready`.
2. The SurrealDB process stops and restarts against the same SurrealKV path.
3. A fresh `IntelligenceBuilderSessionService` reopens the exact prior revision and a fresh resource
   reader emits byte-identical JSON.
4. A later service appends `activation_pending`; every prior resource item remains exactly unchanged
   and the new revision names its immediate predecessor.
5. Backup produces a non-empty native record export and adjacent manifest containing ACE/Surreal
   versions, schema v177, size, and SHA-256.
6. Restore requires a clean, explicit namespace/database, installs the exact packaged schema,
   restores records, and verifies the same schema version.
7. The resource page rebuilt from the restored database is byte-identical to the post-append page.
8. Existing outputs, dirty targets, checksum drift, unsupported manifests, schema mismatch, and
   partial native import all fail closed.

## Defects found by the real-store gate

- SurrealDB 3.2 selected an inapplicable partial path for the Builder historical read when no index
  was named. The immutable-record adapter now selects `immutable_record_scope_key` explicitly for
  scoped historical reads and counts.
- Canonical JSON persistence necessarily represents tuples as arrays and datetimes as strings.
  Strict Builder contracts now perform JSON-compatible rehydration before their existing digest and
  identity validators run; exact material checks remain unchanged.

## Recovery boundary

The artifact includes all SurrealDB table records. ACE definitions are recreated from the exact
recorded package version because generated full-schema exports can contain stale historical index
definitions that SurrealDB accepts at runtime but rejects on clean import. Database users/access
definitions, environment configuration, provider or connector credentials, external secret stores,
and non-persisted source bodies are excluded and explicitly named in the manifest.
