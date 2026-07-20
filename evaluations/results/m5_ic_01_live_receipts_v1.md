# Decision-delta evaluation: m5-ic-01-live-continuity-v1
Contract: `ace.decision-delta-receipt/v1`

Recorded 2 tasks across 1 task shapes. Material: 2; null: 0; degraded: 0.

> Recorded-response conformance proves receipt behavior and portability of the contract. It is not live cross-model quality evidence and does not establish ACE superiority.

| Case | Shape | Evidence | Exact changed fields | Control | Route | Surface | Status |
|---|---|---|---|---|---|---|---|
| m5-ic-01-live-claude | implementation_planning | decision-material | constraints, rejected_alternatives, next_action | matched | CLIProvider / claude-sonnet-4-6 / subscription | claude_cli_stateless_completion | complete |
| m5-ic-01-live-gpt | implementation_planning | decision-material | selected_option, constraints, rejected_alternatives, next_action | matched | CodexCLIProvider / gpt-5.6-terra / subscription | codex_cli_ephemeral_stateless_completion | complete |

## Unsupported claims

- Claude is better or worse than GPT.
- Cross-provider or cross-model variance is an ACE architecture effect.
- One live pair per provider establishes general, longitudinal, or outcome-supported lift.
- The running ACE API was restarted during this packet.
- Full M5 is complete.

## Missing live evidence

- No external outcome, repeated trial, variance estimate, or blinded judgment was collected.
- The existing user-owned ACE API and schema-v141 database were not disrupted to force an API restart; fresh client and provider subprocess boundaries were exercised instead.
- The capture agent's native model identifier was not exposed to the supported capture surface and remains unreported.

## Receipt details

### m5-ic-01-live-claude

Receipt: `decision_delta:46d7e9e92443d2a960b12163`

Decision: Choose the interaction surface for the next inspectable demonstration.

Material intelligence: observation:pi9q6a3ceeh247701bg0.

- `constraints`: `["Demonstration must be inspectable \u2014 internal state, tool calls, and reasoning steps must be visible to observers", "No ACE memory context is available to inform surface-specific history or prior commitments", "Selection must be made without file inspection, browsing, or tool use"]` → `["Preserve exactly 11 MCP tools", "Keep Atrium out of the executable preview", "Demonstration must remain inspectable"]`
- `rejected_alternatives`: `["production_atrium_demo \u2014 production surfaces prioritize end-user polish over transparency; instrumentation and intermediate-state visibility are typically suppressed, undermining the 'inspectable' requirement"]` → `["production_atrium_demo"]`
- `next_action`: `"Scaffold the thin MCP + CLI harness with explicit logging of agent loop steps, tool invocations, and memory reads/writes so observers can follow ACE execution in real time"` → `"run the CLI receipt verifier"`

### m5-ic-01-live-gpt

Receipt: `decision_delta:8eccb40734d6caf3abdd7316`

Decision: Choose the interaction surface for the next inspectable demonstration.

Material intelligence: observation:pi9q6a3ceeh247701bg0.

- `selected_option`: `"production_atrium_demo"` → `"thin_mcp_and_cli"`
- `constraints`: `["Select exactly one option", "Use only supplied task and explicit ACE memory", "No tools, file inspection, browsing, delegation, or state changes"]` → `["Preserve exactly 11 MCP tools", "Keep Atrium out of the executable preview"]`
- `rejected_alternatives`: `["thin_mcp_and_cli"]` → `["production_atrium_demo"]`
- `next_action`: `"Prepare the next inspectable demonstration using the production_atrium_demo surface."` → `"Run the CLI receipt verifier."`
