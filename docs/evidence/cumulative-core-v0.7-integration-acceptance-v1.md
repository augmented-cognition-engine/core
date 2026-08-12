# Cumulative Core 0.7 integration acceptance candidate v1

Status: **candidate, local**. This record proves one exact cumulative Core source tree and prepares
it for review. It does not merge, release, tag, publish a package, close issue #39, or replace the
separate review authority of any stacked pull request.

## Exact coordinates

- release base: `main` / `origin/main` at
  `492b99667b0a119234d4a8af26e448254c0a6abd` (`ace-core` 0.6.0 closeout);
- cumulative source: `codex/v0.7-agent-memory-am3` at
  `656ddc83cc40d2e078c27d816d7c66d6fc2c6533`;
- integration-preparation branch: `codex/v0.7-cumulative-integration-acceptance`;
- initial integration branch head: exactly
  `656ddc83cc40d2e078c27d816d7c66d6fc2c6533` before any integration-owned change;
- base is an ancestor of the source, with 27 cumulative commits, 179 changed paths, 55,501
  additions, and 165 deletions before integration closeout.

The cumulative tree is a fast-forward descendant of the exact release base. Every required
candidate head is present as an ancestor, and the two intentional convergence commits preserve
their two parents.

## Ordered review topology

| Review authority | Exact head | Dependency or convergence constraint |
|---|---|---|
| PR #99 | `f667b12ecf75a7a5c4e6e7d5aea6950db8976919` | exact 0.6 main |
| PR #100 | `793758b7274308c4ddcc4a6b5e37facfb0ebf469` | PR #99 |
| PR #102 | `20a8a29e0eef9bfa5b6048f057fb2187d809ecbb` | PR #100; includes 0.7B implementation parent `2ff29ac` |
| PR #103 | `e1f6492db2417cbeccee14c04c5803ba1502afa6` | PR #102 |
| PR #104 | `dab0866af239af9a13b4d2772a0d3950f932fa2e` | PR #103 |
| PR #105 | `10bbed620291ac5f552c3313dd37580938a5b9d7` | PR #104; includes activation implementation parent `1fe4c35` |
| PR #107 | `26fa78dda31db1041f5bf0d838ede0916f0749af` | PR #105; AC1–AC3 composition spine |
| PR #108 | `48e1aea6ff848be63aab2d49adda1428231ca522` | PR #105; independent AM0 sibling |
| PR #109 | `78cbf7b810dd0774e878ca7ec0a6d06a6055ea73` | PR #107; composition bridge |
| PR #110 | `da545b2e8a41d343e4d034a3e244861895cf95f9` | PR #109; lifecycle sibling |
| PR #111 | `5536da71e37b153739a910f90f80737079ce9453` | PR #107; governance sibling |
| PR #112 | `37dd899c7a5b54c0f6a01f5691da95f992f31c4d` | two-parent convergence of PRs #110 and #111 |
| PR #113 | `f8b3ea3ab764d0630ad6e4b0649f566893cba484` | PR #112 |
| PR #114 | `79629ed4da17908b194df5c2d64ae7ec1a00dcbd` | PR #113 |
| PR #116 | `c7ff511a80ab3bdd3a13e7ca270567eaf6b3b1bf` | PR #114; AC7 freeze point |
| PR #117 | `a55edc2848c742dc98cfa01f6632bb75d5f31d81` | two-parent convergence of PRs #116 and #108 |
| PR #118 | `8b5cd08e5c49962024323bb981bc221deacef649` | PR #117; AM1 |
| PR #119 | `0938a63d577f817a68c61cbd8b56841c50d770e2` | PR #118; AM2 |
| PR #120 | `9cf4d56fa88dc8c75c69a730319f05af976d3240` | PR #119; isolated four-path AM2 repair |
| PR #121 | `656ddc83cc40d2e078c27d816d7c66d6fc2c6533` | PR #120; AM3 implementation parent `52c3d9c` and evidence closeout |

No required candidate is missing. No candidate head is silently duplicated. PR #108 remains the
AM0 review authority; PR #117 is only the exact convergence authority. PRs #110 and #111 remain
sibling authorities; PR #112 is only their exact convergence authority.

## Collision and public-boundary audit

- Effective source diff against exact main applies without textual conflict or whitespace error.
- `ace.application`, `ace.core`, `ace.intelligence.contracts`, and `ace.testing` export unions contain
  respectively 344, 217, 397, and 26 unique names with no duplicate `__all__` entries.
- Package identity remains `ace-core` version `0.6.0`. The cumulative package-data change only adds
  the machine-readable `ace/intelligence/schemas/*.json` contract family.
- Schema head remains v177. The cumulative diff adds no Surreal schema or migration.
- The thin public MCP surface remains exactly eleven tools.
- World and Market nouns, source adapters, policies, fixtures, and application code remain outside
  Core.
- The only cumulative CI collision found was formatting drift in 16 stacked-candidate paths. The
  integration branch applies the repository's installed Ruff formatter mechanically to those paths;
  no contract, identity, authority, persistence, or runtime behavior is changed.

## Combined journey

`tests/test_cumulative_v07_integration_acceptance.py` runs one provider-free cumulative path:

