# Measured-impact observed-result provenance candidate evidence (v1)

**Status:** stacked local candidate. This is not 0.6 release evidence, an SI4 pass, or an applied
governance change.

**Recorded:** 2026-08-10

**Base:** measured-impact disposition candidate
`3c920bb5c411bd9d91a5e2a6c96d4014e9b66763`

**Candidate branch:** `codex/measured-impact-observed-result`

## Contract demonstrated

The candidate implements the exact provenance contract frozen in the
[work packet](../design/measured-impact-observed-result-provenance-work-packet-v1.md):

- product criteria explicitly state whether an exact observed-result record is required;
- Outcome measures can name one exact immutable product result without exposing its domain schema
  to Core or Intelligence;
- the application service verifies product scope, cutoff availability, observation time, recording
  order, and exact durable envelope before classification;
- missing or unavailable result provenance becomes explicit unproven evidence; and
- post-cutoff result material is excluded from envelope metadata without payload access.

## Negative controls

Focused tests cover missing exact result, post-cutoff result leakage, and cross-product result
scope in addition to the kickoff packet's missing attribution, mismatched conditions, unavailable
Outcome, duplicate evidence, divergent replay, atomic interruption, restart durability, and denied
authority controls. The new required-result flag and exact reference are covered by the existing
content-derived criterion, Outcome, request, evaluation, and transaction identities.

## Verification

Candidate verification:

```text
python -B -m pytest tests/intelligence/test_contract_boundaries.py \
  tests/intelligence/test_measured_impact.py \
  tests/intelligence/test_measured_impact_disposition.py -q --tb=short -rs
45 passed, 2 skipped in 1.48s

ACE_DISABLE_EXTENSIONS=1 python -B -m pytest \
  -m "not e2e and not requires_extensions" \
  --ignore=tests/test_grounded_state_runtime_baseline.py -q --tb=short
7259 passed, 243 skipped, 260 deselected; 4 loopback-sandbox failures

# The four exact socket bind/connect cases rerun outside the restricted loopback sandbox.
uv run pytest <four exact loopback cases> -q --tb=short
4 passed in 5.97s

python -B -m pytest tests/test_kernel_boundary.py -q --tb=short
4 passed in 1.78s

# Same committed source cloned to an ordinary checkout with a directory-form .git.
python -B -m pytest tests/test_grounded_state_runtime_baseline.py -q --tb=short
7 passed in 0.60s

ruff check .
PASS

ruff format --check .
2043 files already formatted

uv build --out-dir <temporary-directory>
Successfully built source distribution and wheel

wheel-only import of ImpactCriterionV1Alpha1.requires_observed_result,
ImpactOutcomeMeasuresV1Alpha1.observed_result, and MeasuredImpactService
PASS

git diff --check
PASS
```

The two focused skips are the kickoff and disposition SurrealDB restart tests when the local
database socket is unavailable in this task environment. Their unchanged production-store and
fresh-process paths passed in the two stacked base packets. This packet adds no persistence
implementation; its exact result is loaded through the same immutable-record store and participates
in the already tested Outcome/request/evaluation replay identities.

The broad run's only failures were four tests whose purpose requires binding or connecting to a
loopback socket. The sandbox returned `operation not permitted`; all four passed unchanged through
the approved test runner outside that restriction.

The historical grounded-state baseline reads `.git/HEAD` as a directory and cannot execute three
replay assertions from a Git worktree, where `.git` is a pointer file; four assertions pass there.
All seven passed from an ordinary clone of the exact committed candidate source.

## World integration result

World P2C5 records an independently authorized citation-correctness review as an immutable World
result, names that exact record from each Core Outcome, and requires observed-result provenance in
the frozen impact criterion. The real Brief and a citation-preserving semantic-corruption control
both retain the same two exact citation identities and therefore score `1.0` citation coverage.
Independent correctness review scores the real cited claim `1.0` and the date-swapped control
`0.0` across two matched pairs. The domain-neutral evaluator classifies the bounded result as
`useful` and emits only a non-effective, non-selectable `promote` proposal requiring separate
review. Historical replay performs no reauthorization.

## Remaining boundary

The result is a deterministic association under one World-owned recorded-source policy, not a
causal estimate, population result, live-freshness proof, general Brief-quality score, or human-
benefit finding. Public artifacts, independent Market reproduction, broader outcome dimensions,
compatibility/security/release gates, and any authorized proposal application remain future work.
Issue #49 F1, F3, and F5 still need explicit 0.6 release-owner disposition.
