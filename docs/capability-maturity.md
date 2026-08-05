# ACE 0.3.0 capability maturity

ACE 0.3.0 is a developer preview. This page distinguishes the public contract from implemented
surfaces that remain experimental.

## Preview contract

The supported self-hosted path is:

```text
install ace-core → configure a provider and SurrealDB → start ACE → authenticate
→ ace doctor → reason and capture → load retained intelligence → stop cleanly
```

The 0.3.0 public identities are:

- Python distribution: `ace-core`
- Python import: `ace`
- CLI command: `ace`
- thin MCP command: `ace-mcp-client`
- version: `0.3.0`

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
provider routes are the compatibility focus for 0.3.x. Changes to these surfaces receive
migration notes when needed.

The supported CLI also includes `ace landscape`, a versioned, authenticated, strictly read-only
Living Product Graph snapshot. It exposes stable object identity, canonical and non-operational
assertion states, evidence, provenance, uncertainty, history, decisions, corrections, and outcomes
without adding an MCP tool or any write, execution, extension, or model-inference authority. Its
[read contract](living-product-graph.md) freezes ordering, bounds, absence, failure, redaction, and
0.3.x compatibility behavior.

## Supported governed-cognition boundary

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

The shipped reference journey is executable from a source checkout as documented in the
[README](../README.md#reproduce-the-v02-state-engine-journey). It performs, in order:

1. install/configuration diagnostics;
2. bounded adapter ingestion;
3. count and terminal-receipt inspection;
4. grounded evidence query and frozen pack retrieval;
5. reviewed temporal belief projection;
6. transition hypothesis challenge/review;
7. action/no-action consequence reasoning;
8. provenance, uncertainty, degraded-coverage, simulation, and I3 receipt inspection;
9. explicit eligible promotion with authenticated human authority;
10. real restart and fresh authoritative retrieval; and
11. correction plus append-only supersession inspection.

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
the retained post-sustained store held 220,000 claims and 256,000 semantic records. K1-K3 `ready`
means only the published bounded single-node contracts and repeated journeys.

Schema zero and the public 0.1.4 predecessor upgrade to v168 are supported. Current-head partial
application resumes through the ordinary installer; arbitrary interruption inside historical
pre-v142 migrations requires restoring a pre-migration backup. The
[operations runbook](state-engine-operations.md) covers health, backup/restore, interrupted replay,
archival/reactivation, and stop conditions. Distributed ordering, multi-writer consistency,
multi-region recovery, real-world causal accuracy or calibration, autonomous learning, general
world-model intelligence, and L1 beneficial impact are not supported claims.

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
and degraded outcomes. The single-process preview does not claim distributed task claiming,
transparent resumption after interruption, or general task cancellation. The experimental
extension-invocation surface separately supports explicit linked retries and negotiated
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

The experimental L1 `ace.foresight.impact-evaluation/v1` evaluator now computes bounded,
cluster-aware later-outcome comparisons without accepting caller-supplied quality labels. Its first
checksum-frozen public-data probe did not establish benefit. A tamper-evident prospective protocol
is now frozen, but its executed readiness receipt is `collection_not_started`. L1 therefore remains
candidate and no beneficial-impact capability is part of the supported preview contract. See the
[L1 evidence gate](evidence/l1-foresight-impact-evidence.md).

Atrium is repository beta source and is not included in the Python wheel or sdist. It is a
research surface, not a required installation or interaction path.

## Promotion rule

A capability moves into the preview contract only after it has a documented user journey,
failure behavior, compatibility boundary, and reproducible tests. Product ideas and planned
work belong in the [public roadmap](../ROADMAP.md), not in this support inventory.
