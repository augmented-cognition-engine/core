# ACE 0.7F Agent Memory AM3 work packet v1

## Frozen coordinate and claim

AM3 begins at exact AM2 head `0938a63d577f817a68c61cbd8b56841c50d770e2` on
`codex/v0.7-agent-memory-am2`. PR #108 remains AM0 authority, PR #117 remains the exact
non-rewriting AC7+AM0 convergence, PR #118 remains AM1 authority, and PR #119 remains AM2
authority. AM3 does not rewrite those branches, PRs, identities, contracts, or claims.

AM3 establishes a bounded capability only: an authenticated later task can receive the smallest
eligible context set selected under an exact frozen policy and retrieval-state snapshot, and a
matched memory/no-memory comparison can establish a declared output or decision delta. Selection,
injection, reflection, material influence, correctness, and benefit remain distinct. AM3 never
claims benefit.

AM4 retention/export/erasure, AM5 governed evolution, AM6 impact calibration, autonomous policy
updates, provider credentials, package identity changes, public TaskCreate fields, MCP expansion,
delivery effects, and external repository work remain out of scope.

## Ownership and reuse decision

AM3 is additive over existing owners:

- AM2 immutable reconciliation decisions remain canonical assertion material.
- AM2's identifiers-only graph remains the bounded graph projection and is rebuilt from canonical
  immutable decisions.
- Core's `ImmutableRecordStore` and `SurrealImmutableRecordStore` remain the only durable receipt
  substrate; AM3 adds no table, migration, or database.
- Core runtime-use and the AM1/AM2 authorization resolver remain present-tense authority seams.
- AC1–AC7 composition continues to own participant, authority, execution binding, tools, plan, and
  run-manifest identity.
- `ace.context.manifest/v1` becomes the canonical AM3 expansion rather than a parallel context
  family.
- I3 `intelligence-use-receipt-v1` remains the owner of retained-intelligence material-use evidence;
  AM3 lineage stores only exact references.
- Existing search, embedding, and optional provider paths enter through provider-neutral signal
  ports. AM3 creates no search engine, vector store, cache, or provider-specific index.

The only required repair below AM3 is an implementation correction in AM2 graph construction:
correction candidates are classified as correction nodes on first insertion instead of being
inserted first as assertions and then rejected as a conflicting node kind. No AM2 contract,
identity, stored record, branch, PR, or claim changes.

## Versioned contract families

`ace/intelligence/contracts/agent_memory_recall.py` freezes content-addressed contracts for:

1. exact receiving task, composition plan, stage, participant, and run manifest;
2. authenticated private recall requests and independent ledger/knowledge/applicability selectors;
3. frozen fused-rank policy and exact policy/index/projection/head/cache-dependency snapshot;
4. per-signal availability, score, authorization evidence, and measured-or-explicitly-unknown
   telemetry;
5. authorized candidates, deterministic rank, selection, omission, budget, and degradation;
6. a separately authenticated instruction-policy request and resolution receipt;
7. Context Planner request/result and canonical `ace.context.manifest/v1` expansion;
8. content-free context-block evidence for profile, instruction, fact, uncertainty, decision,
   cognition, document, and code context;
9. query-aid derivation receipts that cannot grant authority or mint identity;
10. injection, reflection, decision-material, context-use, and I3 lineage receipts; and
11. matched memory/no-memory condition assignment and materiality comparison with benefit fixed to
    `unknown`.

Private request text and assembled bodies are not persisted in those public receipt families.
Context blocks persist source coordinates, lifecycle, uncertainty, freshness evidence, digest,
budget use, authorization receipt, and receiving stage only.

## Authorization order

`ContextPlannerService` authorizes separately before:

- recall request admission;
- retrieval-state resolution and inspection;
- instruction-policy resolution;
- candidate listing and each candidate inspection;
- structured lookup;
- each lexical, vector, entity, temporal, graph, diversity, reliability, lifecycle, or optional
  signal;
