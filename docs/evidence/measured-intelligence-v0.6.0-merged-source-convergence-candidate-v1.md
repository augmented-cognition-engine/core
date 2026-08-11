# ACE 0.6.0 Measured Intelligence merged-source convergence candidate evidence (v1)

**Status:** bounded candidate evidence. This is not a tag, publication, issue #38 closeout, SI4
pass, proposal application, or ACE 0.6.0 release claim.

**Recorded:** 2026-08-11

## Exact source and review identities

| Surface | Exact identity |
|---|---|
| Core merged `main` | `7013de62ae7320c51c3de9e9a03b049e768e4d84` |
| Core merged stack | PRs #88 through #93, merged in dependency order |
| Core main CI | [run 31520372788](https://github.com/augmented-cognition-engine/core/actions/runs/31520372788), all six gates passed |
| World executable source | `cb7b6fdb2b9fe4dd3c34df8afc1368c86d026710` |
| World merged-Core evidence commit | `a85da4289ff80fff6e6507b546dca191ff92d841` |
| World review surface | draft [PR #17](https://github.com/augmented-cognition-engine/domain-world-intelligence/pull/17) |
| World PR CI | [run 31522715774](https://github.com/augmented-cognition-engine/domain-world-intelligence/actions/runs/31522715774), passed |
| Independent Market source | `cd1f2f2c862e5665344e47885f594a77c5aaa59b` |

The World and Market consumers used the exact installed Core wheel below. Market remained a
separate private repository; this public record contains no private fixture, source, customer
material, credential, or extension code.

## Reproducible artifact identities

Each wheel was built twice with the exact source epoch shown. The paired SHA-256 values were
identical.

| Artifact | Source epoch | SHA-256 |
|---|---:|---|
| `ace_core-0.5.0-py3-none-any.whl` | `1786471152` | `662c4197f3ff0cf7dc1e64b0f8bc6bc705c8a1d6373a8468d9cb1d2df3d8c214` |
| `ace_reference_workspace_action-0.1.0-py3-none-any.whl` | `1786471152` | `31463fbcfe2a9c62b5cc9abe0a67814cd7fdd36de3c9f6ec47835d7be080ed5a` |
| `ace_ext_world_federal_register_source-0.2.0-py3-none-any.whl` | `1786466888` | `4841a02b46fba867d8bac092cd2eab1a45e71537d364fda389192857313e049c` |
| `ace_domain_world_intelligence-0.9.0-py3-none-any.whl` | `1786466888` | `8470b903c165e6897159172c918245fbc7bae7470ce6ad82dbb940776417c049` |

No version changed and no artifact was published. The local Core wheel still reports `0.5.0`; its
complete source commit and hash distinguish it from public `ace-core==0.5.0`.

## Public World result

A fresh Python 3.12 environment installed all four exact wheels plus public dependencies. Core,
the reference Action adapter, and the World source adapter imported from `site-packages`. The
generator rejected every declared Core checkout root. Two fresh workspaces emitted byte-identical
canonical JSON:

```text
sha256:c62a7db77b66a15f2930c850bdb8bbc44b542f928c2e0b146b5bf3dde08f30df
```

The exact BLS correction pair still produces treatment `[1.0, 1.0]`, control `[0.0, 0.0]`, two
matched pairs, mean effect `1.0`, and bounded `useful`. The `promote` proposal remains
non-effective, non-selectable, unapplied, requires human review, and is not reauthorized on
historical replay.

World verification against the installed merged Core wheel:

```text
complete World suite: 123 passed in 37.82s
official-source connector suite: 80 passed in 0.65s
package/release contract: 7 passed in 0.07s
updated convergence and release controls: 10 passed in 2.20s
```

## Independent Market result

The independent Market production-store acceptance retained its deliberately different result:

```text
classification: unproven
treatment mean: 1.0
control mean: 0.5
mean effect: 0.5
proposal: reject
live_effect: false
selectable: false
requires_human_review: true
evaluation digest: sha256:cba0ec7d5252f53f65243d1ecd3c98295f6773b1fa90649cbc544b377cec8dca
transaction receipt: append_only_receipt:f384e488f58f3752e6591a427ce4fc5c
```

Core schema v177 was applied to a disposable SurrealDB 3.2.1 store. The execute phase persisted the
exact journey through `SurrealImmutableRecordStore`; a fresh process reopened the same transaction
after a real database restart without current authorization or reclassification. The focused
authority, interruption, and replay lane passed `5` tests. The complete Market backend passed
`379 passed, 8 skipped, 4 deselected` against the installed merged Core wheel.

This private second-domain falsifier proves unchanged neutral expressibility and durability. It is
not public Market data, a new provider run, causal evidence, customer benefit, or general Market
quality evidence.

## Core and security verification

```text
merged measured-impact + F1/F5 focused lane: 82 passed in 10.83s
main push CI: lint, fast tests, naked kernel, Canvas, security audit, Docker build passed
clean installed-environment pip-audit 2.10.1: no known vulnerabilities found
```

The vulnerability audit could not resolve the two separately built adapter distributions on PyPI
and reported them explicitly as skipped; all public resolved dependencies were audited. The clean
environment installed public dependencies from the public index, but it used local exact candidate
wheels. A public-index-only 0.6 install remains impossible until a 0.6 package is actually
published and is therefore still an open release gate.

## Release-state corrections and issue #49

The stacked merge automatically closed issue #38 despite the explicit no-close boundary. The
milestone was reopened with a public correction; it remains **Next**.

F1 and F5 implementation are now merged and reproduced from exact `main`. Issue #49 remains open
until an authenticated owner reconciles its checklist. F3 remains unimplemented and requires an
explicit owner decision; this evidence neither waives nor silently re-dates it.

## What this proves and what remains

The exact merged Core source supports a reproducible public World `useful` result and an independent
Market `unproven` result through the same neutral measured-impact contract. Both preserve exact
attribution, append-only replay, explicit uncertainty, restart durability, and proposal-only
authority. This is the smallest honest cross-domain convergence result; it is not a supported or
published release.

Remaining gates are World PR #17 review/merge, explicit issue #49 owner
reconciliation including F3, final Core/World version and artifact identities, public-index-only
installation, release compatibility/security acceptance, publication, and explicit release-owner
acceptance. No tag or publication occurred.
