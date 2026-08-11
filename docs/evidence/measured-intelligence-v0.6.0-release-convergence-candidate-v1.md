# ACE 0.6.0 Measured Intelligence release-convergence candidate evidence (v1)

**Status:** bounded candidate evidence. This is not a merge, tag, publication, issue #38 closeout,
SI4 pass, or ACE 0.6.0 release claim.

**Recorded:** 2026-08-11

## Source identities

- Core measured-impact source: `433e3d16c5458c975557dcd1552824fb959d4d12`
- Core branch: `codex/measured-intelligence-release-convergence`
- World executable/hygiene source: `7fec49b163fd4c50964576a45511c8645e856f3d`
- World evidence head: `68c5bfe`
- World branch: `codex/world-measured-intelligence-release-convergence`
- Independent Market live-wiring candidate:
  `cd1f2f2c862e5665344e47885f594a77c5aaa59b`

Core source remains four commits ahead of live `main`
`be5e76c79715bb34bcbdcae9a0471a5c317fafe7`; World source begins from P2C10, eight commits ahead of
its live `main`. All changes remain in stacked draft candidates.

## Candidate artifact identities

The exact Core, reference action-adapter, World source-adapter, and World wheels were built with
fixed `SOURCE_DATE_EPOCH` values from clean exact source commits:

| Artifact | SHA-256 |
|---|---|
| `ace_core-0.5.0-py3-none-any.whl` | `29752aa751570286794ff2abd1071a43f622883d4778e161687e10363f76f6c3` |
| `ace_reference_workspace_action-0.1.0-py3-none-any.whl` | `9c600d4b3e0d19525f1e04629bd231d8d6913d2ad11bc63fa2858e7da396f8f1` |
| `ace_ext_world_federal_register_source-0.2.0-py3-none-any.whl` | `bee0161c6a02b2d82b698d72365e401e7c58af633c8f0e774e513619866a90d6` |
| `ace_domain_world_intelligence-0.9.0-py3-none-any.whl` | `61abbd08bfedb2dc23cdd0eab8b9a0454b7d7a911ba150e4308e12d9e1cfa534` |

No package version was changed and no artifact was published. The Core wheel still reports 0.5.0;
the complete source commit and candidate hash distinguish it from the released 0.5.0 artifact.

## World public-data convergence result

A fresh Python 3.12 environment installed all four exact wheels plus public dependencies. Core and
both adapters imported from `site-packages`; the generator rejected all declared Core checkout
roots. Two fresh workspace runs emitted byte-identical
`artifacts/measured-intelligence/convergence-v1.json`:

```text
sha256:c91359485418be85c6740462bce3c2afd5c8eca6250c7288669c0cdff07a4da9
```

The canonical record binds the public BLS correction fixture, stable source Observation keys,
World-owned product rule, exact corrected and stale statements, treatment scores `[1.0, 1.0]`,
control scores `[0.0, 0.0]`, two matched pairs, mean effect `1.0`, and classification `useful`.
Governed feedback proposes `promote`, but `live_effect=false`, `selectable=false`,
`requires_human_review=true`, and `applied=false`; historical replay does not reauthorize.

The portable projection excludes availability-derived material and review digests that honestly
change across fresh hosts. Exact runtime receipts remain in each append-only host; the public
record freezes only fields demonstrated byte-stable across hosts.

## Verification

Core focused and boundary lanes:

```text
pytest tests/intelligence/test_contract_boundaries.py \
  tests/intelligence/test_measured_impact.py \
  tests/intelligence/test_measured_impact_disposition.py -q -rs
45 passed, 2 skipped in 2.02s

pytest tests/test_kernel_boundary.py -q
4 passed in 1.79s

# locked repository environment, extensions disabled, loopback allowed;
# worktree-incompatible historical baseline handled separately
pytest -m "not e2e and not requires_extensions" \
  --ignore=tests/test_grounded_state_runtime_baseline.py -q
7456 passed, 50 skipped, 260 deselected in 244.50s

# ordinary clone of exact Core source
pytest tests/test_grounded_state_runtime_baseline.py -q
7 passed in 0.99s

ruff 0.15.7 check .
All checks passed!

ruff 0.15.7 format --check .
2043 files already formatted

pip-audit 2.10.0
No known vulnerabilities found
```

The focused SurrealDB restart tests skipped because the restricted sandbox denied the local socket;
their unchanged production-store paths passed in the stacked base packets. The broad fast lane
reported eight environment-only failures: four denied loopback nodes, three historical-baseline
nodes that require directory-form `.git`, and one catalog count polluted by the developer venv's
editable Market extension. The four loopback nodes passed unchanged outside the socket sandbox,
the seven-test baseline passed from the exact ordinary clone, and the catalog test passed in the
clean candidate-wheel environment. The locked naked-kernel lane above then passed as one complete
run with loopback available. A separate unpinned wheel environment was not used for Core suite
evidence after newer native scanner dependencies segfaulted; repository CI and this evidence use
the committed lock.

World lanes:

```text
# P2C3-P2C10 plus convergence controls
33 passed in 13.95s

# complete World suite after hygiene reconciliation
116 passed in 35.57s

# separately packaged source adapter
26 passed in 0.37s

# package/release contract
7 passed in 0.05s

ruff 0.16.2 check --no-cache .
All checks passed!

ruff 0.16.2 format --check --no-cache .
85 files already formatted

git diff --check
PASS
```

The locked Core vulnerability audit skipped only the unrelated editable local
`ace-ext-b2b-marketing==0.1.0` distribution because it is not on PyPI; all resolved Core
dependencies were audited. No credential, private fixture, proprietary source, merge, tag, release,
or publication was used.

## Issue #49 literal disposition

F1, F3, and F5 are **open 0.6 release gates; not waived, deferred, or resolved**. Candidate work may
continue, but this record cannot satisfy or close them. Before 0.6 closeout, the release owner must
either accept bounded hardening packets or record a new dated deadline and containment rationale
on issue #49. F2/F6 retain `2026-11-05`, F4 remains due with the next security bundle, and F7 remains
due before production traffic.

## What this proves and what remains

This packet proves that the exact candidate Core artifact can support a reproducible public World
correction journey from governed intelligence through measured, proposal-only feedback, while a
materially different Market candidate remains independently expressible. It proves neither
causality nor a supported release.

Remaining work is release-owner review of the Core and World stack order, explicit #49 disposition,
merged-source CI/security, final version and compatibility decisions, final artifact hashes and
provenance, public-index installation, and publication. The next bounded packet is therefore a
merge-candidate audit over the reviewed stack plus #49 owner decisions—not another domain outcome
or proposal-application feature.
