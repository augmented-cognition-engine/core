# Changelog

Notable user- and contributor-visible changes are recorded here.

## 1.0.2

### Durable runtime authority use

- Normalize the same SurrealDB JSON-shaped fixed-grant representation at the runtime-use resolver,
  so export, two-step deletion, and other exactly authorized operations continue to work after a
  process restart while retaining scope, operation, lifecycle, head, and receipt checks.
- Add regression coverage for both grant loading and current authority-use resolution after a full
  governed-state JSON round trip.

## 1.0.1

### Durable local-owner restart verification

- Accept the JSON-shaped representation returned by SurrealDB when re-validating the four fixed
  local-owner grants after an API restart, while retaining exact material-hash, approved-material,
  lineage, and receipt comparisons that fail closed on any real change.
- Add regression coverage that forces every governed-state record through the same JSON boundary
  as durable storage before the idempotent bootstrap recheck.

## 1.0.0

### Stable single-user Intelligence OS

- Complete the guided single-user journey from Intelligence selection and exact reviewed source
  binding through permission/readiness checks, activation, source health, and a cited first Brief.
- Add append-only later-source updates with retained prior Briefs and a semantic what-changed/why/
  evidence diff through the same governed resource path.
- Publish signed local-owner authority for building and reading personal intelligence without
  silently granting source, delivery, or external-effect authority.
- Add deterministic hybrid retrieval using indexed lexical and vector plans, reciprocal-rank
  fusion, product/type/tag isolation, correction promotion, a no-answer gate, and explicit degraded
  receipts across HTTP and the unchanged eleven-tool MCP surface.
- Preserve provider neutrality across direct API-key, subscription-backed Codex and Claude CLI,
  OpenAI-compatible, and local Ollama routes; a consumer subscription is used through its signed-in
  CLI route rather than treated as a transferable API key.
- Complete the bounded World and Market solution-bundle paths through trusted, separately installed
  Builders. Market additionally proves a content-addressed direction package, exact package and
  destination approval, acknowledged reference delivery, a later Outcome, and proposal-only
  Feedback using the existing Core handoff and learning contracts.
- Keep the release single-user and single-node. Universal connector/destination catalogs, managed
  hosting, collaboration, autonomous delivery or policy application, customer-corpus relevance,
  multilingual quality, high concurrency, and distributed availability remain explicit post-1.0
  work or non-claims.
- Publish the unchanged reference workspace-action implementation as distribution 0.4.1 with an
  `ace-core>=0.8.0,<1.1` compatibility envelope. Installation still grants no operation authority.

## 0.8.3

### External-pack compatibility and source time

- Add the public conformance seam external packages use to resolve and verify exact installed
  Domain Packs without importing the private host runtime.
- Preserve source publication time separately from observation and ingestion time in declarative
  source mapping, including explicit unknown publication time.
- Export the durable Intelligence build-host composer through the public Application surface so
  isolated installed-surface conformance cannot depend on test import order.
- Carry the merged single-user Builder hardening through active-session first-Brief binding while
  preserving schema head v177, exactly eleven MCP tools, and the 0.8 compatibility line.

## 0.8.2

### Intelligence Catalog and outcome-led onboarding

- Discover all admitted Intelligence onboarding profiles through the existing authenticated
  resource plane and deduplicate them by durable profile identity.
- Open Atrium by asking what intelligence the user wants, with domain-provided starter questions
  and source groups plus a Core-owned Custom Intelligence path.
- Keep domain vocabulary and selection metadata in inert Domain Packs; catalog discovery grants no
  source, monitor, installation, or activation authority.
- Preserve schema head v177, the 24-kind resource plane, exactly eleven MCP tools, and the 0.8
  compatibility line.

## 0.8.1

### Intelligence Builder product experience

- Project declarative, non-authorizing onboarding profiles and every append-only Intelligence
  Builder session revision through the existing authenticated resource plane. The projection adds
  no second store, grants no source or monitor authority, and exposes blocked/retrying state as
  explicit degradation.
- Bind Atrium's onboarding progress to durable Builder state instead of presentation animation.
  Proposal-only plans remain visibly proposed; completion and first-Brief navigation appear only
  when the exact session reaches `first_briefing_ready`.
- Add the paired World AI Command Center acceptance journey over four real builder agent roles and
  two already-admitted recorded official-source lineages.
- Make Atrium the Intelligence OS command center with Intelligence, Opportunities, Agents,
  Connections, and Strategy as first-class destinations while keeping downstream Work outside the
  product center.
