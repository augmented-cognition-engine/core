# ACE Builds ACE comparison harness v1

- Date: 2026-08-17
- Status: **draft for owner review; not frozen.** The freeze event is the owner approving this
  document and the pinned configuration, then recording the configuration digest per §9. Until
  that digest exists, no PI12 subject run is preregistered.
- Authority: [ACE 1.2 work packet](personal-intelligence-v1.2-work-packet-v1.md) decisions 13, 15,
  and 16; [governed Code Intelligence improvement loop](governed-code-improvement-loop-v1.md)
  `ACE Builds ACE` acceptance program; [issue #195](https://github.com/augmented-cognition-engine/core/issues/195).
- Evidence destination: `docs/evidence/ace-builds-ace-v1.md`.

## 1. Purpose and freeze rule

This harness is the preregistered instrument for the PI12 comparison: the same coding agent
implementing bounded 1.2 packet Decisions with and without ACE, under equivalent model, tools,
task, and authority. Per packet decision 15, every measured element — agent, model, tool
allowlist, budgets, metric definitions, subject eligibility, and analysis rules — freezes before
the first subject run. A run collected before the freeze, or under any configuration that differs
from the frozen digest, is labeled **exploratory**, reported with its exclusion reason, and
excluded from the comparative result. This is the L1 v7 rule: the control that is not frozen
before collection does not count afterward.

## 2. Arms and assignment protocol

| Arm | Definition | Disposition of output |
|---|---|---|
| **Baseline** | The pinned coding agent in a fresh session, in an isolated worktree at the subject's frozen repository head, with the subject Decision text and repository access only. No ACE context package, no ACE tools. | Evidence only. The baseline implementation is never merged, cherry-picked, or reused. |
| **ACE-assisted** | The same agent, same model, same tool allowlist plus the shipped 1.1 Code Intelligence journey: Topic orientation, bounded context package, propagation verification, and receipts. | The production path. Its output proceeds through ordinary review and merge. |

Protocol rules, all preregistered:

1. **Fresh sessions per arm.** Each arm starts a new agent session with no memory of the other
   arm. Session identifiers are recorded in the evidence record.
2. **Isolated worktrees.** Each arm works in its own worktree at the identical frozen repository
   head recorded for the subject Decision.
3. **Fixed arm order, disclosed.** Baseline runs first. This is a known limitation (the human
   operator sees the baseline before the ACE arm), mitigated by rule 4 and disclosed in the
   evidence record rather than hidden.
4. **Minimal-intervention operation.** The operator issues the subject Decision prompt and the
   frozen follow-up prompts only. Every unscripted human intervention is logged, counted, and
   reported as a measure; the intervention log is part of the evidence record.
5. **Asymmetric stakes, disclosed.** Only the ACE arm merges. The evidence record states this
   asymmetry explicitly; it is a design consequence of refusing to merge unreviewed baseline
   work, not a concealed advantage.
6. **Authority parity.** Neither arm holds approval, merge, release, deploy, or promotion
   authority. Both produce work that a human reviews. This is also the no-self-authority proof
   surface required by PI12.

## 3. Pinned configuration

The normative pinned values live in
[`ace-builds-ace-harness-config-v1.json`](ace-builds-ace-harness-config-v1.json); the freeze
digest is computed over that file. Values marked `OWNER_DECISION_REQUIRED` must be pinned by the
owner at freeze time — the digest cannot be computed around them.

| Element | Pin | Notes |
|---|---|---|
| Coding agent + exact version | `OWNER_DECISION_REQUIRED` | One agent for both arms. Candidates: Claude Code, Codex. The version string is recorded, not a floating "latest". |
| Model + exact identifier | `OWNER_DECISION_REQUIRED` | Identical in both arms; provider-neutral substitution is not permitted mid-program. |
| Tool allowlist | `OWNER_DECISION_REQUIRED` | Identical base allowlist; the ACE arm adds only the shipped 1.1 Code Intelligence surface. |
| Token budget per arm-run | `OWNER_DECISION_REQUIRED` | Exhaustion is a recorded terminal state, not grounds for a quiet rerun. |
| Wall-clock budget per arm-run | `OWNER_DECISION_REQUIRED` | Same rule. |
| Cost ceiling per subject | `OWNER_DECISION_REQUIRED` | Covers both arms plus reruns; exceeding it ends collection for that subject with the partial state reported. |
| Concurrent participants (ACE arm) | ≥ 2, per PI12 | At least one stale-context event must occur or be induced; the induction method is recorded. |
| Repository head per subject | Frozen at subject registration | Recorded as exact commits for repo and packet docs. |

## 4. Subject eligibility

- A subject is a bounded Decision from the remaining 1.2 slices **PI5–PI10**, frozen (scope,
  acceptance criteria, repository heads) before either arm runs.
- PI12 requires at least two subjects. Each subject registers an **answer key** at freeze time:
  the governing contracts, the files expected to change, and the acceptance criteria — used to
  score orientation and coverage without post-hoc judgment.
- A Decision already partially implemented in any arm, or whose scope changes after registration,
  is withdrawn and reported as withdrawn; it is not silently replaced.

## 5. Measures

**Primary** (quality of the produced change):

| Measure | Definition |
|---|---|
| Acceptance-criteria coverage | Fraction of the subject's frozen acceptance criteria the change satisfies at first review |
| Review findings | Count and severity of human-review findings against the change |
| Rework cycles | Review→revise iterations until the change is acceptable (baseline: until the reviewer would have accepted it; it still does not merge) |
| Unsupported claims | Claims in the agent's plan or report not grounded in the repository or a resolving ACE citation |
| Propagation result | ACE arm only: true propagation gap found, explicit complete-coverage result, or degraded/unknown — never assumed from passing tests |

**Secondary** (cost of producing it):

| Measure | Definition |
|---|---|
| Orientation time | Session start until the agent states a plan matching the answer key's contracts and affected files |
| Context volume | Tokens supplied to and loaded by the agent, and for the ACE arm the context-manifest selection/omission receipts |
| Latency, tokens, cost | Wall-clock, total tokens, and cost per arm-run |
| Failures and degraded states | Count and kind, including budget exhaustion and interventions from §2 rule 4 |

**Deferred:** later material use and release Outcome linkage are attached at 1.2 closeout, not at
run time.

## 6. Analysis rules

- Results are **descriptive, per subject**. With two to six subjects there is no statistical
  claim, and the evidence record says so in those words.
- **Better**: the ACE arm improves a majority of primary measures on a subject and materially
  worsens none. **Worse**: the inverse. **Mixed**: anything else. The program-level result is the
  per-subject tally, reported without aggregation into a single score.
- Secondary measures never convert a quality result: an ACE arm that is cheaper but produces a
  worse change is **worse**.
- A negative or mixed result is a valid program outcome, ships in the evidence record, and does
  not gate J1–J10 (packet §2).

## 7. Exclusion and drift

Any of the following makes an arm-run exploratory: configuration differing from the frozen
digest; a rerun after budget exhaustion; scope change mid-run; operator intervention beyond the
frozen prompts that materially redirects the implementation. Exploratory runs are listed in the
evidence record with reasons. Deleting a run is not an available action.

## 8. Experience-capture record shape (packet decision 16)

Every PI12 arm-run appends one experience-capture record. The shape is frozen with this harness so
1.6 matched evaluation can consume PI12 output without retrofitting:

| Field | Content |
|---|---|
| `capture_id`, `subject_decision_id`, `arm` | Identity and arm assignment |
| `run_ids`, `participant_ids`, `session_ids` | Exact run lineage, both arms |
| `context_manifest_refs` | ACE arm: the manifests actually resolved, with selection/omission receipts |
| `corrections`, `failures`, `interventions` | What went wrong and who redirected it |
| `rework_count`, `review_findings`, `verification_results` | Quality trail |
| `costs` | Tokens, cost, wall-clock |
| `outcome_ref` | Attached at closeout; empty until then |
| `proposal` | Kind (`agent`, `procedure`, `context`, `routing`, `verification`, `no_learning`), evidence refs, eligible scope, expected effect, conflicts, expiry |

Records are append-only. Nothing in 1.2 evaluates, approves, activates, or retires a proposal; a
well-supported `no_learning` record is a valid and expected outcome. These records are the input
corpus for ACE 1.6 and for the corrected issue #199 dependency (packet §3).

## 9. Freeze procedure

1. Owner pins every `OWNER_DECISION_REQUIRED` value in the config file.
2. Owner approves this document and the config in the amendment PR.
3. The SHA-256 of `ace-builds-ace-harness-config-v1.json` at the merged commit is recorded as the
   opening entry of `docs/evidence/ace-builds-ace-v1.md`.
4. From that moment, configuration changes require a `-v2` harness with its own digest; v1 runs
   remain reported under v1.
