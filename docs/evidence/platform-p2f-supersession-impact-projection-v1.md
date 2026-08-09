# Platform P2F — Domain-neutral supersession-impact projection (v1)

Packet: **WI-CR-004**. Status: **implemented and verified as candidate/local evidence**.

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

A public, append-only answer to *"what depended on the record that was just
superseded?"* — and, just as importantly, *"what did not?"*.

| Layer | Addition |
|---|---|
| Core | **none** — Core learns nothing about supersession or impact |
| Intelligence logic | `ace/intelligence/supersession.py`: `project_supersession_impact`, `project_claim_impact`, `SupersessionImpact`, `ImpactedResource`, `SupersessionImpactError`, `IMPACT_RELATIONS`, `SUPERSEDING_RELATION`, `SUPERSESSION_IMPACT_POLICY` |
| Intelligence contracts | `contracts/supersession.py`: `SupersessionImpactPathV1Alpha1`, `SupersessionClaimImpactV1Alpha1`, `SupersessionImpactProjectionV1Alpha1` |
| Application | `ace/application/supersession_impact.py`: `SupersessionImpactService`, `supersession_impact_record` |

No Domain Pack declaration was needed. Impact is a property of admitted lineage,
not of domain vocabulary, so nothing was added to the Pack schema, compiler, or
runtime — the smallest possible surface.

## Direction, and why the superseder sits outside the closure

Lineage points *backwards*: a resource records which records it used. Impact
flows *forwards*. The traversal therefore builds a reverse index over the
closure. That is also why the superseding record may legitimately sit **outside**
the closure — a correction normally arrives after the work it affects — while its
target must sit inside it.

A supersession must be **asserted by the superseding record** through a
`supersedes` lineage edge naming the exact target. It is never inferred: a
`derived_from` edge is a derivation, not a correction, and is rejected.

## Impact is dependency, not falsehood

Being in scope means "your grounding included a record that has since been
superseded". ACE cannot judge whether a statement is now wrong and never
pretends to. The projection therefore carries:

* the exact path and `via_relation` that put each resource in scope,
* `depth` (1 = direct, >1 = transitive),
* the full `unaffected_resource_ids` set, so the boundary is **disclosed rather
  than inferred**,
* per-claim impact split into `fully_impacted` and partially impacted,
* `preserved_artifact_ids` — the historical artifacts this record explains and
  explicitly does not touch.

Every lineage relation propagates impact, because lineage exists precisely to
record "this resource used that one". The relation that carried each step is
recorded so a consumer can weigh `derived_from` differently from `contradicts`
without ACE guessing on their behalf.

## Append-only, never rewriting

The projection is a single additive immutable record appended under governed
authorization at the authorization time, on its own transaction key and record
kind (`supersession_impact_projection`). It never mutates a Brief, receipt,
Case, or earlier projection. The World packet proves the prior Brief keeps its
exact identity, replays byte-identically, and consumes no new reasoning after the
correction lands.

## Fail-closed conditions

`SupersessionImpactError` for: a target absent from the closure; a superseder
declaring no `supersedes` edge; a superseder superseding a *different* record;
an ambiguous supersession; an edge whose digest, `as_of`, or availability
disagrees with the admitted target; an edge crossing the target's resource kind;
a resource available after the cutoff (future leakage); a duplicate closure
identity; a self-supersession; an empty closure.

One guard is **defence in depth and unreachable through the contracts**, and the
test says so instead of pretending: a supersession that semantically precedes
its target cannot be constructed, because `ObservationV1Alpha1` already rejects
lineage with a later `as_of`.

## Identity preservation

Nothing existing changed. The projection is a new sibling contract on a new
record kind and a new transaction-key namespace. All 346 pre-existing
`tests/intelligence` tests pass unchanged, and the World packet reproduces the
accepted WI-CR-003 `brief:25d8232c9bfa27050bdcb160fb75f06c` and
`case:412426eee708d56f6bda931ccf9e5d8b` byte-for-byte by reusing that exact
activation.

## Honest limits

* **Impact is dependency, not invalidation.** A statement grounded on a corrected
  record may still be entirely correct.
* **Impact is only as strong as the admitted lineage.** A resource that used the
  superseded record without declaring an edge is invisible to this traversal,
  exactly as with derivation families.
* **Supersession must be asserted, never guessed.** If no record declares a
  `supersedes` edge, ACE reports no impact rather than inventing one.
* **Claim impact requires the synthesis receipt.** Without the receipt's support
  bindings the projection reports resource impact only.

## Verification

```
tests/intelligence            360 passed   (346 baseline + 14 new)
ruff check ace/ tests/        All checks passed
git diff --check              clean
installed wheel probe         imports and projects outside the source tree
```
