# AC6 measured composition candidate evidence v1

- Date: 2026-08-12
- Exact base: `f8b3ea3ab764d0630ad6e4b0649f566893cba484`
- Candidate branch: `codex/v0.7-agent-measured-composition`
- Status: local candidate; draft publication pending final verification

## Candidate claim

The candidate preregisters and deterministically evaluates exact fixed-minimal, fixed-multi, and
dynamic composition conditions. It may generate an inert governed proposal only when the exact
paired evidence clears every frozen validity, evidence-closure, material-use, outcome, telemetry,
latency, call, token, and cost threshold.

This is not a general claim that dynamic composition is better. The positive deterministic case
proves the bounded evaluator and proposal gate under one exact provider-free fixture. Solo
sufficiency and dynamic-cost-without-benefit remain explicit non-proposal results; all authority,
timeout, taint, telemetry, delivery/effect, abstention, and self-activation cases fail closed.

## Frozen identities

- Evaluation authority:
  `composition_evaluation_authority_resolution:545c7b8aa3588fdf5a99672466c7c176`
  (`sha256:545c7b8aa3588fdf5a99672466c7c176ebb46102e8948b6d0ad7cc1ac84ffc2e`)
- Protocol: `composition_evaluation_protocol:96c3c13495976d8734301af72fbb9864`
  (`sha256:96c3c13495976d8734301af72fbb9864057758495610d46b565909990bcbb732`)
- Positive matched comparison:
  `composition_matched_comparison:3352cc8a2017567a73ef1016b5663649`
  (`sha256:3352cc8a2017567a73ef1016b566364956930546d7a99915f9865a00b778ed54`)
- Inert proposal: `composition_policy_change_proposal:cb759967e70809413edf0360734a1656`
  (`sha256:cb759967e70809413edf0360734a1656028949ae11ecf3cc78241bda7b4daa2a`)
- Preregistration transaction receipt:
  `append_only_receipt:1792f37a9706252a12235954a1213852`

The complete comparison identity set is in
`evaluations/results/ac6_measured_composition_v1.json` and is reproduced from the frozen fixture by
`scripts/verify_ac6_measured_composition.py`.

## Matched result summary

Fourteen provider-free cases each ran all three frozen conditions. One exact case was
`dynamic_materially_helps` and emitted the single inert proposal. Solo sufficiency was
`control_suffices`. Dynamic cost without gain and duplicate-effect reconciliation were
`no_material_benefit`. Ten failure/degraded cases were `unproven_fail_closed`. Fresh-service closure
returned byte-stable artifact identities and the same append receipt.

No network, credential, provider model, optional live-model run, Domain Pack coordinate, external
repository, or Agent Memory path was used.

## Governance and causal boundaries

- The proposal cannot activate or rewrite policy, alter a roster, grant authority, schedule work,
  deliver, export, send an effect, write memory, or train a model.
- Accept/reject/supersede/rollback disposition evidence is separately typed and non-applying.
- Adoption requires a future present-tense approval, separate admission, and governed policy-head
  commit.
- Historical activation and AC5 delivery/export evidence are rejected as evaluation authority.
- Any unpaired, uncontrolled, deviated, stale, or telemetry-incomplete comparison is unproven.

## Verification record

| Check | Result |
|---|---|
| Focused AC6 contracts, protocol, comparison, governance, persistence, restart, deterministic-process and frozen-result suite | 22 passed |
| AC1–AC6, runtime authority, measured impact, action/effect and restart targeted regression | Effective 188 passed, 3 skipped. The first sandboxed run was 187 passed, 3 skipped, 1 localhost-bind denial; the exact unchanged restart test passed with local-process access. |
| Full extension-free, non-E2E/non-extension lane | Effective 7,464 passed, 243 skipped, 261 deselected. The first run had four localhost permission failures, all of which passed unchanged with local access, plus one AC6 pure-interpreter allowlist expectation that was updated and passed. |
| Exact naked-kernel, package identity, public-boundary and eleven-tool MCP gate | 56 passed, 1 skipped |
| Repository Ruff, scoped format, lock and diff checks | Passed |
| Secret scan over every AC6-owned path | Passed |
| Scoped domain vocabulary and AM1 import scan | No domain nouns and no Agent Memory/AM1 import |
| Scoped authority/effect scan | Only exact current evaluation authority, denial metrics, immutable evidence, and literal false proposal-effect fields |
| Optional real-model run | Not performed; no supported credentialed run was needed or used |

## Installed-wheel reproduction

- Wheel: `ace_core-0.6.0-py3-none-any.whl`
- SHA-256: `fc9546839875373ed4159b9f36e87fc1450b9a114ca936797bd1d560d82b281a`
- A fresh checkout-free target import loaded the public AC6 service and protocol contracts and ran
  all 14 provider-free cases from the installed fixture.
- It reproduced protocol
  `composition_evaluation_protocol:96c3c13495976d8734301af72fbb9864`, one inert proposal, and
  `restart_replay_identical=true`.
- The wheel inventory contains the Core-facing Application/Intelligence modules, fixture, frozen
  result, evaluation source, verification script, design packet, and this evidence record.

The initial isolated-worktree environment setup attempted a dependency download and was blocked by
the sandbox's network policy. No dependency or lock change was needed: all verification and the
wheel build then used the exact complete locked AC5 environment. That setup limitation is not
counted as a product test failure.

## AC7 entry gate

AC7 requires separate control-tower authority for the policy-admission path, production durable
evaluation head owners, exact approval and compare-and-swap semantics, rejection/supersession/
rollback preservation, operator recovery, and provider-free proof that no proposal can
self-activate. The AC6 positive fixture cannot be generalized into a product or causal claim.
