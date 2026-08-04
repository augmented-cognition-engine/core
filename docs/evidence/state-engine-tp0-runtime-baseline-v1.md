# ACE State Engine TP0 current-runtime baseline v1

Status: **executed; capability not established**

This record freezes and executes the current-ACE baseline against the owner-approved TP0 corpus.
It is an architecture-capability measurement, not an LLM quality comparison and not evidence that
TP1 or TP2 is complete.

## Frozen inputs

- Corpus: `ace.grounded-state.temporal-reference-corpus/v1`
- Corpus hash: `4b029bff64564abc226d431b373a3d75cbf971c66aa6bb53e2cf29c7198c4b09`
- Baseline contract: `ace.grounded-state.runtime-baseline-config/v1`
- Configuration hash: `6c8391536f55f8685fa10178fbbe7d3482f93415cd03233c1c2328e5d68080a9`
- Adapter: `ace.grounded-state.current-thin-mcp-adapter/v1`
- Adapter/rule source hash: `b42ec0dd7a25810ec2c923e3adf6811dbb84db22b9313f3abc86d6c2c6c9b88d`
- Current public surface: supported thin 11-tool MCP contract
- Public-surface source hash: `7bf2e0959cf19a9aa65d1b53d64e940346ddcc564eccee2d218ee0c616c9662c`
- Reference source revision: `6b6342f65224ca0c3db2f38c3bc141a58de9e8ea`
- Reference environment: ACE 0.1.4, CPython 3.12.13, Darwin 25.6.0, arm64, 11 logical CPUs
- Evaluation seed: `1729`; no model seed because no model call is permitted
- Budgets: 40 cases, at most 20 evidence inputs per case, 30 seconds, zero model calls, tokens,
  estimated provider cost, and database writes

The complete machine-readable configuration is
[`state_engine_tp0_runtime_baseline_v1.json`](../../evaluations/fixtures/state_engine_tp0_runtime_baseline_v1.json).

## Rules

1. A case passes only through exact, machine-checkable structured semantics.
2. The adapter receives evidence, product scopes, and as-of times, but not the reference answers.
3. Generic prose does not count as belief state, a typed relationship, a transition hypothesis, or
   a consequence rollout.
4. Unsupported capability counts as failure. Negative controls cannot pass merely because the
   runtime emitted nothing.
5. Partial credit cannot advance maturity.
6. The baseline uses only the supported public contract. Private modules and direct database access
   cannot substitute for missing product behavior.

## Execution result

The reference environment matched. The current supported thin MCP surface has no input contract for
the frozen grounded evidence shape and no typed output contract for belief state, grounded
relationships, transition hypotheses, or consequence rollouts. Execution therefore stopped at the
public contract boundary for every case instead of fabricating model or persistence behavior.

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
| Estimated provider cost | $0.00 |
| Database writes | 0 |
| Conclusion | `capability_not_established` |

The durable outcome hash is
`7aed1cdd929dc6159b7233ebab5bc90bdb9a7e07be7ed38529dc959b2930357f`.
The full [JSON result](../../evaluations/results/state_engine_tp0_runtime_baseline_v1.json) and
[human-readable report](../../evaluations/results/state_engine_tp0_runtime_baseline_v1.md) preserve
all 40 case dispositions and the inspected public tool contract.

## Reproduction

```bash
uv run python -m core.engine.grounded_state.baseline
```

Replay must preserve the material outcome hash when the configuration, corpus, and public surface
are unchanged. Execution time and duration are observational metadata and do not affect that hash.

Verification produced:

- Ruff lint and format checks: passed;
- focused TP0 corpus and runtime-baseline tests: 44 passed;
- F1, roadmap, package-identity, and kernel-boundary lanes: 18 passed and 1 expected naked-kernel
  skip; and
- full non-E2E, extension-disabled compatibility suite: 6,711 passed, 47 skipped, and 244
  deselected.

## Interpretation and boundary

The zero result is useful: it establishes the pre-implementation architecture gap without confusing
LLM plausibility with State Engine behavior. It does not mean ACE has no existing memory, graph, or
reasoning capability. It means those current surfaces do not implement the frozen State Engine
contract.

The runtime-baseline packet is complete. TP0 itself remains not passed until the persistence-bearing
work proves real restart, replay, and foreign-product isolation behavior. That evidence must be
produced by TP1/TP2 implementation; it cannot be manufactured by this zero-write baseline.
