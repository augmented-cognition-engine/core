# ACE 1.1 database upgrade operations

ACE 1.1 adds two dry-run-first upgrade paths. Neither path rewrites a published migration, guesses product ownership, or activates historical assertions merely because they were imported.

## Before either upgrade

1. Stop ACE writers and record the installed ACE and SurrealDB versions.
2. Create and verify a native backup with `ace recovery backup <new-path>.surql`. Keep its adjacent manifest outside the database host.
3. Restore that backup into a disposable database and verify application startup before changing the source database.
4. Run the relevant inventory command without `--apply` and retain its JSON report.

The backup command exports records and recreates the exact packaged schema during restore. It excludes environment configuration, connector credentials, external secret stores, and source bodies ACE never persisted.

## SurrealDB 3.2 export/import cleanup

Historical org-to-product migrations removed several `org` fields while some older index definitions survived. SurrealDB 3.2 includes those invalid definitions in a native export and rejects a fresh import with `The field 'org' does not exist`.

Run the inspection:

```text
ace recovery prepare-surreal32
```

The report considers only the audited historical org-index tables. An index is eligible only when its live definition references `org` and the table no longer defines that field. Product indexes and deliberately retained compatibility fields are not changed. The report also verifies that SurrealDB exposes the reserved `config_entry.value` field using the escaped `` `value` `` idiom.

After reviewing the exact table/index/definition list, apply it:

```text
ace recovery prepare-surreal32 --apply
```

Apply re-inspects the database and fails unless all eligible indexes are gone. A second apply must report no removed indexes. Then perform a native export/import into a new disposable SurrealDB 3.2.x database and run ACE's schema/startup checks there. Do not treat a clean report alone as round-trip evidence.

This cleanup removes invalid schema definitions only. It does not delete table records, replace product indexes, or rename fields. If a reported definition differs from the dry-run receipt before apply, stop and repeat the inventory after investigating the concurrent change.

## v1.0.3 and schema <=v135 assertion history

The relational-assertion tables were introduced after v135. Upgrade the packaged schema first, then inventory any unscoped `relationship_proposal`, `relationship_assertion`, `assertion_review`, `assertion_event`, and `assertion_dependency` rows. A source older than the assertion tables reports them as unavailable and has no assertion history to assign.

Run the bounded inventory:

```text
ace recovery upgrade-assertion-history
```

The command reads at most 10,000 rows per table by default and fails rather than truncating. It groups references into deterministic connected components. Each component reports its source rows, any already scoped products, typed-field or dangling-reference problems, and a stable component ID.

Create a reviewed mapping document. Every component must be named explicitly:

```json
{
  "contract": "ace.assertion-history-product-map/v1",
  "components": {
    "assertion_history_component:0123456789abcdef0123456789abcdef": "product:platform"
  }
}
```

Never derive this mapping from the current default product, row count, local path, or a single-product installation. If ownership cannot be demonstrated, leave the component unmapped. Cross-product, conflicting, malformed, or dangling components are quarantined as a whole; individual rows are never split out and assigned independently.

Review the mapped dry-run before apply:

```text
ace recovery upgrade-assertion-history --mapping reviewed-map.json
```

Apply only after verifying that each target product exists and the mapping matches the backup inventory:

```text
ace recovery upgrade-assertion-history --mapping reviewed-map.json --apply
```

Apply leaves every source row unchanged and copies validated material to current product-bound identities. Proposal, assertion, review, event, and dependency references are rewritten together. Imported assertions are forced non-operational and provisional (except already rejected or retired history) with `legacy_history_requires_current_policy_replay`; they cannot become operational until the current resolver and current review policy replay the product's proposals. This is data attribution, not activation authority.

Each successful component gets one append-only `assertion_history_upgrade_receipt` containing its source rows, created rows, exact product, and identity maps. Quarantined components get an append-only quarantine record with reasons. A process restart and repeated apply must return the existing component receipt without creating more rows.

## Rollback and recovery

The source history remains unmodified, so the preferred rollback is to stop writers and restore the pre-upgrade backup into a new clean database. Do not import back into the partially changed database.

For a component-level reversal, use the receipt's `created_row_ids` only after proving none of those rows has gained downstream references or current-policy events. If any created row has been used after the upgrade, preserve the database for audit and restore the full backup instead. Append-only upgrade and quarantine receipts remain evidence and are not deleted as part of rollback.

Record the pre-upgrade backup manifest, dry-run report, reviewed mapping, apply report, restart replay report, disposable SurrealDB 3.2 export/import result, and application verification together as the upgrade evidence set.
