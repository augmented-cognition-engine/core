# GI2 — public cross-domain falsification (v1)

**Status:** passed
**Date:** 2026-08-09
**Outcome:** GI2, domain-neutral Intelligence substrate

## Claim

ACE Core + Intelligence can compile, activate, and isolate materially different external Domain
Packs without adding domain vocabulary, persistence, authority, reasoning, or lifecycle branches to
the platform. This is a bounded falsification result over the published World and Market packages.
It is not a claim that every possible domain fits unchanged.

## Public release identities

| Component | Public identity | Release |
|---|---|---|
| Core + Intelligence | `ace-core==0.4.1` | [GitHub](https://github.com/augmented-cognition-engine/core/releases/tag/v0.4.1) · [PyPI](https://pypi.org/project/ace-core/0.4.1/) |
| World Domain Pack | `ace-domain-world-intelligence==0.8.0` | [GitHub](https://github.com/augmented-cognition-engine/domain-world-intelligence/releases/tag/v0.8.0) · [PyPI](https://pypi.org/project/ace-domain-world-intelligence/0.8.0/) |
| Market Domain Pack | `ace-domain-market-intelligence==0.6.0` | [GitHub](https://github.com/augmented-cognition-engine/domain-market-intelligence/releases/tag/v0.6.0) · [PyPI](https://pypi.org/project/ace-domain-market-intelligence/0.6.0/) |

The Market release was built from commit `7c144db9eab03964d37a06e3f3222afeef084b37` by the
credential-free trusted-publication workflow. Its published artifacts are:

- wheel `ace_domain_market_intelligence-0.6.0-py3-none-any.whl`, SHA-256
  `73220bbd16d295734e7dc322147e6e3137752306ef9758f48fa6aecabdfeb080`;
- sdist `ace_domain_market_intelligence-0.6.0.tar.gz`, SHA-256
  `8082a5589f9608fa9d7f9827a8986d5413514d57e5878bcba7e829fb47388575`.

The [successful publication run](https://github.com/augmented-cognition-engine/domain-market-intelligence/actions/runs/31333497948)
records both hashes and their PyPI attestations.

## Independent tagged-domain reproduction

The public World `v0.8.0` tag resolves to commit
`a19126814fe620131ca1ccef4d91f57b27c275af`. From a fresh clone of that tag, the locked test
environment and the source-path declared by its CI produced:

```text
81 passed in 12.70s
```

The tagged fixtures and tests reproduce the frozen identities:

- Case `case:412426eee708d56f6bda931ccf9e5d8b`;
- Brief `brief:25d8232c9bfa27050bdcb160fb75f06c`.

This converts the P2A–P2F World packets from local candidate support into a publicly rerunnable
second-domain challenge. The original packet records remain unchanged as point-in-time evidence.

## Clean public-index two-domain journey

A new Python 3.12 virtual environment installed only these exact public requirements:

```text
ace-core==0.4.1
ace-domain-market-intelligence==0.6.0
ace-domain-world-intelligence==0.8.0
```

No source checkout, local wheel, Market connector, World connector, or private B2B application was
on the runtime path. The verifier then:

1. loaded each installed pack through `importlib.resources`;
2. compiled both through the unchanged public `ace.intelligence.packs` contract;
3. confirmed distinct pack identities and digests with the same compatibility contract;
4. prepared and bound independent active revisions under the same product;
5. confirmed distinct activation identities and domain vocabularies;
6. appended a `RETIRED` Market revision; and
7. rebound the exact World revision and confirmed it remained `ACTIVE` and byte-identical.

Observed result:

```text
{
  'core': '0.4.1',
  'market': '0.6.0',
  'world': '0.8.0',
  'market_state': 'retired',
  'world_state': 'active',
  'connector_absent': True,
  'public_index_gi2': 'passed'
}
```

The Market release-line suite separately passed `126` tests with one intentionally skipped
network-ownership case. Its wheel boundary contains exactly 39 JSON resources and no Python or
native executable payload.

## Layer-boundary result

- **Core** remained unchanged and owned authority, temporal and immutable state, receipts, and
  activation persistence.
- **Intelligence** remained unchanged and owned pack compilation, activation binding, and lifecycle
  interpretation.
- **World** supplied actor, claim, event, correction, epistemic-status, Case, and public-source
  semantics.
- **Market** supplied competitor, product, price-move, persona, routing, Brief, and bounded feedback
  semantics.
- Retiring one domain did not alter or invalidate the other.

That is the narrow domain-neutrality claim GI2 required.

## Limits and outcomes not advanced

GI2 does not establish hostile-code isolation, distributed operation, private-source entitlement,
continuous scheduling, Monitor or Subscription product behavior, delivery authority, autonomous
learning, general causal accuracy, omniscience, or beneficial real-world impact. It does not close
GC1, E2, SI1, SI2, SI3, or SI4. Those outcomes retain their own acceptance gates.

## Reconciliation decision

All GI2 acceptance dependencies are public and independently rerunnable: the Core evidence is on
the 0.4.1 release line, World is a tagged second-domain conformance journey, Market is an independent
public package, and their clean public-index coexistence and retirement isolation pass. GI2 advances
from `not ready` to `passed`.
