# ACE 0.5.0 capability maturity

ACE 0.5.0 is a developer preview. This page distinguishes the public contract from implemented
surfaces that remain experimental.

## Preview contract

The supported self-hosted path is:

```text
install ace-core → configure a provider and SurrealDB → start ACE → authenticate
→ ace doctor → reason and capture → load retained intelligence → stop cleanly
```

The 0.5.0 public identities are:

- Python distribution: `ace-core`
- Python import: `ace`
- CLI command: `ace`
- thin MCP command: `ace-mcp-client`
- version: `0.5.0`

The thin MCP surface contains exactly eleven tools:

| Tool | Purpose |
|---|---|
| `ace_start` | Establish product and session context |
| `ace_load` | Load relevant accumulated intelligence |
| `ace_capture` | Persist an observation or correction |
| `ace_task` | Submit complex orchestration with a durable receipt |
| `ace_status` | Retrieve task or system status |
| `ace_capture_idea` | Preserve an emerging idea |
| `ace_search` | Search accumulated intelligence |
| `ace_briefing` | Retrieve a return briefing |
| `ace_impact` | Inspect likely code impact |
| `ace_history` | Inspect file or symbol history |
| `ace_related` | Find related code and knowledge |

The CLI, thin MCP adapter, persistence migrations, reference extension mechanism, and documented
provider routes are the compatibility focus for the current developer preview. Changes to these
surfaces receive migration notes when needed.

The supported CLI also includes `ace landscape`, a versioned, authenticated, strictly read-only
Living Product Graph snapshot. It exposes stable object identity, canonical and non-operational
assertion states, evidence, provenance, uncertainty, history, decisions, corrections, and outcomes
without adding an MCP tool or any write, execution, extension, or model-inference authority. Its
[read contract](living-product-graph.md) freezes ordering, bounds, absence, failure, redaction, and
0.3.x compatibility behavior.

## Supported governed-cognition boundary

Roadmap outcome E1 is **passed** for the exact ace-core 0.3.0 release. The
[E1 release evidence](evidence/e1-governed-cognition-release-v1.md) binds the implementation to the
published package matrix, deployment inventory, independent Claude Fable 5 AI security review, and
release-owner countersignature. The security record is intentionally described as an independent
AI review, not a human penetration test, professional audit, or certification.

ACE 0.3.0 supports one canonical governed-cognition contract for reusable recipes, instruments,
frameworks, tools, perspectives, and procedural knowledge. Stable cognition identity, immutable
revision identity, scoped active heads, proposals, human review receipts, bounded selection/use
receipts, and effectiveness observations remain distinct. The supported lifecycle is
`teach → propose → inspect → approve → use → measure → revise or retire`; proposal or use alone
cannot approve, activate, or promote cognition.

Core recipes and current trusted in-process extensions enter the same typed catalog. Current Core
adapts the v0.2.0 reference registration contract, while v0.2.0 Core refuses the current reference
extension before any partial registration. Unknown, future, malformed, conflicting, unapproved,
expired, superseded, unavailable, or scope-incompatible cognition fails closed. The naked kernel,
zero-extension configuration, mixed wheel/source-distribution packages, and independently packaged
consumer remain supported conformance cases.

The authenticated cognition HTTP boundary owns proposal, semantic diff, review, activation,
rollback, expiry, disablement, retirement, discovery, and use inspection. Deprecated skill,
framework, and self-optimizer facades project into this boundary without manufacturing approval
provenance. The existing thin MCP surface remains exactly eleven tools and gains only additive
cognition receipt projections. E1 adds no writable model authority and supports no untrusted
in-process extension execution, distributed approval, or exactly-once external side-effect claim.

See the [governed-cognition operations runbook](governed-cognition-operations.md),
[threat model](design/governed-cognition-extension-threat-model-v1.md), and
[architecture/migration packet](design/governed-cognition-architecture-migration-work-packet-v1.md).

## Supported v0.2 State Engine boundary and journey

The product-scoped State Engine v1 contracts are supported for the measured single-node topology:
one ACE API/worker deployment, one SurrealDB/SurrealKV database, and bounded synchronous adapter
clients. The supported Core boundary includes material-derived evidence identities; item/batch and
operational receipts; deterministic candidate/evidence packs; reviewed as-of belief projections;
reviewed transition revisions; labeled action/no-action simulations and reconciliation; I3
reasoning-use receipts; and human-authority promotion, correction, and supersession lineage.

