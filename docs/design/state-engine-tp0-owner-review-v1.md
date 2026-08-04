# ACE State Engine TP0 owner review v1

## Disposition

On 2026-08-03, ACE owner `maintainer:eamirian` approved all 18 current subjective
expectations after the semantic audit and its six corrections. The review applies only to the
expectation and judgment hashes recorded below. Any material expectation edit invalidates the
corresponding review binding and requires renewed adjudication.

- Review authority: ACE owner
- Reviewer: `maintainer:eamirian`
- Reviewed at: `2026-08-03T16:20:15Z`
- Pre-freeze candidate corpus hash:
  `9ce304daa643e0612c1ed4fe7ecba8e495ebf8b6541662c6cb3510565ae4cb91`
- Frozen corpus hash: `4b029bff64564abc226d431b373a3d75cbf971c66aa6bb53e2cf29c7198c4b09`
- Disposition: all 112 current subjective judgments accepted

## Reviewed cases

| Case | Reviewed expectation hash | Judgments | Decision |
|---|---|---:|---|
| `alias_registry_version_change` | `a0247b4ebfe39251255e23077b53888ef5cf1ae46c96de5f43a5aaf3e7fe435a` | 7 | Accepted |
| `ambiguous_heron_mention` | `bb652e8b370bbb382cf4a4787e511cef4e9a8b2913a219a20db8e5659e1ec3f5` | 6 | Accepted |
| `attributed_source_dependency` | `40d8a566bbd9d27d43537c5bd6182cbcaf1d72a4e37acba1e164da9f84fb1cdf` | 6 | Accepted |
| `causal_claim_requires_human_gate` | `b432daa2df6dafde6546bcb7faf71ac317d376249a6eecc6d43699a6f2babc39` | 7 | Accepted |
| `contested_delivery_belief` | `5ca1df5da56e8b694e42ceabefdd7743b63b73f872e867cbb50df14b6b52be42` | 6 | Accepted |
| `entity_alias_same_identity` | `9c008aa162b3154b41653c8a9b7e74ff9808a8883b1fb38c60660029cd49d58b` | 6 | Accepted |
| `entity_legal_name_change` | `4bb82d3b4c584883e2d8482ac47d1eea57da9672b0648bd99bc8d80738b98bc5` | 6 | Accepted |
| `entity_name_collision` | `c2e7fa14aa8978775edb6db5e69a1676901af2262b9d7b590a99dc213ad154d7` | 6 | Accepted |
| `independent_factory_corroboration` | `3bab93d6de22228e51941aba4bb0fca602d90b96b4527e854ce01e18225ecf4f` | 6 | Accepted |
| `lexically_similar_unrelated_control` | `9af3021f3a935f237133eddec494039706e2292b119d641159b5308ccaac06e8` | 6 | Accepted |
| `mechanism_supported_transition` | `26e9065f9f31fa6421bb0e825a078177667b9240078fef711801905791ac6885` | 6 | Accepted |
| `mechanism_with_contrary_evidence` | `954af83063828361bebaab63b7bfb919bba22bb98db8bac420131e327139f960` | 6 | Accepted |
| `overlapping_capacity_reports` | `6e341cac59e195022b1e34f1defcdb1ccfa2a7035613ef40288912fd94bb61e6` | 7 | Accepted |
| `price_reaction_not_causal_fact` | `b9c728c87beba438dc3b90efc0ccaafd40488ae8370927fb3202a3b662acd45a` | 6 | Accepted |
| `restatement_not_corroboration` | `894b426d2b3defdc209abb53adc4bac6a76f7d386dac34dea93bad8157d79290` | 6 | Accepted |
| `same_interval_operating_conflict` | `ee5dac8c93c01178f432a5bdb2572d2c75c05cfef237b9b38cd9472c57d083dc` | 6 | Accepted |
| `sequence_without_causal_promotion` | `a10c2eee60dd99f0d88066c4d5ddb37cb322f768c854e244f5bd2a740a593659` | 6 | Accepted |
| `world_state_changes_over_time` | `e4bbdaab52b1eff8979abc118dea059b7a8bcb7b39572483eabf1f90c4899190` | 7 | Accepted |

## Scope boundary

This adjudication freezes the reference corpus and its expected semantics. It does not claim that
the current ACE runtime passes an implementation baseline against the corpus, nor does it add a
database schema, ingestion API, resolver, dynamics executor, or rollout engine.
