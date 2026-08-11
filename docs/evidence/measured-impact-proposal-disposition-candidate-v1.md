# Measured-impact proposal disposition candidate evidence (v1)

**Status:** stacked candidate, local. This is not 0.6 release evidence and does not apply a
governance proposal or complete issue
[#38](https://github.com/augmented-cognition-engine/core/issues/38).

**Recorded:** 2026-08-10

**Base:** Measured Intelligence kickoff candidate
`9078018a5fd3c310011b6c9efbfe5255e0e36887`

**Candidate branch:** `codex/measured-impact-disposition`

## Contract demonstrated

The candidate implements the exact non-applying disposition contract frozen in the
[work packet](../design/measured-impact-proposal-disposition-work-packet-v1.md):

- the request binds exact evaluation and proposal references, authenticated product context,
  reviewer role, accept/reject disposition, rationale, and decision time;
- the service exact-loads the target, evaluation, and proposal and verifies their durable envelope
  and lineage before authority;
- the resulting generic Core Decision names the exact proposal as its subject and always records
  `no_action`;
- authorization preserves the exact criterion and operation heads and any stricter current
  capability/grant closure;
- one immutable transaction records the Decision without changing governed state; and
- exact replay is historical and does not reauthorize, while contradictory replacement conflicts.

## Negative and durability controls

Deterministic tests cover accept and reject, mismatched evaluation/proposal lineage, cross-product
scope, unsupported `revise`, denied authority, a changed authorized head, stale criterion state,
stronger current authority closure, contradictory replay, and interrupted append. Every failure
path leaves no effective state change; denial and interruption leave no disposition Decision.

The production-store acceptance uses actual governed criterion and operation heads and the
SurrealDB immutable-record adapter. A fresh service reopens the exact historical Decision with a
denying authorizer, then a separate Python process reopens the same Decision and transaction with
an authorizer that raises if invoked. The focused run completed all 11 tests, including that real-
store restart path.

## Verification

Focused verification at candidate creation:

```text
uv run pytest tests/intelligence/test_measured_impact_disposition.py -q --tb=short -rs
11 passed in 3.92s

uv run pytest tests/intelligence/test_contract_boundaries.py \
  tests/intelligence/test_measured_impact.py \
  tests/intelligence/test_measured_impact_disposition.py -q --tb=short
41 passed, 2 skipped in 1.28s

ruff check .
PASS

ruff format --check .
2043 files already formatted

ACE_DISABLE_EXTENSIONS=1 python -B -m pytest \
  -m "not e2e and not requires_extensions" \
  --ignore=tests/test_grounded_state_runtime_baseline.py -q --tb=short
7255 passed, 243 skipped, 260 deselected; 4 loopback-sandbox failures

# The four exact socket bind/connect cases rerun outside the restricted loopback sandbox.
uv run pytest <four exact loopback cases> -q --tb=short
4 passed in 1.08s

python -B -m pytest tests/test_kernel_boundary.py -q --tb=short
4 passed in 1.02s

# Same candidate source tree cloned to a temporary ordinary-checkout layout.
python -B -m pytest tests/test_grounded_state_runtime_baseline.py -q --tb=short
7 passed in 0.56s

uv build --out-dir <temporary-directory>
Successfully built source distribution and wheel

wheel-only import of MeasuredImpactDispositionService and
MeasuredImpactDispositionRequestV1Alpha1
PASS

git diff --check
PASS
```

The two composed skips are the kickoff and disposition real-store tests when a direct interpreter
invocation cannot connect through the task sandbox. The disposition packet's production-store and
fresh-process path separately ran through the approved test runner and passed all 11 focused tests.

The repository-wide run's only failures were the four exact tests whose purpose requires binding or
connecting to loopback sockets; the sandbox returned `operation not permitted`. All four passed
unchanged through the approved runner outside that socket restriction. The historical grounded-
state baseline reads `.git/HEAD` as a directory and therefore cannot execute three replay assertions
from a Git worktree, where `.git` is a pointer file; four of seven assertions pass there. The same
candidate source tree was cloned to a temporary ordinary-checkout layout with a directory-form
`.git`; all seven assertions passed, as in the kickoff candidate evidence.

## World integration result

The stacked World P2C4 source-checkout journey preserves the P2C3 `useful` classification and
`promote` proposal, then records a separately authorized `reject` / `no_action` Decision against
the exact proposal. Historical replay does not reauthorize and the governed-state head map is
identical before and after the Decision. The World audit freezes the exact point-in-time record
references and its narrower product rationale.

This demonstrates inspectable disagreement between a frozen measurement rule and a governed
reviewer without rewriting either result. It does not establish human benefit, causality, citation
correctness, general Brief quality, live network freshness, or effective proposal application.

## Remaining boundary

The source candidate changes no release version, schema, MCP/CLI surface, existing public contract,
or effective head. It proves the explicit disposition step for one recorded official-public-data
World fixture. Stronger independently reviewed product outcomes, public artifacts, Market
reproduction, compatibility/security/release gates, and any separately authorized application
remain future work. Issue #49 F1, F3, and F5 still need explicit 0.6 release-owner disposition.
