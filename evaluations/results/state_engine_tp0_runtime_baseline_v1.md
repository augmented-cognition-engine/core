# ACE State Engine TP0 current-runtime baseline v1

- Baseline: `state-engine-tp0-current-ace-thin-mcp-v1`
- Executed: `2026-08-03T17:55:11.462317+00:00`
- Corpus hash: `4b029bff64564abc226d431b373a3d75cbf971c66aa6bb53e2cf29c7198c4b09`
- Configuration hash: `6c8391536f55f8685fa10178fbbe7d3482f93415cd03233c1c2328e5d68080a9`
- Public-surface hash: `7bf2e0959cf19a9aa65d1b53d64e940346ddcc564eccee2d218ee0c616c9662c`
- Outcome hash: `7aed1cdd929dc6159b7233ebab5bc90bdb9a7e07be7ed38529dc959b2930357f`
- Reference environment matched: **yes**
- Conclusion: **capability_not_established**

## Result

| Measure | Result |
|---|---:|
| Cases | 40 |
| Exact structured matches | 0 |
| Unsupported | 40 |
| Mismatches | 0 |
| Errors | 0 |
| Matched judgments | 0 / 247 |
| Model calls | 0 |
| Tokens | 0 |
| Estimated cost USD | 0.00 |
| Database writes | 0 |

Current ACE exposes the supported thin 11-tool MCP contract, but that contract cannot accept the
frozen grounded-evidence shape or emit typed belief state, relationships, transition hypotheses,
or consequence rollouts. All 40 cases therefore remain unsupported. Unsupported cases count as
failures; negative controls receive no vacuous credit.

## Public surface

| Tool | Parameters | Return |
|---|---|---|
| `ace_briefing` | `date` | `dict` |
| `ace_capture` | `observation_type, content, domain_path, confidence, affected_decision_id, affected_task_id, lifecycle_state, supersedes_correction_id, invalidates_correction_id, contests_correction_id, expires_at, intervention, indicator, comparator, measurement` | `dict` |
| `ace_capture_idea` | `raw_idea, context` | `dict` |
| `ace_history` | `file_path, graph_id` | `str` |
| `ace_impact` | `file_path, graph_id` | `str` |
| `ace_load` | `topic` | `dict` |
| `ace_related` | `file_path, graph_id` | `str` |
| `ace_search` | `query, knowledge_type` | `dict` |
| `ace_start` | `` | `dict` |
| `ace_status` | `filter, task_id` | `dict` |
| `ace_task` | `description, skill_hint, frameworks_hint, request_id, decision` | `dict` |

## Declared limitations

- A future State Engine implementation requires a new adapter and a new result; this baseline must not be rewritten into success.
- The no-write route does not claim persistence, restart continuity, replay continuity, or database-enforced product isolation.
- The provider-free route cannot measure model variability, token consumption, or provider latency because no model call is permitted.
- This evaluates the supported thin MCP contract, not private Core functions or direct database access.
- This is a structured architecture-capability baseline, not an LLM prose-quality comparison.

## Interpretation

This is an architecture capability baseline, not an LLM quality comparison and not evidence
that TP1 or TP2 is complete. It establishes the honest zero point before a grounded-state
ingestion/query surface exists.
