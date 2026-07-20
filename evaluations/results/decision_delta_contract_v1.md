# Decision-delta evaluation: ia-01-decision-delta-contract-v1
Contract: `ace.decision-delta-receipt/v1`

Recorded 8 tasks across 6 task shapes. Material: 4; null: 3; degraded: 1.

> Recorded-response conformance proves receipt behavior and portability of the contract. It is not live cross-model quality evidence and does not establish ACE superiority.

| Case | Shape | Evidence | Exact changed fields | Control | Route | Surface | Status |
|---|---|---|---|---|---|---|---|
| architecture-relevant-correction | architecture_choice | outcome-supported | selected_option, constraints, rejected_alternatives, next_action | matched | CLIProvider / claude-haiku-4-5-20251001 / subscription_backed | mcp | complete |
| release-irrelevant-memory | release_prioritization | injected, retrieved | none | matched | OllamaProvider / qwen3:4b / local | cli | complete |
| risk-contested-guidance | risk_sensitive_recommendation | decision-material | selected_option, constraints, risk_classification, next_action | matched | CLIProvider / claude-haiku-4-5-20251001 / subscription_backed | mcp | complete |
| implementation-invalidated-memory | implementation_planning | invalidated | none | matched | OllamaProvider / qwen3:4b / local | cli | complete |
| planning-null-relevant-memory | roadmap_prioritization | reflected | none | matched | CLIProvider / claude-haiku-4-5-20251001 / subscription_backed | mcp | complete |
| research-harmful-memory | evaluation_research_decision | decision-material | selected_option, ranking, next_action | matched | OllamaProvider / qwen3:4b / local | cli | complete |
| cross-path-portability | implementation_planning | decision-material | selected_option, constraints, rejected_alternatives, next_action | matched | OllamaProvider / qwen3:4b / local | cli | complete |
| degraded-mismatched-counterfactual | architecture_choice | reflected | selected_option, constraints, next_action | mismatched | CLIProvider / claude-haiku-4-5-20251001 / subscription_backed | mcp | degraded |

## Unsupported claims

- ACE outperforms either recorded model path.
- Cross-model differences prove a memory effect.
- The deterministic portability fixture is a live provider or runtime-restart trial.
- Decision-material memory is necessarily beneficial; the harmful case is explicitly retained.
- Eight recorded tasks establish general or longitudinal decision lift.

## Missing live evidence

- A paid or otherwise configured second live ACE reasoning route was not exercised because no spending authority was supplied.
- A live cross-surface capture-through-MCP then reason-through-CLI run on a second model/access class remains required.
- Repeated matched trials, variance, blinded judgments, and externally observed outcomes remain required for comparative or longitudinal claims.

## Receipt details

### architecture-relevant-correction

Receipt: `decision_delta:7f9860499da0a7707be6da23`

Decision: Choose the persistence boundary for a new inspectable receipt.

Material intelligence: observation:fixture-correction-1.

- `selected_option`: `"add_receipt_endpoint"` → `"extend_evaluation_artifact"`
- `constraints`: `[]` → `["keep exactly 11 MCP tools", "do not create roadmap write authority"]`
- `rejected_alternatives`: `[]` → `["twelfth MCP tool", "new runtime control plane"]`
- `next_action`: `"add public receipt API"` → `"build pure receipt adapter"`

### release-irrelevant-memory

Receipt: `decision_delta:175b793b9c7ad5160d3c773f`

Decision: Decide whether a security regression blocks release.

Material intelligence: none.

- Null result: the structured decision did not change.

### risk-contested-guidance

Receipt: `decision_delta:e755ea25ba1c36f304a4d46f`

Decision: Choose whether to enable an irreversible migration.

Material intelligence: observation:fixture-contested-a, observation:fixture-contested-b.

- `selected_option`: `"enable_migration"` → `"defer_for_human_resolution"`
- `constraints`: `[]` → `["preserve both conflicting directives"]`
- `risk_classification`: `"ordinary"` → `"authority_contested"`
- `next_action`: `"run migration"` → `"request explicit owner disposition"`

### implementation-invalidated-memory

Receipt: `decision_delta:b9c9e11eb53e4e668ef7861d`

Decision: Plan database result parsing after a superseding correction.

Material intelligence: none.

- Null result: the structured decision did not change.

### planning-null-relevant-memory

Receipt: `decision_delta:e974afea1b5d081a36f56bcc`

Decision: Choose the next bounded verification task.

Material intelligence: none.

- Null result: the structured decision did not change.

### research-harmful-memory

Receipt: `decision_delta:f240efa48a51eb12a4d93ca0`

Decision: Rank evaluation methods for a small pilot.

Material intelligence: insight:fixture-harmful-1.

- `selected_option`: `"deterministic_rubric"` → `"unblinded_self_grading"`
- `ranking`: `["deterministic_rubric", "blinded_human_review", "unblinded_self_grading"]` → `["unblinded_self_grading", "deterministic_rubric", "blinded_human_review"]`
- `next_action`: `"freeze rubric before pilot"` → `"run self-graded pilot"`

### cross-path-portability

Receipt: `decision_delta:6e63f6a6b9171394b17669c4`

Decision: Choose the interaction surface for the next inspectable demonstration.

Material intelligence: observation:fixture-portable-1.

- `selected_option`: `"atrium_demo"` → `"thin_mcp_and_cli"`
- `constraints`: `[]` → `["preserve exactly 11 MCP tools", "keep Atrium out of executable preview"]`
- `rejected_alternatives`: `[]` → `["production Atrium demo"]`
- `next_action`: `"build interactive canvas"` → `"run CLI receipt verifier"`

### degraded-mismatched-counterfactual

Receipt: `decision_delta:1d41593483e529cad19c59c7`

Decision: Choose a queue implementation under an unmatched control.

Material intelligence: none.

- `selected_option`: `"in_memory_queue"` → `"durable_queue"`
- `constraints`: `[]` → `["survive restart"]`
- `next_action`: `"implement process queue"` → `"implement persistence"`
- Degraded: counterfactual_conditions_mismatched, recorded fixture intentionally uses a different control model.