- Define Opportunities as evidence-backed decision openings across Cases, material Shifts, and
  early Signals rather than as leads or tasks.
- Establish the ACE design system with cognitive blue as the primary identity, cyan reserved for
  live intelligence, violet for agent/memory composition, and green for verified outcomes.
- Add a local-only immutable resource replay for the World AI Command Center demo without adding a
  second persistence, authority, or domain state path.
- Forward the shared resource-detail sheet overlay ref through its Radix boundary so opening cited
  Brief details remains free of React runtime warnings on desktop and mobile.
- Project canonical Brief sections and every decision-facing Signal, Shift, Case, Decision,
  Action, Outcome, and Feedback record into a visual **What changed / Why it matters / How we know /
  When it changed** grammar in Atrium. Generic fallbacks disclose missing materiality or event time
  instead of inventing it; unknowns, limitations, receipts, and lineage remain available in the
  same governed resource detail.

The patch preserves schema head v177, exactly eleven public MCP tools, the Core 0.8 compatibility
line, and the existing reference action adapter 0.4.0 boundary.

## 0.8.0

### Intelligence Operating System

- Add one authorized, point-in-time Intelligence resource plane over Sources, Connections,
  Observations, Entity state, Signals, Shifts, Cases, Briefs, Monitors, Subscriptions, Agents,
  Decisions, Actions, Outcomes, Feedback, governed memory, and provenance. Exact revision identity,
  product scope, cursoring, restart reconstruction, and explicit partial/degraded state are shared
  by machine consumers and Atrium.
- Realign runtime ownership around the public `ace.core`, `ace.intelligence`, and
  `ace.application` boundaries. Core owns durable cognition, identity, state, authority, and
  outcomes; Intelligence owns domain-neutral sensing and orientation; Domain Packs remain inert
  vocabulary and policy; separately reviewed connectors/adapters own I/O and effects.
- Add rebuildable projections for live sources, monitored owner lifecycles, governed Agents,
  Decisions, Actions, Outcomes, non-effective Feedback proposals, authorized memory use, and
  evidence lineage without creating a second persistence or authority path.
- Complete authorized Agent Memory through AM4 retention and erasure while preserving explicit
  recall authority, material-use attribution, reconstruction, non-reappearance, and the eleven-
  tool MCP boundary.

### Atrium and cross-domain proof

- Rebuild Atrium as a briefing-first Intelligence OS workspace with first-class Intelligence,
  Opportunities, Agents, Connections, and Strategy; keep Work downstream. Ask ACE ranks only
  authorized resource records and cites exact revisions. Empty, partial, degraded, desktop, mobile,
  keyboard, and screen-reader states are covered in the repository-delivered preview.
- Reproduce the complete public resource contract through independent World and Market
  Intelligence repositories. World proves a recorded official-source path through reviewed Action
  and measured Feedback; Market proves a competitive-price path with explicit `no_action` and
  non-live Feedback. No domain noun or policy branch enters Core.
- Preserve proposal-only learning, inert Domain Packs, explicit source/effect authority, schema
  head v177, the single-node trusted-adapter topology, and exactly eleven public MCP tools.
- Version the Core distribution at 0.8.0 and the separately packaged reference action adapter at
  0.4.0 with an `ace-core>=0.8.0,<0.9` dependency. Its unchanged executable implementation retains
  capability artifact identity 0.1.0.

## 0.7.0

### Intelligence Builder Foundation

- Add the provider-free `Connect → Map → Watch → Brief → Activate` onboarding journey through five
  separate proposal services: Connection, Ontology, Intelligence, Briefing, and Activation. Exact
  human/Core approval remains required before activation.
- Stabilize the generated Domain Pack contract with machine-readable schemas, deterministic
  compilation, compatibility negotiation, golden-fixture conformance, structured diagnostics,
  content-addressed receipts, and fail-closed activation. Packs remain inert declarative data.
- Add governed Agent Composition through AC7: provider-neutral contracts, task and lifecycle
  bridges, participant governance, delivery/export, measured evaluation, and policy admission.
  Composition policy cannot grant authority or manufacture participant eligibility.
- Add authorized Agent Memory through AM3: foundation contracts, episodic experience, typed
  assertions and corrections, explicit reconciliation, authorized recall, visible ranking and
  omissions, and canonical Context Manifests. Memory cannot select agents, widen tools, or rewrite
  run authority.
