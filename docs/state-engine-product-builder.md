# Build a State Engine product with an extension

Status: **supported bounded ACE 0.2.x product-builder journey**

This guide builds the fictional Fjord Operations product without forking ACE Core. The separately
installable extension owns the product vocabulary, public-safe corpus mapping, evidence-query and
promotion-review actions, and the one deterministic acceptance hook. Core owns authenticated product
scope, stable identity, validation, append-only persistence, review authority, task lifecycle,
restarts, reconciliation, and receipts.

The example is intentionally provider-free. It proves the supported integration and durability path;
it does not claim hosted-model quality, real-world causal accuracy, or beneficial product impact.

## 1. Inspect and install the example extension

The extension lives at `examples/ace_ext_fjord_operations`. Its package advertises the
`fjord-operations` entry point in the public `ace.extensions` group and depends on the compatible
ACE Core 0.2.x line.

```bash
python -m pip install --no-deps examples/ace_ext_fjord_operations
```

At startup, the ordinary ACE extension loader discovers:

- adapter `fjord-operations:public-fixture` on
  `Registry.register_grounded_state_adapter`; and
- actions `fjord-operations:evidence-query` and
  `fjord-operations:promotion-review` on `Registry.register_task_action`.

These are extension capabilities, not additional MCP tools. The supported public MCP surface remains
the same eleven thin tools.

For source-checkout development only, the equivalent explicit loader setting is:

```bash
export PYTHONPATH="$PWD/examples/ace_ext_fjord_operations:$PWD"
export ACE_EXTENSIONS="fjord_operations_extension.extension:FjordOperationsExtension"
```

Do not combine the development setting with an installed entry point in the same process.

## 2. Verify the frozen scenario

The acceptance fixture was frozen before execution. It binds the product and foreign-control scopes,
extension identity, corpus digest, as-of time, horizon, supported v168 schema head, provider budget,
required epistemic meanings, failure cases, and exact eleven-tool boundary.

```bash
python scripts/run_state_engine_product_journey.py freeze-check
```

The corpus is fictional CC0 data. Its five source records include separate event/valid,
publication, ingestion, and extraction times. ACE creation time is added only when Core persists the
records. One source sentence resembles an instruction; the journey verifies that it remains quoted
data with no prompt or tool authority.

## 3. Run the supported acceptance journey

The runner needs the repository's normal development dependencies plus the `surreal` executable. It
uses a disposable directory and starts one real SurrealDB process, one API process, and one worker.

```bash
python scripts/run_state_engine_product_journey.py run \
  --work-dir /tmp/ace-fjord-product-journey \
  --output evaluations/results/state_engine_product_journey_v1.json \
  --markdown-output evaluations/results/state_engine_product_journey_v1.md
```

The runner performs this bounded sequence:

1. Build the extension wheel, install it into a clean environment, and discover its entry point.
2. Apply schema zero and the supported predecessor upgrade to the frozen v168 head.
3. Ingest the corpus, replay it exactly, and reconcile stable IDs, counts, product fences, and
   same-coordinate source-version lineage.
4. Freeze an as-of evidence pack and projection containing supported, contested, provisional,
   superseded, and unknown meanings.
5. Challenge and provisionally review a mechanistic transition with explicit preconditions, horizon,
   probability interval, support, counterevidence search, review receipt, and causal limit.
6. Compare action and no-action branches, then a named alternative and no-action branch, within the
   production task-injection budget.
7. Persist the structured decision, rollout, reasoning-use receipt, and accepted promotion receipt.
8. Record incomplete and matched later outcomes without rewriting the original simulation.
9. Stop and restart the database, API, and worker; use a fresh thin client to prove material I3 use.
10. Capture an explicit correction, accept it as an append-only supersession, restart again, and prove
    later retrieval uses the corrected authoritative material.
11. Interrupt a real task attempt, restart the topology, and resume it as an immutable successor.
12. Recheck product isolation, unavailable evidence, unsupported causal authority, stale transition,
    incomplete reconciliation, simulation/observation separation, and the unchanged MCP boundary.

The command exits nonzero if any required check fails. Its JSON result is self-validating through an
acceptance hash; the Markdown receipt is a human-readable rendering of the same material.

## Supported surfaces and semantic limits

Product builders may use the documented extension entry point and registry facade, extension task
invocation HTTP lifecycle, Core-owned grounded-state contracts/services, and the ordinary eleven thin
MCP tools. There is no supported broad State Engine MCP and no twelfth product tool.

Models and source text may propose content only. They do not choose trusted product scope, mint
authoritative IDs, accept their own claims, turn simulations into observations, or silently promote
memory. Evidence, beliefs, transition hypotheses, simulated consequences, observed outcomes,
decisions, promoted memory, and corrections remain distinct records with explicit lineage.

The acceptance scope is a bounded single-node topology with synchronous fixture adapters. It does not
cover distributed ordering, multi-writer or multi-region operation, autonomous learning, a general
world model, hosted-provider performance, or real-world causal correctness.