- current-correction resolution;
- graph query and graph receipt inspection;
- body fetch;
- instruction or ordinary context assembly;
- Context Manifest inspection;
- composition consumption; and
- context-use receipt creation.

Authorization failures use one bounded non-disclosing error. A missing resource and an inaccessible
resource cannot be distinguished through the public AM3 service.

## Instruction-policy isolation

Instruction policy never enters relevance ranking. The instruction resolver accepts only exact
already-admitted policy references through its own authenticated channel and returns current-head
evidence plus private policy material. A blocked, stale, mismatched, missing, or body-digest-invalid
resolution stops context assembly. Source statements, system/tool/assistant content, ordinary
assertions, query aids, Packs, overlays, models, memories, and composition policy cannot populate
that channel.

## Retrieval and ranking

Structured lookup covers exact identity, admitted instruction reference, current governed
correction, uncertainty, and current-state questions. It uses only exact structured coordinates and
stops before relevance-provider calls when it satisfies the request.

Fused retrieval uses the frozen weighted signals below when available:

- existing lexical signal;
- existing vector signal;
- exact entity/semantic target;
- independent temporal eligibility;
- bounded AM2 graph distance;
- source diversity/independence;
- explicitly governed source reliability; and
- current correction, uncertainty, and lifecycle priority.

Personalized, spatial, and prior-use signals remain optional ports and are unavailable unless an
existing provider-neutral owner supplies them. An unavailable signal contributes zero under the
full frozen denominator, reports a reason, and never defaults to a perfect score. External signal
snapshots must match an exact index, projection, policy, or canonical-head coordinate in the
request. Candidate ties resolve by aggregate score descending and candidate reference ascending.

Progressive resolution stops at the first safe satisfying tier. This implementation supports
structured lookup and fused retrieval with bounded graph expansion. No dependency-valid memory
response cache or synthesis owner exists in the integrated base, so AM3 does not invent either.

## Context and composition

The Context Manifest binds the exact recall receipt, selected and omitted candidates, instruction
resolution, retrieval snapshot, receiving coordinates, blocks, budgets, omissions, and degraded
states. Bodies remain private `AssembledContextBlock` values and are never included in the durable
manifest.

`CompositionContextManifestBridge` invokes the existing AC runtime-authority port for the exact
manifest, participant, operation, grant, scope, and policy at the current clock. It returns only the
manifest and selection-receipt exact references after current heads pass. It cannot select a
participant, grant authority, activate policy, widen tools, change a plan, or change a run manifest.

## Material-use rule

The state progression is monotonic:

`selected → injected → reflected → decision-material`

Each step requires its own receipt. A decision-material receipt additionally requires an exact
matched comparison, a bounded changed-field set, and an exact I3 intelligence-use receipt. The
matched comparison rejects any difference in task, prompt contract, provider, model, configuration,
decision schema, or toolset. A changed declared field establishes only material influence. Benefit
is always `unknown` in AM3.

## Required verification matrix

- deterministic structured lookup and fused replay;
- independent temporal selectors and unknown-time behavior;
- correction/uncertainty priority and superseded/lifecycle omission;
- authorization before each signal, graph, body, assembly, and receipt read;
- cross-scope and nonexistent-resource non-disclosure;
- stale or missing policy, index, projection, graph, canonical head, and cache dependency;
- missing signal, provider failure, unknown telemetry, budget exhaustion, deterministic ties, and
  truncation;
- instruction-channel and query-aid authority/identity attacks;
- exact replay, divergent conflict, concurrent no-op, and atomic append failure;
- real SurrealKV restart, fresh service/process, exact manifest reopen, canonical graph rebuild, and
  stale-manifest refusal;
- independent later invocation using eligible memory after restart; and
- provider-free matched no-memory materiality with benefit unknown.

## AM4 entry gate

AM4 remains closed until the control tower accepts an AM3-only stacked draft, exact verification
evidence, installed-wheel hashes, restart/rebuild proof, privacy and authority scans, explicit
limitations, and the material-influence/no-benefit boundary. AM3 must not begin retention, export,
erasure, or governed memory evolution work.