- Preserve one Core + Intelligence install, schema head v177, naked-kernel startup, and exactly
  eleven public MCP tools.

### External acceptance and release boundary

- Reproduce the activation lifecycle against materially distinct World and Market Intelligence
  consumers through unchanged Core APIs, including exact effect/capability/authority preview,
  restart, separately approved upgrade and rollback, runtime bindings, and fail-closed stale
  conformance.
- Version the Core distribution at 0.7.0 and the separately packaged reference action adapter at
  0.3.0 with an `ace-core>=0.7.0,<0.8` dependency. The unchanged adapter implementation retains
  its 0.1.0 capability artifact identity.
- Keep the release a developer preview for the documented single-node topology. The supported
  artifact does not claim a graphical workspace, hostile-code isolation, distributed operation,
  autonomous learning, general memory benefit, or general real-world causal correctness.

## 0.6.0

### Measured Intelligence

- Add domain-neutral, versioned criteria, condition, evidence, evaluation, and governance-proposal
  contracts that link an intelligence artifact or cognition revision to exact material-use,
  Decision, reviewed Action, observed-result, Outcome, control, and cutoff provenance.
- Classify bounded matched evidence as `useful`, `harmful`, or `unproven` without accepting a
  caller-supplied quality label. Missing attribution, mismatched conditions, future leakage,
  unavailable outcomes, duplicate evidence, and insufficient matched support remain explicit.
- Persist evaluation and proposal receipts atomically through Core's append-only record boundary.
  Exact historical replay survives restart; divergent replay, scope drift, and unauthorized
  promotion fail closed.
- Keep promotion, rejection, rollback, and retirement proposals non-effective, non-selectable, and
  unapplied. A separately authorized reviewer may record an accept/reject `no_action` Decision but
  cannot silently change effective state.

### Release and hardening boundary

- Version the Core distribution at 0.6.0 and the separately packaged reference action adapter at
  0.2.0 with an `ace-core>=0.6.0,<0.7` dependency. The unchanged adapter implementation retains its
  0.1.0 capability artifact identity.
- Add the issue #49 F1 generation guard and durable receipt reconciliation, and pin the legacy
  optimizer query to `self_optimizer_proposal`. F3 remains unresolved and tracked separately under
  its explicit containment and 2026-11-05 deadline.

### Owner-governed monitoring

- Add public append-only lifecycle requests, receipts, and a durable application service for one
  principal-owned Monitor or Subscription. Create, pause, resume, and terminal revoke preserve the
  exact intent and owner binding, fail closed on divergent replay, and reopen across service
  restarts through Core's immutable-record port. A stable append-once lifecycle anchor prevents a
  revoked intent from being silently recreated under a new transition key; append-once sequence
  slots prevent two transitions from branching off the same prior receipt.
- Add explicitly requested sensing-window requests, evaluations, receipts, and a durable service.
  Each bounded window records exact lifecycle revisions, source transactions, accepted/replayed
  material, and one routed-or-suppressed disposition. Paused or revoked windows require zero
  acquisition, stale lifecycle receipts fail closed, and corrections cannot be suppressed as no
  material change.
- Keep the new surface effect-free: it grants no scheduler, source transport, delivery,
  publication, persuasion, Decision, Outcome, or external-action authority.

## 0.5.0

### Reasoning into Action

- Carry an exact approved Decision into a bounded action lifecycle without granting Domain Packs
  executable authority. Core validates the Decision, adapter identity, permissions, target,
  preconditions, timeout, and declared side effects; persists admission before an effect; and
  records success, failure, partial effect, cancellation, timeout, or restart uncertainty
  honestly.
- Add durable exact-material human review before execution, separate post-effect verification,
  linked repair as a new successor rather than a silent retry, and a separate promotion decision.
  Unknown effects cannot be retried, and success never promotes itself.
- Add constructor-only host composition and restart-safe action replay. An admitted action without
  a terminal receipt reopens as uncertain after restart and is never implicitly executed again.
- Add the separately packaged `ace-reference-workspace-action` 0.1.0 adapter as a bounded reference
  implementation. It performs one create-only workspace export, imports only the public Core
  contract, is never dynamically discovered, and is not included in the `ace-core` distribution.

### Governed task execution

- Add negotiated durable cancellation, declared wall-clock limits, terminal resource receipts,
  generic attempt identity, and restart-safe linked replay for eligible direct tasks.
- Keep the supported execution topology explicit: single-node host composition with trusted
  in-process adapters. This release does not claim distributed exactly-once effects, remote
  execution, compensation, arbitrary filesystem access, untrusted-code isolation, or unrestricted
  autonomy.

