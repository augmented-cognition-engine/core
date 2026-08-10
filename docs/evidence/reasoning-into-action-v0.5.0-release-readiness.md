# ACE 0.5.0 Reasoning into Action release evidence

Status: **public, passed**

Date: 2026-08-10

## Outcome

ACE 0.5.0 closes the bounded Reasoning into Action milestone. Under the supported single-host
topology, an approved Decision can proceed through an effect-free adapter plan, exact human review,
durable admission, bounded execution, an honest terminal receipt, separate verification, linked
repair when the prior effect is known, and separate promotion. Task cancellation, declared
wall-clock limits, terminal resource reporting, durable attempt identity, and restart-safe linked
replay support that journey.

This record promotes T1 and B1 only for that documented topology. It does not claim remote workers,
distributed locks, multi-writer ordering, cross-process exactly-once effects, compensation,
arbitrary filesystem access, hostile-code isolation, or unrestricted autonomy.

## Published identities

| Artifact | Public identity | SHA-256 |
|---|---|---|
| Core wheel | `ace_core-0.5.0-py3-none-any.whl` | `7a932993c38c24dd0c6da170862c50c27d638601c8bedf57ff54b035864ea7b4` |
| Core source distribution | `ace_core-0.5.0.tar.gz` | `c5855bef74e5a7d487e032b2f5c609c1ffe91abcd6c5e034fe122b0268ba334e` |
| Reference adapter wheel | `ace_reference_workspace_action-0.1.0-py3-none-any.whl` | `628329e3a11d51b341da3974d094873dcfddd4eccb6f76bc8aa980b3948c5ec0` |
| Reference adapter source distribution | `ace_reference_workspace_action-0.1.0.tar.gz` | `9bab525150d7a53d84a1b296f5a23e2517877ce9cf4aa4a423afb1c1769d8ad5` |

- Release: [`v0.5.0`](https://github.com/augmented-cognition-engine/core/releases/tag/v0.5.0)
- Release target: `5744776fefc97c7ca610c89d9c3683c096d98a7d`
- Published: `2026-08-10T18:14:05Z`
- Registry package: [`ace-core==0.5.0`](https://pypi.org/project/ace-core/0.5.0/)
- Future adapter uploads were repaired in
  [PR #86](https://github.com/augmented-cognition-engine/core/pull/86), merged as
  `88ee1fed6889ba629d892098e4c366c7952ad521`; the two 0.5.0 assets above were recovered from the
  release build and attached with matching GitHub digests.

## Public-artifact reproduction

A fresh environment outside the Core and World repositories installed `ace-core==0.5.0` from
PyPI without cache and installed the reference adapter wheel from the public GitHub Release. Both
modules imported from `site-packages` with exact versions `0.5.0` and `0.1.0`; no Core checkout was
present on the import path.

The same environment then exercised the independent World Intelligence P2C2 consumer using only
World source paths:

- focused governed Reality Brief journey: **2 passed**;
- complete World domain suite: **83 passed**;
- Federal Register connector suite: **26 passed**.

World Intelligence subsequently published
[`v0.9.0`](https://github.com/augmented-cognition-engine/domain-world-intelligence/releases/tag/v0.9.0)
and [`ace-domain-world-intelligence==0.9.0`](https://pypi.org/project/ace-domain-world-intelligence/0.9.0/).
A second clean public-index environment installed that package and resolved `ace-core==0.5.0`; its
Federal Register monitor pack loaded from `site-packages`. The separately distributed live-source
adapter was absent, as designed.

## Accepted journey

```text
admitted public evidence
→ governed reasoning
→ exact cited Brief
→ authorized Decision
→ effect-free adapter plan
→ durable exact-material human review
→ admitted bounded effect
→ honest terminal receipt
→ separate human verification
→ separate promotion
→ exact replay with no second reasoning call or effect
```

The World pack is inert JSON and contains no action code or authority. The only demonstrated effect
is a human-reviewed create-only local workspace export through an explicitly constructed trusted
adapter. Exact replay does not invoke reasoning or the adapter a second time; an unresolved effect
after restart remains uncertain and cannot be silently retried.

## Reconciliation

The release gate in the
[0.5.0 work packet](../design/reasoning-into-action-v0.5.0-release-work-packet-v1.md) is complete.
The candidate records for T1A–T1C and B1A–B1D remain immutable point-in-time evidence; this public
record composes them with the release, registry, clean-install, and external-consumer receipts.
T1, B1, and the 0.5.0 Reasoning into Action milestone are therefore **passed** within the explicit
single-host boundary above.
