# State Engine TP8 K1–K3 readiness decision

This is the human-readable companion to
[`state_engine_tp8_readiness_v1.json`](state_engine_tp8_readiness_v1.json). The complete measurements
and limits are in the [TP8 evidence record](../../docs/evidence/state-engine-tp8-scale-stability-v1.md).

## K1 — ready

ACE reproduced 200,000 claims and 236,000 semantic records with exact receipts and lineage after
database, adapter, and client interruption. The 20,000-claim sustained sample ran at 990.410
claims/second against a frozen 68,000/day target. Candidate p95 was 14.189 ms, combined evidence-query
and pack p95 was 16.510 ms, and no cross-product result was observed. Provenance, event and validity
time, unknowns, disagreement, supersession, deterministic as-of projection, backup/restore, and
restart continuity remain explicit.

`ready` means the measured single-node, product-scoped capability on the named reference hardware.
It does not mean distributed or multi-writer readiness, arbitrary interruption of historical
pre-v142 migrations, private-corpus proof, or production deployment approval.

## K2 — candidate

The frozen TP5 matrix still passes mechanisms, preconditions, supporting/contrary evidence, causal
limits, review/challenge, revision, and later-outcome calibration. Transition resolution persisted
in 10.815 ms while the 200,000-claim store was active, and the stable/extension-owned boundary is
explicit.

K2 remains `candidate` because only one deterministic transition scenario was executed alongside the
large corpus. Before R7, repeat the frozen domain matrix at scale and publish per-domain errors,
abstentions, challenges, revisions, and calibration. This is not evidence of real-world causal
accuracy or calibrated forecasting.

## K3 — candidate

The actual durable task path now resolves bounded evidence, freezes state, executes action and
no-action branches, injects consequences into reasoning, persists I3 use, exposes assumptions and
falsifiable outcomes, reconciles later observations without rewriting the forecast, promotes only
authorized durable material, survives restart, and applies correction/supersession. Rollout service
latency was 13.131 ms and no simulation was returned as an observation.

K3 remains `candidate` because the actual task proof is one provider-free deterministic journey,
not a repeated large-corpus fresh API/worker/client p95 trial. Before R7, run that repeated journey
and publish task reasoning, promotion, restart, and later-retrieval latency plus a frozen later-outcome
reconciliation set. Beneficial impact and general consequence accuracy remain unsupported.