## 0.4.4

### Governed Cognition source evidence

- Normalize task-source evidence to JSON-native values before computing its canonical proposal
  hash. Teaching reusable cognition from completed tasks now handles nested database-native
  timestamps without weakening deterministic provenance.

## 0.4.3

### Governed Cognition persistence correctness

- Preserve exact canonical JSON alongside queryable SurrealDB object projections for cognition
  identities, revisions, heads, proposals, review receipts, selection receipts, and use receipts.
  This prevents flexible-object normalization from changing nested optional material across a
  database round trip and invalidating content-derived identities.
- Prefer the canonical payload on reload while retaining read compatibility with records written
  before schema v176. A real-database restart regression covers proposal, approval, discovery,
  material use, lifecycle governance, and receipt reload with nested null material.

## 0.4.2

### Governed Cognition builder experience

- Add the `ace cognition` command family over the existing authenticated cognition API: teach from
  a task, inspect proposals and semantic diffs, record authorized human review, require materially
  attributed fresh use, inspect revisions/heads/receipts, and govern rollback, reactivation,
  disablement, expiry, or retirement.
- Keep authority and persistence unchanged. The CLI adds no model write path, refuses to report a
  fresh task as successful cognition use without matching non-empty selection/use revision IDs and
  a material-use hash, and leaves the eleven-tool MCP surface unchanged.
- Add a builder guide for the supported lifecycle and its explicit GC1 boundary.

## 0.4.1

### Intelligence public surface

- Export the per-statement epistemic-status and Case-bound Brief synthesis contracts from
  `ace.intelligence`. `ace/intelligence/contracts/epistemic.py` existed but was not re-exported at
  all, and twelve Case-bound synthesis contracts were missing from
  `ace.intelligence.contracts`. An external Domain Pack consuming the published surface could not
  reach them without importing a private module path.
- Additive only: 23 names are re-exported, no contract, behaviour, or record identity changes. The
  pure-contract boundary is preserved — the pack compiler and activation machinery stay in
  `ace.intelligence.packs` and are deliberately not promoted to the top-level surface, as
  `tests/intelligence/test_contract_boundaries.py` requires.

## 0.4.0

### Governed Cognition

- Add governed LIVE source ingress as a packaged public application service: one exact resolved
  source definition is captured through an activation-bound, authority-checked adapter and admitted
  atomically as five durable records (acquisition receipt, canonical source snapshot, Observation,
  Entity Snapshot, admission receipt) under four rechecked governed-state heads.
- Add the governed LIVE Intelligence bridge and LIVE Brief synthesis services: admitted snapshots
  derive Shift -> Signal -> attention dispositions and route-triggered Briefs through Core governed
  reasoning, with exact idempotent replay and restart reopening of every admission.
- Compose LIVE cognition into the host exclusively through the private
  `core.engine.core.live_cognition` adapter: source connectors register in a bounded
  constructor-supplied registry keyed by exact artifact identity, with no dynamic entry-point
  loading, no embedded code in domain packs, and no persistence path outside Core's
  immutable-record port.
- Source acquisition fails closed on scope, URI, redirect, DNS/IP-rebinding, payload-size, digest,
  replay, timing, and authority violations; authority-use receipts remain single-use and
  non-reusable across admissions.

### Compatibility, security, and evidence

- Keep the public MCP surface at exactly eleven tools and preserve extension-disabled
  (naked-kernel) startup without composing any LIVE service.
- Add architecture gates proving public `ace` contracts stay host-free, LIVE services depend only
  on public ports, and host adapters remain the only `core.engine` edge into the public package.
- Preserve schema head v175 with additive, append-only governed-state and immutable-record
  migrations; restart and replay behavior is exact across service restarts.

## 0.3.1

### Productized State

- Add one supported extension-first journey from authenticated product-context ingestion through
  inspectable state, reasoning, decision capture, correction, restart, and materially changed later
  reasoning.
- Add deterministic Product State capability discovery and ingestion under Core-owned token scope.
  Extensions own source mapping and domain ontology; Core owns identity, validation, persistence,
  replay, isolation, and receipts.
- Add the focused `ace state capabilities`, `ingest`, `invoke`, `correct`, and `inspect` workflow
  without widening the eleven-tool MCP contract.
- Extend the read-only Living Product Graph projection with allowlisted ingestion, belief,
  transition, task-evidence, material-use, rollout, reconciliation, promotion, decision,
  deliberation, and correction receipt families.

