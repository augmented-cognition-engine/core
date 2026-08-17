# Code Intelligence governed resource admission — first packet

Status: implemented backend and explicit governed host dispatch; deployed coordinates still required

## Decision

Atrium Code lens history uses Core's existing product-scoped immutable-record store and the public
Intelligence resource plane's existing `semantic_revision` kind. It does not add repository, file,
symbol, or other Code nouns to `ace.core` or the shared resource-plane contracts.

The local phase-one index snapshot store remains provider-free reconstruction evidence. It is not a
product record, does not grant authority, and cannot publish a resource-plane revision by itself.
The explicit host dispatch makes the admitted envelope the product-scoped record that says which
exact reconstruction was accepted into product history. Production composition uses Core's
SurrealDB immutable-record adapter and governed-state authority resolver. Test evidence uses an
in-memory immutable-record store and synthetic authority port; it is not a deployed append receipt.

Shared `ace.core` and `ace.intelligence` contracts remain noun-neutral. Code-specific admission and
projection live in the installed product application adapter
`core.engine.code_intelligence.resource_plane`; the `code_intelligence` solution package belongs to
the existing `installed_product_application` disposition alongside `atrium`. That declaration is not
yet present in `core-engine-compatibility-disposition-v0.8.0.json`, so
`tests/test_intelligence_os_ownership_boundary.py` currently reports the package as undeclared; no
historical disposition is reclassified by this packet.
The installed `code-intelligence` solution contributes that adapter through the existing
`ace.extensions` registry; the generic resource-plane host no longer imports a Code reader. Provider
identity, version, declared generic kinds, and factory are retained. Duplicate scoped identities and
overlapping valid kinds fail before a query; malformed or failed providers return bounded degradation
only when their claimed kind is queried. Provider identity is scoped by
extension ID plus local name, so entry-point enumeration order cannot choose which extension owns a
name. With `ACE_DISABLE_EXTENSIONS=1`, the
naked kernel keeps its Core contributors, omits the Code provider, and reports `semantic_revision`
as unsupported rather than silently instantiating a product lens.

## Admitted envelope

Each append-only revision binds:

- authenticated product and actor scope plus a freshly evaluated `mutate_internal` grant;
- the exact index snapshot ID, digest, and generation;
- the exact repository index ID and digest;
- the exact Atrium Code lens ID, digest, and contract;
- a stable lens-family ID derived from product, repository reference, target, and query digest;
- immediate-predecessor revision ID and digest;
- body-free counts and target coordinates; and
- literal-negative source, reasoning, delivery, and effect authority.

The immutable envelope and public payload contain no source excerpt or coding-agent context body.
The contract explicitly records `source_body_count = 0`, `context_bodies_exposed = false`, and
`local_snapshot_is_product_truth = false`.

## Revision and concurrency behavior

Revision numbers are contiguous within one lens family. Every revision after the first names the
immediately previous revision and digest. The Core record key and transaction key both use the lens
family and revision number, so concurrent attempts to create different material at the same next
revision conflict instead of forking history. Replaying the same exact admission intent returns the
existing durable transaction receipt only after exact product, record-space, transaction-key,
commit-time, immutable-record, original request hash, and exact authority-grant-head precondition
revalidation.

Every successor must use the immediately next local snapshot generation and bind the prior admitted
snapshot ID and digest as its exact parent. Its indexed `as_of` cannot precede the prior revision's
`as_of`. A forked local index, generation gap, or temporally regressed observation therefore cannot
be presented as a linear semantic-revision history.

The admission service does not auto-retry or silently renumber a losing concurrent append. The
caller must reacquire current product authority, reread the durable revision chain, and submit a new
exact intent. This keeps conflict resolution observable and prevents the adapter from choosing
product history on its own.

Projection revalidates every immutable envelope and its complete per-family chain. Invalid,
incomplete, or forked history returns a degraded empty Code-lens batch rather than partially
asserting a product revision.

## Local index cache preconditions

The local phase-one snapshot store is a writable cache and is never
self-authenticating: anything with write access to that directory can rewrite
the phase-one state and recompute a fully coherent chain, latest pointer, and
every derived snapshot file name, ID, and digest. Reuse therefore requires
coordinates the caller recorded *outside* it.

`POST /v1/code-intelligence/journey` and `POST /v1/code-intelligence/admissions`
share one request contract carrying an optional, all-or-none
`expected_snapshot_id`, `expected_snapshot_digest`, and
`expected_snapshot_generation`. A partially supplied triple is a malformed
request (422). Both responses return `index_snapshot_id`,
`index_snapshot_digest`, and `index_generation` so a caller can hold the
complete triple externally and present it on its next request.

