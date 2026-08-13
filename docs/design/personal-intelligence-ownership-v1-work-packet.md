# Personal Intelligence ownership v1 work packet

Status: bounded Core candidate

## User promise

One person can export the immutable records for one ACE product as canonical,
checksummed portability evidence. The same person can preview deletion, review
the exact record count and snapshot digest, and confirm only that exact preview.
Core then removes the previewed immutable records and preserves a content-free
proof in the configured primary immutable-record store.

This is an ownership and exit boundary. It is not collaboration, tenancy,
managed hosting, native database backup, or a runnable restore workflow.

## Contracts and behavior

- Export, preview, and confirmation require a host-owned authorization port in
  addition to an exact authenticated product and actor context.
- Export preserves complete canonical `ImmutableRecordV1` values in stable
  storage-identity order and derives an artifact digest over that material.
- The artifact states `runnable_restore_supported: false`. It can be inspected,
  archived, or transformed by future tooling, but this packet does not claim
  that it can recreate a working ACE installation.
- Delete preview captures exact immutable record references, material hashes,
  count, expiry, and a separate confirmation digest.
- Confirmation must bind the same actor, product, preview, digest, and validity
  window. Any observed record-set change invalidates the preview before erasure.
- Confirmed removal uses the existing exact atomic erasure primitive: content
  records are removed in the same transaction that appends one content-free
  proof record and its append-only transaction receipt.
- Successful replay returns the same proof and transaction receipt identity.
- Ownership proof records are excluded from later content exports and deletes.

## Authenticated API and CLI exposure

The host exposes three authenticated `POST` operations under
`/v1/intelligence/ownership`: export, deletion preview, and deletion confirm.
There is deliberately no one-step HTTP `DELETE`. Every request derives product
and actor scope only from verified token claims, persists credential-free
authentication evidence in the excluded ownership control space, checks token
authority attenuation, and resolves the named current Core authority grant.
Export requires `deliver_export`; preview and confirm require
`administer_lifecycle`.

The CLI mirrors those operations under `ace ownership`. Export and preview are
written as canonical JSON files created with mode `0600`. Confirmation requires
the preview file plus the exact digest shown after review. The CLI repeats that
exports are not runnable restore artifacts and that deletion does not purge
backups or external copies.

## Acceptance evidence

Focused in-memory tests cover:

1. deterministic product-scoped export with no runnable-restore claim;
2. fail-closed host-authorization denial;
3. rejection of a mismatched confirmation digest;
4. stale-preview refusal without deletion;
5. content removal, foreign-product isolation, content-free proof, and replay;
6. atomic failure preserving every original record and appending no proof.

Focused transport tests additionally cover verified product scope, token and
current-grant denial, fresh authentication between preview and confirmation,
stale-preview HTTP conflict, POST-only OpenAPI shape, private canonical CLI
files, explicit digest confirmation, and server-error preservation.

## Exact limitations

The proof establishes non-reappearance only in the configured primary
immutable-record store as observed immediately after the atomic transaction.
ACE cannot prove removal from pre-existing database backups, user-created
exports, connector-owned bodies, caches, indexes outside the immutable-record
port, or third-party copies. Operators must expire or purge those separately.

The service serializes confirmed deletions within one service instance and
refuses an already-stale preview. The existing persistence port has no
product-wide write-quiescence primitive, so a host must stop other write paths
during confirmed deletion. Native SurrealDB backup enumeration/purge, external
connector erasure orchestration, a restore/import service, API/CLI exposure,
and UI wiring remain separate work. Until a host supplies that quiescence and
backup policy, the product must not present the proof as universal deletion.

## Rollback

Remove the additive ownership contracts, service, public exports, tests, and
this packet. No schema migration is introduced. Existing immutable records and
agent-memory lifecycle behavior are unchanged.