```text
Connect -> Map -> Watch -> Brief -> Activate
        -> AC7 policy admission/runtime resolution
        -> AM3 authorized recall -> Context Manifest consumption
```

The test binds the exact approved Watch/Brief coordinates into the v1alpha2 activation plan,
reopens the committed activation, admits and reopens the independently reviewed AC7 policy,
resolves its non-authoritative runtime result, plans and reopens the AM3 Context Manifest, and lets
the composition bridge consume only the exact opaque manifest and selection references after a
fresh runtime check. Activation lineage remains historical/non-live. The composition policy grants
no authority and creates no participant eligibility. Memory cannot choose participants, widen
tools, or rewrite activation or composition authority.

## Verification

| Gate | Result |
|---|---|
| Combined 0.7A–0.7E, AC1–AC7, AM0–AM3 plus aggregate journey | 318 passed |
| GitHub CI-equivalent Core posture, `not e2e` | 7,820 passed, 48 skipped, 249 marker-deselected |
| Naked kernel, `not e2e and not requires_extensions` | 7,806 passed, 50 skipped, 261 marker-deselected; one teardown-only transaction conflict passed in exact isolated rerun |
| Package/schema/evidence integrity selection | 45 passed |
| Exact MCP/package/kernel boundary selection | 53 passed |
| Ruff lint and whole-repository format | passed after the 16-path mechanical integration fix |
| Lock and Git whitespace | passed |

The normal and naked full gates include the cumulative restart/reopen tests. Focused AM1–AM3 real
Surreal restart, fresh-process, projection-rebuild, stale-refusal, and later material-use coverage
also remains in the exact source ancestry. One sandboxed focused rerun could not bind localhost;
the unchanged selection passed 318 tests when rerun with loopback permission.

## Installed-wheel reproduction

The final integration tree built `ace_core-0.6.0-py3-none-any.whl`:

- size: 6,277,408 bytes;
- SHA-256: `9853c8dbe32cc05c2fffa2694e029019c3ccc65c2bed7f8c6d27310307c6bd73`.

Two independent target directories installed that exact wheel without dependencies. Both imported
`ace` from their target rather than the source checkout and reproduced identical first-Brief,
session-revision, AC7 fixture/result, and Context Manifest contract identities. Both exposed the
activation, composition-policy, and context-planner services and exactly these eleven thin tools:
`ace_start`, `ace_load`, `ace_capture`, `ace_task`, `ace_status`, `ace_search`, `ace_related`,
`ace_briefing`, `ace_history`, `ace_capture_idea`, and `ace_impact`.

The candidate intentionally still identifies as distribution version 0.6.0. Consumers must bind
the exact artifact hash and required symbols; a version comparison alone cannot distinguish this
candidate from the published 0.6.0 artifact.

## CI finding

Core's unchanged workflow already declares `pull_request: branches: [main]`. Every current stacked
review PR targets another feature branch, so GitHub correctly created no pull-request workflow run
for those heads. There was no missing workflow and no safe reason to broaden CI to every internal
stack edge. A draft aggregate review against exact main is the smallest honest mechanism for CI on
the cumulative tree. It must remain review/CI-only until the control tower accepts a landing plan.

## External consumer gates

- World PR #21 is accepted external evidence at
  `201f2a0e742ab81109e0da0bc62818f8dae57006`; CI run 31631295659 completed successfully. It binds
  exact Core candidate wheel SHA-256
  `19b75ab8dd2e2cc69f432a97fd7401eb0f55c9b5b7e2deeed0ae17e2396dff57` and World wheel SHA-256
  `fe51c3266036b3a83c34d510ce3460524d4ad4a5ae515adc4272b2a9d3fc4ad8` without claiming public
  resolver compatibility.
- Market remains an external dependency owned in its repository. This record does not claim a
  green or conflict-free Market gate until that owner provides an accepted handoff.

## Safe landing and rollback map

The aggregate draft is an integration review and CI surface, **not** an authority to squash the
entire stack. A squash would erase the two convergence-parent relationships and obscure the
separate sibling review authorities.

Safe landing requires either:

1. accept every stacked authority in the topological order above, preserving the two convergence
   commits and retargeting only after each dependency is accepted; or
2. after all individual reviews are accepted, merge the exact cumulative DAG to main with a merge
   commit that retains its parents and close the individual PRs as reviewed constituents.

Do not squash the aggregate. Before landing, rollback is deletion of only the integration branch.
After a merge-commit landing, rollback is one explicit revert of that aggregate merge; immutable
records already written by a candidate runtime remain history and are not rewritten. If constituent
PRs land separately, rollback proceeds in reverse topological order: AM3, AM2 repair, AM2, AM1,
the AC7+AM0 convergence, AC7 through AC5, the AC4/AC3 convergence and siblings, AC1–AC3, AM0,
Activate, Watch/Brief, Map, Connect, stable pack contract, and kickoff. Reverting a convergence
must not delete or rewrite either sibling branch's reviewed history.

## Limits

This candidate does not establish a public 0.7 package, resolver compatibility, user interface,
provider implementation, connector execution, hostile-extension isolation, distributed operation,
general memory benefit, causal correctness, World or Market release, or release readiness. AM4,
AM5, AC8+, merge, tag, release, and publication remain outside this packet.