- An empty cache with no precondition may create generation 1. An empty cache
  presented *with* a precondition conflicts (409).
- A nonempty cache without the complete triple conflicts (409) before any reuse
  or append.
- An unchanged repository reopens only against the externally supplied ID and
  digest, and only when the supplied generation names the reopened snapshot.
- A changed repository authenticates the exact parent using the supplied pair,
  computes a fresh index, and captures the child bound to that exact expected
  parent ID, digest, and generation.
- Stale, forged, or crossed coordinates (an ID from one generation with another
  generation's digest, or a correct pair with the wrong generation) conflict
  (409); nothing is appended. A losing concurrent writer conflicts rather than
  silently renumbering onto the winner's chain.

The store's own chain listing decides only whether the cache is empty and
supplies the reconstruction candidate used to probe whether the repository still
matches what was cached. No authentication coordinate is derived from that chain
or from the replaceable latest pointer. Coordinates that do not name the stored
snapshot fall through to the fresh-index path, where `capture` re-authenticates
the exact expected parent before appending.

These coordinates are local cache continuity evidence. They are never product
truth: `index_snapshot_is_product_truth = false` on the journey response, and
`local_snapshot_is_product_truth = false` on every admitted revision.

## Configuration fences

The configured product is fenced identically on both operations: a structurally
valid principal product must equal `code_intelligence_product_ref` before any
repository, index, or cache object is constructed or read. A missing or
malformed principal product is 401, a different product is 403, and an
unconfigured or untrimmed operator product is 503 — in every case with no
repository access, no cache directory, no authentication receipt, and no
admission record.

`code_intelligence_index_store_root` must be an absolute path that is neither
the configured repository root nor inside it. Both the lexical form
(`normpath`, no symlink traversal) and the resolved form (symlinks and platform
aliases followed) of the cache root are compared against both forms of the
configured repository, so a link or alias cannot place cache writes inside the
tree whose exact revision and working-tree identity the journey reports. The
pair is validated at startup by settings and again at the HTTP boundary before
any directory is created or read.

## Installed projection-provider isolation

The generic resource-plane service already rejects a page that crosses product,
kind, temporal, subject, ordering, or page bounds — but it rejects the *whole*
page, which would let one optional installed provider take unrelated Core kinds
down with it. The compatibility host therefore revalidates each installed
provider's batch itself, before it reaches the composite: output model, record
count within the requested limit, exact requested product, claimed kind,
subject filter and as-of/available-at cutoffs per record, deterministic
strictly ascending unique ordering, cursor advancement, and conservatively
bounded `degraded_reason_refs` (at most 8 unique non-empty strings, 200
characters each, 1024 characters total).

Any provider exception or violation degrades only that provider's claimed kinds
through the existing deterministic hashed
`degraded_reason:projection-provider-unavailable:<kind>:<fingerprint>`
reference. The fingerprint is a digest of extension ID and provider name, so no
provider exception text or batch content reaches a caller, and unrelated Core
kinds keep their exact page. Unknown declared kinds are ignored and overlapping
valid claims fail composition before any provider is constructed.

Chain revalidation is per lens family and must see a family whole, so the Code
projection reader cannot page its own source query. It therefore counts admitted
revisions first and fails closed above an explicit
`MAX_PROJECTED_CODE_LENS_REVISIONS` bound with
`degraded_reason:atrium-code-lens-history-exceeds-projection-bound`, rather than
letting admitted product history dictate unbounded decode, projection, and sort
work behind one bounded page request.

## Authorization and read path

Admission requires a current `mutate_internal` authority-use receipt bound to the exact body-free
admission intent, actor, product, operation, grant, and evaluation time. The authority grant head is
also used as an atomic append precondition.

The existing authenticated Intelligence resource-plane query remains the only public read path for
admitted revision history. Its normal `observe_read` authorization, product fence,
as-of/available-at cutoffs, subject filters, and pagination checks apply unchanged. The separate
`/v1/code-intelligence/journey` endpoint inspects current repository state and does not read or admit
that history. The Code adapter contributes only `semantic_revision` records.

## Deliberate stop line

The current `/v1/code-intelligence/journey` endpoint authenticates a caller but does not resolve a
mutation grant. It is repository/source- and product-history-read-only, while still writing
provider-free local index-cache generations. This packet therefore does not silently admit every
inspection. Its machine contract says `repository_read_only = true`,
`product_history_write = false`, and `local_cache_may_write = true`; it does not compress those
different effects into a bare `read_only` flag.

Fresh scans and reopened snapshots are accepted only when repository revision and working-tree
identity remain stable before and after scan plus after all lens and handoff source reads. A
repository change fails closed; the host never relabels fresh anchors or counts with an older
snapshot identity. Local snapshot-generation races return an explicit conflict instead of an
availability error.

The separate `POST /v1/code-intelligence/admissions` operation is the only host dispatch. It requires
an authenticated product and actor supplied through an `Authorization: Bearer` header, token
attenuation containing `mutate_internal`, a caller-supplied grant reference, and the
operator-configured stable `code_intelligence_repository_ref`. URL/query credentials are rejected on
this durable mutation boundary even though the shared authentication dependency retains query-token
compatibility for SSE routes. The
repository reference is never inferred from a local path, Git remote, or request body. Each request
persists an authentication receipt, freshly resolves the exact current grant against the exact
body-free admission intent, and then appends through the production immutable-record adapter. Missing
authentication, attenuation, grant input, repository configuration, current authority, or durable
storage fails closed. Local index-cache writes remain possible before current-grant or database
failure and are explicitly disclosed by `local_cache_may_write = true`; no product Code-lens revision
is admitted on those failures.

A denial or later persistence failure may therefore leave a body-free authentication receipt without
a linked Code-lens revision. That receipt proves only that authentication was verified at that time;
it is not denial evidence, a grant-decision audit receipt, or proof of admission. Retention and any
future explicit denial-linkage policy remain outside this packet.

No Atrium UI change is part of this packet.

## Evidence

- `tests/test_code_intelligence_resource_plane.py` covers exact authorization, append-only
  admission, idempotent and tamper-resistant replay, immediate snapshot-parent supersession,
  exact original request/grant-head replay binding, generation gaps and forks, monotonic `as_of`, a
  forced two-writer conflict and HTTP conflict classification, body exclusion,
  product scoping, generic semantic-revision projection, and mismatched snapshot/index/lens
  rejection using an in-memory immutable-record store and synthetic authority port.
- `tests/test_api_code_intelligence.py` covers the explicit host dispatch, exact authority
  coordinates, missing authentication and grant input, attenuated tokens, denied current grants,
  header-only bearer enforcement, missing operator repository identity, unavailable durable storage,
  fresh-scan/reopened/late-read repository races, no source-body response or persisted payload, and
  the ordinary journey's lack of any admission-runtime dispatch. It additionally covers the external
  snapshot handshake (empty cache with and without a precondition, partial triples, reopen, changed
  repository with exact parent capture, stale/forged/crossed coordinates, a lost concurrent race, and
  admission inheriting the same contract), the admission product fence proven by repository and cache
  spies with no persisted authentication or admission record, cache-root containment across blank,
  untrimmed, relative, equal, nested, traversal, and symlinked spellings, and the settings-level
  containment negatives.
- `tests/test_code_intelligence_solution_composition.py` covers installed projection-provider
  isolation: malformed output models, oversized record counts, cross-product/kind/subject/temporal
  records, unstable and duplicate ordering, unbounded/non-string/empty/duplicate/oversized degraded
  references, an in-contract success, unknown and duplicate kind declarations, and the regression
  that a violating provider degrades only its claimed kind while unrelated Core kinds stay complete.
- The inherited HTTP and Intelligence resource-plane suites verify that the new contributor does not
  change the established authorization or public page contract.

## Deliberate nonclaims

- No deployed durable append receipt or production-environment authority decision is claimed.
- The local snapshot store authenticates nothing by itself. Its digests, chain, and pointer prove
  internal consistency only; the external coordinate triple is the entire trust boundary for reuse,
  and a caller that loses those coordinates must accept a fresh index rather than trusting the cache.
- Cache-root containment is a configuration fence, not a filesystem sandbox. It does not defend
  against a hostile operator, a race that relocates either path between validation and use, or any
  other write authority already present on the host.
- An installed provider's own well-formed bounded `degraded_reason_refs` are passed through as
  written. The host bounds their count, size, and shape and never adds provider text of its own, but
  it does not inspect a provider's references for content it chose to place there.
- `MAX_PROJECTED_CODE_LENS_REVISIONS` is an explicit refusal bound, not pagination. Above it the
  Code projection degrades rather than partially projecting a family; pageable per-family
  revalidation is not part of this packet.
- No coverage, correctness, or safe-change guarantee is claimed for the inspected repository. The
  journey remains bounded static evidence, and admission records only which exact reconstruction was
  accepted, never that it was right.
