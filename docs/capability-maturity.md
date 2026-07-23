# ACE 0.1.x capability maturity

ACE 0.1.x is a developer preview. This page distinguishes the public contract from implemented
surfaces that remain experimental.

## Preview contract

The supported self-hosted path is:

```text
install ace-core → configure a provider and SurrealDB → start ACE → authenticate
→ ace doctor → reason and capture → load retained intelligence → stop cleanly
```

The 0.1.x public identities are:

- Python distribution: `ace-core`
- Python import: `ace`
- CLI command: `ace`
- thin MCP command: `ace-mcp-client`
- version: `0.1.2`

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
provider routes are the compatibility focus for 0.1.x. Changes to these surfaces receive
migration notes when needed.

The supported CLI also includes `ace landscape`, a versioned, authenticated, strictly read-only
Living Product Graph snapshot. It exposes stable object identity, canonical and non-operational
assertion states, evidence, provenance, uncertainty, history, decisions, corrections, and outcomes
without adding an MCP tool or any write, execution, extension, or model-inference authority. Its
[read contract](living-product-graph.md) freezes ordering, bounds, absence, failure, redaction, and
0.1.x compatibility behavior.

## Implemented architecture beyond the compatibility contract

The broader HTTP and engine MCP APIs, Atrium, worker automation, MAKE/SHIP execution arms,
foresight, calibration, proactive intelligence, continuous-learning paths, and advanced extension
hooks are implemented parts of ACE. They are not stable 0.1.x contracts: their APIs, supported
end-to-end journeys, and compatibility guarantees can change. This maturity label limits the public
promise; it does not reduce those systems to roadmap concepts or peripheral demos.

Long-running public tasks use persisted receipts and expose pending, running, completed, failed,
and degraded outcomes. The single-process preview does not claim distributed task claiming,
transparent resumption after interruption, or public cancellation.

The supported I1 nested decision/correction receipt contract, explicit incomplete provenance,
privacy boundary, lifecycle history, and replay evidence are documented in
[Decision and correction receipts](decision-correction-receipts.md). I1 is passed without widening
the eleven-tool surface or adding execution authority.

The supported I2 `deliberation-receipt-v1` projection is exposed through existing task/status,
opt-in CLI, thin-client, and read-only Living Product Graph paths. It records bounded observable
shape selection, execution-identity contributor artifacts, artifact-grounded conflicts, synthesis
dispositions, and honest partial/degraded coverage without exposing hidden reasoning or adding
execution authority. I2 is passed, but attribution does not establish correctness, causality, or
benefit. See [I2 closeout evidence](i2-attributable-deliberation-evidence.md).

The supported I3 `intelligence-use-receipt-v1` projection is exposed through the existing
`ace_status` task result and read-only Living Product Graph. It distinguishes retrieved, injected,
reflected, and decision-material evidence; limits comparison to the six structured I1 fields; and
degrades missing, mismatched, failed, or partial controls without reconstruction. I3 is passed, but
material influence is not beneficial impact and does not imply L1 success. See
[I3 closeout evidence](i3-intelligence-use-evidence.md).

The experimental L1 `ace.foresight.impact-evaluation/v1` evaluator now computes bounded,
cluster-aware later-outcome comparisons without accepting caller-supplied quality labels. Its first
checksum-frozen public-data probe did not establish benefit, so L1 is candidate and no beneficial-
impact capability is part of the supported preview contract. See the
[L1 evidence gate](l1-foresight-impact-evidence.md).

Atrium is repository beta source and is not included in the Python wheel or sdist. It is a
research surface, not a required installation or interaction path.

## Promotion rule

A capability moves into the preview contract only after it has a documented user journey,
failure behavior, compatibility boundary, and reproducible tests. Product ideas and planned
work belong in the [public roadmap](../ROADMAP.md), not in this support inventory.
