# Platform P2E — Domain-neutral derivation-family independence (v1)

Packet: **WI-CR-003**. Status: **implemented and verified as candidate/local evidence**.

> **Reproducibility status: candidate/local implementation evidence, not public artifact
> verification.** This record documents work against a local ACE Core 0.4.1 candidate; Core 0.4.1
> itself has no git tag, GitHub Release, or PyPI publication yet, so the versions and wheel digests
> below are local build artifacts, not public releases. The World Intelligence conformance journey
> this record relies on lives in `augmented-cognition-engine/domain-world-intelligence`, whose
> source is public but which carries no version tag, GitHub Release, or PyPI publication. Until both
> repositories are tagged, released, and published, an outside reader cannot independently re-derive
> the identities cited below. This record therefore establishes local implementation evidence only.
> It does not establish the public two-domain neutrality proof (GI2, open per the roadmap), and no
> roadmap outcome may be promoted to `passed` on its basis.

## What was added

A public, domain-neutral closure and predicate answering *which admitted
Observations trace back to the same origin*, plus an opt-in Pack constraint that
lets a status demand genuinely distinct origins.

| Layer | Addition |
|---|---|
| Core | **none** — Core learns nothing about sources, families, or independence |
| Intelligence logic | `ace/intelligence/derivation.py`: `derive_observation_families`, `independent_family_roots`, `DerivationFamilyClosure`, `DerivationFamilyError`, `COLLAPSING_RELATIONS`, `DERIVATION_FAMILY_POLICY` |
| Intelligence contracts | `epistemic.py`: `DerivationFamilyMembershipV1Alpha1`, `EpistemicStatusDeclarationV1Alpha2` (adds `min_distinct_derivation_families`), `EpistemicStatusSetV1Alpha2`, `EpistemicStatusModuleV1Alpha2`, `BriefClaimEpistemicStatusBindingV1Alpha2`, `BriefEpistemicStatusProjectionV1Alpha2` |
| Intelligence logic | `epistemic.py`: `derive_claim_epistemic_statuses_with_families` |
| Pack toolchain | module contract `ace.intelligence.epistemic-status/v1alpha2` in the compiler registry, compiled-module registry, and cross-module graph validator; `ResolvedEpistemicStatusPolicy.module_contract` and `.requires_derivation_families` |
| Synthesis contracts | `PreparedFamilyStatusCaseBriefAppend{,Intent,RecordRecipe}V1Alpha1` |
| Application | `ace/application/case_brief_family_status_synthesis.py`: `CaseBriefFamilyStatusSynthesisService` |

## How a family root is derived

A family is **derived, never declared**. ACE walks each Observation's admitted
lineage upward through Observation-kind edges whose relation collapses —
`derived_from` and `supersedes` — and takes the terminal ancestor. The family
identity is that root Observation's exact `resource_id`.

`supports`, `contradicts`, and `context` deliberately do **not** collapse: a
record that merely supports or contradicts another may be genuinely independent.

## The family assignment is disclosed as membership, not just roots

An independent audit found that disclosing only root IDs does not let a reader
check *which* records collapsed into which origin. The projection therefore
carries `closure_families: tuple[DerivationFamilyMembershipV1Alpha1, ...]` —
each family's exact root plus its exact sorted members — assembled directly from
`DerivationFamilyClosure.members_by_root`.

The contract enforces that a family contains its own root, that members are
unique and sorted, that no root appears twice, and that **families never overlap
on any member**. A claim disclosing family roots must also name at least one
member of a closure family. The independence decision is therefore re-derivable
from the durable record alone.

## What is never treated as independence

* **Publisher count.** Two Observations with different `source_ref` values that
  share a derivation root are one family.
* **Textual variation.** Payload content is never inspected; a reworded
  syndication is exactly as dependent as a verbatim one.
* **Acquisition path.** `acquisition_mode` and receipt references are not
  consulted.

## Fail-closed conditions

`DerivationFamilyError` (surfaced as a public synthesis error) for: a collapsing
edge naming a resource outside the exact closure; a collapsing edge naming a
non-Observation; an ambiguous root (parents resolving to more than one root); an
empty closure; a support that is not an admitted Observation; no supports at all.
A status requiring families rejects any claim whose supports are not all
Observations.

Two guards are **defence in depth and unreachable through the contracts**, and
the tests say so rather than pretending otherwise:

* **Cycles.** An Observation's identity derives from its own payload, and its
  lineage is part of that payload, so making `A` declare `B` re-keys `A` and `B`
  can never already name the new `A`. The reachable failure is a dangling parent.
* **Forged edge digests.** `LineageReferenceV1Alpha1` already requires that
  resource kind, ID, and digest identify one record, so a forged edge never
  reaches the closure walk.

## Identity preservation

`min_distinct_derivation_families` could not be added to
`EpistemicStatusDeclarationV1`: that would change its canonical payload, the
module digest, the pack digest, and therefore every artifact of the WI-CR-002
packet. It is a **sibling `v1alpha2` module contract** instead. A Pack on
`v1alpha1` is untouched, and a `v1alpha2` Pack that leaves
`min_distinct_derivation_families` at its default of `1` imposes nothing.

The two services share one code path via `StatusAppendProfile`; every
`v1alpha1` literal (transaction-key prefix and salt, record kind, payload
contract, neutral-recipe string, zero-intent prefix) is reproduced exactly, so
the refactor moved no identity. Proof: the World WI-CR-002 packet still
reproduces `brief:7adb24b596cac21d7aa4e5476bc8733c` and
`brief_epistemic_status_projection:fca9062883e92e2e632388c0069c310e`.

Unlike `v1alpha1` — where `proves_source_family_independence` is pinned to
`False` — `v1alpha2` *derives* it and rejects a Pack that states it incorrectly
in either direction.

## Honest limit

**Independence is exactly as strong as the admitted lineage.** If a Domain Pack
admits two Observations that share an origin without declaring any lineage
between them, ACE has no way to know and counts them as two families. This
predicate collapses *declared* derivation structure; it does not discover
undeclared common origin. **WI-CR-004 remains open** — no public projection
enumerates supersession impact.

## Verification

```
tests/intelligence            346 passed   (315 baseline + 31 new)
ruff check ace/ tests/        All checks passed
git diff --check              clean
installed wheel probe         ace_core-0.3.0 imports and resolves outside the source tree
```
