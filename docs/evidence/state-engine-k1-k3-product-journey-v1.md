# State Engine K1-K3 product-journey evidence v1

Status: **passed on 2026-08-04 — K1 passed, K2 passed, K3 passed**

This record closes the first post-roadmap product-build packet. It is based on the frozen Fjord
Operations fixture and the machine-verifiable receipt in
`evaluations/results/state_engine_product_journey_v1.json`; the paired Markdown rendering is
`evaluations/results/state_engine_product_journey_v1.md`.

## Frozen identities

| Material | Identity |
|---|---|
| Acceptance | `state-engine-k1-k3-product-journey-v1` |
| Config SHA-256 | `7ac1470fd05727b31b794783c40e7afe9aafaa1b628614b8f4f21d72df151a4c` |
| Corpus SHA-256 | `85907acc8ad5b9a73d2d7551ced98d1bb26d4b9ea51a189d262675cb5ff9ea28` |
| Acceptance hash | `d81257a0e379c20248cb546b61b57d18c5ed440950d003733140310f83713e85` |
| Extension | `ace-ext-fjord-operations` 0.1.0 / `fjord-operations` entry point |
| Product | `product:fjord-operations` |
| Provider route | `deterministic-provider-free-acceptance` / `provider-free-v1` |

The scenario and corpus were frozen before the successful run against the supported ACE 0.2.0 State
Engine schema head, v168. Schema-zero reached v168, and the supported v160 predecessor upgrade
retained its sentinel and reached v168. Unrelated, pre-existing governed-cognition work beyond v168
was preserved but intentionally not absorbed into this frozen packet.

## What passed

- A wheel built from the independent example package installed into a clean extension environment;
  ordinary `ace.extensions` discovery loaded one adapter and two extension actions.
- Five fictional CC0 source records produced 26 semantic proposals and 22 stable semantic records
  after exact duplicate reconciliation. Exact replay returned the same receipt; counts reconciled;
  one source-version lineage edge was retained; foreign-product reads were empty.
- Event/valid, publication, ingestion, extraction, and ACE creation meanings remained separate. The
  instruction-like source sentence retained data-only authority.
- The as-of projection contained exactly the required meaning set: `supported`, `contested`,
  `provisional`, `superseded`, and `unknown`.
- The reviewed transition retained its mechanism, source precondition, one-hour to one-day horizon,
  probability interval, evidence references, complete challenge, provisional deterministic-policy
  review, and `mechanistic_hypothesis_not_causal_fact` limit. Deterministic policy could not accept a
  causal-strength proposal that required human authority.
- Production extension invocations exercised action/no-action and named-alternative/no-action bounded
  comparisons. Core persisted the task, structured decision, rollout, reasoning-use receipt,
  promotion proposal, authenticated review, and accepted promotion receipt.
- Incomplete outcome material remained `unresolved`; matched later material reconciled as `matched`.
  Both receipts referenced but did not mutate the original simulated rollout.
- Real SurrealDB, API, and worker processes restarted twice. Fresh thin-client processes materially
  used the promoted I3 artifact, then an explicit correction superseded the initial receipt and was
  the sole authoritative later retrieval. The receipt explicitly does not claim beneficial impact.
- A held production task was interrupted by a real topology restart. The predecessor degraded and the
  supported resume path created a completed immutable successor attempt.
- Unavailable evidence, product isolation, stale transition, unsupported causal authority, restart
  interruption, and incomplete reconciliation all failed or degraded in their declared manner.
- The public MCP list remained exactly the eleven thin tools. No broad State Engine MCP or product
  twelfth tool was used.

## Resource and provider observations

| Observation | Measured value |
|---|---:|
| Schema-zero | 33.902 s |
| v160→v168 upgrade | 6.277 s |
| First full restart | 2.824 s |
| Interruption restart | 2.004 s |
| Task latency p95 | 95.303 ms |
| Provider calls | 0 |
| Input/output tokens | 0 / 0 |
| Retries | 0 |
| Estimated provider cost | $0.00 |

## Verification commands

```bash
python scripts/run_state_engine_product_journey.py freeze-check
python scripts/run_state_engine_product_journey.py run \
  --work-dir /tmp/ace_fjord_product_journey_trial21 \
  --output /tmp/ace_fjord_product_journey_trial21-result.json \
  --markdown-output /tmp/ace_fjord_product_journey_trial21-result.md
pytest tests/test_state_engine_product_journey.py tests/test_consequence_rollouts.py -q --tb=short
```

The acceptance run exited zero. The focused receipt and rollout-contract lane passed 17 tests.

## Corrective Core change found by the journey

The first real replay exposed one narrowly scoped Core defect: SurrealDB omits nested `NONE` values,
so sorting a raw state-snapshot dictionary before restoring contract defaults could change canonical
order and invalidate a previously minted simulated-state ID. `PredictedStateStepV1` now validates
nested `StateSnapshotV1` values before sorting them. The new regression test removes an unknown
state's nested `value=None` field and proves the exact simulated-state identity survives reload.

## Honest limits

This is single-node, synchronous-adapter, fictional-data, provider-free evidence. It does not support
a hosted-model quality or latency claim, real-world causal correctness, distributed ordering,
multi-writer or multi-region behavior, autonomous learning, a general world model, or beneficial
product impact.
