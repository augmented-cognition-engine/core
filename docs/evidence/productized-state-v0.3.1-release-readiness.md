# ace-core 0.3.1 Productized State release evidence

Status: **passed; published artifacts and clean public-index installation verified**

Date: 2026-08-05

## Release decision

ace-core 0.3.1 completes the Productized State promise for the 0.3.x release line. A builder can
install ACE and a compatible extension, discover its bounded Product State adapter, ingest product
context under authenticated Core-owned scope, inspect composed state and provenance, make and
correct a decision, restart the runtime, and observe the correction materially influence a later
decision.

The release preserves the package and import identities, supported Python 3.12 runtime, schema head
v171, existing CLI identities, and exactly eleven thin MCP tools. It adds the focused `ace state`
command group and authenticated Product State HTTP reads/writes without granting models or source
content product-scope, review, promotion, or execution authority.

## Immutable release identity

| Material | Identity |
|---|---|
| Implementation | [PR #51](https://github.com/augmented-cognition-engine/core/pull/51), merge `927b5a367991b13c547aa6b412cdad1624ac2a0c` |
| Release reconciliation | [PR #52](https://github.com/augmented-cognition-engine/core/pull/52), candidate `865b2d7a54ba4f9562648eec782ae6a0ef1ca574` |
| Release commit | `8af5a499b6f57e1b4cdd708af103bf8d0393e369` |
| Release tree | `02138c8246d69eb04c044670871c7bbc293959c4` |
| Tag and GitHub Release | [`v0.3.1`](https://github.com/augmented-cognition-engine/core/releases/tag/v0.3.1), published 2026-08-05 21:00:06 UTC |
| Official release-candidate CI | [run 31045830760](https://github.com/augmented-cognition-engine/core/actions/runs/31045830760) |
| Trusted publication | [run 31046716886](https://github.com/augmented-cognition-engine/core/actions/runs/31046716886), `release` event, exact tag SHA, passed |
| Public package | [`ace-core 0.3.1` on PyPI](https://pypi.org/project/ace-core/0.3.1/) |

The release merge retains the exact candidate tree. The release-commit artifacts were rebuilt from
the merge commit timestamp rather than reusing the pre-merge candidate archives.

## Product acceptance

The frozen [`productized-state-public-journey-v1`](productized-state-journey-v1.md) acceptance
passes authenticated ingestion and exact replay, complete scoped inspection, schema-zero v171 and
v168→v171 upgrade, real database/API/worker restarts, interruption/retry behavior, decision and
correction lineage, and exact later material use with zero provider calls.

The final 0.3.1 release rerun passed all 19 acceptance checks in 90.552 seconds. It recorded schema
zero at v171, a v168→v171 upgrade with its sentinel preserved, maximum restart time of 2.771 seconds,
22 stable records, seven selected evidence items, and zero provider calls, tokens, retries, or cost.
API and worker health both reported 0.3.1. Its acceptance SHA-256 is
`7bb5be92a599560f7c714b0878e3bfcc0ca2f50bcf297710d5a473dff42738fc`; it preserves frozen config
SHA-256 `7916f0f7566e74a9b1981210e3e710ceb5876e9874369ed18f9abc8c1c1cdbd3` and corpus SHA-256
`85907acc8ad5b9a73d2d7551ced98d1bb26d4b9ea51a189d262675cb5ff9ea28`.

## Repository and release gates

- Focused Product State, authentication/scope, graph, journey, and E1 conformance: 53 passed.
- Package identity and same-minor/cross-minor matrix policy: 17 passed.
- Ruff lint, Ruff format, whitespace, secret, JSON, dependency, and archive checks passed; the
  dependency audit found no known vulnerabilities and skipped only the then-unpublished local
  `ace-core==0.3.1` candidate.
- Complete extension-enabled lane: 6,967 passed, 46 skipped, 247 deselected.
- Complete naked-kernel lane: 6,953 passed, 48 skipped, 259 deselected.
- Three tests in each local complete lane assumed that `.git/HEAD` is a regular file and therefore
  failed only inside the linked release worktree. The exact immutable candidate was cloned normally
  and that seven-test baseline module passed 7/7. Official CI then passed the complete lint,
  security, Canvas, fast-test, naked-kernel, and Docker health-check matrix.
- A clean candidate-wheel install verified distribution/import/client/engine version 0.3.1, schema
  v171, packaged README and Productized State documentation, complete `ace state` help, exactly
  eleven named MCP tools, and zero loaded extensions when extensions were disabled.

## Reproducible package and publication evidence

The exact release commit passed the current/v0.3.0 package matrix, both mixed wheel/source
directions, an independently packaged extension consumer, zero-extension boot, and archive
exclusions. Because v0.3.1 and v0.3.0 are same-minor releases, compatibility is accepted in both
directions; the verifier retains fail-closed predecessor behavior across a minor boundary.

| Artifact | SHA-256 |
|---|---|
| Release matrix receipt | `77f3194445fe6f6da7779ca8dce15d2bf57c54881f042a39228402348d41d75e` |
| `ace_core-0.3.1-py3-none-any.whl` | `e6df7a5834c9caed1261e6dc93d4b3335f283b8b8b90e37a3bb434350982b7c6` |
| `ace_core-0.3.1.tar.gz` | `48f881a3f631fff9e0b1d49f78fdc87942049a1ae667fc3f9ef57e37de5ec667` |

Trusted-publishing run 31046716886 validated that the tag matched package version 0.3.1, set the
release commit timestamp for reproducible builds, built both distributions, and published them to
PyPI through the protected `pypi` environment. The downloaded workflow artifacts, PyPI metadata,
and files independently downloaded from `files.pythonhosted.org` all reported the exact hashes
above and compared byte-for-byte with the release-commit matrix artifacts. Neither file is yanked.

A fresh Python 3.12.13 environment then installed `ace-core==0.3.1` with all dependencies from the
public PyPI index. It verified distribution, `ace`, thin-client, and engine version 0.3.1; schema
v171; packaged README, roadmap, and Productized State evidence; complete `ace` and `ace state` help;
and exactly the eleven named thin MCP tools with extensions disabled.

## Security and support boundary

PR #51 hardened the new write boundary so a missing or malformed token product and any adapter
output outside the authenticated product fail before persistence. Official security audit and the
focused cross-product, malformed-scope, foreign-read, and exact-replay tests passed. The v0.3.0
independent AI review is historical evidence for the inherited E1 trusted-extension boundary; it
is not represented as independent certification of the changed 0.3.1 artifact.

The supported claim remains one database, one API/worker deployment, synchronous adapters, trusted
installed Python extensions executing in process, and fictional public-safe evidence. It does not
establish hostile-code isolation, distributed ordering, multi-writer or multi-region guarantees,
general real-world causal correctness, autonomous learning, a general world model, or beneficial
impact.

## Reconciliation

PS1 is `passed`. The public roadmap advances 0.4.0 Governed Cognition to **Now**; milestone issue
[#2](https://github.com/augmented-cognition-engine/core/issues/2) is closed with this immutable
release evidence, and the public Project records the same transition. Future 0.3.x work is limited
to compatible Productized State maintenance unless a separately reviewed roadmap change says
otherwise.