### Compatibility, security, and evidence

- Require canonical authenticated product scope for ingestion and reject missing, malformed, or
  cross-product adapter output before persistence; the legacy default-product fallback is not
  available on this boundary.
- Correct real SurrealDB product filtering to bind typed record IDs, retaining regression coverage
  for complete scoped inspection and empty foreign-product reads.
- Preserve schema head v171, support schema-zero and v168→v171 journeys, keep trusted extensions
  optional, and retain exact replay, restart, interruption, and degraded-state behavior.
- Publish the frozen provider-free Fjord Operations journey and bounded acceptance receipts using
  fictional public-safe data.

### Known limitations

- Productized State is supported only for the documented single-node topology with synchronous,
  explicitly trusted installed Python extensions executing in process.
- It does not establish hostile-code isolation, distributed ordering, multi-writer or multi-region
  guarantees, general real-world causal accuracy, autonomous learning, a general world model, or
  beneficial impact.

## 0.3.0

### Governed cognition

- Add one typed, versioned cognition model for stable identity, immutable revision, scoped active
  heads, proposals, human review receipts, bounded selection/use receipts, and effectiveness
  observations across recipes, instruments, frameworks, tools, perspectives, and procedural
  knowledge.
- Exercise the lifecycle `teach → propose → inspect → approve → use → measure → revise or retire`
  through an authenticated cognition API, durable SurrealDB persistence, real restart coverage, and
  additive receipt projections on the existing eleven-tool MCP boundary.
- Route the composer and legacy skill, framework, and self-optimizer facades through the canonical
  catalog and governance service. Legacy writes become reviewable proposals and cannot fabricate
  approval or activation provenance.

### Compatibility, security, and operations

- Add pre-registration cognition-contract negotiation. Current Core adapts the v0.2.0 reference
  extension, while v0.2.0 Core refuses the current reference before partial registration; unknown
  future or incompatible contracts fail closed.
- Add bounded extension manifests, owner/scope and route collision checks, resource traversal and
  digest validation, explicit unsupported registrations, independent-consumer wheel/sdist tests,
  zero-extension verification, and retained package-matrix receipts.
- Add additive schema migrations v169-v171, complete bounded legacy inventory/import receipts,
  one-for-one persisted read verification, an operator runbook, threat model, and independent-review
  evidence contract.

### Known limitations

- Only trusted in-process extension code is supported. Untrusted extension execution, distributed
  approval or activation, and exactly-once external side effects remain unsupported.
- Cognition use and effectiveness receipts distinguish `helped`, `hurt`, `unproven`, `unused`, and
  `stale`; they do not establish autonomous learning or broad beneficial impact.
- Every real upgraded deployment must retain its own complete legacy inventory receipt before
  deleting a legacy table, selector, executor, or facade.

## 0.2.0

### Supported

- Add the product-scoped State Engine Core contract: bounded adapter manifests, exact item and
  batch receipts, grounded temporal source/entity/claim/event records, deterministic candidate
  receipts and evidence packs, reviewed belief-state projections, transition hypotheses,
  action/no-action consequence rollouts, later-outcome reconciliation, I3 reasoning-use receipts,
  and authority-gated promotion/correction lineage.
- Make the ordinary durable task path own State Engine execution rather than leaving it in an
  evaluator. Authenticated reference task actions can prepare a bounded evidence query and rollout;
  terminal Core task execution persists actual reasoning use and a promotion proposal, and the
  existing task/status, intelligence, and Living Product Graph reads expose the resulting receipts.
- Add a supported single-node adapter and operations boundary. Core owns product scope, stable
  identity, validation, transactions, replay, and receipts; extensions own connectors, extraction
  policy, source mappings, and domain ontologies.
- Keep the supported public MCP adapter at exactly eleven HTTP-backed tools. State Engine contracts
  and reference actions do not add a twelfth tool or a second memory plane.

### Reliability and operations

- Replace ambiguous observation processing with database leases, heartbeats, retry/dead-letter
  states, immutable synthesis-outcome receipts, and a continuously supervised worker drain. A
  terminal green receipt cannot precede semantic persistence, and restart recovery is explicit.
- Add append-only product lifecycle and operational receipts, bounded archive/reactivation,
  health/backlog reporting, and a supervised API/worker Compose topology.
- Raise the base `aiohttp` and `cryptography` safety floors to 3.14.3 and 50.0.0 respectively,
  excluding PYSEC-2026-3545/3546/3547 and PYSEC-2026-3552 from fresh installations.
