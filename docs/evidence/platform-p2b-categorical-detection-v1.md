# Platform P2B — domain-neutral categorical transition detection

**Status:** candidate/local platform substrate slice verified  
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

P2B answers the first generic gap the World Intelligence P2A falsification surfaced: the alpha
detection contract exposed numeric deltas only, so a pack could not declare which exact
state-to-state transitions of a versioned categorical entity attribute are material. P2B adds one
bounded, domain-neutral categorical detector family without touching any v1alpha1 identity,
without adding a World, news, actor, institution, policy, publisher, or narrative branch, and
without creating a truth score.

## Platform result

- `ace.intelligence.detection/v1alpha2` compiles side by side with `v1alpha1`, following the
  synthesis `v1alpha1`/`v1alpha2` precedent. A `v1alpha2` module may declare numeric and
  categorical rules together; detector IDs are unique across both families and all modules.
- `CategoricalTransitionRuleV1` declares one watched single-valued string attribute, exact
  comparison-context attributes, and an explicit set of `from_value → to_value` transitions.
  Transition values are inert pack vocabulary; declaration order is not identity-bearing;
  identity transitions and duplicates fail closed at declaration time.
- The compiler validates categorical rules against the visible ontology exactly as it does numeric
  rules: unknown entity types, unknown or non-string or multi-valued watched attributes, unknown
  comparison context, and cross-module detector collisions fail closed with path diagnostics.
  Persona signal routing sees categorical signal types through the same dependency visibility.
- The pure interpreter (`ace.intelligence.detection.categorical_transition`) mirrors the numeric
  discipline: exact activation binding revalidation, snapshot-pair product/entity/type/mode/time
  discipline, ontology-typed attribute validation without coercion, and frozen comparison context.
  An unconfigured or unchanged transition is not material and yields no Shift, preserving DAG
  semantics (a Signal is never forced from a non-material change).
- Explicit PREPARED (`detect_categorical_shift`, `route_categorical_shift_as_signal`) and LIVE
  (`detect_live_categorical_shift`, `route_live_categorical_shift_as_signal`) entry points are
  mode-restricted in both directions; relabeling a PREPARED resource does not promote it.
- The governed LIVE bridge resolves the detector family from the exact activation-bound Pack IR
  (`resolve_detector_rule`) and dispatches to the matching interpreter. Receipt shape, append
  authorization, governed-state preconditions, atomic four-record persistence, and exact
  provider-free replay are unchanged and now proven for both families through one in-memory
  Core-conformant harness.

## Compatibility result

Adding the `v1alpha2` contract moves no existing identity:

- Market `pack_ir:19de6d59b28095f7bd7600364c3b4de7` recompiles exactly through the modified
  compiler, from source and from the rebuilt installed wheel.
- World `pack_ir:683de57a71669814e507d07d65a109db` recompiles exactly the same way.
- A pinned neutral `v1alpha1` fixture (`pack_ir:3282854421ceb6015e60fb2bf1b160c4`, detection module
  digest `sha256:9997b41d…`) is asserted byte-exact in-repo as a permanent regression guard.

## Verification

- Complete ACE Intelligence suite: `277 passed` (20 new categorical contract/compiler/runtime
  tests, 2 new LIVE bridge dispatch/replay tests)
- Full non-e2e ACE suite: passed except three pre-existing environmental failures in
  `tests/test_grounded_state_runtime_baseline.py`, which read `.git/HEAD` as a directory child and
  fail in any git worktree; unrelated to this packet
- Market conformance suite against the modified ACE source: `88 passed, 1 skipped`
- World P2A conformance suite against the modified ACE source: `7 passed`
- World P2B categorical consumer compile proof: passed for event suspension, record correction,
  claim dispute, and claim corroboration; combined World P2A/P2B result `20 passed, 3 xfailed`
- Ruff check over `ace` and `tests/intelligence`: passed; new files pass `ruff format --check`
- Rebuilt Core wheel `ace_core-0.3.0-py3-none-any.whl` SHA-256:
  `1094667a7dd0e7d7e4d53e0dbc2e437f82973b467ad96c3ff171c93f0bb734c6`; an isolated venv install
  reproduces both consumer pack identities and exposes the categorical public surface

## Epistemic-role and source-independence assessment

P2A also named two candidate gaps. Neither requires new machinery yet; both are expressible by
composition of existing public contracts, so P2B documents the composition and defers new
contracts until the World P2B scenario demonstrably fails against it.

**Epistemic claim roles beyond cited-versus-inference.** `GroundedClaimV1Alpha1` machine-enforces
the only two roles ACE asserts about its own Brief text: a cited claim must carry citations and no
inference basis; an inference claim must carry explicit basis references and an uncertainty
statement. Richer roles (observed, attributed claim, corroborated, disputed, unknown, scenario)
are properties of the domain record, not of ACE's prose, and are already first-class as
pack-declared entity attributes — which the P2B categorical detector now makes operational: a pack
can declare exact material transitions such as `attributed → corroborated` or
`corroborated → disputed` over a claim-status attribute and receive governed, lineage-exact
Shifts and Signals. Cross-resource stances remain expressible through `LineageRelation.SUPPORTS`
and `LineageRelation.CONTRADICTS`. Extending `ClaimGroundingKind` or versioning
`GroundedClaimV1Alpha1` would ripple into `BriefV1Alpha1` identity and is deferred as speculative
until a consumer proves the composition insufficient.

**Provenance-family / source-independence.** Citations already pin exact source, digest, and
acquisition receipts; a pack may declare provenance-family attributes on its source entities (the
World pack does) and assert independence or repetition as an explicit inference claim whose basis
references those snapshots. ACE deliberately has no corroboration counter to enforce
"repetition is not independent corroboration" against, and `CitationV1Alpha1` identity is derived
from its full material, so any citation-level field is an identity-bearing change. A generic
derivation-family contract is deferred until the World P2B scenario shows the composition failing
in practice. No truth score exists anywhere in this packet.

## Remaining boundary and the next World consumer contract

P2B does not claim scheduling, delivery, external action, monitoring, Cases, Subscriptions,
LIVE feedback, autonomous adjudication, or semantic/structural detection. The World consumer
should next exercise, against unchanged ACE:

1. `ace.intelligence.detection/v1alpha2` modules declaring categorical transition rules over its
   event/claim/policy status attributes (World vocabulary stays in the pack);
2. the same public LIVE path P1F proved — ingress, `LiveDerivationRequestV1Alpha1` with a
   categorical `detector_id`, routed attention, governed Brief — which requires no new request or
   receipt contract; and
3. epistemic statuses and provenance families as pack ontology plus grounded-claim composition,
   reporting any concrete case the composition cannot express or enforce as the falsification
   finding that would justify a minimal generic contract.

The World consumer completed item 1 on 2026-08-07 without changing its frozen scenario packet or
default pack identity. An isolated environment containing only newly built ACE Core and World
wheels reproduced the base identity `pack_ir:683de57a71669814e507d07d65a109db` and compiled the
categorical upgrade as `pack_ir:65cc0d2ac4ca0ab2646394a3500d3c27`. Items 2 and 3 remain
World-owned integration and falsification work.

Semantic and structural detector strategies remain explicitly open generic gaps.
