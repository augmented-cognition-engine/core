# A product decision that remembers what changed

A small online-store team has one four-week release. Its public session data makes a targeted
exit-recovery prompt look attractive: returning visitors represent 85.57% of sessions, yet their
observed purchase-session rate is 13.93% versus 24.91% for new visitors. The alternative is a
universal product-navigation improvement available to everyone.

ACE turns that ambiguous evidence into an inspectable recommendation, records the decision, accepts
a human privacy correction, survives a runtime restart, and changes the later experiment because
of that correction. The later answer must do more than find or quote memory: it must identify the
affected earlier option and materially change the allowed plan.

The demonstration answers a product builder's questions before exposing its mechanics:

1. **What decision is being made?** Choose targeted exit recovery or universal navigation for one
   constrained release.
2. **Why is it difficult?** Reach favors the targeted idea, but the evidence is observational and
   the option creates privacy, consent, accessibility, and trust risk.
3. **What does ACE retain?** The frozen evidence identity, provisional decision, human correction,
   task receipts, reasoning shape, and provider provenance.
4. **How is this different from disposable chat?** A later fresh process is not given the
   correction. It must load the exact identifier from durable intelligence after ACE restarts.
5. **What evidence supports the result?** A checksum-backed aggregate of UCI dataset 468, with
   source IDs attached to empirical claims and CC BY 4.0 provenance.
6. **What did the human correct?** The release may not use visitor type, persistent identifiers, or
   session-level behavioral targeting.
7. **What persists?** The decision and correction remain inspectable after the API and client stop.
8. **How does it affect later reasoning?** The later result must reject or modify targeted recovery
   and sequence a privacy-compatible experiment.
9. **What remains uncertain?** The data does not establish causality and contains no qualitative
   intent, consent, implementation-cost, cart-stage, or accessibility evidence.

The acceptance test does not require one model-written answer. It checks the decision structure,
source citations, inspectable classification and composition, route provenance, restart retrieval,
and a traceable decision delta.

## Frozen scenario and public source

The complete input is
[`evaluations/fixtures/r4_product_builder_golden_path_v1.json`](../evaluations/fixtures/r4_product_builder_golden_path_v1.json).
It freezes the question, options, constraints, decision criteria, correction, later question,
acceptance invariants, source attribution, retrieval date, checksums, transform, and limitations.

The only external source is:

- C. Sakar and Yomi Kastro, *Online Shoppers Purchasing Intention Dataset*, UCI Machine
  Learning Repository, DOI [`10.24432/C5F88Q`](https://doi.org/10.24432/C5F88Q), retrieved
  2026-07-21. UCI publishes the dataset under
  [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/).

The repository contains the small derived evidence snapshot, not a second copy of the 1 MB source
archive. To independently reproduce the aggregate, download the recorded UCI URL, verify the
archive SHA-256 in the fixture, extract `online_shoppers_intention.csv`, and run:

```bash
uv run python scripts/verify_product_builder_golden_path.py source \
  --csv /path/to/online_shoppers_intention.csv
```

The verifier rejects a missing, malformed, checksum-mismatched, or numerically changed source
before any recommendation is requested. It never fills a missing fact with model output.

## Reproduce the live journey

Use a fresh clone, an empty ACE configuration directory, a fresh Compose project/volume, and one
explicitly authorized provider route. Do not copy a maintainer `.env`, `.venv`, ACE token, or
SurrealDB volume. A provider CLI's own explicitly selected sign-in is an operational prerequisite,
not ACE state.

Prerequisites are macOS or Linux, Python 3.12, `uv`, Docker Engine with Compose v2, and one provider
from [`docs/providers.md`](providers.md). The canonical evidence uses the Codex CLI / ChatGPT
subscription route. Provider latency and capacity vary; allow 15–30 minutes for setup, two live
reasoning phases, restart checks, and evidence inspection. The verifier records the actual time to
first recommendation and each task's route latency.

From the clean clone:

```bash
export ACE_CONFIG_DIR="$PWD/.r4-clean/config"
export COMPOSE_PROJECT_NAME=ace_r4_clean_replay
export ACE_SURREAL_HOST_PORT=18041
uv sync
uv run ace setup --provider codex --skip-first-task --non-interactive
uv run ace doctor --live-provider --provider-timeout 60 --json-output \
  > evaluations/results/r4_product_builder_provider_check_v1.json
uv run python scripts/verify_product_builder_golden_path.py initial \
  --provider-evidence evaluations/results/r4_product_builder_provider_check_v1.json
```

The initial phase performs a clean health check, explicitly loads prior intelligence, captures the
public evidence, runs the consequential decision, validates its reasoning receipt, captures a
provisional decision, captures the human correction, and proves that the correction is immediately
inspectable. It writes a state file containing only public scenario material and sanitized public
receipts; it never reads or records provider credentials.

Restart the supported local runtime while preserving its named data volume:

```bash
uv run ace service stop
uv run ace service start
uv run ace doctor --json-output
```

Now open a fresh terminal in the same clean clone. Re-export only the disposable ACE configuration
location and run the later phase as a new process:

```bash
export ACE_CONFIG_DIR="$PWD/.r4-clean/config"
uv run python scripts/verify_product_builder_golden_path.py later --runtime-restarted
```

`ace setup` persists the explicit Compose project and SurrealDB host port in the disposable
`.env`, so service stop/start commands continue using the same isolated volume without requiring
those two exports in the fresh terminal. Choose a different free port or project name if either is
already in use.

The later request contains the same public evidence but does **not** contain the correction text or
identifier. The phase fails unless `ace_load` retrieves the earlier correction and the new task:

- emits the exact retained constraint identifier;
- cites at least two frozen source IDs;
- records classification, composition/stages, provider, model, and latency provenance;
- describes a material plan change;
- connects that change to targeted recovery or behavioral visitor classification; and
- produces an output distinct from the initial recommendation.

Inspect the durable artifacts in `evaluations/results/`, the task IDs with `ace_status`, and the
decision/correction with `ace_load("online conversion privacy")` from an MCP client. The supported
MCP server still exposes exactly eleven tools; this script uses its existing HTTP client and adds no
twelfth tool or alternate product surface.

When finished:

```bash
uv run ace service stop
```

## Bounded second-provider check

If a second supported route is already authorized, switch the disposable clone to that route,
restart ACE, run `ace doctor --live-provider`, and execute the bounded structural check:

```bash
uv run ace setup --provider claude-cli --no-start --skip-first-task --non-interactive
uv run ace service start
uv run ace doctor --live-provider --provider-timeout 60 --json-output \
  > evaluations/results/r4_product_builder_provider_check_claude_v1.json
uv run python scripts/verify_product_builder_golden_path.py portable \
  --route-label claude-cli
```

This confirms only that the same public question can produce the required structure and provenance
through another supported route. Different prose or recommendations are allowed. It does not
establish model superiority, equal quality, matched token budgets, or cross-provider equivalence.

## Honest failure and recovery

Run the credential-free bounded failure-contract exercise with:

```bash
uv run python scripts/verify_product_builder_golden_path.py failure-fixtures
```

| Failure | Honest behavior | Actionable next step |
|---|---|---|
| Provider unavailable or timed out | Preserve pending/running receipt or report failed/degraded; never switch providers silently | Retrieve with `ace_status`, then run `ace doctor` |
| Missing authentication | Stop on HTTP 401/403 | Run `ace login --api-key '<API_KEY from .env>'` |
| Database unavailable | Health/doctor fails; no persistence claim | Run `ace service start`, inspect `ace service logs --lines 80`, rerun doctor |
| Stale saved login | Protected load is rejected; stale state is not evidence | Run `ace login` again |
| Malformed or missing source | Local validation stops before model work | Restore the tracked fixture or checksum-matched UCI source |
| Restart before task completion | Durable receipt becomes explicitly `degraded` with `runtime_restarted` | Retrieve and inspect that receipt; intentionally resubmit only after review |
| Prior correction unavailable | Later phase exits nonzero | Verify the preserved volume and rerun `ace_load`; do not claim material reuse |

The verifier emits a JSON failure with the failing stage and next action. It never invents evidence,
silently substitutes a provider, treats polling timeout as task failure, or claims persistence when
the correction cannot be loaded.

## Scope and limitations

- The source data is historical, observational, anonymized, and limited to one retailer.
- The scenario is a reproducibility demonstration, not product advice for a real retailer.
- Provider token, cost, applied-effort, retry, and fallback fields are reported only when the
  configured route exposes them. Unknown remains unknown; applied effort is not inferred.
- Cost for subscription-backed routes is not attributable per task unless the provider supplies it.
- The clean replay uses an AI-operated stranger protocol because no independent human tester is
  available. It is not external usability validation.
- Atrium, the broad engine MCP host, private data, QueryLabs extensions, G1, and IA-R1 are outside
  this journey.
