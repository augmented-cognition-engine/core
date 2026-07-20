# core/engine/product/strategy_seed_data.py
"""The transcribed strategy — authored once, the graph becomes source of truth.

Sources (newer wins): ace-north-star (identity apex) > ace-world-class-roadmap
(current spine) > ace-adopt-priority-matrix + ace-master-roadmap (Jun 17, items
live / build-order superseded).
"""

WC = "ace-world-class-roadmap.md"
MX = "ace-adopt-priority-matrix.md"
NS = "ace-north-star.md"

# (ordinal, title, status, summary)
PHASES = [
    (
        1,
        "Phase 1 · Prove & Foundation",
        "active",
        "Regression-gated benchmark in CI; per-event reasoning log; dormant meta-intelligences in prod.",
    ),
    (
        2,
        "Phase 2 · Complete the Brain / Close the Loop",
        "active",
        "Graph fully shapes reasoning AND reasoning writes its conclusions back as edges.",
    ),
    (
        3,
        "Phase 3 · The Execution Layer",
        "next",
        "ACE takes a gated, sandboxed, simulated-first action and learns from the outcome.",
    ),
    (
        4,
        "Phase 4 · The MAKE Arms",
        "next",
        "At least the code arm ships a real reviewed change end-to-end, scored above baseline.",
    ),
    (
        5,
        "Phase 5 · The SHIP Arms",
        "next",
        "A MAKE-arm output passes automated security/test/observability/deploy gates before ship.",
    ),
    (
        6,
        "Phase 6 · The Skin",
        "next",
        "A new partner uses ACE without a manual; the surface reads as a partnership artifact.",
    ),
]

# (objective, status, priority, phase_ordinal, source_refs)
# status in draft|approved|building|shipped|superseded ; the matrix's check/partial/blocked/open.
SPECS = [
    # Shipped this session
    (
        "Cognify — LLM structured insight↔insight typed-edge extraction",
        "shipped",
        "high",
        2,
        [MX, "2026-06-19-graph-tensions.md"],
    ),
    (
        "Graph Tensions — elevate breaks/reverts/causes into reasoning context + telemetry",
        "shipped",
        "high",
        2,
        ["2026-06-19-graph-tensions.md", MX],
    ),
    (
        "Living Roadmap — roadmap as a computed projection over the graph",
        "shipped",
        "high",
        1,
        ["2026-06-19-living-roadmap.md"],
    ),
    (
        "Arm abstraction foundation — Solution/Arm contract/registry/dispatch (simulated)",
        "shipped",
        "high",
        3,
        ["2026-06-19-arm-abstraction-foundation.md"],
    ),
    ("Wire preferred_lens_set → committee (learned dynamic committee)", "shipped", "high", 2, [MX]),
    ("Learned model-tier routing (route_model learned bump + routing_perf)", "shipped", "high", 1, [MX]),
    ("OTel GenAI spans inside get_llm().complete()", "shipped", "high", 1, [MX]),
    ("Self-consistency vote (majority + adaptive stopping)", "shipped", "high", 2, [MX]),
    ("Evaluator-Guided Refinement (LLM-Modulo / Reflexion-at-phase)", "shipped", "high", 2, [MX]),
    ("Semantic entropy on close-call sampling", "shipped", "high", 2, [MX]),
    ("Learned committee composition (committee_perf)", "shipped", "medium", 2, [MX]),
    # In flight / partial / blocked
    ("Event log — reasoning_event append-only (evolve run_ledger)", "building", "high", 1, [MX, WC]),
    ("Cross-model grader → un-starve calibration", "blocked", "high", 1, [MX, WC]),
    ("Mixture-of-Agents at the one highest-stakes phase", "building", "high", 2, [MX]),
    ("Cascade calibration / CascadeRouter prod instantiation", "building", "high", 1, [MX]),
    # Open, refreshed-order (buildable-now leverage)
    ("Graph-informed committee selection (membership-side of Graph Tensions)", "approved", "high", 2, [WC, MX]),
    ("Phase outputs → edges (close the active loop; backward-flow)", "approved", "high", 2, [WC]),
    ("Graph community summaries for briefings", "draft", "high", 2, [MX]),
    ("Hybrid retrieval → cross-encoder rerank", "draft", "high", 2, [MX]),
    ("Contextual chunk enrichment (index-time)", "draft", "high", 2, [MX]),
    ("Recipe-prompt optimization (DSPy MIPROv2 → self_optimizer gate)", "draft", "medium", 2, [MX]),
    ("Sleeptime consolidation (between-run rewrite)", "draft", "medium", 2, [MX]),
    ("Bi-temporal edges (valid_at/invalid_at, invalidate-not-delete)", "draft", "medium", 2, [MX]),
    # Execution layer + arms (the product roadmap, post-vision)
    (
        "Sandboxed execution runtime — enforcement gates + foresight simulation (Plan 2)",
        "approved",
        "high",
        3,
        [WC, MX],
    ),
    ("Action → outcome capture (extend active loop to actions)", "draft", "high", 3, [WC]),
    ("Forkable foresight — branch-from-checkpoint, simulate, compare", "draft", "medium", 3, [WC, MX]),
    ("Code arm — first MAKE arm (Cursor/Devin/Aider frontier)", "draft", "high", 4, [WC]),
    ("Design arm (v0/Figma-Make frontier)", "draft", "medium", 4, [WC]),
    ("Data arm (dbt/text-to-SQL frontier)", "draft", "medium", 4, [WC]),
    ("SHIP arms — security/testing/observability/devops/scale gates", "draft", "high", 5, [WC]),
    ("Eval / benchmark harness — golden set + regression gate (make eval)", "approved", "high", 1, [WC, MX]),
    ("Canvas maturity + conceptual onboarding (partnership surface)", "draft", "medium", 6, [WC]),
]

