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

*(appended per arm-run; empty at freeze)*
