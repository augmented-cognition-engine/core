# ACE 0.8.0 unified Intelligence resource plane work packet

Status: **active 0.8C packet; facade, ledger/monitoring projections, and governed HTTP query implemented**
Public milestone: [issue #40](https://github.com/augmented-cognition-engine/core/issues/40)
Accepted base: `main@794183b` (0.8A architecture, AM4 lifecycle, completed 0.8B, facade,
ledger projection, and governed HTTP query)

## Outcome

ACE exposes one domain-neutral, authorized resource plane for people, applications, and Atrium.
Consumers can inspect the same Intelligence OS resources without reaching into legacy hosts,
inventing a second authority system, or learning Core's storage layout.

The plane is a rebuildable read model over authoritative Core state and Intelligence-owned
projections. It does not acquire sources, execute effects, grant authority, or become a new
persistence engine.

## Canonical resource families

The first public contract covers:

- Connections, Sources, and Source Health;
- Entities, Observations, Signals, Shifts, and Cases;
- Briefs, Monitors, Subscriptions, and Agents;
- Decisions, Actions, Outcomes, and Feedback; and
- Evidence Lineage, Uncertainty, Conflicts, Semantic Revisions, Context Manifests, and Memory Use.

Atrium may present product language over these families. In particular, **Opportunities** is a
filtered and ranked Case experience, not a second kernel concept. Domain Packs provide vocabulary,
policy, projections, and presentation hints without adding public resource kinds to Core.

## C1 — public query contract and application service

The C1 seam provides:

1. strict, frozen, versioned references, records, selectors, cursors, and pages;
2. stable product-scoped identities and immediately adjacent revision lineage;
3. exact provenance available no later than the projected resource revision;
4. explicit available, degraded, and tombstoned states;
5. point-in-time `as_of` and `available_at` cutoffs;
6. deterministic ascending pagination with content-addressed cursors;
7. current Core authority resolution for every page request; and
8. a rebuildable projection-reader port owned by adapters rather than the application service.

Queries and cursors never become bearer authority. Every page preserves the exact authenticated
principal, product, query digest, grant, operation, evaluation time, and Core authority-use receipt.
A cursor changes the read position but not the query identity. Resource queries use Core's existing
`observe_read` authority class; the resource plane does not invent a parallel grant vocabulary.

Readers fail closed if they widen product, resource-kind, subject, temporal, pagination, or result
size boundaries. Degraded results require explicit reason references. Tombstoned resources cannot
return payload material.

## Ownership

| Concern | Owner |
| --- | --- |
| Authentication, authority, governed state, durable receipts | Core |
| Resource meaning, evidence semantics, revision and projection rules | Intelligence |
| Authorized query composition and fail-closed boundary checks | Application |
| Source acquisition and read-model materialization | Adapters |
| Domain vocabulary, mappings, policy, templates, presentation hints | Domain Pack |
| Product navigation and human experience | Atrium |

Projections may be cached, but they must be fully derivable from governed state and source receipts.
They are never authoritative and must declare degradation when their dependencies cannot reproduce
the requested point-in-time view.

## Remaining 0.8C sequence

C2 binds the six existing immutable PREPARED/LIVE resource families—Observations, Entity Snapshots,
Signals, Shifts, Cases, and Briefs—to the same public plane. The adapter merges record spaces,
projects Entity Snapshots as public Entities, preserves exact lineage and payloads, filters by
subject and cursor, and remains reproducible when reconstructed over the same store. Unsupported or
unavailable buckets return explicit degradation while preserving available truth.

C3 exposes `POST /v1/intelligence/resources/query` as the first machine interface. The host derives
the authenticated context from a verified bearer token, persists an opaque authentication receipt,
requires the token's `observe_read` authority, resolves the current Core grant, and returns the same
public page contract. Historical data cutoffs are independent from login time; every page is
reauthenticated and reauthorized, while query identity remains stable across authentication receipt
refreshes for the same actor and exact selector.

The next additive projection contributor exposes the current Monitor and Subscription lifecycle
revision from the existing append-only monitoring ledger. It validates the complete contiguous
receipt chain, projects revoke as a payload-free tombstone, preserves immediate supersession,
declares incomplete or divergent chains as degraded, and composes with ledger resources through
disjoint family ownership. The host—not FastAPI—binds this composite reader to the same governed
query service.

0.8C must still add governed-state projections for the remaining canonical families and complete
packaged schema/import integrity. 0.8D must prove Atrium consumes this interface rather than
privileged internal state.

The 0.8C exit gate is one authorized query path that can reproduce the evidence-to-outcome resource
chain after restart, report partial truth honestly, and remain identical for World and Market
Intelligence.

## Acceptance

C1 passes only when:

1. all canonical families are represented without domain nouns;
2. public `ace.intelligence` and `ace.application` imports expose the contracts and service;
3. exact schema generation succeeds;
4. product, subject, kind, time, and pagination widening fail closed;
5. provenance, degradation, tombstone, and immediate-supersession rules are tested;
6. current Core authority is re-resolved on every request;
7. the resource plane imports no host, transport, connector, or extension implementation;
8. the exact eleven-tool MCP surface remains unchanged; and
9. no World, Market, UI, or provider code enters Core.

## Rollback

C1 is additive. Reverting its contracts, service, exports, tests, and this packet removes the public
facade without rewriting governed state or projections. No existing runtime path depends on it until
C2 installs an explicit adapter.