The supported extension-first journey is executable from a source checkout as documented in the
[product-builder guide](state-engine-product-builder.md) and
[README](../README.md#reproduce-the-v02-state-engine-journey). It performs, in order:

1. build, clean-install, and discover the independent product extension;
2. schema-zero and supported-predecessor upgrade verification;
3. bounded adapter ingestion, exact replay, counts, lineage, and scope checks;
4. grounded evidence query and frozen as-of projection with five explicit epistemic meanings;
5. transition hypothesis challenge/review with mechanism, uncertainty, evidence, and causal limits;
6. action/no-action and named-alternative/no-action consequence comparisons;
7. structured decision, task-time I3 use, and explicit eligible promotion receipts;
8. incomplete and matched later-outcome reconciliation without rollout mutation;
9. real database/API/worker restart and fresh-client material use;
10. correction plus append-only supersession and post-correction restart; and
11. interruption recovery, degraded/failure cases, and exact eleven-tool revalidation.

The adapter supplies bounded, untrusted proposals and content digests. Authenticated Core context
owns product scope, stable identity, validation, transactions, replay, and receipts. Source or model
content cannot select product, task, tool, review, mutation, causal, or promotion authority. Source
claims stay in the grounded evidence plane unless an independently eligible conclusion completes
the explicit promotion lifecycle; simulations remain separate from observations and beliefs.

The reference `evidence-query` and `promotion-review` task actions are real production-router
integration but remain on the explicitly experimental extension-invocation HTTP surface. They are
not a new stable CLI/MCP contract. The public thin MCP adapter remains exactly eleven tools, and the
legacy in-process engine MCP surface is not the supported public MCP boundary.

The frozen reference envelope is 200 records per item, 200 items per manifest, 200 candidate
records, 50 returned candidates, 20 evidence-pack records, 8 runtime evidence records, 8 rollout
branches/steps/transitions, and 20 promotion retrieval results. The measured initial corpus was
200,000 claims and 236,000 semantic records under a 2 GiB store budget on an 11-core, 18 GB M3 Pro;
the retained post-sustained store held 220,000 claims and 256,000 semantic records. K1-K3 `passed`
means only the published bounded single-node contracts, scale packet, and the frozen extension-first
journey recorded in the
[K1-K3 product evidence](evidence/state-engine-k1-k3-product-journey-v1.md).

Schema zero and the public 0.1.4 predecessor upgrade to v168 are supported. Current-head partial
application resumes through the ordinary installer; arbitrary interruption inside historical
pre-v142 migrations requires restoring a pre-migration backup. The
[operations runbook](state-engine-operations.md) covers health, backup/restore, interrupted replay,
archival/reactivation, and stop conditions. Distributed ordering, multi-writer consistency,
multi-region recovery, real-world causal accuracy or calibration, autonomous learning, general
world-model intelligence, and general real-world L1 beneficial impact are not supported claims.

## Supported 0.3.1 Productized State journey

ACE 0.3.1 adds a builder-facing `ace state` workflow and authenticated Product State HTTP boundary.
The supported claim is bounded to the contract, topology, and failure behavior below.

The release supports:

- `GET /product-state/capabilities` for deterministic adapter/action/version discovery;
- `POST /product-state/ingestions` for extension mapping under authenticated Core product scope;
- `ace state capabilities`, `ingest`, `invoke`, `correct`, and `inspect` as one outcome-led journey;
- additive, allowlisted Living Product Graph metadata for ingestion, belief, transition,
  task-evidence, material-use, rollout, reconciliation, promotion, decision, deliberation, and
  correction receipts; and
- schema-zero v171 and v168→v171 compatibility in the frozen extension-first acceptance.

The ingestion and inspection contracts are supported surfaces. The underlying grounded-
state adapter and extension task-action registration remain experimental extension hooks: installed
extensions are explicitly trusted in-process, action authority stays bounded by their manifest, and
failures remain visible. The CLI adds no MCP tool and does not make capture equivalent to promotion.

The [Productized State guide](productized-state.md) and
[release evidence](evidence/productized-state-v0.3.1-release-readiness.md) record the exact journey,
failure behavior, receipt identities, and artifact boundary.

## Supported 0.5.0 Reasoning into Action boundary

ACE 0.5.0 supports one ACE host, one durable store, and explicitly trusted in-process Action
adapters. Approved reasoning proceeds through an exact Decision, human review of the effect-free
plan, Core authorization and admission, a terminal result, separate post-effect verification, and
explicit promotion. Cancellation, attempt identity, replay, limits, restart recovery, and resource
outcomes remain durable and inspectable. Neither a successful effect nor verification promotes
itself.

The supported claim is not distributed execution, untrusted adapter isolation, globally exactly-
once effects, compensation, or remote orchestration. The separate World Intelligence adapter
proves public-contract portability for this bounded topology. The exact tag, packages, restart
journey, hashes, and non-claims are in the
[0.5.0 release evidence](evidence/reasoning-into-action-v0.5.0-release-readiness.md).

## Experimental 0.6.0 Measured Intelligence candidate

The source tree contains a bounded candidate for exact measured-impact evaluation. It links an
intelligence artifact or immutable cognition revision to product-owned criteria, matched
conditions, material-use attribution, Decision, reviewed Action, observed Outcome, uncertainty,
and a useful, harmful, or unproven receipt. Its append-only proposal may name promotion, rejection,
rollback, or retirement but is non-effective, non-selectable, and requires separate human/Core
authority. Exact replay survives a fresh real-store process without reclassification.

The stacked [proposal disposition candidate](design/measured-impact-proposal-disposition-work-packet-v1.md)
adds an exact authorized accept/reject Core Decision over one proposal. The Decision is always
`no_action`: it preserves append-only history and cannot apply the proposal or change effective
state. World P2C3/P2C4 compose the source-checkout candidate over recorded official public data,
preserving a bounded `useful` structural result while a separately authorized reviewer rejects its
broader `promote` proposal.

These candidates are not a supported 0.6.0 capability or release claim. SI4 is not passed, no
proposal application path is added, the recorded transport does not prove live freshness, and
material use or statistical association does not establish causality or general benefit. See the
[kickoff evidence](evidence/measured-intelligence-v0.6.0-kickoff-candidate-v1.md) and
[disposition evidence](evidence/measured-impact-proposal-disposition-candidate-v1.md).

## Implemented architecture beyond the compatibility contract

The broader HTTP and engine MCP APIs, Atrium, worker automation, MAKE/SHIP execution arms,
foresight, calibration, proactive intelligence, continuous-learning paths, and advanced extension
hooks are implemented parts of ACE. They are not stable 0.3.x contracts: their APIs, supported
end-to-end journeys, and compatibility guarantees can change. This maturity label limits the public
promise; it does not reduce those systems to roadmap concepts or peripheral demos.

The authenticated `extension-invocation-v1` HTTP envelope and
`extension-invocation-receipt-v1` projection are experimental. They add an extension-owned
preparation/outcome bridge over Core's durable task lifecycle, including linked attempt-level
resume after restart. This is real HTTP execution authority, not a supported CLI/MCP surface, and
does not broaden the supported governed-cognition boundary. See the
[experimental extension-invocation contract](extension-invocation-contract.md).

Long-running public tasks use persisted receipts and expose pending, running, completed, failed,
cancelled, and degraded outcomes. In the supported 0.5.0 single-host topology, durable attempt
identity, cancellation, exact replay, limits, and restart recovery are passed. This does not claim
distributed task claiming, multi-host coordination, or general exactly-once external effects. The
experimental extension-invocation surface separately supports linked retries and negotiated
process-local cancellation; neither is a distributed guarantee.

The supported I1 nested decision/correction receipt contract, explicit incomplete provenance,
privacy boundary, lifecycle history, and replay evidence are documented in
[Decision and correction receipts](decision-correction-receipts.md). I1 is passed without widening
the eleven-tool surface or adding execution authority.

The supported I2 `deliberation-receipt-v1` projection is exposed through existing task/status,
opt-in CLI, thin-client, and read-only Living Product Graph paths. It records bounded observable
shape selection, execution-identity contributor artifacts, artifact-grounded conflicts, synthesis
dispositions, and honest partial/degraded coverage without exposing hidden reasoning or adding
execution authority. I2 is passed, but attribution does not establish correctness, causality, or
benefit. See [I2 closeout evidence](evidence/i2-attributable-deliberation-evidence.md).

The supported I3 `intelligence-use-receipt-v1` projection is exposed through the existing
`ace_status` task result and read-only Living Product Graph. It distinguishes retrieved, injected,
reflected, and decision-material evidence; limits comparison to the six structured I1 fields; and
degrades missing, mismatched, failed, or partial controls without reconstruction. I3 is passed, but
material influence is not beneficial impact and does not imply L1 success. See
[I3 closeout evidence](evidence/i3-intelligence-use-evidence.md).

The L1 `ace.foresight.impact-evaluation/v1` evaluator computes bounded,
cluster-aware later-outcome comparisons without accepting caller-supplied quality labels. Its first
checksum-frozen public-data probe did not establish benefit. A tamper-evident prospective protocol
was frozen, but a pre-outcome collection-start audit invalidated v1 because it cannot be executed
without adding unfrozen cohort, route, outcome, estimator, attribution, and leakage choices.
The fully frozen agent-only v5 successor later completed 144 decisions over 36 eligible clusters
but failed naïve/base-rate and matched model-only. V6 preserved a favorable statistical result but
failed closed on one I3 field-level lineage record. Its independently seeded v7 correction
replicate froze that already-required validation before collection, completed 192 decisions over
48 eligible clusters, and passed persistence, naïve/base-rate, and matched model-only under the
all-controls interval rule. L1 is therefore passed for the frozen executable-workload claim only;
human, customer, external-product, provider, and general real-world benefit remain unsupported. See the
[L1 evidence gate](evidence/l1-foresight-impact-evidence.md).

Atrium is repository beta source and is not included in the Python wheel or sdist. It is a
research surface, not a required installation or interaction path.

## Promotion rule

A capability moves into the preview contract only after it has a documented user journey,
failure behavior, compatibility boundary, and reproducible tests. Product ideas and planned
work belong in the [public roadmap](../ROADMAP.md), not in this support inventory.