- Validate exact replay, interruption recovery, current-head migration resume, backup/restore,
  product isolation, adapter equivalence, and fresh database/API/worker/thin-client restarts at
  schema v168.

### Scale and readiness

- Retain the frozen TP8 result for 200,000 initial claims and 236,000 semantic records, followed by
  220,000 claims and 256,000 semantic records after the sustained sample. The measured single-node
  path includes bounded ingestion, candidate/evidence queries, belief projection, transitions,
  rollouts, replay, restart, migration, backup/restore, and isolation.
- Record K1, K2, and K3 as `ready` for their bounded single-node meanings. The repeated readiness
  audit produced 40/40 exact transition cases and replays across eight domains, five predeclared
  calibration sequences, and 5/5 fresh-process task/promotion/restart/retrieval/correction journeys.

### Compatibility and migration

- Align the distribution, `ace` import, engine and health output, thin MCP client, reference
  extension, lockfile, container metadata, and trusted-publishing default at `0.2.0`.
- Add restart-safe migrations v161-v168. Schema zero and the public 0.1.4 predecessor upgrade to
  v168 are supported; current-head partial application resumes through the ordinary installer.
- Preserve existing CLI identities, the eleven-tool thin MCP contract, I1-I3 receipt meanings, the
  existing `insight` memory plane, and current/N-1 extension-envelope conformance.

### Experimental

- The reference `evidence-query` and `promotion-review` task actions remain on the experimental
  extension-invocation HTTP surface. They are real production-router integration, but are not a new
  stable CLI or MCP contract and do not establish general exactly-once external effects.
- Candidate weights, physical indexes, deterministic transition/rollout implementations, and broad
  automatic promotion policy remain versioned/internal or experimental behind stable receipts.

### Known limitations

- The measured deployment is one ACE API/worker deployment and one SurrealDB/SurrealKV database.
  Distributed ordering, multi-writer consistency, multi-region failover, and exactly-once delivery
  across independent databases are not claimed.
- Arbitrary interruption inside historical pre-v142 migration files is unsupported; restore a
  pre-migration backup and replay schema installation instead. Python 3.12 remains required.
- Synthetic/public-safe fixtures and deterministic provider-free trials establish contract,
  isolation, replay, and bounded performance—not real-world causal accuracy, calibrated
  forecasting, autonomous learning, a general world model, decision quality, or L1 beneficial
  impact.

## 0.1.4

### Fixed

- Restore the complete 177-prompt built-in reasoning-framework library. Schema v158 makes the
  three nested framework object fields `FLEXIBLE`; API and worker startup now seed and verify every
  authored prompt and fail closed instead of silently substituting generic reasoning text.
- Make self-optimizer framework proposals persist and materialise correctly. Schema v160 accepts
  nested proposal drafts and evidence, proposal generation writes its required product/type/name
  identity, and approval creates product-scoped frameworks with complete affinity and
  composability data before marking the proposal approved.
- Correct relational-assertion maintenance: use typed record IDs while pruning projections,
  canonicalise symmetric endpoints, and contest contradictory directional assertions across
  unordered endpoint pairs.
- Rank insight-neighbour recall by proposal confidence rather than saturated evidence strength,
  preserve `informed_by` edges through the resolved insight specialty, and cast conflict-detector
  subdomain bindings to records.
- Finish the runner's product-scoping schema migration and allow recommendation queue metadata.
  API startup and restart verification now exercise that schema against the real database.
- Make schema installation fail closed on unknown database errors, validate required runtime
  tables, require API startup and test schema setup to succeed, and lint modern migrations for
  restart safety.

### Runtime and migration

- Upgrade the default standalone SurrealDB server from 3.1.4 to 3.2.3 and the Python client from
  the 1.x line to `surrealdb` 2.x.
- Raise GitPython to 3.1.55 or later to exclude four fixed upstream security advisories.
- Add restart-safe schemas v158-v160 for framework nested objects, runner product scope, and
  self-optimizer proposal payloads. Existing installations are upgraded in place; fresh schema
  replay is validated through v160.
- Clarify that `ace doctor` certifies operational readiness—configuration, connectivity, schema,
  authentication, provider routing, API, and MCP registration—not stored-graph correctness.

## 0.1.3

### Supported