# (title, rationale, decision_type, alternatives, source_ref) — the "why" + reframes.
DECISIONS = [
    (
        "Build is the purpose; reasoning is the OS underneath",
        "ACE's intelligence is the substrate; the point is to BUILD durable products intelligently. Systems thinking embedded as a product.",
        "direction",
        ["reasoning-OS-as-the-product"],
        NS,
    ),
    (
        "ACE is not Cursor — a different category",
        "ACE is an AI Product Manager with an embedded team, for anyone with a vision — not an engineer's code tool. Homegrown for all.",
        "direction",
        ["compete-with-Cursor", "code-first-IDE"],
        NS,
    ),
    (
        "World-class roadmap is the current roadmap spine",
        "ace-world-class-roadmap unifies the matrix + arms + world-class gaps by dependency. It is the live spine; docs are snapshots.",
        "direction",
        ["per-doc-roadmaps"],
        WC,
    ),
    (
        "master-roadmap phase-0-6 framing is superseded",
        "Reframed by the world-class roadmap's dependency sequencing (stated in the doc).",
        "direction",
        None,
        WC,
    ),
    (
        "adopt-priority matrix build-order is superseded (items remain valid)",
        "The matrix predates the vision; its brain-pattern items + shipped-status are live, but its consolidated build-order is reframed by the world-class roadmap.",
        "direction",
        None,
        WC,
    ),
    (
        "Adopt the pattern, not the library",
        "Across 10 OSS framework analyses: wholesale adoption would damage ACE's differentiated architecture. Adopt patterns only.",
        "direction",
        ["fork-a-framework"],
        MX,
    ),
]

# SKIP-rejections — so the roadmap never re-proposes them. (title, rationale)
REJECTIONS = [
    ("Reject MeTTa / Distributed Atomspace (OpenCog)", "Pre-alpha, AGPL-adjacent risk."),
    ("Reject full MCTS/LATS and HTN/PDDL planning", "Expensive theater without a fast value function."),
    ("Reject SELF-DISCOVER", "ACE's recipe composition already is this."),
    ("Reject named crews / code-as-action for reasoning", "Anti-thesis (no bench); pure-compute conflict."),
    ("Reject offline topology search (AFlow/GPTSwarm)", "Overfits ACE's open, shifting task space."),
    ("Reject Agentic/Self-RAG · HyDE · ColBERT", "Latency / scale not justified at current size."),
    ("Reject trained PRM · NeMo/Llama Guard", "No labeled data / no policy requirement."),
    ("Reject HRM dual-timescale as a composer pattern", "Adversarially refuted twice this program."),
]

# Supersession edges (superseding_title -> superseded_title) for lineage.
SUPERSEDES = [
    ("World-class roadmap is the current roadmap spine", "master-roadmap phase-0-6 framing is superseded"),
    (
        "World-class roadmap is the current roadmap spine",
        "adopt-priority matrix build-order is superseded (items remain valid)",
    ),
]
