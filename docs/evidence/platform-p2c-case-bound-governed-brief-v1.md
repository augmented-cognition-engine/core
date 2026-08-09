# Platform P2C — Case-bound governed Brief synthesis

**Status:** candidate/local verification complete; `WI-CR-005` closed. The seven-status epistemic requirement remains falsified as `WI-CR-002`
**Date:** 2026-08-07

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

The immutable Case closure slice proved that one orientation product can span several
independently admitted developments. It left the question that actually matters open: can ACE
reason over that exact Case under governance, or does a consumer still have to concatenate
closures in private code and hand a prompt to a provider?

It can. This slice binds governed synthesis to one exact Case.

## Platform result

The path is **additive and domain-neutral**. Nothing about the existing single-derivation Brief
contract, identity, transaction key, record kind, or service changed.

New public surfaces:

- `CaseMemberAttentionBindingV1Alpha1` — one exact Case Signal member bound to the exact
  derivation and attention receipt that admitted it.
- `CaseBriefSynthesisRequestV1Alpha1` — binds one exact PREPARED Case reference plus one attention
  binding per Signal member. Refuses at contract level if the Case is not a PREPARED Case, if its
  `as_of` is not the Brief cutoff, or if it is not available by the context cutoff.
- `CaseBriefSynthesisReceiptV1Alpha1` — durable semantic correlation carrying the Case, its exact
  member identities, and every routed attention binding. Refuses unless the Case itself and every
  direct member appear in the selected frozen context.
- `PreparedCaseBriefAppendIntentV1Alpha1`, `PreparedCaseBriefAppendRecordRecipeV1Alpha1`, and
  `PreparedCaseBriefAppendV1Alpha1` — the Case-bound authorization-reference/time recipe and
  second-phase packet. The packet refuses unless the Brief carries its exact Case in lineage.
- `CaseBriefSynthesisService` — resolve, validate, route, freeze, reason, render, authorize,
  atomically persist, and deterministically replay.

The service:

1. binds one exact PREPARED Case and revalidates its public identity;
2. walks the complete transitive member closure breadth-first, rejecting nested Cases or Briefs,
   non-`derived_from` lineage, and any cone that does not terminate at persisted Observations;
3. requires **one exact routed attention receipt per Signal member and no others** — a suppressed
   route, a swapped receipt, a receipt whose Shift lineage does not match, or a missing binding all
   fail closed before reasoning;
4. derives **exactly one** compatible Brief template across every routed member, and the union
   persona scope, both resolved only from the bound compiled Pack IR;
5. freezes the whole closure — Case included — as opaque, non-authoritative Core context;
6. re-resolves the Case closure after reasoning and refuses to persist if it moved;
7. authorizes the append against a recipe that binds the Case identity, then commits the Brief and
   receipt in one atomic transaction under four governed state preconditions;
8. replays deterministically through `execute_historical`, invoking no provider.

The Brief contract is untouched: `BriefV1Alpha1.lineage` is a `SUPPORTS` edge over whatever closure
it is given, so a Case-bound Brief carries the Case in lineage without any new Brief field. The
canonical renderer `assemble_canonical_brief` is reused verbatim.

### Preserved identity

Adding an optional field to `BriefSynthesisReceiptV1Alpha1` would have changed the canonical
payload of every existing receipt and therefore every existing receipt identity. That is why this
is a sibling contract family rather than an extension. Verified: the pre-existing ACE Intelligence
suite is unchanged at `281 passed`, the single-derivation transaction key prefix
(`brief_synthesis:`) and record kind (`brief_synthesis_receipt`) are untouched, and the Case path
uses its own (`case_brief_synthesis:`, `case_brief_synthesis_receipt`).

## Fail-closed coverage

`tests/intelligence/test_case_brief_synthesis.py` (11 tests) covers, with no Brief or receipt
residue and no wasted provider call where the failure precedes reasoning:

