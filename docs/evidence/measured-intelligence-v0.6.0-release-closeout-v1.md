# ACE 0.6.0 Measured Intelligence public release closeout (v1)

**Status:** public, passed for the bounded release contract described here

**Recorded:** 2026-08-11

This immutable point-in-time receipt closes the ACE Core 0.6.0 Measured Intelligence milestone. It
does not pass general SI4, apply a governance proposal, establish causality or general benefit, or
rewrite the earlier candidate evidence records.

## Exact public identities

| Surface | Exact identity |
|---|---|
| Core tag/source | `v0.6.0` at `1e383e1e265e59290478eef6483c2565a0d3dbbc` |
| Core release | [GitHub Release](https://github.com/augmented-cognition-engine/core/releases/tag/v0.6.0) and [`ace-core==0.6.0`](https://pypi.org/project/ace-core/0.6.0/) |
| Core release PR | [#96](https://github.com/augmented-cognition-engine/core/pull/96), merged as the tag/source commit |
| Core publication repair | [#97](https://github.com/augmented-cognition-engine/core/pull/97), `9781bfe5f6e88ec4571350e51bbf5fa9e9e490d9`; build-tooling-only, no release artifact source change |
| Core trusted publication | [run 31536228192](https://github.com/augmented-cognition-engine/core/actions/runs/31536228192), passed all build, attachment, and PyPI jobs |
| World tag/source | `v0.10.0` at `f6fdad88ce51ff983e582f5f913801cf3084807d` |
| World release | [GitHub Release](https://github.com/augmented-cognition-engine/domain-world-intelligence/releases/tag/v0.10.0) and [`ace-domain-world-intelligence==0.10.0`](https://pypi.org/project/ace-domain-world-intelligence/0.10.0/) |
| World release PR | [#19](https://github.com/augmented-cognition-engine/domain-world-intelligence/pull/19), merged as the tag/source commit |
| World trusted publication | [run 31538936902](https://github.com/augmented-cognition-engine/domain-world-intelligence/actions/runs/31538936902), passed all build, attachment, and PyPI jobs |
| World closeout | [PR #20](https://github.com/augmented-cognition-engine/domain-world-intelligence/pull/20), merged as `0bddbd4f84d5b0ca3b22ed817fb293b9db37bed7`; [CI 31540061181](https://github.com/augmented-cognition-engine/domain-world-intelligence/actions/runs/31540061181) passed |

The Core publication workflow first failed before upload because the release environment omitted
the pinned build backend. PR #97 corrected only that workflow dependency. The successful rerun
built from the unchanged `v0.6.0` tag, and no conflicting artifact was published.

## Public artifact receipts

| Public artifact | SHA-256 | Published |
|---|---|---|
| `ace_core-0.6.0-py3-none-any.whl` | `1dd6e28f43f8d0894aba11e16e95b6b66eb8198c233ef297425e3561285373b3` | PyPI 2026-08-11T21:06:37.332663Z |
| `ace_core-0.6.0.tar.gz` | `a3f117a8b40f1f87826606a41542a77989ac537346538989c014953f59894e5e` | PyPI 2026-08-11T21:06:39.631376Z |
| `ace_reference_workspace_action-0.2.0-py3-none-any.whl` | `eaa51ea704e9162363a4483d1f7d7779778b953ed2a2d80b67dfb332e1cd3f62` | Core GitHub Release |
| `ace_reference_workspace_action-0.2.0.tar.gz` | `f6614bd571384c3e68a1f51472642be1043b67f521d955a0540e6177bab53ae0` | Core GitHub Release |
| `ace_domain_world_intelligence-0.10.0-py3-none-any.whl` | `616ae3f3d8d670b142761eaff7ded7e0baf37029201027ccc5b0b9c1018da9ad` | PyPI 2026-08-11T21:40:32.681331Z |
| `ace_domain_world_intelligence-0.10.0.tar.gz` | `079c674a14499c540c53efb6684e54969dae1c6c2c3e3655219e71ae025b082a` | PyPI 2026-08-11T21:40:33.855803Z |
| `ace_ext_world_federal_register_source-0.3.0-py3-none-any.whl` | `b4b28220a85f1c8353d772bece9e22c775fe7e73a825db0510d90e3dff39e652` | World GitHub Release 2026-08-11T21:40:32Z |

The Core and World wheel/source pairs and both separate adapter wheels were independently rebuilt
byte-identically before publication. Public registry and release-asset hashes match those builds.

## Contract proved

The public Core contract gives product code domain-neutral identities for an exact artifact or
cognition revision, frozen product criterion and matched conditions, material-use attribution,
Decision, reviewed Action and terminal result, exact observed-result provenance, Outcome, controls,
evaluation cutoff, classification, and optional governance proposal. Complete matched evidence is
classified deterministically as `useful`, `harmful`, or `unproven`; the receipt retains effect and
uncertainty, exclusions, limitations, latency, cost, failures, and degraded states.

The application boundary authorizes against exact governed heads and atomically appends evaluation
and proposal history. Replaying the same identity returns the historical transaction without
reauthorization or reclassification; changed material conflicts. Every promote, reject, rollback,
or retire proposal has `live_effect=false`, `selectable=false`, and
`requires_human_review=true`. A separate disposition records an authorized accept/reject Core
Decision as `no_action`; it cannot mutate effective state.

Deterministic Core coverage proves all three classifications and the required negative controls:
missing exact attribution, mismatched conditions, unavailable Outcome, post-cutoff leakage,
missing or unavailable observed-result provenance, cross-product scope, duplicate or relabelled
evidence, contradictory replay, denied or expired authority, partial transaction interruption, and
attempted live-effect proposal construction. The real SurrealDB path and a fresh Python process
reopen the exact evaluation, proposal, disposition, and transaction without duplicate append.

## Public World proving journey

A cache-free Python 3.12 environment installed public `ace-domain-world-intelligence==0.10.0` and
resolved public `ace-core==0.6.0`; optional adapters were not installed transitively. A second
isolated run cloned only the exact public World tag and explicitly installed the hash-verified Core
reference Action adapter and World official-source adapter. Core and both adapters imported from
`site-packages`, no Core checkout was present, network access was disabled for the recorded-data
journey, and two fresh workspaces produced identical bounded projections.

The public path is:

```text
Observation -> Shift -> Signal -> Brief -> Decision -> reviewed Action
            -> observed Outcome -> governed feedback
```

| World-owned measure | Classification | Matched pairs | Mean effect | Proposal |
|---|---|---:|---:|---|
| structural citation coverage | useful | 2 | 1.0 | promote, non-effective |
| citation correctness | useful | 2 | 1.0 | promote, non-effective |
| contradiction attention | useful | 2 | 1.0 | promote, non-effective |
| correction detection delay | useful | 2 | 1.0 | promote, non-effective |
| correction-induced revision stability | useful | 2 | 1.0 | promote, non-effective |
| single-event forecast scoring | useful | 2 | 0.5 | promote, non-effective |
| independent BLS correction quality | useful | 2 | 1.0 | promote, non-effective |

The contradiction-attention treatment preserved one valid silence with recall `1.0` and false-
alert rate `0.0`; the control used the same alert volume while alerting on the valid statement and
remaining silent on the contradiction. Raw ingestion or alert count therefore cannot explain the
measured difference, and silence remains an explicitly scored valid result.

Every proposal remained non-selectable and unapplied. The separately authorized structural-
coverage review reproduced `reject` / `no_action`, preserved the useful evaluation and promote
proposal, and changed no effective governed state. Historical evaluation replay required no new
authorization. These exact product-owned measures and recorded-source policies remain in World;
the Core and Intelligence contracts contain no World nouns.

World pre-publication verification passed 135 domain tests, 80 separate-adapter tests, 9 release-
contract tests, Ruff check/format, workflow-YAML and diff checks, strict metadata validation, and
repeated byte-identical builds. World merged-main CI and the public closeout CI passed against the
public Core 0.6.0 dependency.

## Core verification composed

The exact release candidate passed 51 focused package, measured-impact, disposition, and adapter
tests with 2 environment skips. Pull request #96 then passed all six required normal-checkout jobs:
lint, Canvas typecheck/tests/build, fast tests, security audit, zero-extension kernel, and Docker
build/health probe. Earlier focused packets passed the 99-test measured-impact/action composition
lane, all real-store restart paths, the complete non-E2E/non-extension suite split around the
linked-worktree-only historical baseline limitation, package builds, installed-wheel imports,
format checks, and diff checks. The trusted publication rerun passed after the build-only repair
described above.

## Issue #49 disposition

Issue [#49](https://github.com/augmented-cognition-engine/core/issues/49) remains open. F1 and F5
are complete in merged Core `7013de62ae7320c51c3de9e9a03b049e768e4d84`. F3 is explicitly
unresolved and unwaived, due `2026-11-05`, under trusted-installed-packages-only containment, the
`ACE_DISABLE_EXTENSIONS=1` kill switch, compatibility matrix, and operator disablement. ACE 0.6.0
does not expand the supported extension surface. F2, F4, F6, and F7 retain their recorded deadlines
and containment; this release does not silently resolve them.

## Acceptance and boundaries

The exact public artifacts satisfy issue #38's bounded acceptance gate: the public journey links
inspectable outcomes and provenance through a governed change; uses frozen matched conditions;
discloses leakage controls and limitations; distinguishes useful evaluated signals from raw
ingestion; preserves no-change/no-action as valid outcomes; and passes compatibility, security,
artifact, publication, and clean-install checks. ACE 0.6.0 is therefore passed.

This result is deterministic association under explicit product-owned recorded-data criteria. It
does not establish causality, population performance, general model or Brief quality, human or
customer benefit, current network freshness, autonomous monitoring, autonomous publication,
distributed execution, hostile-code isolation, or general SI4 completion. Material use is not
benefit. Evaluation and proposal do not grant action, policy, or promotion authority. F2 remains
not ready because no demonstrated product need justified broadening the consequence contract.

The next bounded packet is the 0.7.0 Domain and Extension Platform contract, using an independently
public Market Intelligence measured-impact journey as a second-domain falsifier. It must preserve
the same neutral identities and authority boundary; it is not required to retroactively complete
this World-based public release receipt.
