# ACE Builds ACE evidence record v1

## Freeze record (opening entry, per harness spec §9)

- Date: 2026-08-18
- Harness: `ace-builds-ace-harness-v1`
- Frozen at: commit `a48eb8a7e0d224370f6ebef0621429514ec65534` (squash merge of PR #230, owner-approved)
- Config digest (SHA-256 of `docs/design/ace-builds-ace-harness-config-v1.json` at the frozen
  commit): `5ec835f197ebfb8c9e81e72b506ff119b1e77e0ab795139fd39b7ab5c8a18130`
- Spec: [`docs/design/ace-builds-ace-harness-v1.md`](../design/ace-builds-ace-harness-v1.md) at
  the same commit.

**From this entry forward, the harness is frozen.** Arm runs under any configuration whose digest
differs from the value above are exploratory by definition (spec §7). Configuration changes
require a `-v2` harness with its own digest; v1 runs remain reported under v1.

## Preregistered scope at freeze

- Eligible subjects: **PI8, PI9, PI10** (minimum two). PI2–PI7 merged before this freeze and are
  admissible only as `retrospective: true` records excluded from the preregistered comparative
  result (spec §8.2); unannotated gaps are valid and reported.
- Arms per subject, in order: B (bare `claude-sonnet-5`, evidence-only), A (bare
  `claude-fable-5`, evidence-only), C (`claude-sonnet-5` + shipped 1.1 Code Intelligence, the
  production path). Optional exploratory arm D (`claude-fable-5` + ACE) on at most one subject.
- Verdicts per subject: within-tier (C vs B) and tier-jump (C vs A), as defined in spec §6.
- Operator: the 1.2 ingestion session, acting under spec §2 rules 7–8 (operator is not an arm;
  production safety valve).
- Pre-existing exploratory material: `docs/evidence/ace-1.2-pi12-code-intelligence-smoke-v1.md`
  predates this freeze and is exploratory, not an arm run.

## Run log

### PI8 — Grounded Ask and correction (J7/J8) — 2026-08-18

First preregistered subject. Frozen head `3899ae741909a0da7675767e77a924fcfeea6c18`
(origin/main tip at registration); frozen subject prompt and answer key identical for every arm;
CC pinned 2.1.224; config digest as frozen above. Full operator registration, void rulings,
environment workarounds, and review reports:
[`artifacts/pi12-pi8/pi8-subject-registration.md`](artifacts/pi12-pi8/pi8-subject-registration.md).
One §8 capture record per arm-run in [`artifacts/pi12-pi8/`](artifacts/pi12-pi8/).

| Arm-run | Model / config | Outcome |
|---|---|---|
| `aba-PI8-armB-20260818T162829Z` | bare claude-sonnet-5 | **Completed**, 187 turns / 39.0 min. First review: 6/6 acceptance criteria PASS, 1 minor finding (self-validated lexical answerer placeholder). Operator gates 72/72 + ruff clean. |
| `aba-PI8-armA-20260818T171602Z` | bare claude-fable-5 | **Completed**, 103 turns / 25.0 min. First review: 4/6 PASS + 2 PARTIAL, 2 major findings (Core→`ace.intelligence` boundary regression failing a pre-existing unconditional gate; parallel reimplementation of the proposal-only feedback machinery contra the answer key), 1 unsupported claim. |
| `aba-PI8-armC-20260818T185240Z` | claude-sonnet-5 + shipped 1.1 ACE MCP | **Degraded/invalid as the C measurement (§7): ZERO ACE MCP calls** across 182 turns despite 11 registered, error-free tools and a verified 31,424-node code graph. Confirmed by transcript tool_use parse, ACE API request log, and a live traffic monitor. |
| `aba-PI8-armC-20260818T193907Z` | claude-sonnet-5 + shipped 1.1 ACE MCP (sanctioned rerun 1 of 1) | **Degraded/invalid again: ZERO ACE MCP calls** across 143 turns under byte-identical conditions. No further reruns. As bare work product: reviewer scored 6/6, COMPLETE-WITH-DEFECTS, and ranked it first of the three arms for delivery. |

Void launches (listed per §7; zero subject work product in each, rulings in the registration):
`armB-…T162429Z` (exit 127, host lacked GNU `timeout`), `armA-…T162907Z` (provider API 500 at
start), `armA-…T163245Z` (provider incident kill mid-exploration, clean worktree; documented
status-page incident from 16:20Z).

**Verdicts (per §6):**

- **C vs B (within-tier): no valid arm C measurement.** The preregistered comparative claim for
  PI8 is vacant. The recorded arm C program result is the adoption failure itself:
  **availability without adoption** — a fully provisioned, verified ACE backend and a bare-Sonnet
  agent that never elected to call it, twice. Ships as a valid negative-class outcome (§6).
- **C vs A (tier-jump): not computed** (same reason).
- **B vs A (descriptive observation, not a preregistered verdict):** bare Sonnet outscored bare
  Fable at first review on the frozen answer key (6/6 + 1 minor vs 4/6 + 2 major). Token and
  latency figures are not compared across tiers.
- **Intelligence-curve point (§8.1):** provisioned-but-unadopted; `prior_slice_provenance` empty;
  no compounding claim. The capture records carry a `context`-kind proposal (task-shaped tool
  surface / session-start injection), implemented as ordinary 1.2 work (PR #237) and to be
  measured under this same harness in PI9.

**Delivery (harness §2 rule 8):** with no valid arm C, PI8 shipped as an ordinary implementation
with disclosed bare-model provenance — the arm C rerun's work product plus operator review fixes,
PR #236. The experiment did not block 1.2 delivery.

**Instrument findings recorded for PI9:** the runner's `ace_mcp_calls` check counted transcript
lines (matching the tools-available attachment) rather than `tool_use` blocks and reported 1 for
zero-call runs — fixed on `codex/pi12-arm-runner` (`e88ae86`) alongside the two arm-B launch
defects (`$OLDPWD` prompt-path doubling, missing GNU `timeout`) fixed at `134705f`. PI9
registration pins the repaired runner.

**Retrospective PI2–PI7 (§8.2):** not yet annotated — reported as gaps, which the spec treats as
a valid state. Any future annotation appends here labeled `retrospective: true`.
