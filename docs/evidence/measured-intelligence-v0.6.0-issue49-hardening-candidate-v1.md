# ACE 0.6.0 issue #49 F1/F5 hardening candidate evidence (v1)

**Status:** bounded candidate evidence. This record does not merge a pull request, change issue #49
checklist state, pass SI4, bind a published artifact, or declare ACE 0.6.0 complete.

**Recorded:** 2026-08-11

## Source identity

| Surface | Exact identity |
|---|---|
| Frozen base | `7234506655223d49285f2a8c921bff31742bc7b0` |
| Executable implementation | `1ddac875d2f91b60f0dfdcf49d78264c5805fe9e` |
| Branch | `codex/issue-49-f1-f5-hardening` |
| Work packet | [issue #49 hardening work packet](../design/measured-intelligence-v0.6.0-issue49-hardening-work-packet-v1.md) |

## Contract proved

The executable candidate adds an in-transaction product-scoped proposal-state check and exact
cognition-head generation check before any review effect. The v169 unique
cognition/scope/generation activation index remains an independent backstop. An ambiguous commit is
accepted only if the exact stable review, disposition-implied proposal state, immutable revision,
and expected head all reload consistently; missing, divergent, or partial durable facts fail
closed.

The deprecated self-optimizer facade now parses a bounded legacy proposal key and pins both lookup
and projection to `type::record('self_optimizer_proposal', $record_key)`. Same-product foreign
tables and malformed coordinates cannot reach a query or mutation.

## Deterministic and real-store acceptance

| Gate | Exact result |
|---|---|
| F1/F5 unit, cognition, legacy facade, and API lane with extensions disabled | `102 passed, 1 skipped, 2 deselected` |
| Disposable SurrealDB restart, ambiguous post-commit response, and forced two-connection race | `2 passed` |
| Locked non-E2E/non-extension lane, excluding only the linked-worktree-incompatible baseline file | `7470 passed, 50 skipped, 261 deselected` |
| Exact grounded-state baseline from an ordinary clone of the implementation commit | `7 passed` |
| Loopback-dependent controls plus evidence-index integrity | `9 passed` |
| Kernel, Intelligence contract boundary, and evidence-index gates | `23 passed` |
| Changed-file Ruff | passed |
| Changed-tree whitespace | passed |

The forced race places two independent SurrealDB clients at the transaction boundary for different
proposals targeting the same cognition and expected generation. Exactly one review commits. The
loser proposal remains pending, the winner reloads exactly after restart, and the database contains
one revision and one activation for that cognition. A separate wrapper commits successfully and
then simulates transport loss; the service returns only after exact receipt/proposal/revision/head
reconciliation.

Negative controls cover missing or divergent review material, mismatched proposal state, missing
revision, missing head, foreign record table, empty key, nested coordinate, and malformed key. The
legacy controls assert that invalid coordinates fail before database access and that valid reads
and writes contain no caller-selected `<record>$id` query.

## Required-lane environment split

The first locked extension-disabled repository attempt reported:

```text
7276 passed, 243 skipped, 261 deselected, 8 failed
```

Those eight results are retained rather than hidden:

- four tests could not bind or connect to loopback under the workspace sandbox;
- three grounded-state baseline tests assume `.git` is a directory and therefore cannot resolve a
  linked-worktree `.git` file; and
- one evidence-index check correctly failed because this evidence file had not yet been created.

The four loopback-dependent controls and the now-present evidence index passed in a permitted local
environment: `9 passed`. The locked lane then passed with only the baseline file excluded:
`7470 passed, 50 skipped, 261 deselected`. An ordinary clone of exact implementation commit
`1ddac875d2f91b60f0dfdcf49d78264c5805fe9e` passed all seven baseline cases. The kernel,
Intelligence contract boundary, and evidence-index gates passed together: `23 passed`.

Exact commands used for the authoritative split were:

```text
ACE_DISABLE_EXTENSIONS=1 /private/tmp/ace-core-observed-result/.venv/bin/pytest \
  -m "not e2e and not requires_extensions" \
  --ignore=tests/test_grounded_state_runtime_baseline.py -q --tb=short
ACE_DISABLE_EXTENSIONS=1 /private/tmp/ace-core-observed-result/.venv/bin/pytest \
  tests/test_grounded_state_runtime_baseline.py -q --tb=short
ACE_DISABLE_EXTENSIONS=1 /private/tmp/ace-core-observed-result/.venv/bin/pytest \
  tests/test_kernel_boundary.py \
  tests/intelligence/test_contract_boundaries.py tests/test_evidence_index_integrity.py -q --tb=short
```

The ordinary-clone split changes no assertion and hides no test. It isolates an existing source-
revision helper that reads `.git/HEAD` as a directory path and therefore cannot execute from a Git
linked worktree whose `.git` is a pointer file.

## Issue #49 and release boundary

F1 and F5 have implementation candidates only. They remain unchecked until reviewed, merged, and
re-derived from merged-source evidence. F3 is unchanged: it is not implemented, resolved, waived,
or re-dated by this branch and still requires an explicit authenticated owner disposition on issue
[#49](https://github.com/augmented-cognition-engine/core/issues/49).

No Intelligence contract, measured-impact classification, proposal application, package version,
schema, World policy, Market policy, or eleven-tool MCP surface changes. This evidence makes no
distributed-consensus, exactly-once external-effect, causal, general-benefit, live-monitoring, SI4,
or release claim.

## Next bounded packet

After this candidate is reviewed and merged, rerun Core, World, and Market from merged source;
derive final artifacts and compatibility/security results; update issue #49 only from accepted
evidence; and perform the final 0.6 release audit. Publication and issue #38 closeout remain separate
release-owner actions.
