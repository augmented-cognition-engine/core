# GC1 — public governed-cognition external-consumer closeout (v1)

**Status:** public, passed

**Date:** 2026-08-09

**Outcome:** GC1, supported governed-cognition builder journey

## Claim

The public governed-cognition lifecycle is reproducible from published artifacts by an independent
domain consumer. Market Intelligence used only the supported `ace` CLI from a clean
`ace-core==0.4.4` installation to teach a sourced capability, inspect it, approve it through human
authority, materially use the exact approved revision, stop and restart the API over the same
durable database, use the same revision again, retire it, and prove that a distinct later required
use failed closed.

This record composes that external journey with the public Core builder-surface receipt and the
released Core conformance tests for the lifecycle branches that the Market journey did not repeat.
It does not treat one successful domain demonstration as proof of reasoning quality or general
beneficial impact.

## Public identities

| Component | Public identity | Exact source |
|---|---|---|
| Core + Intelligence | `ace-core==0.4.4` | [release `v0.4.4`](https://github.com/augmented-cognition-engine/core/releases/tag/v0.4.4), commit `ca7ee1f1e04c02e43a2db05c3bb6355feb011180` |
| Market Domain Pack | `ace-domain-market-intelligence==0.6.0` | unchanged inert distribution |
| External consumer packet | Market repository main | [pull request #3](https://github.com/augmented-cognition-engine/domain-market-intelligence/pull/3), squash commit `eb596664a2e2736a9b4d97e296c3e59ebcd9b88f` |

The [trusted publication run](https://github.com/augmented-cognition-engine/core/actions/runs/31345474622)
published the exact Core tag to PyPI. Public artifacts were:

- `ace_core-0.4.4-py3-none-any.whl`, SHA-256
  `25949e984d68e1f917fc0aef9a123e550618d401ec4be73d2f49f21c77a9245e`;
- `ace_core-0.4.4.tar.gz`, SHA-256
  `85af82368f71abfa4da94a11b37049e760e42da7c30d4c0633a8f9a160b6eff9`.

A fresh Python 3.12 environment installed 0.4.4 from the public PyPI index. The distribution,
`ace.__version__`, `ace_mcp_client.__version__`, and Core runtime version all reported `0.4.4`.
The database migrated from schema v0 to v176. No Core source checkout or locally built Core wheel
was on the consumer runtime import path.

## External journey result

The independent consumer packet is archived in the
[Market repository](https://github.com/augmented-cognition-engine/domain-market-intelligence/blob/main/docs/evidence/gc1-market-external-consumer-v1.md).
Its machine-readable receipt has SHA-256
`b239b314b34c3dfedddb72907b63abe5bf3197013b8d1460466ff4942f714682`.

| Boundary | Exact result |
|---|---|
| Source task | `task:9295nllkmh074tv3pr58` |
| Proposal | `cognition_proposal:a1306d345dfd5bc0e9fb7182905ab383`, initially non-selectable |
| Semantic diff | SHA-256 `5211778bfd65a2177894180029898fa80a27374246fb8819959261d46db342b5` |
| Human review | `cognition_review:2dead1ebed5de7e6fea92a553b6c3e5c`, disposition `approve` |
| Approved revision | `cognition_revision:02db82ccd8f2f5776bc49ef88f71ec62` |
| Active head | `cognition_head:dcc2299f646ad9a0a811f8bd4898a1c9`, generation 1 |
| Pre-restart use | task `task:3ohtjhggviqo25arnoax`, material-use hash `919ac46758ee244fbf9e029b79155313d568aa08295e0c0e8097a7ca516872f5` |
| Post-restart use | task `task:ino203d0bq12znb1dlmz`, same required revision and material-use hash |
| Retirement | `cognition_lifecycle:5d673126b4c5e84b46014c038b29fd74`, resulting lifecycle `retired` |
| Distinct later request | failed with `cognition_use_attribution_incomplete` |

The revision hash
`e04977c31966cef53b85f64bbefa20b871f3223245463eab18f6700642d29730` and active-head hash
`7bb755abaabf53da8933de9981b4c377c79aab34f01087e7ad94a81cabf11f05` were byte-identical before
and after the API restart. Both successful tasks had matching non-empty selection and use revision
sets that included the approved Market revision.

The failure probe intentionally used a different post-retirement request. ACE replays an identical
task inside its idempotency window; repeating the earlier request would retrieve its valid durable
receipt rather than make a new eligibility decision.

## Composed lifecycle coverage

The external journey proves the public prepare → restart → resume → retire path. The released Core
suite supplies deterministic branch coverage for the rest of the supported lifecycle:

| Promise | Released verification |
|---|---|
| model cannot approve or mutate governed state | `tests/test_governed_cognition_governance.py` and `tests/test_governed_cognition_lifecycle.py` |
| rejection creates a durable receipt without a revision or head change | `test_rejection_creates_receipt_without_revision_or_head_change` |
| approval creates an immutable revision and generation-checked active head | `test_human_approval_creates_immutable_revision_and_cas_head_atomically` |
| revision and rollback preserve history and restore selection | `test_governed_cognition_chain_survives_fresh_database_connection` |
| expired cognition is filtered before scoring | `test_expired_active_head_is_filtered_before_scoring` |
| unavailable required dependencies fail the candidate closed | `test_unavailable_required_dependency_fails_candidate_closed` |
| selected-but-unused cognition cannot be reported as successful use | `test_cognition_use_fails_closed_without_material_use_attribution` |
| matched outcomes distinguish helped, hurt, unproven, unused, and stale | `tests/test_governed_cognition_effectiveness.py` |
| harmful or stale evidence proposes revision or retirement but cannot activate it | `test_matched_high_confidence_help_and_harm_are_distinct` and `test_unused_and_stale_are_explicit_and_only_stale_can_propose_retirement` |

These tests are part of the exact public 0.4.4 source identity. The Core 0.4.4 release gates passed
7,378 normal and 7,376 extension-disabled tests; all six official pull-request checks and trusted
publication passed. The Market consumer repository passed 133 tests with one expected skip in its
CI-equivalent locked environment; its official pull-request CI passed.

## Boundary result

- Core owns immutable proposals and revisions, human review receipts, active heads, discovery,
  selection/use attribution, lifecycle transitions, effectiveness receipts, and persistence.
- Intelligence and the Market Domain Pack supply the external consumer context without adding
  Market nouns to the cognition model or receiving approval authority.
- The consumer imports no `ace` or `core.engine` Python modules. It drives the public CLI over the
  authenticated application boundary and is excluded from the inert Market wheel.
- No twelfth MCP tool, second cognition model, model-write authority, or domain-specific Core path
  was added.

## Limitations

This evidence is bounded to ACE's documented single-node topology and trusted in-process Python
extensions. It does not prove cross-database portability, distributed approval, hostile-code
isolation, general causal accuracy, autonomous learning, or beneficial real-world outcomes. The
Market revision was selected alongside Core-default cognition: the receipts prove exact inclusion
and material use, not exclusive use. Effectiveness classification and revision/retirement
recommendations are proven by released Core conformance tests, not by a real Market outcome cohort.

## Reconciliation decision

GC1 advances from `active` to `passed`. The public builder surface, external-consumer lifecycle,
restart durability, exact attribution, failure controls, measurement classifications, revision,
rollback, and retirement promises now have reproducible evidence with explicit boundaries. This
closes the 0.4.x Governed Cognition milestone; 0.5.0 Reasoning into Action remains `next`, with its
own T1 and B1 acceptance work still not ready.
