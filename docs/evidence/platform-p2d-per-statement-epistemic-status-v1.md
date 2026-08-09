# Platform P2D — Domain-neutral per-statement epistemic status (v1)

Packet: **WI-CR-002**. Status: **implemented and verified as candidate/local evidence**.

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

A generic capability for binding one **Domain-Pack-declared** epistemic status to
every statement of a governed Brief, validated against the strongest
domain-neutral support facts ACE holds, and persisted as a durable sibling
projection inside the Brief's atomic transaction.

| Layer | Addition |
|---|---|
| Core | **none** — Core learns no status vocabulary |
| Intelligence contracts | `ace/intelligence/contracts/epistemic.py`: `EpistemicStatusDeclarationV1`, `EpistemicStatusSetV1`, `EpistemicStatusModuleV1`, `BriefDraftClaimStatusBindingV1Alpha1`, `BriefClaimEpistemicStatusBindingV1Alpha1`, `BriefEpistemicStatusProjectionV1Alpha1` |
| Intelligence logic | `ace/intelligence/epistemic.py`: `derive_claim_epistemic_statuses`, `EpistemicStatusValidationError` |
| Pack toolchain | new module contract `ace.intelligence.epistemic-status/v1alpha1` in the compiler registry, the compiled-module model registry, and the cross-module graph validator; `resolve_epistemic_status_policy` in the prepared runtime |
| Synthesis contracts | `BriefSynthesisDraftV1Alpha2` plus the three-record `PreparedStatusCaseBriefAppend*` intent/recipe/packet |
| Application | `ace/application/case_brief_status_synthesis.py`: `CaseBriefStatusSynthesisService` |

## Identity preservation

No existing identity-bearing contract gained a field. Status could not be added
to `GroundedClaimV1Alpha1`, `BriefV1Alpha1`, or `CaseBriefSynthesisReceiptV1Alpha1`
because each derives its identity from its canonical payload — a new field would
silently re-key every historical artifact. Status therefore lives only in the
sibling `brief-epistemic-status-projection/v1alpha1` record, which names the
exact Brief and receipt it explains.

`BriefSynthesisDraftV1Alpha1` and `BriefDraftClaimV1Alpha1` are reused verbatim
by `v1alpha2`, so their canonical payloads are unchanged.

Evidence:

- `tests/intelligence/test_case_brief_epistemic_status.py::test_pre_existing_identity_bearing_contracts_did_not_gain_fields`
  pins the exact field tuples and one hand-built claim identity
  (`brief_draft_claim:272104501f520344275098f6794aea34`).
- All 292 pre-existing `tests/intelligence` tests pass unchanged.
- World reproduces `case:2ee200c03f2576307b0bc43e6e128f30` and
  `brief:8fb3173069eca502652b1c9c004c92e6` byte-identically.

## What is enforced, and what is not

For each claim ACE validates the declared status against:

- the claim's `ClaimGroundingKind` (`allowed_grounding_kinds`),
- its exact selected support record identities,
- support cardinality (`min_support_count` / `max_support_count`),
- support resource kinds (`allowed_support_kinds` / `required_support_kinds`),
- distinct support-kind count (`min_distinct_support_kinds`),
- presence of an explicit uncertainty statement (`requires_uncertainty`).

**Not enforced: independence of source families.** ACE has no public
derivation-family or source-independence predicate. A `corroborated`-style label
is therefore enforceable only to the strength of the cardinality and
resource-kind rules above. `EpistemicStatusDeclarationV1.proves_source_family_independence`
is pinned to `Literal[False]` so no Domain Pack can declare a stronger guarantee
than the runtime can deliver. **WI-CR-003 remains open.**

## Fail-closed coverage

`tests/intelligence/test_case_brief_epistemic_status.py` (23 tests) rejects, with
no durable residue in every case: an interruption after staging two of the three
atomic records, undeclared status, invalid status/grounding
combination, insufficient support, excess support for a bounded status,
wrong-kind support, missing status, duplicate claim binding, a legacy draft on
the status path, a Pack with no governing status set, and a tampered durable
projection on replay. It also asserts a module must depend on a synthesis
module, and that a template cannot be governed by two status sets.

## Verification

```
tests/intelligence            315 passed   (292 baseline + 23 new)
ruff check ace/ tests/        All checks passed
git diff --check              clean
```
