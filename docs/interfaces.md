# CLI, MCP, and Atrium interfaces

ACE exposes human and machine interfaces over one governed resource plane. The stable 1.0 thin MCP boundary remains exactly eleven tools; Atrium and the CLI use the same ACE API and do not become separate state or authority systems.

For CLI setup and Atrium launch commands, start with [Getting started](getting-started.md).

## CLI

The `ace` CLI owns guided setup, authentication, health inspection, local service control, Atrium
launch, and human-readable projections of the same durable resources used by machine clients.

```bash
ace setup
ace doctor
ace atrium
ace landscape
ace service status
```

`ace landscape` is a versioned, authenticated, read-only Living Product Graph projection. It adds
no model inference, write, extension, or execution authority. See the
[Living Product Graph contract](living-product-graph.md).

## Atrium

Atrium is the supported optional human command center for the documented 1.0 single-user journey.
It presents onboarding, source coverage, Ask ACE, cited Briefs, attention, decisions, outcomes, and
inspection state through the authorized ACE API. It is never a second database, policy engine, or
authority path.

## MCP: exactly eleven tools

The stable 1.0 thin, pure-HTTP MCP client exposes exactly eleven tools:

| Tool | Purpose |
|---|---|
| `ace_start` | Establish product and session context |
| `ace_load` | Load relevant accumulated intelligence |
| `ace_capture` | Persist an observation or correction |
| `ace_task` | Submit orchestration with a durable receipt |
| `ace_status` | Retrieve task or system status |
| `ace_capture_idea` | Preserve an emerging idea |
| `ace_search` | Search accumulated intelligence |
| `ace_briefing` | Retrieve a return briefing |
| `ace_impact` | Inspect likely code impact |
| `ace_history` | Inspect file or symbol history |
| `ace_related` | Find related code and knowledge |

To connect a client, register the command `uv run ace-mcp-client` with its working directory set to
the clone. It reuses the token written by `ace login`. Call `ace_start` first, then `ace_load(...)`
before domain work.

`ace_task` uses a durable asynchronous receipt contract: it returns within a bounded submission
window with either a completed result or a `pending`/`running` task ID, and long reasoning continues
after the MCP call ends. Retrieve it with `ace_status(filter="task:…")`. `completed`, `failed`, and
`degraded` are distinct terminal states — a polling timeout is not a task failure.

The public interfaces do not expose private prompts, scratchpads, raw transcripts, or hidden
chain-of-thought. Receipts expose attributable inputs, routing, participant identity, evidence,
terminal state, and declared omissions at the level permitted by the public contract.

Setup and provider details:
[`docs/providers.md`](https://github.com/augmented-cognition-engine/core/blob/main/docs/providers.md)
·
[`docs/capability-maturity.md`](https://github.com/augmented-cognition-engine/core/blob/main/docs/capability-maturity.md)
·
[`docs/governed-cognition-builder.md`](https://github.com/augmented-cognition-engine/core/blob/main/docs/governed-cognition-builder.md)
·
[`docs/governed-cognition-operations.md`](https://github.com/augmented-cognition-engine/core/blob/main/docs/governed-cognition-operations.md)

---