- Add the bounded `deliberation-receipt-v1` projection through existing task/status, CLI, thin
  client, and Living Product Graph reads. It records observable reasoning-shape selection,
  execution-identity-backed contributor artifacts, artifact-grounded conflicts, synthesis
  dispositions, and honest partial/degraded coverage without exposing hidden reasoning.
- Preserve the existing async task contract, I1 decision/correction and I3 intelligence-use
  receipts, and exactly eleven public MCP tools; no write or execution authority is added.

### Experimental

- Add the authenticated `extension-invocation-v1` HTTP envelope and
  `extension-invocation-receipt-v1` projection for extension-owned reference resolution and
  outcome projection over Core's durable task lifecycle. Failed or restart-degraded work resumes
  as a linked successor attempt, never as a fictitious continuation of a lost provider stream.
  This adds experimental HTTP execution authority but no CLI command or MCP tool; E1 remains not
  ready.
- Expand the experimental runtime with deterministic capability negotiation, schema discovery,
  product/user/workspace-scoped listing and attempt history, strict resolved-record provenance,
  idempotent concurrent resume, explicit retry policy/actor/reason lineage, cooperative
  cancellation states, output-contract validation hooks, immutable artifact references, and a
  provider-free reusable conformance helper. The shipped reference extension now registers the
  minimal `product:product-check` action.
- Harden the candidate Extension SDK with unambiguous tuple registration identities,
  registration-time action bounds, duplicate lifecycle rejection, self-validating public
  manifests, callable-free discovery, immutable-artifact conformance checks, an action handle
  returned from registration, and an independently executable scaffold conformance example.

### Migration

- Add schema v156 as one optional task receipt field and v157 as optional extension invocation,
  receipt, retry-lineage, cancellation, and retry-parent index fields without rewriting legacy rows.

### Release maintenance

- Align the Python distribution, import package, engine, thin MCP client, reference extension,
  editable lockfile, and trusted-publishing workflow at `0.1.3`.
- Separate durable product and contributor documentation from point-in-time evidence and design
  notes, with `ROADMAP.md` as the versioned operational authority and packaged evidence/design
  archives retained for auditability.
- Make Layer 5 decision-context integration tests independent of nondeterministic host scheduling
  while separately pinning production timeout defaults, index selection, and explicit degraded
  timeout behavior.
- Preserve Python 3.12 support, the existing CLI identities, and exactly eleven public MCP tools.
- Keep extension invocation explicitly experimental: this release does not establish an N-1
  compatibility promise, isolated execution, distributed recovery, or exactly-once external effects.

### Known limitations

- Inspectable attribution is bounded final-artifact and execution evidence. It does not establish
  correctness, causality, benefit, decision quality, or access to hidden chain-of-thought.
- Extension task actions are trusted in-process code. Attempt-level resume is not distributed
  recovery or exactly-once external execution, and a complete receipt does not establish a
  correct or beneficial domain outcome.
- Cancellation is cooperative and process-local; it cannot undo completed provider calls or
  extension-owned external side effects. Capability negotiation and task actions remain
  experimental until the multi-package conformance/version-skew matrix is complete.

## 0.1.2

### Supported

- Add the versioned, authenticated, strictly read-only `ace landscape` journey for inspecting the
  Living Product Graph with stable identity, evidence, provenance, uncertainty, assertion history,
  deterministic ordering, bounded degraded behavior, and no change to the eleven-tool MCP surface.
- Complete I1 decision and correction inspection with structured evidence, assumptions,
  alternatives and reconsideration conditions; all four human dispositions; preserved
  supersession, invalidation, contestation and expiry; explicit incomplete provenance; fail-closed
  authorization, isolation and redaction; and restart-safe schema replay.
- Add the bounded `intelligence-use-receipt-v1` projection to existing task/status and Living
  Product Graph reads. It distinguishes retrieval, injection, reflection, and exact material I1
  decision deltas while preserving null, stale, invalidated, contested, harmful, mismatched, and
  failed comparisons.
- Preserve the public CLI and exactly eleven thin MCP tools. No new public write or execution
  authority is introduced.

### Provider and runtime

- Add the explicit ChatGPT-subscription Codex route with persistent `codex app-server` transport,
  `codex exec` compatibility mode, exact model/effort provenance, bounded structured output, and
  no automatic metered API-key fallback.
- Add process-wide provider admission control and task-level calls, tokens, latency, retry, route,
  and degraded-state accounting.
- Durable public task receipts now expose contributor and phase coverage in an `execution` block,
  including explicit partial-result attention without discarding usable output.

### Experimental

