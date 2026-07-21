# Living Product Graph read contract

The supported Living Product Graph journey is a deterministic, authenticated, read-only view of
the current product. It answers a product question without requiring graph-database, assertion,
schema, or kernel knowledge:

> Show me the current product landscape: intent, capabilities, evidence, decisions, dependencies,
> contested assumptions, corrections, work, and expected or observed outcomes.

Run:

```bash
uv run ace landscape
```

The command calls `GET /product/landscape` for the product in the authenticated token and prints
the complete JSON snapshot. It never accepts a caller-supplied product identifier. To inspect the
full trail behind one relationship shown in the snapshot, use its stable assertion identifier:

```bash
uv run ace assertion relationship_assertion:<id>
```

Both operations are reads. The thin MCP surface remains exactly eleven tools; G1 adds no MCP tool
and does not change the meaning or signature of an existing one.

## Contract identity

| Name | Frozen value | Meaning |
|---|---|---|
| Snapshot schema | `ace.living-product-snapshot.v1` | Public response shape and field semantics |
| Projection | `ace.living-product-projection.g1.v1` | Deterministic selection, filtering, ordering, and issue policy |
| Assertion ontology | `ace.relationships.v1` | Canonical predicate vocabulary and endpoint typing |
| Assertion resolver | `ace.assertion-resolver.v1` | Deterministic assertion-state and operational-edge policy |
| Result identity | `product_snapshot:<sha256>` | Content identity computed from the canonical snapshot before this field is added |

Clients may pin the projection:

```bash
uv run ace landscape --projection-version ace.living-product-projection.g1.v1
```

An unsupported version fails with HTTP `409`, code `unsupported_projection_version`, the supported
versions, and a retry instruction. The server does not silently substitute another projection.

## Required top-level fields

Every successful response contains:

- `schema_version`, `projection_version`, and content-derived `snapshot_id`;
- `authority`, including `mode=read_only`, `writes_permitted=false`, and the rule that only
  `relationships.operational` is canonical semantic truth;
- `projection_state`, including `complete`, `partial`, `degraded`, or `unknown`, assertion-state
  counts, and issue count;
- the focal `product`, intent, projects, capabilities, relationships, decisions, foresight,
  intelligence, work, assertion history, source receipts, and issues.

Projected product records have a stable `id`, `object_type`, `lifecycle_state`, `authority`, and
`provenance`. Family-specific fields are allowlisted from existing records; database rows are not
exposed indiscriminately. Structural relationships are labeled `source_record`. Resolved
assertions are labeled `resolved_assertion_state`. Only accepted, projection-eligible assertions
with matching endpoints and predicate can appear as `canonical_operational_truth`.

## Assertion and uncertainty semantics

| Assertion state | Visible in `relationships.assertions` | Eligible for `relationships.operational` |
|---|---:|---:|
| `accepted` | yes | only when `projection_eligible=true` and the edge matches |
| `provisional` | yes | no |
| `contested` | yes, with contradictions, evidence, assumptions, and explanation | no |
| `rejected` | yes for historical inspection | no |
| `superseded`, `stale`, `retired` | yes when retained | no |

Confidence, evidence strength, resolver certainty, provenance quality, freshness, evidence
references, assumptions, supporting/contradicting assertion references, review depth, explanation,
and degraded reason remain visible when present. Missing evidence is reported; the read never
invents a replacement. Disagreement remains disagreement: a contested relationship is never
collapsed to an operational edge.

## Absence, nulls, ordering, and bounds

- Required containers are always present. Known-empty collections are `[]`.
- Optional source fields are omitted when the source record did not contain them.
- Required scalar fields use `null` only when the focal product is explicitly unknown or a source
  receipt has no reason or bound.
- All record and relationship arrays are ordered by stable identifier, then by a canonical content
  hash as a tie-breaker. Nested object keys and set-like values are canonicalized.
- Every database-backed record family is ordered and fetched with `LIMIT 257`; at most 256 records
  are returned. If another record exists, the family is marked `truncated` with `record_limit`, the
  projection is `degraded`, and no continuation is fabricated. Pagination is not part of v1.
- Cycles are preserved as finite records. The v1 snapshot performs no recursive traversal, so a
  cycle cannot make the read unbounded.

## Provenance, history, and redaction

Every object or relationship carries source-family and record references. Assertions also carry
proposal and evidence references. Assertion lifecycle events appear under
`history.assertion_events`. Decisions, corrections, predictions, observed outcomes, action
outcomes, supersession, and derived-from links use their existing durable identities.

The endpoint derives product scope only from the authenticated token. Extra `product`, `filter`,
serialized payload, or method-like query parameters cannot change it. Cross-product and unscoped
legacy records are excluded and reported. Only allowlisted fields are serialized; product settings
and arbitrary database fields are not returned.

## Failure and degraded behavior

| Condition | Supported behavior |
|---|---|
| Unknown authenticated product | `200` snapshot with product `unknown`, no fabricated records, and recovery issues |
| Missing evidence or dangling assertion history | `partial` snapshot with stable issue code, references, and recovery |
| Contested relationship | both sides remain visible; neither becomes operational |
| Rejected-only relationship | rejected assertion remains visible; no operational edge |
| Incomplete migration or unavailable table | affected source is `unavailable`; available sections remain; projection is `degraded` or `unknown` |
| Unsupported projection | `409 unsupported_projection_version`; supported value and retry are explicit |
| Malformed authenticated identity | `422 malformed_product_identity` before a database query |
| Cyclic graph | finite, deterministic serialization; no recursive traversal |
| Oversized family | first 256 stable records; `truncated` receipt and `source_degraded` issue |
| Database unavailable | deterministic `unknown` snapshot with sanitized `database_<type>` source reasons |
| Partial history or legacy record | empty/degraded history or explicit exclusion issue; no inferred replacement |
| Missing authentication | `401`; the endpoint reveals no product state |
| Cross-product or arbitrary private field | excluded by token scope and field allowlist |

Raw database exception text is never returned. Every issue includes an actionable `recovery`
field. Reads never repair, migrate, accept, reject, execute, dispatch, infer with a model, invoke
an extension, or mutate provenance.

## 0.1.x compatibility policy

For 0.1.x, ACE guarantees the `ace landscape` command name, authenticated GET path, schema and
projection version values above, stable source record identifiers, content-derived snapshot IDs,
field semantics, deterministic ordering, assertion-state behavior, 256-record family bound,
sanitized failure codes, and read-only authority.

Additive optional fields and new issue codes may appear without a schema-version change. Removing
or renaming a required field, changing an existing field's meaning or type, changing identifier or
ordering rules, allowing a non-accepted assertion to become operational, or widening authority is
breaking and requires a new snapshot schema or projection version plus migration notes. Legacy
records without stable identity or product scope stay excluded until migrated.

The internal database layout, broad engine MCP/API surfaces, Atrium rendering, pagination, and
write/edit interactions remain experimental. Extensions may create records through their own
documented authority, but this kernel projection never imports or invokes extensions and the
kernel/extension dependency direction is unchanged.

## Reproduce the evidence

No provider credential, LLM, database, or private data is required:

```bash
uv sync --frozen
uv run python scripts/verify_g1_living_product_graph.py
```

The verifier checks structural acceptance, repeated and reordered execution, fresh-process replay,
failure examples, zero model calls, and zero domain writes. The input manifest and sanitized result
are in `evaluations/fixtures/g1_living_product_graph_manifest_v1.json` and
`evaluations/results/g1_living_product_graph_v1.json`.
