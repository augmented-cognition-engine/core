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
- version: `0.1.0`

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

## Implemented architecture beyond the compatibility contract

The broader HTTP and engine MCP APIs, Atrium, worker automation, MAKE/SHIP execution arms,
foresight, calibration, proactive intelligence, continuous-learning paths, and advanced extension
hooks are implemented parts of ACE. They are not stable 0.1.x contracts: their APIs, supported
end-to-end journeys, and compatibility guarantees can change. This maturity label limits the public
promise; it does not reduce those systems to roadmap concepts or peripheral demos.

Long-running public tasks use persisted receipts and expose pending, running, completed, failed,
and degraded outcomes. The single-process preview does not claim distributed task claiming,
transparent resumption after interruption, or public cancellation.

Atrium is repository beta source and is not included in the Python wheel or sdist. It is a
research surface, not a required installation or interaction path.

## Promotion rule

A capability moves into the preview contract only after it has a documented user journey,
failure behavior, compatibility boundary, and reproducible tests. Product ideas and planned
work belong in the [public roadmap](../ROADMAP.md), not in this support inventory.