- Freeze the additive continuous-delta F1 foresight foundation: conditional forecast,
  intervention, indicator, outside-view, comparator-plan, structured-measurement, resolution, and
  proper interval-score contracts. These engine/HTTP surfaces remain experimental rather than a
  general 0.1.x compatibility promise.
- Add bounded interactive-output routing and advisory adaptive stage plans with inspectable route
  evidence; these do not add public MCP tools or unattended execution authority.
- Add the `ace.foresight.impact-evaluation/v1` L1 evidence gate. Its first checksum-frozen public-
  data probe is deliberately recorded as `benefit_not_established`; L1 remains candidate and F2
  remains gated.

### Fixed

- The experimental conflict workflow now persists product-scoped pending conflicts and
  quarantines both claims atomically, writes a durable attention signal, and returns provenance-
  bearing claims and resolution actions through the authenticated conflict API.
- API startup and the standalone schema installer share one audited historical-migration
  compatibility policy while migrations v142 and later remain fail-closed.
- Provider-selection tests now isolate explicit local subscription configuration, and roadmap
  projection tests no longer depend on rows in a developer database.

### Migration

- Add schema v143-v155 for conflict visibility, I1 decision/correction receipts, the F1 continuous
  foresight evidence chain, and the I3 intelligence-use receipt. Migrations are additive and
  existing public CLI/MCP identities remain unchanged.

### Known limitations

- L1 beneficial impact is not established: the current retrospective probe did not beat
  persistence, cluster-adjusted intervals include zero, and matched model-only plus verified
  intervention/confounder evidence are still required.
- F1, bounded adaptive routing, and the broader foresight HTTP engine remain experimental.
- Python 3.12 remains the supported interpreter, and the complete self-hosted Compose journey still
  uses a source checkout for pinned runtime assets.

## 0.1.1

### Supported

- Lead the public entry journey with one product-builder quickstart: bring a real decision,
  choose an existing model route, start the self-hosted runtime, and receive a recommendation.
- Keep advanced architecture, MCP, provider, extension, and manual-operation material available
  through progressive disclosure after the quickstart.

### Fixed

- Use concise outcome-led package metadata and absolute public links that continue to work when
  the README is rendered on PyPI.
- Make installed `ace setup --help`, missing-runtime guidance, provider selection, `ace doctor`,
  and service recovery point to concrete commands or public documentation without assuming
  repository knowledge.
- Include the R1 setup fixes for optional Discord configuration, Docker/Colima recovery, API log
  discovery, failed activation exit status, managed-process shutdown, and doctor recovery actions.

### Release maintenance

- Keep distribution, import package, engine, thin MCP client, reference extension, and public
  capability versions aligned at `0.1.1`.
- Default manual trusted publishing to `v0.1.1` and fail closed when a release tag does not match
  package metadata.

### Known limitations

- The complete self-hosted first-recommendation flow still uses a source checkout for its pinned
  Compose stack and local service scripts; the wheel provides imports and commands but does not
  silently download or provision runtime assets.
- Python 3.12 is the supported interpreter. R1 usability evidence is based on isolated AI-operated
  proxy trials rather than independent human testing, and model quality, capacity, and latency
  remain provider-dependent.

## 0.1.0

- Initial developer preview of the `ace-core` Python distribution, preserving the `ace` import
  package, `ace` CLI command, and version `0.1.0`.
- The supported public interaction boundary is the thin 11-tool MCP package and CLI.
- Atrium remains a separate experimental visual-product/research track and releases as public
  repository beta source while staying outside the Python wheel/sdist, golden path,
  supported-runtime claims, and supported release contract.
- The frozen `ace-preview-surface-v1` M2 scenario proved one durable preference survived restart
  and materially affected a later decision. Its matched-model evidence is n=1 and does not support
  a general superiority claim.
- Python packaging includes the kernel, CLI, thin MCP client, schema migrations, reference
  extension, evaluation material, public documentation, license, and notice while excluding
  Atrium beta source and local state.
- `ace doctor` validates a protected authenticated request and reports the effective provider-neutral
  model policy; `ace model-policy` exposes fast/capable/frontier mapping and degraded state.
- Supported Python is 3.12; the SurrealDB Python client is constrained to the compatible 1.x line.
- The heavyweight CodeSage/PyTorch embedding backend is now an explicit `codesage` extra; the
  default ONNX-backed install no longer pulls GPU/CUDA packages into the release container.

Release entries separate supported, experimental, fixed, security, migration, and known-
limitation notes.