| Failure | Result |
|---|---|
| Bound Case missing from durable scope | fails closed before reasoning |
| Case member missing from durable scope | fails closed before reasoning |
| Case member envelope changed under a stable identity | fails closed before reasoning |
| Members route to incompatible Brief templates | fails closed before reasoning |
| A Signal member has no bound attention receipt | fails closed before reasoning |
| Case context changes during governed reasoning | reasons once, persists nothing |
| Stale context cutoff excludes the Case | refused at contract level |
| Append authority denied by an advanced governed head | reasons once, persists nothing |
| Same synthesis key, different request material | replay conflict |

## Consumer result

World consumes only public ACE APIs. It admits the frozen `meridia_reservoir_release_72h`
derivations through ACE's durable PREPARED ledger — admitting each source record exactly once, by
reaching shared Observations through persisted lineage rather than duplicating them — freezes the
pinned Case, and synthesizes one governed Reality Brief:

- Case: `case:2ee200c03f2576307b0bc43e6e128f30` (identity unchanged from the closure slice);
- Brief: `brief:8fb3173069eca502652b1c9c004c92e6`;
- Brief digest: `sha256:8fb3173069eca502652b1c9c004c92e6f5ef16b6ffecfcd7fc2e97daed594d81`;
- receipt: `case_brief_synthesis_receipt:3e122634e7f7a76390e6574dfc4f3e8d`;
- lineage: 26 resources — 1 Case, 4 Signals, 5 Shifts, 10 Entity Snapshots, 6 Observations;
- template `reality_change_brief`; personas `general_reader`, `public_researcher`;
- 11 sections, 11 grounded claims, 6 citations, 2 atomic records, 4 governed preconditions;
- one provider invocation across synthesis and replay.

## Remaining falsified boundary

`WI-CR-002` is **not** closed and was deliberately not closed by adding World semantics to ACE.

The governed Case-bound Brief binds each claim to `cited` or `inference` grounding — two
expressible values against the seven epistemic statuses the World domain requires per statement
(`admitted_record`, `attributed_claim`, `corroborated`, `disputed`, `ace_inference`, `unknown`,
`scenario`). The synthesis receipt does bind each claim to a required section, but section
membership is structural placement that ACE never validates as an epistemic status: nothing in the
platform prevents a corroborated statement from being placed in a "where sources conflict" section.

A per-statement epistemic status that ACE can validate would be the next domain-neutral platform
slice. It is not implied by, and was not smuggled into, this one. `WI-CR-003` (source-family
independence) and `WI-CR-004` (supersession impact projection) also remain open and unchanged.

## Verification

- Complete ACE Intelligence suite: `292 passed` (was `281 passed`; the 11 new tests are additive).
- Complete World suite: `33 passed, 3 xfailed` (was `26 passed, 3 xfailed`).
- Focused Market Domain Pack compatibility control: `88 passed, 1 skipped`, plus `110 passed` for
  the broader hermetic `unit` selection. No Market source file was touched. A separate full
  application-suite run reached `482 passed, 1 skipped, 1 failed`; the failure,
  `test_story_recipe.py::test_three_new_instruments_are_registered`, is a pre-existing
  test-ordering collision in `core/engine/cognition/instrument_registry.py` (conflicting
  registration provenance under global registry pollution). It passes in isolation and is
  unrelated to this slice, which touches no instrument registration code.
- Ruff: clean across `ace/` and `tests/`, and across the World `scripts/` and `domain_packs/tests/`.
- Installed-artifact probe from outside every checkout: a fresh Python 3.12 environment with only
  the freshly built `ace-core==0.3.0` and `ace-ext-world-intelligence==0.4.0` wheels (full
  dependency resolution) imports every new public Case-bound surface, reproduces the exact Case,
  Brief, and receipt identities from packaged conformance resources, and confirms the three
  single-derivation Brief contract identifiers are unchanged.
  - ACE Core wheel: `sha256:51e877edb026d8a6935be59487185c5fd7806c5f1e07ecacd1f7270ef8de3d31`;
  - World Intelligence wheel: `sha256:d59f0b06ea097ee4bb636ab8af3479a763676ea5e69dff42d7c704510d458e5f`.
