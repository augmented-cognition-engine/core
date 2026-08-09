# P1E governed PREPARED Decision, Outcome, and feedback

**Status:** local, candidate evidence verified on 2026-08-06 for one bounded PREPARED Market
Intelligence conformance loop. This is a source-checkout/local-wheel reproduction, not verification
of a published artifact — no ace-core 0.4.1 git tag, GitHub Release, or PyPI package exists yet. No
LIVE learning, delivery, or external action is claimed.

P1E closes the prepared architecture loop over the exact historical P1D1 Brief:

```text
exact PREPARED Brief
  → named Decision: accept + explicit no_action
  → later qualitative Outcome: useful
  → Intelligence feedback proposal: 0.50 + 0.05 = 0.55
  → separate Core approval and append-only PREPARED policy-state commit
  → exact replay and fresh-service reload
```

## Ownership boundary proved

- **Core** owns domain-neutral Decision and Outcome contracts, exact subject and principal scope,
  authenticated time windows, action/no-action separation, authorization receipts, immutable
  record admission, governed-state approval, compare-and-swap, replay, and history.
- **Intelligence** owns the closed `decision-outcomes/v1alpha1` pack schema, exact activation-bound
  policy resolution, eligibility checks, and the bounded feedback proposal. A proposal is not
  effective state.
- **The Market pack** owns only inert declarations: eligible persona, route, decision disposition,
  explicit no-action, outcome measure, bounds, and categorical adjustments. It contains no
  callable, command, provider, connector, persistence logic, or authority.

The resulting Core API remains free of Market nouns. Core authorization receipts use opaque
operation and subject identity; Intelligence retains the mapping to Decision, Outcome, and
feedback concepts. Accepting the Brief does not authorize an action. Recording an Outcome does
not mutate policy. Only a later exact approval can commit a new state revision.

## Exact identities

| Material | Identity | Digest or receipt hash |
|---|---|---|
| Market Pack 0.5.0 | `pack_ir:0d967de698cd10fc06b91d2a4559ec9f` | `sha256:0d967de698cd10fc06b91d2a4559ec9fea80bb421d6a8e79c9766635ccbd8b05` |
| decision-outcomes module | `market_decision_outcomes` | `sha256:02653650c8cface55656a16bdec94788ffab5d8cbf33f661273256bcf55e7918` |
| activation revision 4 | `activation_revision:a1b0d2c58860bbeb12c655c0e29fba11` | `a1b0d2c58860bbeb12c655c0e29fba112e9d6e25365692e14aa628abed80e662` |
| source Brief | `brief:c65102850e3d543713a0ff71d02dcc78` | `sha256:c65102850e3d543713a0ff71d02dcc7803d0255bcc116abb6caafdbab307dff5` |
| Decision | `decision:9d82a0f0dfd71c21b33d297c937f74c4` | `sha256:9d82a0f0dfd71c21b33d297c937f74c44ef7285c73cdeb915d0f438996dcdd5b` |
| Outcome | `outcome:3b4fb39da38ef739ccaede9e7d1fcb18` | `sha256:3b4fb39da38ef739ccaede9e7d1fcb18818944ffe707b11a40d67c96e38de5fc` |
| feedback proposal | `feedback_proposal:82002cc4e6b73068f99e8c80161bde73` | `sha256:82002cc4e6b73068f99e8c80161bde7348b59bf32a7fd0ad4a1a57bdbd99aba1` |
| feedback policy state | `feedback_policy:95d871b225970e45a0954f18e21f3c3c` | revision `feedback_policy_revision:a1e605128ae66c99e34e5bcdc3d4b427` |
| feedback commit | `governed_state_commit:ccd83f8a585d8d6072242597630b9e95` | `ccd83f8a585d8d6072242597630b9e95c3d3913203beb9d59b3b19e95745f16c` |

The exact result preserves the five 0.4.0 modules byte-for-byte. It adds only the inert
`decision_outcomes.json` module and its root manifest declaration. The committed prepared value is
`0.55`; a fresh service reloads the same revision and value with `live_effect=false`.

## Fail-closed matrix

Nine pinned negative cases reject:

1. an unknown feedback policy;
2. a persona outside pack eligibility;
3. denied Core Decision authorization;
4. the wrong outcome measure;
5. an Outcome predating Decision availability;
6. an unmapped outcome value;
7. a wrong immutable Outcome digest;
8. an approval for the wrong feedback-proposal subject; and
9. a stale proposal after the policy head advances.

Every case records zero downstream residue at its failing boundary across Decision, Outcome,
feedback proposal, action-authorization, and feedback-state records.

## Verification

- New Core contract/compiler tests: **5 passed**.
- Complete Core Intelligence suite: **254 passed**.
- Market P1E pack and end-to-end conformance tests: **6 passed**.
- Full positive and nine-case negative acceptance script: **passed**.
- Installed-wheel probe from outside both checkouts: **passed**; Core imports and Market 0.5.0
  resources resolved from the installed artifacts.
- Core wheel: `ace_core-0.3.0-py3-none-any.whl`, SHA-256
  `44287fe0f7cff79186c732d00d6b9eba5f44c508522aa2911f1a63a88a7fa68f`.
- Market wheel: `ace_ext_b2b_marketing-0.1.0-py3-none-any.whl`, SHA-256
  `041ca87ad62060d758615b2c7f00019fcd2bca90657096b7fe04ca8efce4eba4`.

The reproducible Market packet lives under
`domain_packs/market_intelligence/releases/v0_5_0/conformance/` in the Market repository. Its
manifest pins the exact Core wheel, three Core source surfaces, acceptance script, input, expected
projection, and nine negative cases.

## Explicit limitations and next gate

All fixture-derived records and policy state are PREPARED. They do not enter LIVE counts,
freshness, scoring, delivery, operational outcomes, or learning. No reasoning provider is called,
no adapter runs, no external action executes, and no delivery authority exists. This packet also
does not prove beneficial impact, numeric calibration, autonomous optimization, or production
database restart.

P1E is sufficient to start the next paired platform/domain packet: Core and Intelligence must
create the governed LIVE Shift, Signal, routing, and Brief bridge while Market consumes that exact
public path. The later P1F roadmap reconciliation selected World Intelligence as the second-domain
falsification immediately after that bridge and moved Corporate Strategy Intelligence to the
third-domain proof; customer and CX intelligence remain Market facets for now. No equivalent LIVE
feedback claim can be attempted before the LIVE derivation path exists.
