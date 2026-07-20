#!/usr/bin/env python3
# engine/cognition/seed.py
"""Seed new cognitive instrument frameworks + meta-skill definitions to DB.

Run: uv run python engine/cognition/seed.py

This seeds:
1. New instrument framework entries (~120 slugs) to the `framework` table
2. Meta-skill definitions (22) to the `meta_skill` table

Idempotent: uses delete-then-create. Existing frameworks from seed_frameworks.py are NOT touched.
"""

import asyncio
import importlib

from core.engine.cognition.composer import _RECIPE_MODULES
from core.engine.core.db import pool

NEW_FRAMEWORKS = [
    # ═══════════════════════════════════════════════════════════════
    # GENERIC (7)
    # ═══════════════════════════════════════════════════════════════
    # GEN-01 (provided in plan)
    {
        "slug": "three-mode-critique",
        "name": "Three-Mode Critique",
        "family": "adversarial",
        "tier": "built-in",
        "description": "Evaluate a solution from three distinct critical perspectives: correctness, alternatives, and polish.",
        "activation_signals": [
            "critique",
            "review",
            "find problems",
            "what's wrong",
            "improve",
            "evaluate quality",
            "sanity check",
        ],
        "archetype_affinity": {"analyst": 0.9, "executor": 0.8, "advisor": 0.7},
        "mode_affinity": {"deliberative": 0.9, "reflective": 0.8},
        "composability": {"complements": ["holistic-validation", "pairwise-comparison"], "conflicts": []},
        "system_prompt": (
            "Critique this work from three distinct modes:\n"
            "1. CORRECTNESS MODE: Is this factually, logically, technically correct? List specific errors, violations, or falsehoods. Be precise — name the exact failure.\n"
            "2. ALTERNATIVES MODE: What better approaches exist? Not minor tweaks — meaningfully different solutions. Why are they superior?\n"
            "3. POLISH MODE: Assuming correctness, what's mediocre? Style, naming, structure, completeness, clarity. What separates good from excellent here?\n"
            "4. TRIAGE: Rank all findings by impact. Correctness failures block. Alternatives inform. Polish refines.\n"
            "5. VERDICT: One sentence: ship it / fix these 3 things first / fundamental rethink needed.\n"
            "Do not hedge. Call the failures directly."
        ),
    },
    # GEN-02 (provided in plan)
    {
        "slug": "holistic-validation",
        "name": "Holistic Validation",
        "family": "evaluative",
        "tier": "built-in",
        "description": "Validate a solution against the full problem space: stated requirements, unstated expectations, edge cases, and integration points.",
        "activation_signals": [
            "validate",
            "check completeness",
            "does this cover",
            "edge cases",
            "missing anything",
            "sanity check",
            "verify",
        ],
        "archetype_affinity": {"analyst": 0.9, "executor": 0.8, "advisor": 0.7},
        "mode_affinity": {"deliberative": 0.9, "procedural": 0.8},
        "composability": {"complements": ["three-mode-critique", "mece"], "conflicts": []},
        "system_prompt": (
            "Validate this solution holistically:\n"
            "1. STATED REQUIREMENTS: Does the solution address every explicit requirement? List each requirement and whether it's met, partially met, or missed.\n"
            "2. UNSTATED EXPECTATIONS: What does a reasonable person expect that wasn't written down? Check: performance, security, maintainability, backwards compat.\n"
            "3. EDGE CASES: What inputs, states, or sequences break this? Enumerate at least 5 non-obvious edge cases.\n"
            "4. INTEGRATION POINTS: What does this touch? Will existing consumers break? Check interfaces, contracts, and downstream dependencies.\n"
            "5. VERDICT: Red (do not ship) / Yellow (ship with caveats) / Green (ship). State the blocking issues.\n"
            "Output: validation_matrix, edge_case_list, integration_risks, verdict"
        ),
    },
    # GEN-03 (provided in plan)
    {
        "slug": "pairwise-comparison",
        "name": "Pairwise Comparison",
        "family": "evaluative",
        "tier": "built-in",
        "description": "Force a direct head-to-head comparison between two options across explicit criteria to eliminate false equivalence.",
        "activation_signals": [
            "compare",
            "which is better",
            "option A vs B",
            "choose between",
            "trade-offs",
            "versus",
            "decide",
        ],
        "archetype_affinity": {"analyst": 0.9, "advisor": 0.8, "executor": 0.7},
        "mode_affinity": {"deliberative": 0.9, "exploratory": 0.7},
        "composability": {"complements": ["allocation", "three-mode-critique"], "conflicts": []},
        "system_prompt": (
            "Perform a forced pairwise comparison:\n"
            "1. NAME both options precisely. Resist the urge to redefine them favorably.\n"
            "2. DEFINE criteria: list 4-6 dimensions that actually matter for this decision. Not generic criteria — specific to this context.\n"
            "3. SCORE each option per criterion on a 1-5 scale. Justify every score in one sentence.\n"
            "4. IDENTIFY the decisive dimension: which single criterion, if weighted heavily, flips the outcome? That's where the real decision lives.\n"
            "5. FORCE A CHOICE: given your actual context (stage, constraints, risk tolerance), which option wins? State it plainly.\n"
            "Do not hedge. Force a choice."
        ),
    },
    # GEN-04 (provided in plan)
    {
        "slug": "allocation",
        "name": "Resource Allocation",
        "family": "evaluative",
        "tier": "built-in",
        "description": "Distribute a fixed resource (time, points, budget, tokens) across competing uses to make implicit trade-offs explicit.",
        "activation_signals": [
            "allocate",
            "distribute",
            "trade-offs",
            "budget",
            "prioritize effort",
            "time split",
            "how much to each",
        ],
        "archetype_affinity": {"analyst": 0.8, "advisor": 0.9, "executor": 0.7},
        "mode_affinity": {"deliberative": 0.9, "procedural": 0.8},
        "composability": {"complements": ["pairwise-comparison", "mece"], "conflicts": []},
        "system_prompt": (
            "Allocate resources using explicit trade-off reasoning:\n"
            "1. ENUMERATE competing uses: what are all the things that want a share of this resource?\n"
            "2. STATE the total: 100 points, 40 hours, $10k — whatever the unit is, make it explicit.\n"
            "3. ALLOCATE: assign a specific share to each use. The numbers must sum to the total.\n"
            "4. JUSTIFY each allocation: why this share and not more or less? What would you sacrifice to shift 10 points from one bucket to another?\n"
            "5. IDENTIFY the hidden choice: what does this allocation reveal about what you actually value?\n"
            "Output: allocation_table (use, share, rationale), revealed_priority"
        ),
    },
    # GEN-05
    {
        "slug": "hypothesis-framing",
        "name": "Hypothesis Framing",
        "family": "diagnostic",
        "tier": "built-in",
        "description": "Frame an assumption as a falsifiable hypothesis by identifying what evidence would disprove it and what the null hypothesis is.",
        "activation_signals": [
            "assumption",
            "hypothesis",
            "we think",
            "we believe",
            "test this",
            "validate assumption",
            "what would prove",
            "falsify",
        ],
        "archetype_affinity": {"researcher": 0.9, "analyst": 0.8, "advisor": 0.7},
        "mode_affinity": {"deliberative": 0.9, "exploratory": 0.8},
        "composability": {"complements": ["first-principles", "assumption-identification"], "conflicts": []},
        "system_prompt": (
            "Frame this as a testable hypothesis:\n"
            "1. STATE the assumption precisely as a hypothesis: 'We believe X is true because Y.'\n"
            "2. IDENTIFY the null hypothesis: what would the world look like if X is false?\n"
            "3. LIST falsification criteria: what specific evidence, measurements, or observations would disprove this hypothesis?\n"
            "4. ESTIMATE prior probability: how confident are you in X before testing? (0-100%). Justify the number.\n"
            "5. DESIGN the minimal test: what is the cheapest, fastest experiment that would move your confidence significantly?\n"
            "6. STATE the decision: if the hypothesis is disproved, what changes? If it holds, what does that unlock?\n"
            "Do not state beliefs as facts. Force them into hypothesis form."
        ),
    },
    # GEN-06
    {
        "slug": "coverage-mapping",
        "name": "Coverage Mapping",
        "family": "diagnostic",
        "tier": "built-in",
        "description": "Map the expected territory of a problem space to identify which domains are in scope, which are out, and which haven't been considered.",
        "activation_signals": [
            "coverage",
            "scope",
            "what's in",
            "what's out",
            "territory",
            "map the space",
            "what domains",
            "comprehensive scope",
        ],
        "archetype_affinity": {"analyst": 0.9, "researcher": 0.8, "advisor": 0.7},
        "mode_affinity": {"deliberative": 0.8, "exploratory": 0.9},
        "composability": {"complements": ["mece", "gap-analysis"], "conflicts": []},
        "system_prompt": (
            "Map the coverage of this problem space:\n"
            "1. DEFINE the full territory: what is the complete set of domains, areas, or concerns that exist in this space? Be exhaustive.\n"
            "2. CLASSIFY each domain: IN SCOPE (actively addressed), OUT OF SCOPE (explicitly excluded), or UNEXAMINED (not yet considered).\n"
            "3. JUSTIFY exclusions: for each out-of-scope domain, state why it was excluded — intentional decision or oversight?\n"
            "4. FLAG unexamined areas: these are the risk surface. Which unexamined domain is most likely to matter?\n"
            "5. ASSESS coverage quality: what percentage of the full territory is actively addressed? Is that sufficient?\n"
            "Output: coverage_map (domain, status, justification), coverage_score, biggest_unexamined_risk"
        ),
    },
    # GEN-07
    {
        "slug": "gap-analysis",
        "name": "Gap Analysis",
        "family": "evaluative",
        "tier": "built-in",
        "description": "Identify what is missing from a solution, system, or plan and prioritize gaps by their impact on the whole.",
        "activation_signals": [
            "what's missing",
            "gaps",
            "incomplete",
            "holes",
            "not covered",
            "find gaps",
            "what's lacking",
        ],
        "archetype_affinity": {"analyst": 0.9, "advisor": 0.8, "researcher": 0.7},
        "mode_affinity": {"deliberative": 0.9, "reflective": 0.8},
        "composability": {"complements": ["coverage-mapping", "mece", "absence-ranking"], "conflicts": []},
        "system_prompt": (
            "Perform a gap analysis:\n"
            "1. DEFINE what completeness looks like: what would a fully realized version of this contain?\n"
            "2. AUDIT what exists: map current state to that ideal state.\n"
            "3. ENUMERATE gaps: list everything present in the ideal but absent in current state.\n"
            "4. CLASSIFY each gap: blocking (prevents function), degrading (reduces quality), cosmetic (minor polish).\n"
            "5. PRIORITIZE by impact: which gap, if filled, produces the most improvement? Rank top 3.\n"
            "6. IDENTIFY root cause: is each gap accidental (forgot), deferred (known, not done), or architectural (hard to add now)?\n"
            "Output: gap_list (item, classification, impact_rank, root_cause), top_priority_gap"
        ),
    },
    # ═══════════════════════════════════════════════════════════════
    # EVALUATION (5)
    # ═══════════════════════════════════════════════════════════════
    # EVA-01
    {
        "slug": "multi-lens-framing",
        "name": "Multi-Lens Framing",
        "family": "diagnostic",
        "tier": "built-in",
        "description": "Apply three orthogonal lenses — technical correctness, craft quality, and user impact — to frame what an evaluation should assess.",
        "activation_signals": [
            "evaluate",
            "assess",
            "review quality",
            "multiple perspectives",
            "different angles",
            "comprehensive review",
            "quality check",
        ],
        "archetype_affinity": {"analyst": 0.9, "advisor": 0.8, "creator": 0.7},
        "mode_affinity": {"deliberative": 0.9, "reflective": 0.8},
        "composability": {"complements": ["criteria-maxdiff", "three-mode-critique"], "conflicts": []},
        "system_prompt": (
            "Frame this evaluation through three lenses:\n"
            "1. TECHNICAL LENS: Is it correct, complete, and robust? Identify correctness failures, missing cases, brittleness.\n"
            "2. CRAFT LENS: Is it well-made? Assess clarity, consistency, elegance, and maintainability independent of correctness.\n"
            "3. USER IMPACT LENS: Does it serve the intended audience? Would the person receiving this output be well-served?\n"
            "4. TENSION MAPPING: Where do the lenses conflict? (technically correct but poor craft; great UX but fragile implementation)\n"
            "5. PRIMARY LENS for this context: given the purpose and audience, which lens should dominate the overall verdict?\n"
            "Output: findings_by_lens, tensions, primary_lens_rationale"
        ),
    },
    # EVA-02
    {
        "slug": "criteria-maxdiff",
        "name": "Criteria MaxDiff",
        "family": "evaluative",
        "tier": "built-in",
        "description": "Use MaxDiff logic to identify which quality dimensions matter most for a specific evaluation, forcing prioritization over generic checklists.",
        "activation_signals": [
            "what matters most",
            "quality criteria",
            "evaluation dimensions",
            "most important",
            "which criteria",
            "weight criteria",
        ],
        "archetype_affinity": {"analyst": 0.9, "advisor": 0.8},
        "mode_affinity": {"deliberative": 0.9, "procedural": 0.8},
        "composability": {"complements": ["multi-lens-framing", "quality-pairwise"], "conflicts": []},
        "system_prompt": (
            "Identify the most important quality dimensions using MaxDiff reasoning:\n"
            "1. LIST all plausible quality dimensions for this specific evaluation target (aim for 8-12).\n"
            "2. APPLY MaxDiff: for this specific context, which 2 dimensions matter MOST? Which 2 matter LEAST?\n"
            "3. FORCE RANKING: order all dimensions from most to least critical. No ties.\n"
            "4. JUSTIFY the top 3: why do these dominate? What about this context makes them critical?\n"
            "5. CULL the bottom: are the lowest-ranked dimensions genuinely irrelevant here, or just less urgent?\n"
            "Output: ranked_criteria (dimension, rank, weight 1-10, justification), culled_list"
        ),
    },
    # EVA-03
    {
        "slug": "quality-pairwise",
        "name": "Quality Pairwise",
        "family": "evaluative",
        "tier": "built-in",
        "description": "Evaluate quality by pairwise comparison against a high bar rather than running down a checklist, forcing genuine discrimination.",
        "activation_signals": [
            "quality bar",
            "high standard",
            "compare to best",
            "meets the bar",
            "production ready",
            "good enough",
            "quality standard",
        ],
        "archetype_affinity": {"analyst": 0.9, "executor": 0.8, "advisor": 0.7},
        "mode_affinity": {"deliberative": 0.9, "reflective": 0.8},
        "composability": {"complements": ["criteria-maxdiff", "severity-allocation"], "conflicts": []},
        "system_prompt": (
            "Evaluate quality by comparison against a defined high bar:\n"
            "1. DEFINE the high bar: describe what an excellent version of this would look like. Be specific.\n"
            "2. COMPARE directly: put the submitted work next to the bar. Where does it match? Where does it fall short?\n"
            "3. IDENTIFY the gap: what specifically separates this from excellent? List concrete differences, not vague impressions.\n"
            "4. CLASSIFY the gap: is this a correctness gap (wrong), a completeness gap (missing), or a craft gap (mediocre)?\n"
            "5. FORCE A VERDICT: excellent / acceptable / below bar. Not 'it depends.' Choose.\n"
            "Do not use a checklist. Compare directly against the bar."
        ),
    },
    # EVA-04
    {
        "slug": "severity-allocation",
        "name": "Severity Allocation",
        "family": "evaluative",
        "tier": "built-in",
        "description": "Distribute 100 severity points across defect classes (correctness, completeness, craft) to force explicit prioritization of findings.",
        "activation_signals": [
            "severity",
            "how bad",
            "prioritize findings",
            "triage defects",
            "rank issues",
            "worst problems",
            "impact of issues",
        ],
        "archetype_affinity": {"analyst": 0.9, "executor": 0.7, "advisor": 0.8},
        "mode_affinity": {"deliberative": 0.9, "procedural": 0.8},
        "composability": {"complements": ["quality-pairwise", "three-mode-critique"], "conflicts": []},
        "system_prompt": (
            "Allocate severity across finding categories:\n"
            "1. ENUMERATE all findings from your evaluation.\n"
            "2. CLASSIFY into buckets: DEFECT (wrong/broken), MEDIOCRITY (works but poor quality), TASTE (style/opinion).\n"
            "3. ALLOCATE 100 severity points total across all findings. Higher points = higher severity.\n"
            "4. JUSTIFY concentrations: why does this finding get 30 points when others get 5?\n"
            "5. THRESHOLD: findings above 15 points are blocking. Below 5 are noise. State blocking items explicitly.\n"
            "Output: severity_table (finding, class, points, blocking), total_severity_score"
        ),
    },
    # EVA-05
    {
        "slug": "meta-evaluation",
        "name": "Meta-Evaluation",
        "family": "adversarial",
        "tier": "built-in",
        "description": "Critique the evaluation itself: was it rigorous, unbiased, and complete? What biases or blind spots affected the verdict?",
        "activation_signals": [
            "evaluate the evaluation",
            "was the review fair",
            "biases",
            "blind spots",
            "review quality",
            "second-order",
            "meta",
        ],
        "archetype_affinity": {"analyst": 0.9, "advisor": 0.8, "researcher": 0.7},
        "mode_affinity": {"reflective": 0.9, "deliberative": 0.8},
        "composability": {"complements": ["three-mode-critique", "self-calibration"], "conflicts": []},
        "system_prompt": (
            "Critique this evaluation for rigor and bias:\n"
            "1. AUDIT criteria coverage: did the evaluation check what actually matters, or what was easy to check?\n"
            "2. IDENTIFY bias sources: confirmation bias (looking for expected result), familiarity bias (judging harshly what's unfamiliar), authority bias (deferring to source).\n"
            "3. FIND blind spots: what dimension was systematically under-weighted or ignored?\n"
            "4. ASSESS evidence quality: were findings backed by specific evidence or vague impressions?\n"
            "5. CHECK calibration: are severity ratings proportional to actual impact? Over-severe? Under-severe?\n"
            "6. VERDICT: is this evaluation trustworthy? What would change if re-run by a different evaluator?\n"
            "Output: bias_list, blind_spots, calibration_assessment, trustworthiness_score (1-10)"
        ),
    },
    # ═══════════════════════════════════════════════════════════════
    # CREATIVE (5 — provided in plan)
    # ═══════════════════════════════════════════════════════════════
    # CRE-01 (provided)
    {
        "slug": "context-inference",
        "name": "Context Inference",
        "family": "diagnostic",
        "tier": "built-in",
        "description": "Infer the creative context from sparse signals: audience, purpose, tone, and constraints that were not explicitly stated.",
        "activation_signals": [
            "what's the context",
            "who is this for",
            "infer",
            "read between lines",
            "implied audience",
            "what do they want",
            "understand the brief",
        ],
        "archetype_affinity": {"creator": 0.9, "advisor": 0.8, "researcher": 0.6},
        "mode_affinity": {"exploratory": 0.9, "deliberative": 0.7},
        "composability": {"complements": ["audience-modeling", "message-maxdiff"], "conflicts": []},
        "system_prompt": (
            "Infer the creative context from available signals:\n"
            "1. AUDIENCE: Who is this actually for? Demographics, sophistication level, what they care about, what they already know.\n"
            "2. PURPOSE: What should this accomplish? Inform, persuade, delight, instruct, signal status?\n"
            "3. TONE: What register fits? Formal, casual, urgent, playful, authoritative? Infer from the request style.\n"
            "4. CONSTRAINTS: What's off-limits? Length, format, voice, brand, prior commitments?\n"
            "5. SUCCESS CRITERIA: How will the creator know this worked? What reaction does it need to produce?\n"
            "6. GAPS: What's missing from the brief that you're inferring? Flag explicitly so it can be corrected.\n"
            "Output: inferred_context (audience, purpose, tone, constraints, success_criteria), confidence, gaps"
        ),
    },
    # CRE-02 (provided)
    {
        "slug": "maxdiff-values",
        "name": "MaxDiff Values",
        "family": "evaluative",
        "tier": "built-in",
        "description": "Use MaxDiff to identify which creative values matter most for this specific project, forcing explicit trade-offs between clarity, originality, impact, and craft.",
        "activation_signals": [
            "creative values",
            "what matters",
            "originality vs clarity",
            "creative priorities",
            "trade-offs in design",
            "what to optimize",
        ],
        "archetype_affinity": {"creator": 0.9, "advisor": 0.7, "analyst": 0.6},
        "mode_affinity": {"deliberative": 0.9, "exploratory": 0.7},
        "composability": {"complements": ["context-inference", "framing-selection"], "conflicts": []},
        "system_prompt": (
            "Identify the dominant creative values using MaxDiff:\n"
            "1. LIST all creative values relevant to this project: clarity, originality, emotional impact, brevity, craft, surprise, authority, warmth, precision, elegance.\n"
            "2. APPLY MaxDiff: for this specific project, which 2 values matter MOST? Which 2 matter LEAST?\n"
            "3. FORCE RANKING: rank all values 1-N. No ties. Justify your top 3 choices.\n"
            "4. RESOLVE TENSIONS: clarity vs. surprise; brevity vs. completeness. How do you break ties for this specific project?\n"
            "5. OUTPUT a creative brief: given these ranked values, what does an excellent version of this look like?\n"
            "Output: ranked_values, resolved_tensions, creative_brief"
        ),
    },
    # CRE-03 (provided)
    {
        "slug": "pairwise-tournament",
        "name": "Pairwise Tournament",
        "family": "evaluative",
        "tier": "built-in",
        "description": "Run a tournament-style pairwise comparison across multiple creative options to find the strongest through head-to-head elimination.",
        "activation_signals": [
            "which version is best",
            "compare options",
            "tournament",
            "multiple variants",
            "pick the winner",
            "A vs B vs C",
            "best of",
        ],
        "archetype_affinity": {"creator": 0.9, "analyst": 0.8, "advisor": 0.7},
        "mode_affinity": {"deliberative": 0.9, "exploratory": 0.7},
        "composability": {"complements": ["maxdiff-values", "pairwise-comparison"], "conflicts": []},
        "system_prompt": (
            "Run a pairwise tournament to find the strongest option:\n"
            "1. LIST all options entering the tournament. Each needs a clear label.\n"
            "2. DEFINE the judging criterion: one primary dimension on which options are compared.\n"
            "3. FIRST ROUND: pair options head-to-head. For each pair, state which wins and why in one sentence.\n"
            "4. ADVANCE winners to next round. Continue until one option remains.\n"
            "5. AUDIT the result: does the tournament winner actually deserve to win, or did bracket luck affect the outcome?\n"
            "6. IDENTIFY the runner-up: which option would you use if the winner is unavailable?\n"
            "Output: tournament_bracket, winner, runner_up, winner_rationale"
        ),
    },
    # CRE-04 (provided)
    {
        "slug": "conjoint-validation",
        "name": "Conjoint Validation",
        "family": "evaluative",
        "tier": "built-in",
        "description": "Validate creative work by testing it against multi-attribute audience profiles: does it land for the target audience given their specific context and preferences?",
        "activation_signals": [
            "will this land",
            "audience fit",
            "resonance",
            "validate for audience",
            "does this work for them",
            "test the message",
        ],
        "archetype_affinity": {"creator": 0.9, "advisor": 0.8, "researcher": 0.7},
        "mode_affinity": {"deliberative": 0.9, "reflective": 0.7},
        "composability": {"complements": ["context-inference", "audience-modeling"], "conflicts": []},
        "system_prompt": (
            "Validate creative work against the target audience using conjoint analysis:\n"
            "1. BUILD 3 distinct audience profiles: for each, define role, prior knowledge, main concern, and what would make them dismiss this.\n"
            "2. SIMULATE each profile's reaction: how does this land for each audience member? What resonates? What alienates?\n"
            "3. IDENTIFY conflicts: what works for Profile A but fails for Profile B? These are the real trade-off decisions.\n"
            "4. FIND the universal: is there anything that works across all profiles? That's the core message.\n"
            "5. RECOMMEND: given the primary audience, accept or reject each conflict resolution.\n"
            "Output: profile_reactions (profile, resonance, friction), conflicts, universal_core, recommendation"
        ),
    },
    # CRE-05 (provided)
    {
        "slug": "investment-allocation",
        "name": "Investment Allocation",
        "family": "evaluative",
        "tier": "built-in",
        "description": "Allocate creative effort across work phases (concept, structure, language, polish) by treating time as a budget with explicit trade-offs.",
        "activation_signals": [
            "where to focus",
            "how to spend time",
            "creative effort",
            "polish vs structure",
            "where to invest",
            "time allocation",
            "effort budget",
        ],
        "archetype_affinity": {"creator": 0.9, "advisor": 0.7, "executor": 0.6},
        "mode_affinity": {"deliberative": 0.9, "procedural": 0.8},
        "composability": {"complements": ["maxdiff-values", "allocation"], "conflicts": []},
        "system_prompt": (
            "Allocate creative effort as an investment budget:\n"
            "1. DEFINE the work phases: concept development, structural design, language/execution, polish/refinement.\n"
            "2. ASSESS current state: which phases are underdeveloped vs. over-engineered relative to impact?\n"
            "3. ALLOCATE 100 effort points across phases. Justify each allocation.\n"
            "4. IDENTIFY the constraining phase: which phase, if skimped, makes the whole piece fail regardless of other investment?\n"
            "5. SET the quality floor: what's the minimum viable investment per phase before diminishing returns kick in?\n"
            "Output: effort_allocation (phase, points, current_state, justification), constraining_phase, quality_floor"
        ),
    },
    # ═══════════════════════════════════════════════════════════════
    # RESEARCH (4 — provided in plan)
    # ═══════════════════════════════════════════════════════════════
    # RES-01 (provided)
    {
        "slug": "evidence-hierarchy",
        "name": "Evidence Hierarchy",
        "family": "evaluative",
        "tier": "built-in",
        "description": "Rank evidence by reliability tier (primary source, replication, expert consensus, single study, anecdote) to prevent weak evidence from driving strong conclusions.",
        "activation_signals": [
            "evidence",
            "sources",
            "how reliable",
            "what's the proof",
            "primary source",
            "research quality",
            "citation strength",
        ],
        "archetype_affinity": {"researcher": 0.9, "analyst": 0.8, "advisor": 0.7},
        "mode_affinity": {"deliberative": 0.9, "exploratory": 0.8},
        "composability": {"complements": ["structured-comparison", "confidence-allocation"], "conflicts": []},
        "system_prompt": (
            "Evaluate evidence using a reliability hierarchy:\n"
            "1. CATEGORIZE each piece of evidence: Tier 1 (primary source, direct measurement), Tier 2 (replicated study, systematic review), Tier 3 (expert consensus), Tier 4 (single study, case report), Tier 5 (anecdote, authority claim).\n"
            "2. AUDIT the evidence base: what tier is the weakest evidence supporting your key claims?\n"
            "3. FLAG weak foundations: any strong conclusion resting on Tier 4-5 evidence needs to be downgraded.\n"
            "4. IDENTIFY gaps: what Tier 1-2 evidence is missing that would significantly change confidence?\n"
            "5. STATE calibrated conclusions: rewrite claims to match their evidence tier. 'Evidence suggests' ≠ 'It is proven.'\n"
            "Output: evidence_map (claim, evidence, tier), weakest_link, confidence-adjusted conclusions"
        ),
    },
    # RES-02 (provided)
    {
        "slug": "structured-comparison",
        "name": "Structured Comparison",
        "family": "evaluative",
        "tier": "built-in",
        "description": "Compare research findings across sources using a fixed attribute grid to surface agreements, conflicts, and patterns across studies.",
        "activation_signals": [
            "compare sources",
            "research synthesis",
            "what do studies say",
            "compare findings",
            "conflicting evidence",
            "across sources",
            "literature review",
        ],
        "archetype_affinity": {"researcher": 0.9, "analyst": 0.8},
        "mode_affinity": {"deliberative": 0.9, "procedural": 0.8},
        "composability": {"complements": ["evidence-hierarchy", "synthesis-coherence"], "conflicts": []},
        "system_prompt": (
            "Compare research findings using a structured grid:\n"
            "1. DEFINE comparison attributes: methodology, sample size, context, findings, limitations, date.\n"
            "2. BUILD the grid: map each source across all attributes. Fill every cell — 'not reported' is a data point.\n"
            "3. FIND agreements: where do multiple sources converge? This is your most reliable signal.\n"
            "4. FIND conflicts: where do sources disagree? What explains the conflict (methodology, population, context)?\n"
            "5. IDENTIFY patterns: what does the aggregate shape of the evidence suggest beyond any individual source?\n"
            "6. WEIGHT the synthesis: given agreements and conflicts, what's the most defensible conclusion?\n"
            "Output: comparison_grid, agreements, conflicts_with_explanations, weighted_synthesis"
        ),
    },
    # RES-03 (provided)
    {
        "slug": "synthesis-coherence",
        "name": "Synthesis Coherence",
        "family": "adversarial",
        "tier": "built-in",
        "description": "Verify that a research synthesis is internally coherent: no contradictions, no conclusions that outrun their evidence, and proper handling of uncertainty.",
        "activation_signals": [
            "does this hold together",
            "synthesis check",
            "internal consistency",
            "contradictions",
            "coherent argument",
            "does the logic hold",
        ],
        "archetype_affinity": {"researcher": 0.9, "analyst": 0.8, "advisor": 0.7},
        "mode_affinity": {"deliberative": 0.9, "reflective": 0.8},
        "composability": {"complements": ["structured-comparison", "evidence-hierarchy"], "conflicts": []},
        "system_prompt": (
            "Verify synthesis coherence:\n"
            "1. MAP the argument structure: what are the key claims and how do they connect?\n"
            "2. CHECK for internal contradictions: does any conclusion conflict with another? List every contradiction found.\n"
            "3. AUDIT conclusion-evidence alignment: for each conclusion, does the cited evidence actually support it, or does the conclusion outrun the evidence?\n"
            "4. TEST the chain: if you remove the weakest link, does the synthesis collapse or hold?\n"
            "5. ASSESS uncertainty handling: are confidence levels stated? Are caveats proportional to the evidence quality?\n"
            "Output: argument_map, contradictions, overreach_list, weakest_link, coherence_verdict (coherent / minor issues / fundamental incoherence)"
        ),
    },
    # RES-04 (provided)
    {
        "slug": "confidence-allocation",
        "name": "Confidence Allocation",
        "family": "evaluative",
        "tier": "built-in",
        "description": "Distribute 100 confidence points across competing hypotheses or interpretations to force explicit probabilistic reasoning.",
        "activation_signals": [
            "how confident",
            "probability",
            "which explanation",
            "likelihood",
            "confidence level",
            "assign probability",
            "best explanation",
        ],
        "archetype_affinity": {"researcher": 0.9, "analyst": 0.8, "advisor": 0.7},
        "mode_affinity": {"deliberative": 0.9, "reflective": 0.8},
        "composability": {"complements": ["evidence-hierarchy", "hypothesis-framing"], "conflicts": []},
        "system_prompt": (
            "Allocate confidence across competing hypotheses:\n"
            "1. LIST all viable hypotheses or interpretations. Include the null hypothesis.\n"
            "2. ALLOCATE 100 confidence points total across all hypotheses. Numbers must sum to 100.\n"
            "3. JUSTIFY each allocation: what evidence drives these numbers?\n"
            "4. IDENTIFY the pivot point: what single piece of evidence, if true, would most shift your allocation?\n"
            "5. TEST extreme cases: what would it take to push any hypothesis above 80 points? Below 5?\n"
            "6. STATE the actionable belief: given this distribution, how should decisions be made?\n"
            "Output: confidence_distribution (hypothesis, points, evidence_basis), pivot_evidence, decision_guidance"
        ),
    },
    # ═══════════════════════════════════════════════════════════════
    # CODING (4 — provided in plan)
    # ═══════════════════════════════════════════════════════════════
    # COD-01 (provided)
    {
        "slug": "approach-maxdiff",
        "name": "Approach MaxDiff",
        "family": "evaluative",
        "tier": "built-in",
        "description": "Use MaxDiff to identify the best and worst implementation approaches for a coding task, forcing discrimination between options before writing a line.",
        "activation_signals": [
            "which approach",
            "implementation options",
            "how to implement",
            "best way to code",
            "design options",
            "approach comparison",
        ],
        "archetype_affinity": {"executor": 0.9, "analyst": 0.8, "advisor": 0.6},
        "mode_affinity": {"deliberative": 0.9, "procedural": 0.8},
        "composability": {"complements": ["codebase-comparison", "complexity-budget"], "conflicts": []},
        "system_prompt": (
            "Select the best implementation approach using MaxDiff:\n"
            "1. GENERATE approaches: list 4-6 meaningfully different ways to implement this. Not minor variations — genuinely different designs.\n"
            "2. APPLY MaxDiff: which approach is BEST given constraints (performance, maintainability, testability, complexity)? Which is WORST?\n"
            "3. RANK all approaches: 1 (best) to N (worst). No ties. Justify each position.\n"
            "4. IDENTIFY the discriminating factor: what single criterion separates top from bottom?\n"
            "5. STATE the chosen approach and the irreversible decisions it makes.\n"
            "Do not default to the familiar approach. Consider all options before ranking."
        ),
    },
    # COD-02 (provided)
    {
        "slug": "codebase-comparison",
        "name": "Codebase Comparison",
        "family": "evaluative",
        "tier": "built-in",
        "description": "Choose between implementation approaches by grounding the comparison in the actual codebase: existing patterns, consumers, and technical debt.",
        "activation_signals": [
            "codebase patterns",
            "existing code",
            "how does existing code do",
            "fit with codebase",
            "consistent with patterns",
            "what does the codebase use",
        ],
        "archetype_affinity": {"executor": 0.9, "analyst": 0.7},
        "mode_affinity": {"deliberative": 0.9, "procedural": 0.8},
        "composability": {"complements": ["approach-maxdiff", "integration-validation"], "conflicts": []},
        "system_prompt": (
            "Choose implementation approach by comparing against the actual codebase:\n"
            "1. AUDIT existing patterns: what conventions, abstractions, and patterns does the codebase already use for similar problems?\n"
            "2. COMPARE options against patterns: which approach fits naturally? Which requires new conventions?\n"
            "3. ASSESS consumer impact: what calls, imports, or interfaces would each approach change? Who is affected?\n"
            "4. WEIGH technical debt: does the 'clean' approach introduce new debt, or does it pay down existing debt?\n"
            "5. FORCE A CHOICE: given the actual codebase state (not the ideal), which approach wins?\n"
            "Output: pattern_audit, consumer_impact, chosen_approach_given_codebase"
        ),
    },
    # COD-03 (provided)
    {
        "slug": "integration-validation",
        "name": "Integration Validation",
        "family": "evaluative",
        "tier": "built-in",
        "description": "Validate that a new implementation composes correctly with existing system boundaries, interfaces, and contracts.",
        "activation_signals": [
            "integration",
            "compose with existing",
            "interface compatibility",
            "contract",
            "boundaries",
            "will this break",
            "API surface",
        ],
        "archetype_affinity": {"executor": 0.9, "analyst": 0.8},
        "mode_affinity": {"deliberative": 0.9, "procedural": 0.8},
        "composability": {"complements": ["codebase-comparison", "holistic-validation"], "conflicts": []},
        "system_prompt": (
            "Validate integration with existing system boundaries:\n"
            "1. MAP the integration points: what existing interfaces, contracts, or boundaries does this touch?\n"
            "2. CHECK interface compatibility: does the new implementation satisfy each interface's contract exactly?\n"
            "3. VERIFY data shape: at each boundary, are the data types, shapes, and nullability consistent?\n"
            "4. TEST the seams: where is this most likely to fail at runtime? What assumption is most dangerous?\n"
            "5. ASSESS composability: can this be combined with other components without unexpected coupling?\n"
            "Output: integration_map (boundary, contract, compatible yes/no, risk), composability_verdict"
        ),
    },
    # COD-04 (provided)
    {
        "slug": "complexity-budget",
        "name": "Complexity Budget",
        "family": "evaluative",
        "tier": "built-in",
        "description": "Allocate complexity budget across implementation components, distinguishing essential complexity that must be handled carefully from accidental complexity to eliminate.",
        "activation_signals": [
            "complexity",
            "too complex",
            "simplify",
            "over-engineered",
            "accidental complexity",
            "necessary complexity",
            "budget complexity",
        ],
        "archetype_affinity": {"executor": 0.9, "analyst": 0.8, "advisor": 0.6},
        "mode_affinity": {"deliberative": 0.9, "reflective": 0.8},
        "composability": {"complements": ["approach-maxdiff", "allocation"], "conflicts": []},
        "system_prompt": (
            "Allocate complexity budget across implementation components:\n"
            "1. CLASSIFY complexity: essential (inherent to the problem domain) vs. accidental (created by our approach).\n"
            "2. ENUMERATE complex components: list each part that carries cognitive load.\n"
            "3. ALLOCATE 100 budget points: how much complexity budget does each component deserve?\n"
            "4. IDENTIFY waste: which components consume complexity budget without proportional value?\n"
            "5. ELIMINATE accidental complexity: for each waste item, what simpler alternative exists?\n"
            "Output: complexity_map (component, type, points, waste yes/no), elimination_candidates, simplified_design"
        ),
    },
    # ═══════════════════════════════════════════════════════════════
    # STRATEGIC (5)
    # ═══════════════════════════════════════════════════════════════
    # STR-01
    {
        "slug": "problem-space-modeling",
        "name": "Problem Space Modeling",
        "family": "diagnostic",
        "tier": "built-in",
        "description": "Frame the actual decision to be made by distinguishing real constraints from assumed constraints and identifying the true decision variables.",
        "activation_signals": [
            "what's the real problem",
            "actual decision",
            "real constraints",
            "what are we actually deciding",
            "frame the problem",
            "define the problem",
        ],
        "archetype_affinity": {"advisor": 0.9, "analyst": 0.8, "researcher": 0.7},
        "mode_affinity": {"deliberative": 0.9, "exploratory": 0.8},
        "composability": {"complements": ["leverage-analysis", "strategy-pairwise"], "conflicts": []},
        "system_prompt": (
            "Model the problem space before attempting any solution:\n"
            "1. STATE the actual decision: what is the one thing that must be chosen? Collapse compound decisions into the atomic unit.\n"
            "2. SEPARATE constraints: list everything labeled as a constraint. For each, classify: real (violating causes failure) vs. assumed (self-imposed or inherited).\n"
            "3. CHALLENGE assumed constraints: what happens if you remove each one? Which assumptions are actually negotiable?\n"
            "4. IDENTIFY the real decision variables: given only the real constraints, what are the actual degrees of freedom?\n"
            "5. DEFINE success: what does a good outcome look like? How will you know the decision was correct in 6 months?\n"
            "Output: decision_statement, constraint_classification, real_variables, success_definition"
        ),
    },
    # STR-02
    {
        "slug": "leverage-analysis",
        "name": "Leverage Analysis",
        "family": "evaluative",
        "tier": "built-in",
        "description": "Identify which efforts produce disproportionate returns by finding high-leverage points in the system where small inputs yield large outputs.",
        "activation_signals": [
            "highest leverage",
            "80/20",
            "biggest impact",
            "where to focus",
            "disproportionate return",
            "most effective",
            "highest ROI",
        ],
        "archetype_affinity": {"advisor": 0.9, "analyst": 0.8},
        "mode_affinity": {"deliberative": 0.9, "exploratory": 0.7},
        "composability": {"complements": ["problem-space-modeling", "bottleneck-analysis"], "conflicts": []},
        "system_prompt": (
            "Identify highest-leverage intervention points:\n"
            "1. MAP the system: what are the key components, flows, and feedback loops?\n"
            "2. FIND leverage points: where does a small input produce a disproportionately large output? Look at bottlenecks, feedback loops, and choke points.\n"
            "3. RANK by leverage ratio: for each intervention, estimate output/input. What's the ratio?\n"
            "4. IDENTIFY the 20%: which 20% of efforts would produce 80% of results? List no more than 3.\n"
            "5. BEWARE anti-leverage: which efforts look impactful but are actually theater? Name them.\n"
            "Output: leverage_map (intervention, estimated_ratio, confidence), top_3_leverage_points, anti_leverage_list"
        ),
    },
    # STR-03
    {
        "slug": "strategy-pairwise",
        "name": "Strategy Pairwise",
        "family": "evaluative",
        "tier": "built-in",
        "description": "Compare strategic paths head-to-head given stage, buyer, and constraints to force a choice between meaningfully different directions.",
        "activation_signals": [
            "which path",
            "strategic options",
            "direction A vs B",
            "strategy comparison",
            "which bet",
            "strategic choice",
            "which direction",
        ],
        "archetype_affinity": {"advisor": 0.9, "analyst": 0.8},
        "mode_affinity": {"deliberative": 0.9, "reflective": 0.8},
        "composability": {"complements": ["problem-space-modeling", "optionality-assessment"], "conflicts": []},
        "system_prompt": (
            "Compare strategic paths head-to-head:\n"
            "1. STATE both paths clearly: what does Path A look like in 12 months? Path B?\n"
            "2. DEFINE the comparison context: current stage, primary buyer/user, binding constraints, risk tolerance.\n"
            "3. COMPARE on strategic dimensions: speed to value, defensibility, reversibility, resource requirements, optionality preserved.\n"
            "4. IDENTIFY the decisive factor: given your actual context, which single dimension dominates the comparison?\n"
            "5. FORCE A CHOICE: given stage, buyer, and constraints, which path wins? State it directly.\n"
            "Do not hedge with 'it depends.' Name the context and make the call."
        ),
    },
    # STR-04
    {
        "slug": "optionality-assessment",
        "name": "Optionality Assessment",
        "family": "evaluative",
        "tier": "built-in",
        "description": "Assess which decisions preserve future options versus lock you in, to avoid irreversible commitments before you have the information to make them wisely.",
        "activation_signals": [
            "reversible",
            "lock in",
            "optionality",
            "future flexibility",
            "can we undo",
            "commitment",
            "preserve options",
        ],
        "archetype_affinity": {"advisor": 0.9, "analyst": 0.8},
        "mode_affinity": {"deliberative": 0.9, "reflective": 0.8},
        "composability": {"complements": ["strategy-pairwise", "reversibility-assessment"], "conflicts": []},
        "system_prompt": (
            "Assess optionality in the decision set:\n"
            "1. LIST all decisions to be made: both explicit decisions and decisions implied by choices already made.\n"
            "2. CLASSIFY each: one-way door (irreversible, high cost to undo) vs. two-way door (reversible, low cost to undo).\n"
            "3. SEQUENCE properly: two-way door decisions can be made now with imperfect information. One-way door decisions deserve more deliberation.\n"
            "4. IDENTIFY option value: which decisions, if deferred, would be made with better information in 30/90 days?\n"
            "5. ALLOCATE deliberation: assign effort proportional to irreversibility, not perceived importance.\n"
            "Output: decision_classification (decision, door_type, deferrable, deliberation_effort), sequencing_recommendation"
        ),
    },
    # STR-05
    {
        "slug": "negative-space-reasoning",
        "name": "Negative Space Reasoning",
        "family": "adversarial",
        "tier": "built-in",
        "description": "Reason from what is absent: what should we NOT do, what is conspicuously missing from the plan, and what decisions have been implicitly made by not deciding.",
        "activation_signals": [
            "what we shouldn't do",
            "what's not there",
            "missing from plan",
            "conspicuously absent",
            "anti-portfolio",
            "what to avoid",
            "not doing",
        ],
        "archetype_affinity": {"advisor": 0.9, "analyst": 0.8, "researcher": 0.7},
        "mode_affinity": {"deliberative": 0.9, "reflective": 0.8},
        "composability": {"complements": ["problem-space-modeling", "gap-analysis"], "conflicts": []},
        "system_prompt": (
            "Reason from what is absent:\n"
            "1. AUDIT the anti-portfolio: what options are conspicuously NOT in the plan? For each, is this a deliberate choice or an oversight?\n"
            "2. IDENTIFY implicit decisions: what has been decided by not deciding? Inaction is a choice — name it explicitly.\n"
            "3. MAP the NOT-to-do list: what should explicitly never be done here? Why?\n"
            "4. FIND the missing voice: whose perspective or concern is entirely absent from the current plan?\n"
            "5. ASK the uncomfortable question: what is the plan afraid to confront directly?\n"
            "Output: anti_portfolio, implicit_decisions, not_to_do_list, missing_voice, uncomfortable_question"
        ),
    },
    # ═══════════════════════════════════════════════════════════════
    # COMMUNICATION (5)
    # ═══════════════════════════════════════════════════════════════
    # COM-01
    {
        "slug": "audience-modeling",
        "name": "Audience Modeling",
        "family": "diagnostic",
        "tier": "built-in",
        "description": "Model the target audience for a communication: who reads it, what they care about, what they already know, and what would cause them to dismiss it.",
        "activation_signals": [
            "who is the audience",
            "target reader",
            "who reads this",
            "audience profile",
            "what do they care about",
            "reader context",
        ],
        "archetype_affinity": {"creator": 0.9, "advisor": 0.8, "analyst": 0.6},
        "mode_affinity": {"deliberative": 0.8, "exploratory": 0.7},
        "composability": {"complements": ["context-inference", "message-maxdiff", "channel-matching"], "conflicts": []},
        "system_prompt": (
            "Model the target audience before crafting communication:\n"
            "1. IDENTIFY the reader: role, seniority, technical depth, domain expertise, time available.\n"
            "2. MAP prior knowledge: what do they already know that can be assumed? What must be explained?\n"
            "3. SURFACE their agenda: what are they trying to accomplish? What problem are they solving when they read this?\n"
            "4. IDENTIFY dismissal triggers: what would cause them to stop reading or discount the message? (too long, too jargony, not credible, off-topic)\n"
            "5. DEFINE their desired outcome: after reading, what should they think, feel, or do?\n"
            "Output: audience_profile (role, knowledge_level, agenda, dismissal_triggers), desired_outcome"
        ),
    },
    # COM-02
    {
        "slug": "message-maxdiff",
        "name": "Message MaxDiff",
        "family": "evaluative",
        "tier": "built-in",
        "description": "Use MaxDiff to identify which messages matter most to this specific audience, forcing prioritization over the instinct to say everything.",
        "activation_signals": [
            "most important message",
            "what to lead with",
            "key message",
            "what matters most to say",
            "message priority",
            "single most important point",
        ],
        "archetype_affinity": {"creator": 0.9, "advisor": 0.8},
        "mode_affinity": {"deliberative": 0.9, "procedural": 0.7},
        "composability": {"complements": ["audience-modeling", "framing-selection"], "conflicts": []},
        "system_prompt": (
            "Identify the most critical messages using MaxDiff:\n"
            "1. LIST all messages you want to convey: everything that could go into this communication.\n"
            "2. APPLY MaxDiff: which message is MOST important for this specific audience at this moment? Which is LEAST?\n"
            "3. RANK all messages 1-N. No ties.\n"
            "4. APPLY the one-message test: if the audience remembers only one thing, what must it be?\n"
            "5. CULL ruthlessly: messages below the top 3 are likely noise for this communication. Confirm or cut each.\n"
            "Output: ranked_messages, one_message_test_winner, culled_messages, message_hierarchy"
        ),
    },
    # COM-03
    {
        "slug": "framing-selection",
        "name": "Framing Selection",
        "family": "evaluative",
        "tier": "built-in",
        "description": "Select the narrative frame that best moves the intended decision by comparing how different frames land with the target audience.",
        "activation_signals": [
            "how to frame",
            "narrative frame",
            "angle to take",
            "how to present",
            "which framing",
            "story angle",
            "how to position",
        ],
        "archetype_affinity": {"creator": 0.9, "advisor": 0.8, "analyst": 0.6},
        "mode_affinity": {"deliberative": 0.9, "exploratory": 0.7},
        "composability": {"complements": ["audience-modeling", "message-maxdiff"], "conflicts": []},
        "system_prompt": (
            "Select the optimal narrative frame for this communication:\n"
            "1. GENERATE 3 distinct frames: different ways to position the same core content (e.g., problem/solution, opportunity/risk, before/after, data/story).\n"
            "2. TEST each frame against the audience: which frame matches their worldview and agenda? Which creates cognitive friction?\n"
            "3. EVALUATE the decision impact: which frame is most likely to produce the desired action or belief change?\n"
            "4. CHECK for framing risks: which frame might backfire with secondary audiences or in future contexts?\n"
            "5. CHOOSE the frame: state it explicitly and describe how it shapes the opening, structure, and close.\n"
            "Output: frame_options (frame, audience_fit, decision_impact, risks), chosen_frame, structural_implications"
        ),
    },
    # COM-04
    {
        "slug": "channel-matching",
        "name": "Channel Matching",
        "family": "evaluative",
        "tier": "built-in",
        "description": "Validate that the communication format, tool, and granularity match the audience, message, and desired action.",
        "activation_signals": [
            "right format",
            "which channel",
            "email vs doc vs meeting",
            "format choice",
            "medium",
            "how to deliver",
            "right tool for",
        ],
        "archetype_affinity": {"creator": 0.8, "advisor": 0.9},
        "mode_affinity": {"deliberative": 0.8, "procedural": 0.9},
        "composability": {"complements": ["audience-modeling", "granularity-calibration"], "conflicts": []},
        "system_prompt": (
            "Validate channel and format selection:\n"
            "1. DEFINE the communication's purpose: inform, request action, seek alignment, build trust, create record?\n"
            "2. ASSESS channel fit: for the stated purpose and audience, does the chosen channel (email, doc, meeting, chat, PR comment) fit?\n"
            "3. CHECK format fit: is the format (length, structure, visual, interactive) appropriate for how this audience consumes information?\n"
            "4. EVALUATE granularity: is the level of detail calibrated to the audience's need and time? (1-page ≠ 20-page)\n"
            "5. TEST for channel failure modes: what goes wrong if the channel is wrong? (ignored, misunderstood, no paper trail, no dialogue)\n"
            "Output: channel_fit_assessment (purpose, channel, format, granularity, fit_score 1-5), failure_modes, recommendation"
        ),
    },
    # COM-05
    {
        "slug": "granularity-calibration",
        "name": "Granularity Calibration",
        "family": "evaluative",
        "tier": "built-in",
        "description": "Calibrate the level of detail to the audience: CEOs get the outcome, engineers get the full context, operators get the steps.",
        "activation_signals": [
            "how much detail",
            "level of detail",
            "too long",
            "too brief",
            "appropriate depth",
            "right length",
            "executive summary vs detail",
        ],
        "archetype_affinity": {"creator": 0.8, "advisor": 0.9},
        "mode_affinity": {"deliberative": 0.8, "procedural": 0.9},
        "composability": {"complements": ["audience-modeling", "channel-matching"], "conflicts": []},
        "system_prompt": (
            "Calibrate granularity to the audience:\n"
            "1. IDENTIFY the audience tier: decision-maker (needs outcome + risk), implementer (needs full context + steps), peer (needs reasoning), observer (needs summary).\n"
            "2. MAP required detail by tier: what does each tier need to take the desired action?\n"
            "3. AUDIT current granularity: where is the current content too detailed? Too thin?\n"
            "4. APPLY the rule: outcome (1-2 lines), rationale (1 paragraph), full context (structured detail). Build the document to serve all tiers.\n"
            "5. TEST the summary: can a decision-maker read the first 3 sentences and know what to do?\n"
            "Output: granularity_audit (section, current_level, required_level, adjustment), summary_test_result"
        ),
    },
    # ═══════════════════════════════════════════════════════════════
    # SYSTEMS (5)
    # ═══════════════════════════════════════════════════════════════
    # SYS-01
    {
        "slug": "bottleneck-analysis",
        "name": "Bottleneck Analysis",
        "family": "evaluative",
        "tier": "built-in",
        "description": "Identify the constraint that limits system throughput and confirm that interventions target the actual bottleneck rather than non-limiting components.",
        "activation_signals": [
            "bottleneck",
            "constraint",
            "throughput",
            "limiting factor",
            "what's slowing",
            "slowest part",
            "theory of constraints",
        ],
        "archetype_affinity": {"analyst": 0.9, "executor": 0.8, "advisor": 0.7},
        "mode_affinity": {"deliberative": 0.9, "exploratory": 0.7},
        "composability": {"complements": ["leverage-analysis", "scaling-projection"], "conflicts": []},
        "system_prompt": (
            "Identify the system bottleneck using Theory of Constraints logic:\n"
            "1. MAP the flow: what are the sequential steps or components through which work moves?\n"
            "2. MEASURE each stage: what's the capacity or throughput of each component? Where does work pile up?\n"
            "3. IDENTIFY the constraint: which single component limits total system throughput? There is exactly one primary constraint.\n"
            "4. VERIFY the bottleneck: if you improved every other component but not this one, would system output improve significantly? If not, recheck.\n"
            "5. EXPLOIT before elevating: can you get more from the current constraint before adding capacity?\n"
            "Output: flow_map, bottleneck_component, verification, exploitation_options"
        ),
    },
    # SYS-02
    {
        "slug": "architecture-pairwise",
        "name": "Architecture Pairwise",
        "family": "evaluative",
        "tier": "built-in",
        "description": "Compare architectural options by stress-testing them at 10x scale, at failure, and at migration to surface the differences that don't appear at current load.",
        "activation_signals": [
            "architecture options",
            "design comparison",
            "option A vs B architecture",
            "at scale",
            "at failure",
            "architectural trade-off",
        ],
        "archetype_affinity": {"executor": 0.9, "analyst": 0.8, "advisor": 0.7},
        "mode_affinity": {"deliberative": 0.9, "reflective": 0.8},
        "composability": {"complements": ["codebase-comparison", "scaling-projection"], "conflicts": []},
        "system_prompt": (
            "Compare architectural options under stress:\n"
            "1. STATE both architectures precisely: not vague names — what are the actual components and interfaces?\n"
            "2. TEST at 10x scale: how does each perform when load, data, or team size is 10x current? Where does each break?\n"
            "3. TEST at failure: when a component fails, how does each architecture degrade? Graceful degradation vs. cascading failure?\n"
            "4. TEST at migration: 18 months from now, how easy is it to migrate away from or evolve each option?\n"
            "5. FORCE THE CHOICE: given your actual scale today and expected scale in 12 months, which architecture is better? State it.\n"
            "Output: stress_test_results (architecture, 10x_behavior, failure_behavior, migration_cost), verdict"
        ),
    },
    # SYS-03
    {
        "slug": "scaling-projection",
        "name": "Scaling Projection",
        "family": "evaluative",
        "tier": "built-in",
        "description": "Project system behavior at 1x, 10x, and 100x current scale to identify where design assumptions break and plan interventions before they become emergencies.",
        "activation_signals": [
            "scale",
            "at 10x",
            "growth",
            "as this grows",
            "scaling behavior",
            "breaks at scale",
            "load projection",
        ],
        "archetype_affinity": {"executor": 0.9, "analyst": 0.8, "advisor": 0.6},
        "mode_affinity": {"deliberative": 0.9, "exploratory": 0.7},
        "composability": {"complements": ["bottleneck-analysis", "architecture-pairwise"], "conflicts": []},
        "system_prompt": (
            "Project system behavior across scale levels:\n"
            "1. DEFINE scale dimensions: what grows? (users, data volume, request rate, team size, geographic reach)\n"
            "2. ASSESS 1x (current): how does the system behave today? What's already under strain?\n"
            "3. PROJECT 10x: which components degrade first? At what point does the current design break?\n"
            "4. PROJECT 100x: what fundamental assumptions of the current design fail at this level?\n"
            "5. IDENTIFY break points: at what specific scale does each component require architectural change?\n"
            "6. SEQUENCE interventions: which scale challenges must be addressed now vs. when growth actually arrives?\n"
            "Output: scale_projection_matrix (component, 1x_status, 10x_break_point, 100x_break_point), intervention_sequence"
        ),
    },
    # SYS-04
    {
        "slug": "failure-budget",
        "name": "Failure Budget",
        "family": "evaluative",
        "tier": "built-in",
        "description": "Allocate reliability investment across system components by deciding which deserve redundancy and which should remain simple.",
        "activation_signals": [
            "reliability",
            "redundancy",
            "failure budget",
            "SLA",
            "what needs HA",
            "where to invest reliability",
            "resilience trade-offs",
        ],
        "archetype_affinity": {"executor": 0.9, "analyst": 0.8, "advisor": 0.6},
        "mode_affinity": {"deliberative": 0.9, "procedural": 0.8},
        "composability": {"complements": ["failure-cascade", "scaling-projection"], "conflicts": []},
        "system_prompt": (
            "Allocate reliability investment as a failure budget:\n"
            "1. ENUMERATE system components: list everything that can fail.\n"
            "2. CLASSIFY by impact: what happens to the user/system if each component fails? (data loss, degraded, unavailable, imperceptible)\n"
            "3. ALLOCATE the reliability budget: 100 points across components, weighted by impact of failure.\n"
            "4. ASSIGN design posture: high-allocation components get redundancy + monitoring. Low-allocation components get simplicity.\n"
            "5. IDENTIFY the mismatch: which components have high complexity but low failure impact? Simplify those first.\n"
            "Output: failure_budget_table (component, failure_impact, budget_points, design_posture), simplification_candidates"
        ),
    },
    # SYS-05
    {
        "slug": "failure-cascade",
        "name": "Failure Cascade",
        "family": "adversarial",
        "tier": "built-in",
        "description": "Map the blast radius of a failure by tracing cascading effects through the system to find unexpected failure propagation paths.",
        "activation_signals": [
            "blast radius",
            "what cascades",
            "failure propagation",
            "if X breaks",
            "cascade failure",
            "ripple effects",
            "dependency failure",
        ],
        "archetype_affinity": {"executor": 0.9, "analyst": 0.8, "advisor": 0.7},
        "mode_affinity": {"deliberative": 0.9, "reflective": 0.8},
        "composability": {"complements": ["failure-budget", "bottleneck-analysis"], "conflicts": []},
        "system_prompt": (
            "Map failure cascades through the system:\n"
            "1. STATE the initial failure: which component fails, and how? (timeout, crash, corruption, unavailability)\n"
            "2. TRACE first-order effects: what does this component's failure immediately affect?\n"
            "3. TRACE second-order effects: what do those affected components affect when they fail or degrade?\n"
            "4. FIND unexpected paths: are there non-obvious dependencies that create surprise blast radius?\n"
            "5. IDENTIFY isolation points: where could a circuit breaker, bulkhead, or timeout limit cascade propagation?\n"
            "6. ASSESS the worst case: if everything goes wrong simultaneously, what is the maximum blast radius?\n"
            "Output: cascade_map (failure, first_order, second_order, unexpected_paths), isolation_points, worst_case_scenario"
        ),
    },
    # ═══════════════════════════════════════════════════════════════
    # DATA (4)
    # ═══════════════════════════════════════════════════════════════
    # DAT-01
    {
        "slug": "anomaly-framing",
        "name": "Anomaly Framing",
        "family": "diagnostic",
        "tier": "built-in",
        "description": "Frame data investigation by identifying what is unusual, what questions haven't been asked, and what the data might be hiding.",
        "activation_signals": [
            "anomaly",
            "unusual",
            "weird data",
            "what's strange",
            "outliers",
            "unexpected pattern",
            "what haven't we asked",
        ],
        "archetype_affinity": {"analyst": 0.9, "researcher": 0.8},
        "mode_affinity": {"exploratory": 0.9, "deliberative": 0.8},
        "composability": {"complements": ["metric-design", "comparison-baseline"], "conflicts": []},
        "system_prompt": (
            "Frame the data investigation by surfacing what is unusual:\n"
            "1. ESTABLISH the expected pattern: what should this data look like under normal conditions?\n"
            "2. IDENTIFY deviations: what in the actual data doesn't match the expected pattern?\n"
            "3. CLASSIFY anomalies: statistical outliers, structural anomalies (wrong shape), temporal anomalies (wrong timing), missing data.\n"
            "4. GENERATE unasked questions: what question about this data has NOT been asked that might be important?\n"
            "5. HYPOTHESIZE causes: for each anomaly, list the top 3 plausible explanations (data error, genuine signal, measurement artifact).\n"
            "Output: expected_pattern, anomaly_list (type, description, top_hypotheses), unasked_questions"
        ),
    },
    # DAT-02
    {
        "slug": "metric-design",
        "name": "Metric Design",
        "family": "evaluative",
        "tier": "built-in",
        "description": "Design metrics that actually answer the question being asked, not metrics that are easy to measure but proxy for something different.",
        "activation_signals": [
            "what to measure",
            "metrics",
            "KPI",
            "how to track",
            "success metrics",
            "measuring",
            "indicator design",
        ],
        "archetype_affinity": {"analyst": 0.9, "advisor": 0.8, "researcher": 0.7},
        "mode_affinity": {"deliberative": 0.9, "procedural": 0.8},
        "composability": {"complements": ["anomaly-framing", "comparison-baseline"], "conflicts": []},
        "system_prompt": (
            "Design metrics that actually answer the question:\n"
            "1. STATE the question: what are you actually trying to know? Be precise.\n"
            "2. AUDIT proposed metrics: for each metric, does it directly measure what you need to know, or is it a proxy?\n"
            "3. IDENTIFY proxy risks: for each proxy metric, what scenario would make it move in the wrong direction while the actual thing you care about is unchanged or worsening?\n"
            "4. SELECT leading vs. lagging: which metrics tell you where you are (lagging) vs. where you're heading (leading)?\n"
            "5. DESIGN for gaming resistance: how could a rational person make this metric look good while degrading actual outcomes?\n"
            "Output: metric_audit (metric, measures_what, proxy_risk), leading_indicators, lagging_indicators, gaming_risks"
        ),
    },
    # DAT-03
    {
        "slug": "comparison-baseline",
        "name": "Comparison Baseline",
        "family": "evaluative",
        "tier": "built-in",
        "description": "Validate that comparisons are meaningful by ensuring the baseline is appropriate, the sample is sufficient, and the comparison is fair.",
        "activation_signals": [
            "compared to what",
            "baseline",
            "sample size",
            "is this sufficient",
            "comparison validity",
            "control group",
            "reference point",
        ],
        "archetype_affinity": {"analyst": 0.9, "researcher": 0.8, "advisor": 0.6},
        "mode_affinity": {"deliberative": 0.9, "procedural": 0.8},
        "composability": {"complements": ["statistical-confidence", "evidence-hierarchy"], "conflicts": []},
        "system_prompt": (
            "Validate the comparison baseline:\n"
            "1. IDENTIFY the implicit baseline: what is the observed data being compared against?\n"
            "2. ASSESS baseline appropriateness: is this the right reference point? What else could serve as baseline?\n"
            "3. CHECK sample sufficiency: is the sample size large enough to detect the effect you care about? What's the minimum detectable effect?\n"
            "4. VERIFY comparability: are the groups being compared actually comparable? What confounds exist?\n"
            "5. TEST for selection bias: how was the sample selected? What systematic exclusions might bias results?\n"
            "Output: baseline_assessment (current_baseline, appropriate yes/no, alternatives), sample_sufficiency, confound_list, selection_bias_risks"
        ),
    },
    # DAT-04
    {
        "slug": "statistical-confidence",
        "name": "Statistical Confidence",
        "family": "evaluative",
        "tier": "built-in",
        "description": "Assess the confidence level and uncertainty range of data-based claims, preventing over-certainty from noisy signals.",
        "activation_signals": [
            "how confident",
            "uncertainty",
            "confidence interval",
            "error bars",
            "statistical significance",
            "reliable finding",
            "noise vs signal",
        ],
        "archetype_affinity": {"analyst": 0.9, "researcher": 0.8},
        "mode_affinity": {"deliberative": 0.9, "reflective": 0.8},
        "composability": {"complements": ["comparison-baseline", "confidence-allocation"], "conflicts": []},
        "system_prompt": (
            "Assess statistical confidence and uncertainty:\n"
            "1. STATE the claim: what is being asserted based on this data?\n"
            "2. QUANTIFY uncertainty: what is the range within which the true value likely falls? State a confidence interval.\n"
            "3. IDENTIFY noise sources: what factors could cause this measurement to vary that have nothing to do with the underlying effect?\n"
            "4. CHECK for significance vs. magnitude: is the effect statistically significant but practically meaningless?\n"
            "5. CALIBRATE the claim: rewrite the claim in language that accurately reflects the uncertainty. Avoid 'proves' and 'shows.'\n"
            "Output: original_claim, confidence_interval, noise_sources, effect_magnitude, calibrated_claim"
        ),
    },
    # ═══════════════════════════════════════════════════════════════
    # RETRIEVAL (6)
    # ═══════════════════════════════════════════════════════════════
    # RET-01
    {
        "slug": "relevance-scoping",
        "name": "Relevance Scoping",
        "family": "diagnostic",
        "tier": "built-in",
        "description": "Define exactly what information is needed for the current task to prevent context bloat from over-retrieval.",
        "activation_signals": [
            "what context is needed",
            "relevant information",
            "scoping retrieval",
            "what to load",
            "context needed",
            "relevant files",
        ],
        "archetype_affinity": {"executor": 0.8, "researcher": 0.9, "analyst": 0.7},
        "mode_affinity": {"procedural": 0.9, "deliberative": 0.8},
        "composability": {"complements": ["source-ranking", "context-budget"], "conflicts": []},
        "system_prompt": (
            "Define precisely what information is needed for this task:\n"
            "1. STATE the task precisely: what decision or action must be taken?\n"
            "2. DERIVE information requirements: what specific facts, patterns, or context are necessary to complete this task well?\n"
            "3. SEPARATE necessary from useful: what information would be helpful but is not required? Mark it as optional.\n"
            "4. IDENTIFY sufficiency criteria: when do I have enough context to proceed? What would 'enough' look like?\n"
            "5. FLAG scope creep risks: what tempting but irrelevant information might be loaded that would waste context?\n"
            "Output: required_information (item, why_needed), optional_information, sufficiency_criteria, scope_creep_risks"
        ),
    },
    # RET-02
    {
        "slug": "source-ranking",
        "name": "Source Ranking",
        "family": "evaluative",
        "tier": "built-in",
        "description": "Rank information sources by authority for this task: internal docs over general knowledge, recent over stale, primary over derived.",
        "activation_signals": [
            "which sources",
            "source priority",
            "where to look first",
            "most authoritative",
            "best source",
            "ranking sources",
        ],
        "archetype_affinity": {"researcher": 0.9, "analyst": 0.8, "executor": 0.7},
        "mode_affinity": {"deliberative": 0.9, "procedural": 0.8},
        "composability": {"complements": ["relevance-scoping", "context-selection"], "conflicts": []},
        "system_prompt": (
            "Rank information sources by authority for this specific task:\n"
            "1. ENUMERATE available sources: code, internal docs, commit history, issue tracker, general knowledge, external docs.\n"
            "2. APPLY authority hierarchy: for this task, rank sources from most to least authoritative. Internal primary sources beat external general knowledge.\n"
            "3. APPLY recency filter: which sources might be stale? Flag anything older than 90 days for validation.\n"
            "4. ASSESS coverage: does the top-ranked source actually contain the needed information, or does it only appear to?\n"
            "5. ORDER retrieval: specify the sequence in which sources should be consulted.\n"
            "Output: source_ranking (source, authority_tier, recency_risk, coverage_confidence), retrieval_sequence"
        ),
    },
    # RET-03
    {
        "slug": "context-selection",
        "name": "Context Selection",
        "family": "evaluative",
        "tier": "built-in",
        "description": "Choose the specific files, sections, or records to include in context rather than loading entire modules.",
        "activation_signals": [
            "which files",
            "what to include",
            "context selection",
            "specific files needed",
            "minimal context",
            "targeted retrieval",
        ],
        "archetype_affinity": {"executor": 0.9, "researcher": 0.7},
        "mode_affinity": {"procedural": 0.9, "deliberative": 0.7},
        "composability": {"complements": ["source-ranking", "context-budget"], "conflicts": []},
        "system_prompt": (
            "Select specific context to include rather than loading everything:\n"
            "1. DEFINE the context requirement: what specific pieces of information are needed?\n"
            "2. IDENTIFY the minimal set: what are the exact files, functions, or records needed? Not the module — the specific item.\n"
            "3. REJECT the pull toward completeness: resist loading surrounding context 'just in case.' If it's not needed for the decision, don't load it.\n"
            "4. VALIDATE selection: does this minimal set actually contain everything required? Test each item against the task.\n"
            "5. DOCUMENT reasoning: why these specific items and not others? This prevents re-loading the same question.\n"
            "Output: selected_context (item, why_selected), rejected_items (item, why_excluded), completeness_validation"
        ),
    },
    # RET-04
    {
        "slug": "gap-detection",
        "name": "Gap Detection",
        "family": "evaluative",
        "tier": "built-in",
        "description": "Determine whether loaded context is sufficient to proceed or whether critical information is still missing before acting.",
        "activation_signals": [
            "enough context",
            "missing information",
            "can I proceed",
            "context sufficient",
            "what's still needed",
            "information gap",
        ],
        "archetype_affinity": {"executor": 0.8, "researcher": 0.9, "analyst": 0.7},
        "mode_affinity": {"procedural": 0.9, "deliberative": 0.8},
        "composability": {"complements": ["relevance-scoping", "freshness-assessment"], "conflicts": []},
        "system_prompt": (
            "Assess whether current context is sufficient to proceed:\n"
            "1. REVIEW loaded context: what information is currently available?\n"
            "2. COMPARE against requirements: for each required information item, is it present in context?\n"
            "3. CLASSIFY gaps: blocking (cannot proceed without it) vs. acceptable (can make reasonable assumption).\n"
            "4. ASSESS blocking gaps: what would it cost to retrieve the missing information? Is it retrievable?\n"
            "5. MAKE THE CALL: proceed with current context / retrieve specific gaps / escalate because gap cannot be filled.\n"
            "Output: context_inventory, gap_list (item, gap_type, retrievable), proceed_decision"
        ),
    },
    # RET-05
    {
        "slug": "context-budget",
        "name": "Context Budget",
        "family": "evaluative",
        "tier": "built-in",
        "description": "Allocate context budget across categories (code, intelligence, history, meta) to ensure balance and prevent any single source from crowding out others.",
        "activation_signals": [
            "context budget",
            "how much context",
            "token budget",
            "context allocation",
            "loading too much",
            "context limit",
        ],
        "archetype_affinity": {"executor": 0.8, "analyst": 0.7},
        "mode_affinity": {"procedural": 0.9, "deliberative": 0.7},
        "composability": {"complements": ["context-selection", "relevance-scoping"], "conflicts": []},
        "system_prompt": (
            "Allocate context budget explicitly:\n"
            "1. STATE the total context budget available (tokens, items, or relative size).\n"
            "2. ENUMERATE context categories: code, domain intelligence, history/decisions, task meta, system prompts.\n"
            "3. ALLOCATE by task type: code-heavy tasks (40% code, 30% intel, 20% history, 10% meta); research tasks (20% code, 40% intel, 30% history, 10% meta).\n"
            "4. ADJUST for this specific task: which categories are most important here? Shift budget accordingly.\n"
            "5. ENFORCE the budget: if any category exceeds allocation, what gets cut? Prioritize ruthlessly.\n"
            "Output: context_allocation (category, budget_percent, items_included), overages, cut_list"
        ),
    },
    # RET-06
    {
        "slug": "freshness-assessment",
        "name": "Freshness Assessment",
        "family": "adversarial",
        "tier": "built-in",
        "description": "Critique loaded context for staleness, internal conflicts, and reliability — prevent acting on outdated or contradictory information.",
        "activation_signals": [
            "stale context",
            "outdated",
            "is this current",
            "context conflicts",
            "conflicting information",
            "reliability of context",
        ],
        "archetype_affinity": {"researcher": 0.9, "analyst": 0.8, "executor": 0.7},
        "mode_affinity": {"deliberative": 0.9, "reflective": 0.8},
        "composability": {"complements": ["gap-detection", "source-ranking"], "conflicts": []},
        "system_prompt": (
            "Assess context freshness and reliability:\n"
            "1. DATE each piece of context: when was it last updated? Flag anything older than 30 days in a fast-moving area.\n"
            "2. DETECT conflicts: where do two sources in context contradict each other? List every conflict.\n"
            "3. ASSESS conflict severity: for each conflict, which version is more likely correct? On what basis?\n"
            "4. IDENTIFY stale indicators: what language, references, or patterns suggest this context is outdated?\n"
            "5. VERDICT on reliability: is this context trustworthy enough to act on, or does it need validation before proceeding?\n"
            "Output: freshness_map (source, age, freshness_risk), conflicts (sources, conflict, resolution), reliability_verdict"
        ),
    },
    # ═══════════════════════════════════════════════════════════════
    # PLANNING (5)
    # ═══════════════════════════════════════════════════════════════
    # PLA-01
    {
        "slug": "risk-first-ordering",
        "name": "Risk-First Ordering",
        "family": "evaluative",
        "tier": "built-in",
        "description": "Prioritize tasks that validate risky assumptions early so that failures surface before significant investment is made in directions that don't work.",
        "activation_signals": [
            "risk first",
            "validate early",
            "risky assumption",
            "fail fast",
            "de-risk",
            "order of operations",
            "sequence planning",
        ],
        "archetype_affinity": {"advisor": 0.9, "analyst": 0.8, "executor": 0.7},
        "mode_affinity": {"deliberative": 0.9, "procedural": 0.8},
        "composability": {"complements": ["parallelization-assessment", "reversibility-assessment"], "conflicts": []},
        "system_prompt": (
            "Order tasks by risk to validate assumptions early:\n"
            "1. ENUMERATE all tasks in the plan.\n"
            "2. IDENTIFY risky assumptions: which tasks are premised on unvalidated assumptions? The assumption, not the task, is what's risky.\n"
            "3. ASSESS assumption failure cost: if this assumption is wrong and we find out late, how much work is wasted?\n"
            "4. REORDER by risk: tasks that validate high-cost assumptions should come first, regardless of their apparent 'size' or sequence.\n"
            "5. CREATE gates: define explicit checkpoints where assumption validation must succeed before proceeding.\n"
            "Output: task_list with risk_score, assumption_tests, reordered_plan, gate_conditions"
        ),
    },
    # PLA-02
    {
        "slug": "parallelization-assessment",
        "name": "Parallelization Assessment",
        "family": "evaluative",
        "tier": "built-in",
        "description": "Identify what can run concurrently versus what must be sequential to minimize critical path length.",
        "activation_signals": [
            "parallel",
            "concurrent",
            "what can run at same time",
            "critical path",
            "sequential dependency",
            "dependency ordering",
            "what's blocking",
        ],
        "archetype_affinity": {"executor": 0.9, "advisor": 0.8, "analyst": 0.7},
        "mode_affinity": {"procedural": 0.9, "deliberative": 0.8},
        "composability": {"complements": ["plan-coherence", "effort-distribution"], "conflicts": []},
        "system_prompt": (
            "Assess parallelization opportunities in the plan:\n"
            "1. MAP dependencies: for each task, what must be complete before it can start?\n"
            "2. IDENTIFY true sequential constraints: distinguish 'logically must follow' from 'we usually do it this way.'\n"
            "3. FIND parallel opportunities: which tasks have no mutual dependencies and can run simultaneously?\n"
            "4. CALCULATE critical path: what is the minimum time to completion if all parallel work runs concurrently?\n"
            "5. ASSIGN resources: given the parallel tracks, do you have sufficient agents/capacity to run them? If not, what collapses back to sequential?\n"
            "Output: dependency_graph, parallel_tracks, critical_path (duration, steps), resource_requirements"
        ),
    },
    # PLA-03
    {
        "slug": "plan-coherence",
        "name": "Plan Coherence",
        "family": "evaluative",
        "tier": "built-in",
        "description": "Validate that the steps in a plan actually produce the stated goal, with no missing links, no redundant steps, and no unstated assumptions bridging gaps.",
        "activation_signals": [
            "plan check",
            "does this add up",
            "plan coherence",
            "will this work",
            "missing steps",
            "does the plan achieve the goal",
        ],
        "archetype_affinity": {"advisor": 0.9, "analyst": 0.8, "executor": 0.7},
        "mode_affinity": {"deliberative": 0.9, "reflective": 0.8},
        "composability": {"complements": ["risk-first-ordering", "scope-negotiation"], "conflicts": []},
        "system_prompt": (
            "Validate plan coherence:\n"
            "1. STATE the goal: what should the completed plan produce?\n"
            "2. TRACE the steps: does executing steps 1→N actually produce the stated goal, or does the final step only get you 'close'?\n"
            "3. FIND missing links: where does the plan implicitly assume something happens that isn't in the steps?\n"
            "4. FIND redundant steps: which steps don't contribute to the goal and can be removed?\n"
            "5. TEST the chain: if step 3 fails, does the entire plan fail, or do subsequent steps still produce partial value?\n"
            "Output: goal_statement, step_trace, missing_links (where, what_assumed), redundant_steps, failure_resilience"
        ),
    },
    # PLA-04
    {
        "slug": "effort-distribution",
        "name": "Effort Distribution",
        "family": "evaluative",
        "tier": "built-in",
        "description": "Allocate careful treatment versus quick execution across tasks based on complexity, risk, and reversibility — not based on apparent size.",
        "activation_signals": [
            "effort allocation",
            "how much effort",
            "careful vs quick",
            "where to be thorough",
            "where to move fast",
            "treatment allocation",
        ],
        "archetype_affinity": {"advisor": 0.9, "analyst": 0.8, "executor": 0.7},
        "mode_affinity": {"deliberative": 0.9, "procedural": 0.8},
        "composability": {"complements": ["parallelization-assessment", "risk-first-ordering"], "conflicts": []},
        "system_prompt": (
            "Allocate effort quality across tasks:\n"
            "1. LIST all tasks in the plan.\n"
            "2. CLASSIFY each task: requires careful treatment (irreversible, complex, high-stakes) vs. quick execution (reversible, clear, low-risk).\n"
            "3. ALLOCATE effort quality: careful tasks get full design review, testing, documentation. Quick tasks get 'good enough' treatment.\n"
            "4. IDENTIFY mismatches: where is careful treatment being applied to quick tasks (wasting time)? Where is quick execution being applied to careful tasks (creating risk)?\n"
            "5. REDISTRIBUTE: adjust treatment to match task classification.\n"
            "Output: task_classification (task, type, treatment_assigned, correct_treatment), mismatches, redistribution_plan"
        ),
    },
    # PLA-05
    {
        "slug": "scope-negotiation",
        "name": "Scope Negotiation",
        "family": "adversarial",
        "tier": "built-in",
        "description": "Critique a plan's scope: what can be deferred or cut without losing the core goal, and what scope is being added from habit rather than necessity.",
        "activation_signals": [
            "too big",
            "scope creep",
            "what can we cut",
            "defer",
            "minimum viable",
            "trim scope",
            "what's essential vs nice-to-have",
        ],
        "archetype_affinity": {"advisor": 0.9, "analyst": 0.8},
        "mode_affinity": {"deliberative": 0.9, "reflective": 0.8},
        "composability": {"complements": ["plan-coherence", "effort-distribution"], "conflicts": []},
        "system_prompt": (
            "Negotiate scope down to what's essential:\n"
            "1. STATE the core goal: the single thing this plan must achieve to be considered a success.\n"
            "2. AUDIT each element: does this directly contribute to the core goal, or is it supporting / adjacent / nice-to-have?\n"
            "3. IDENTIFY deferral candidates: what can be done later without blocking the core goal? List with no apology.\n"
            "4. CHALLENGE additions: for each item added 'while we're at it' or 'it makes sense to also,' challenge whether it belongs now.\n"
            "5. PROPOSE the minimal viable scope: what's the smallest plan that genuinely achieves the core goal?\n"
            "Output: core_goal, scope_audit (item, necessary yes/no, deferrable yes/no), deferral_list, minimal_viable_scope"
        ),
    },
    # ═══════════════════════════════════════════════════════════════
    # DELEGATION (5)
    # ═══════════════════════════════════════════════════════════════
    # DEL-01
    {
        "slug": "capability-matching",
        "name": "Capability Matching",
        "family": "diagnostic",
        "tier": "built-in",
        "description": "Frame delegation by identifying what capabilities a task requires and matching those to available agents or models.",
        "activation_signals": [
            "who should do this",
            "model selection",
            "haiku vs sonnet",
            "right agent",
            "capability required",
            "assign to",
        ],
        "archetype_affinity": {"advisor": 0.9, "analyst": 0.8},
        "mode_affinity": {"procedural": 0.9, "deliberative": 0.8},
        "composability": {"complements": ["routing-pairwise", "spec-quality"], "conflicts": []},
        "system_prompt": (
            "Frame delegation by matching task requirements to capabilities:\n"
            "1. DEFINE task requirements: what capabilities does this task need? (reasoning depth, domain knowledge, speed, cost sensitivity, creativity)\n"
            "2. ASSESS available agents: what can each agent do well? What are their failure modes?\n"
            "3. MATCH requirements to capabilities: which agent fits which requirement? Note mismatches explicitly.\n"
            "4. IDENTIFY over-delegation: is this task being sent to a higher-capability agent than necessary? That wastes cost.\n"
            "5. IDENTIFY under-delegation: is this task being sent to a lower-capability agent that will produce poor output? That wastes time.\n"
            "Output: task_requirements, agent_capabilities, match_assessment, over/under_delegation_flags"
        ),
    },
    # DEL-02
    {
        "slug": "spec-quality",
        "name": "Spec Quality",
        "family": "evaluative",
        "tier": "built-in",
        "description": "Evaluate whether a delegation spec gives the receiving agent everything needed to succeed: context, constraints, output format, and success criteria.",
        "activation_signals": [
            "spec quality",
            "is this spec clear",
            "delegation spec",
            "will the agent understand",
            "spec review",
            "instructions clear",
        ],
        "archetype_affinity": {"advisor": 0.9, "analyst": 0.8, "executor": 0.7},
        "mode_affinity": {"deliberative": 0.9, "procedural": 0.8},
        "composability": {"complements": ["capability-matching", "output-review"], "conflicts": []},
        "system_prompt": (
            "Evaluate spec quality for delegation:\n"
            "1. CHECK context sufficiency: does the spec give the agent enough background to understand WHY, not just WHAT?\n"
            "2. CHECK constraints: are the constraints explicit? What can't the agent do? What is out of bounds?\n"
            "3. CHECK output format: is the expected output format defined? Will the agent know when it's done?\n"
            "4. CHECK success criteria: how will the delegator evaluate whether the output is correct? Is that standard in the spec?\n"
            "5. SIMULATE the agent: if you were the receiving agent, what would you be confused about? What questions would you ask?\n"
            "Output: spec_audit (element, present yes/no, quality 1-5), confusion_points, spec_score (1-10)"
        ),
    },
    # DEL-03
    {
        "slug": "routing-pairwise",
        "name": "Routing Pairwise",
        "family": "evaluative",
        "tier": "built-in",
        "description": "Compare agent routing options head-to-head: delegate to agent A, agent B, or do it yourself — given complexity, trust, and cost.",
        "activation_signals": [
            "delegate or do it myself",
            "which agent",
            "routing decision",
            "agent vs self",
            "who handles this",
            "routing choice",
        ],
        "archetype_affinity": {"advisor": 0.9, "analyst": 0.8},
        "mode_affinity": {"deliberative": 0.9, "procedural": 0.8},
        "composability": {"complements": ["capability-matching", "cost-aware-routing"], "conflicts": []},
        "system_prompt": (
            "Choose between routing options head-to-head:\n"
            "1. DEFINE the options: Agent A, Agent B, do-it-myself. Describe each route precisely.\n"
            "2. ASSESS by complexity: how complex is this task? Does the complexity justify the overhead of delegation?\n"
            "3. ASSESS by trust: how confident are you in the delegated agent's output quality? What's the cost of an error?\n"
            "4. ASSESS by cost: what is the total cost (time + money + coordination) of each routing option?\n"
            "5. FORCE A CHOICE: given complexity, trust, and cost, pick one routing option. State it and explain why.\n"
            "Do not split routing without a clear reason. Consolidate where possible."
        ),
    },
    # DEL-04
    {
        "slug": "output-review",
        "name": "Output Review",
        "family": "evaluative",
        "tier": "built-in",
        "description": "Validate that delegated output matches the original intent and spec before accepting and integrating it.",
        "activation_signals": [
            "review output",
            "does this match spec",
            "delegated output",
            "accept or reject",
            "output validation",
            "agent output quality",
        ],
        "archetype_affinity": {"advisor": 0.9, "analyst": 0.8, "executor": 0.7},
        "mode_affinity": {"deliberative": 0.9, "procedural": 0.8},
        "composability": {"complements": ["spec-quality", "holistic-validation"], "conflicts": []},
        "system_prompt": (
            "Review delegated output against original intent:\n"
            "1. RESTATE the original intent: what was the spec asking for?\n"
            "2. COMPARE output to spec: does the output satisfy each element of the spec? Check every item.\n"
            "3. ASSESS quality beyond compliance: does the output meet the spirit of the spec, or technically comply while missing the point?\n"
            "4. IDENTIFY deviations: where did the agent go beyond, fall short of, or misinterpret the spec?\n"
            "5. VERDICT: accept as-is / accept with minor fixes / reject and re-delegate. State the reason.\n"
            "Output: spec_compliance_check (element, compliant yes/no), quality_assessment, deviations, verdict"
        ),
    },
    # DEL-05
    {
        "slug": "cost-aware-routing",
        "name": "Cost-Aware Routing",
        "family": "evaluative",
        "tier": "built-in",
        "description": "Allocate tasks to batch API, real-time agents, or human-in-loop based on latency requirements, quality needs, and cost.",
        "activation_signals": [
            "cost routing",
            "batch vs real-time",
            "human in loop",
            "api cost",
            "latency vs cost",
            "cheap route",
            "expensive operation",
        ],
        "archetype_affinity": {"advisor": 0.9, "analyst": 0.8},
        "mode_affinity": {"deliberative": 0.9, "procedural": 0.8},
        "composability": {"complements": ["routing-pairwise", "capability-matching"], "conflicts": []},
        "system_prompt": (
            "Route tasks by cost awareness:\n"
            "1. ENUMERATE task types and their routing requirements: latency, quality floor, volume, consequence of error.\n"
            "2. MAP to routing tiers: batch API (async, cheap, high volume), real-time agent (synchronous, quality), human-in-loop (judgment, irreversible).\n"
            "3. ASSIGN each task to a tier: justify each assignment against requirements.\n"
            "4. IDENTIFY over-routing: tasks sent to expensive tiers that could be batched. Find 3 candidates.\n"
            "5. IDENTIFY under-routing: tasks sent to cheap tiers where quality failures are costly. Flag these.\n"
            "Output: routing_table (task, tier, latency_req, quality_req, cost_estimate), over_routing_candidates, under_routing_risks"
        ),
    },
    # ═══════════════════════════════════════════════════════════════
    # RISK (5)
    # ═══════════════════════════════════════════════════════════════
    # RSK-01
    {
        "slug": "reversibility-assessment",
        "name": "Reversibility Assessment",
        "family": "evaluative",
        "tier": "built-in",
        "description": "Assess which decisions can be undone and at what cost, and calibrate deliberation depth to the irreversibility of each choice.",
        "activation_signals": [
            "can we undo this",
            "reversible",
            "irreversible",
            "blast radius if wrong",
            "rollback",
            "one-way door",
            "how bad if wrong",
        ],
        "archetype_affinity": {"advisor": 0.9, "analyst": 0.8, "executor": 0.7},
        "mode_affinity": {"deliberative": 0.9, "reflective": 0.8},
        "composability": {"complements": ["optionality-assessment", "checkpoint-placement"], "conflicts": []},
        "system_prompt": (
            "Assess reversibility before proceeding:\n"
            "1. IDENTIFY the decision: what specifically is being committed to?\n"
            "2. CLASSIFY door type: one-way door (deletion, production change, external communication, architectural commitment) vs. two-way door (internal refactor, draft, config change).\n"
            "3. ESTIMATE undo cost: if this decision is wrong, what does it cost to reverse? (hours, data loss, user impact, reputational damage)\n"
            "4. CALIBRATE deliberation: the more irreversible, the more justification required before proceeding.\n"
            "5. DEFINE safeguards: what safety nets exist? (backup, staging, feature flag, dry run) If none, require them before proceeding.\n"
            "Output: decision_classification, undo_cost_estimate, deliberation_requirement, required_safeguards"
        ),
    },
    # RSK-02
    {
        "slug": "mitigation-pairwise",
        "name": "Mitigation Pairwise",
        "family": "evaluative",
        "tier": "built-in",
        "description": "Compare prevention, detection, and recovery strategies for each risk to choose the right mitigation posture.",
        "activation_signals": [
            "mitigation strategy",
            "prevent vs detect",
            "how to mitigate",
            "risk response",
            "defense strategy",
            "recovery plan",
        ],
        "archetype_affinity": {"advisor": 0.9, "analyst": 0.8, "executor": 0.7},
        "mode_affinity": {"deliberative": 0.9, "procedural": 0.8},
        "composability": {"complements": ["reversibility-assessment", "blast-radius-review"], "conflicts": []},
        "system_prompt": (
            "Choose mitigation posture for each risk:\n"
            "1. LIST identified risks.\n"
            "2. FOR EACH RISK, compare three postures: PREVENTION (stop it from happening), DETECTION (catch it when it does), RECOVERY (limit damage after it happens).\n"
            "3. SCORE each posture: feasibility (1-5), cost (1-5), effectiveness (1-5). Select the dominant posture for each risk.\n"
            "4. IDENTIFY the prevention/detection/recovery split across your risk portfolio. Balanced? Over-indexed on any one posture?\n"
            "5. FLAG residual risk: for risks where no posture is feasible, explicitly accept or escalate.\n"
            "Output: mitigation_table (risk, prevention_score, detection_score, recovery_score, chosen_posture), portfolio_balance, residual_risks"
        ),
    },
    # RSK-03
    {
        "slug": "assumption-identification",
        "name": "Assumption Identification",
        "family": "diagnostic",
        "tier": "built-in",
        "description": "Surface the hidden assumptions being taken for granted in a plan or decision, especially those that are load-bearing but unexamined.",
        "activation_signals": [
            "hidden assumptions",
            "what are we assuming",
            "taken for granted",
            "unstated assumptions",
            "what if that's wrong",
            "surface assumptions",
        ],
        "archetype_affinity": {"analyst": 0.9, "advisor": 0.8, "researcher": 0.7},
        "mode_affinity": {"deliberative": 0.9, "reflective": 0.8},
        "composability": {"complements": ["hypothesis-framing", "assumption-validation"], "conflicts": []},
        "system_prompt": (
            "Surface hidden assumptions:\n"
            "1. READ the plan or decision carefully. For each step, ask: 'What would have to be true for this step to work?'\n"
            "2. LIST every assumption, including obvious ones. Especially include the obvious ones — they are often the most dangerous.\n"
            "3. CLASSIFY each assumption: validated (tested and confirmed), plausible (untested but reasonable), fragile (untested and potentially wrong).\n"
            "4. RANK fragile assumptions by impact: if this assumption is false, how much does the plan fail?\n"
            "5. FLAG load-bearing assumptions: the ones the entire plan rests on. These require explicit validation before proceeding.\n"
            "Output: assumption_list (assumption, classification, impact_if_wrong), fragile_ranked, load_bearing_assumptions"
        ),
    },
    # RSK-04
    {
        "slug": "checkpoint-placement",
        "name": "Checkpoint Placement",
        "family": "evaluative",
        "tier": "built-in",
        "description": "Identify where to validate assumptions and results before proceeding, placing gates at points of highest risk and irreversibility.",
        "activation_signals": [
            "checkpoint",
            "gate",
            "validate before proceeding",
            "stop and check",
            "when to review",
            "validation point",
            "before committing",
        ],
        "archetype_affinity": {"advisor": 0.9, "analyst": 0.8, "executor": 0.7},
        "mode_affinity": {"procedural": 0.9, "deliberative": 0.8},
        "composability": {"complements": ["reversibility-assessment", "plan-coherence"], "conflicts": []},
        "system_prompt": (
            "Place validation checkpoints at the right points in the plan:\n"
            "1. MAP decision points: where in the plan are irreversible commitments made?\n"
            "2. MAP assumption tests: where in the plan do key assumptions need to be validated?\n"
            "3. PLACE checkpoints: at each irreversible step and each load-bearing assumption, define a validation gate.\n"
            "4. DEFINE gate conditions: what must be true to pass each gate? What does failure look like?\n"
            "5. SPECIFY gate failure response: if a gate fails, what's the fallback? Stop? Reroute? Escalate?\n"
            "Output: checkpoint_plan (step, checkpoint_type, gate_condition, failure_response), critical_gates"
        ),
    },
    # RSK-05
    {
        "slug": "blast-radius-review",
        "name": "Blast Radius Review",
        "family": "adversarial",
        "tier": "built-in",
        "description": "Assess the severity and scope of failure impact: who is affected, what is damaged, and how bad could it get.",
        "activation_signals": [
            "if this goes wrong",
            "blast radius",
            "who is affected",
            "severity",
            "downside scenario",
            "worst case",
            "failure impact",
        ],
        "archetype_affinity": {"advisor": 0.9, "analyst": 0.8, "executor": 0.7},
        "mode_affinity": {"deliberative": 0.9, "reflective": 0.8},
        "composability": {"complements": ["reversibility-assessment", "failure-cascade"], "conflicts": []},
        "system_prompt": (
            "Assess the blast radius of this decision or action:\n"
            "1. IDENTIFY the failure mode: how specifically could this go wrong?\n"
            "2. MAP affected parties: who is directly impacted? Who is indirectly impacted? Who would be surprised to be affected?\n"
            "3. ASSESS damage categories: data integrity, user experience, business continuity, security, reputation.\n"
            "4. ESTIMATE recovery time: how long does it take to restore normal state after each failure mode?\n"
            "5. CLASSIFY overall severity: catastrophic (business-threatening) / major (significant user impact) / minor (contained, recoverable) / negligible.\n"
            "Output: failure_modes, affected_parties, damage_assessment (category, severity), recovery_estimates, overall_severity"
        ),
    },
    # ═══════════════════════════════════════════════════════════════
    # PRIORITIZATION (6)
    # ═══════════════════════════════════════════════════════════════
    # PRI-01
    {
        "slug": "competing-demands-mapping",
        "name": "Competing Demands Mapping",
        "family": "diagnostic",
        "tier": "built-in",
        "description": "Make explicit what is competing for attention so prioritization can happen against the full set of demands, not just the visible ones.",
        "activation_signals": [
            "competing priorities",
            "too many things",
            "what's competing",
            "everything is urgent",
            "prioritize everything",
            "overwhelmed",
            "full plate",
        ],
        "archetype_affinity": {"advisor": 0.9, "analyst": 0.8},
        "mode_affinity": {"deliberative": 0.9, "exploratory": 0.7},
        "composability": {"complements": ["impact-assessment", "attention-budget"], "conflicts": []},
        "system_prompt": (
            "Make competing demands explicit before prioritizing:\n"
            "1. ENUMERATE all demands on attention right now: work items, requests, blockers, background concerns, maintenance.\n"
            "2. CATEGORIZE each demand: new work, ongoing work, reactive work, investment work.\n"
            "3. SURFACE hidden demands: what work is invisible but consuming real capacity? (context switching, waiting, coordination)\n"
            "4. QUANTIFY capacity: total available attention capacity vs. total current demand. What's the ratio?\n"
            "5. IDENTIFY the real constraint: is this an attention deficit problem or a prioritization problem?\n"
            "Output: demand_inventory (item, category, visible yes/no, estimated_capacity), capacity_ratio, constraint_type"
        ),
    },
    # PRI-02
    {
        "slug": "impact-assessment",
        "name": "Impact Assessment",
        "family": "evaluative",
        "tier": "built-in",
        "description": "Assess which task moves the needle most toward the primary goal by explicitly measuring impact rather than urgency.",
        "activation_signals": [
            "what has most impact",
            "which matters most",
            "impact vs urgency",
            "highest value",
            "what moves the needle",
            "most important task",
        ],
        "archetype_affinity": {"advisor": 0.9, "analyst": 0.8},
        "mode_affinity": {"deliberative": 0.9, "procedural": 0.7},
        "composability": {"complements": ["competing-demands-mapping", "dependency-ordering"], "conflicts": []},
        "system_prompt": (
            "Assess impact to identify the highest-value task:\n"
            "1. STATE the primary goal: the one thing that matters most right now.\n"
            "2. MEASURE impact: for each task, how much does it advance the primary goal? Score 1-10.\n"
            "3. SEPARATE urgency from importance: urgency is time pressure; importance is goal advancement. These often conflict.\n"
            "4. IDENTIFY the impact multiplier: which task, if done well, makes other tasks easier or unnecessary?\n"
            "5. FORCE THE ORDER: rank all tasks by impact*reversibility. Do the high-impact, reversible tasks first.\n"
            "Output: impact_scores (task, impact 1-10, urgency 1-10, importance_rank), impact_multiplier, ordered_list"
        ),
    },
    # PRI-03
    {
        "slug": "dependency-ordering",
        "name": "Dependency Ordering",
        "family": "evaluative",
        "tier": "built-in",
        "description": "Order tasks by what unblocks other work, putting the critical path first to prevent downstream stalls.",
        "activation_signals": [
            "what unblocks",
            "critical path",
            "dependency order",
            "what to do first",
            "blocking task",
            "what's downstream",
            "sequencing",
        ],
        "archetype_affinity": {"executor": 0.9, "advisor": 0.8, "analyst": 0.7},
        "mode_affinity": {"procedural": 0.9, "deliberative": 0.8},
        "composability": {"complements": ["parallelization-assessment", "impact-assessment"], "conflicts": []},
        "system_prompt": (
            "Order tasks by dependency to unblock downstream work:\n"
            "1. MAP dependencies: for each task, what does it unblock when complete? What does it depend on?\n"
            "2. BUILD the dependency graph: identify roots (no dependencies), interior nodes, and leaves.\n"
            "3. FIND the critical path: the sequence of dependent tasks with the longest total duration.\n"
            "4. IDENTIFY highest-fan-out tasks: which tasks unblock the most downstream work? These deserve highest priority.\n"
            "5. FLAG circular dependencies: any circular dependency is a planning error — surface and resolve it.\n"
            "Output: dependency_graph, critical_path, fan_out_ranking (task, downstream_count), circular_deps"
        ),
    },
    # PRI-04
    {
        "slug": "risk-adjusted-sequencing",
        "name": "Risk-Adjusted Sequencing",
        "family": "evaluative",
        "tier": "built-in",
        "description": "Sequence high-risk items early to surface problems before they are compounded by downstream work built on faulty assumptions.",
        "activation_signals": [
            "sequence by risk",
            "risky items first",
            "de-risk early",
            "fail fast",
            "surface problems early",
            "risk sequencing",
        ],
        "archetype_affinity": {"advisor": 0.9, "analyst": 0.8, "executor": 0.7},
        "mode_affinity": {"deliberative": 0.9, "procedural": 0.8},
        "composability": {"complements": ["risk-first-ordering", "dependency-ordering"], "conflicts": []},
        "system_prompt": (
            "Sequence tasks with risk-adjusted ordering:\n"
            "1. IDENTIFY risk drivers for each task: technical uncertainty, external dependency, irreversibility, team capability.\n"
            "2. SCORE each task on risk: 1 (low, clear) to 5 (high, unknown).\n"
            "3. IDENTIFY assumption-dependent tasks: tasks whose success depends on unvalidated assumptions.\n"
            "4. MOVE high-risk tasks earlier: sequence them before the work that depends on their outcomes being correct.\n"
            "5. VERIFY the sequence: does this ordering surface failures before they compound? Would you rather find out about this problem now or later?\n"
            "Output: risk_scores (task, risk_score, risk_driver), risk_adjusted_sequence, assumption_gates"
        ),
    },
    # PRI-05
    {
        "slug": "attention-budget",
        "name": "Attention Budget",
        "family": "evaluative",
        "tier": "built-in",
        "description": "Allocate attention across deep work, quick wins, and blockers to ensure the highest-value work gets the focus it requires.",
        "activation_signals": [
            "attention allocation",
            "focus time",
            "deep work vs quick wins",
            "where to spend time",
            "time budget",
            "focus budget",
        ],
        "archetype_affinity": {"advisor": 0.9, "analyst": 0.8},
        "mode_affinity": {"deliberative": 0.9, "procedural": 0.8},
        "composability": {"complements": ["competing-demands-mapping", "impact-assessment"], "conflicts": []},
        "system_prompt": (
            "Allocate attention as an explicit budget:\n"
            "1. DEFINE the total available attention: how many focused work units are available this period?\n"
            "2. CATEGORIZE work types: deep work (requires sustained focus, high cognitive load), quick wins (low effort, visible output), blockers (must be resolved for others to proceed).\n"
            "3. ALLOCATE: assign % of attention to each category. Typical pattern: 60% deep work, 20% blockers, 20% quick wins.\n"
            "4. PROTECT deep work: which time blocks are reserved for deep work? What interruptions are acceptable within those blocks?\n"
            "5. REVIEW the split: does this allocation advance the primary goal or does it maintain the appearance of productivity?\n"
            "Output: attention_allocation (category, percent, items_in_category), deep_work_protection, goal_advancement_test"
        ),
    },
    # PRI-06
    {
        "slug": "dynamic-reprioritization",
        "name": "Dynamic Reprioritization",
        "family": "adversarial",
        "tier": "built-in",
        "description": "Critique the current priority order in light of new information to determine whether the list should be reshuffled.",
        "activation_signals": [
            "reprioritize",
            "new information changes things",
            "should we reorder",
            "priority shift",
            "does this change the plan",
            "update priorities",
        ],
        "archetype_affinity": {"advisor": 0.9, "analyst": 0.8},
        "mode_affinity": {"deliberative": 0.9, "reflective": 0.8},
        "composability": {"complements": ["impact-assessment", "competing-demands-mapping"], "conflicts": []},
        "system_prompt": (
            "Reprioritize in light of new information:\n"
            "1. STATE the new information: what changed? What do we now know that we didn't before?\n"
            "2. AUDIT the current priority list: does this new information change the impact score of any item?\n"
            "3. IDENTIFY items that moved: which tasks became more urgent? Which became less relevant or obsolete?\n"
            "4. CHECK for sunk cost bias: are you keeping something high-priority because you've invested in it, not because it's still the right call?\n"
            "5. PRODUCE the updated list: show before and after. Explain each change.\n"
            "Output: new_information_summary, impact_changes (item, old_score, new_score, reason), sunk_cost_risks, updated_priority_list"
        ),
    },
    # ═══════════════════════════════════════════════════════════════
    # GAP (5 — gap-analysis is in Generic above)
    # ═══════════════════════════════════════════════════════════════
    # GAP-01
    {
        "slug": "absence-ranking",
        "name": "Absence Ranking",
        "family": "evaluative",
        "tier": "built-in",
        "description": "Rank missing pieces by their impact on the whole system to direct gap-filling effort toward the highest-value absences.",
        "activation_signals": [
            "rank missing pieces",
            "most important gap",
            "which absence matters most",
            "prioritize gaps",
            "gap ranking",
            "fill which gap first",
        ],
        "archetype_affinity": {"analyst": 0.9, "advisor": 0.8, "researcher": 0.7},
        "mode_affinity": {"deliberative": 0.9, "exploratory": 0.7},
        "composability": {"complements": ["gap-analysis", "impact-assessment"], "conflicts": []},
        "system_prompt": (
            "Rank identified gaps by impact:\n"
            "1. LIST all identified gaps.\n"
            "2. ASSESS each gap's impact: if this gap were filled, how much would the overall system improve? Score 1-10.\n"
            "3. ASSESS each gap's difficulty: how hard is it to fill? Score 1-10 (1=trivial, 10=extremely hard).\n"
            "4. COMPUTE impact/difficulty ratio: this surfaces high-value, achievable gaps.\n"
            "5. RANK by ratio: highest ratio first. These are the gaps to fill now.\n"
            "Output: gap_ranking (gap, impact_score, difficulty_score, ratio, rank), top_3_gaps_to_fill"
        ),
    },
    # GAP-02
    {
        "slug": "gap-vs-intentional",
        "name": "Gap vs Intentional",
        "family": "evaluative",
        "tier": "built-in",
        "description": "Distinguish gaps that are missing by accident from those that are missing by design, to avoid filling intentional absences.",
        "activation_signals": [
            "intentional gap",
            "by design",
            "is this missing on purpose",
            "deliberate absence",
            "conscious choice vs oversight",
            "missing or excluded",
        ],
        "archetype_affinity": {"analyst": 0.9, "advisor": 0.8, "researcher": 0.7},
        "mode_affinity": {"deliberative": 0.9, "reflective": 0.8},
        "composability": {"complements": ["gap-analysis", "absence-ranking"], "conflicts": []},
        "system_prompt": (
            "Distinguish accidental gaps from intentional absences:\n"
            "1. LIST all identified gaps.\n"
            "2. INVESTIGATE intent: for each gap, search for evidence that it was deliberately excluded (design doc, decision record, architecture choice, stated scope).\n"
            "3. CLASSIFY: intentional (evidence of deliberate exclusion) / likely intentional (probable by context) / accidental (no evidence of exclusion) / unknown.\n"
            "4. FLAG intentional gaps: these should not be filled without revisiting the original decision that excluded them.\n"
            "5. FOCUS on accidental gaps: these are the legitimate targets for gap-filling work.\n"
            "Output: gap_classification (gap, classification, evidence), intentional_gaps_requiring_review, accidental_gaps_to_fill"
        ),
    },
    # GAP-03
    {
        "slug": "completeness-testing",
        "name": "Completeness Testing",
        "family": "evaluative",
        "tier": "built-in",
        "description": "Validate that filling an identified gap makes the whole system cohere, rather than just adding a piece without verifying the overall fit.",
        "activation_signals": [
            "does filling this gap fix it",
            "system coherence",
            "complete after gap fill",
            "whole system works",
            "coherence check after fill",
        ],
        "archetype_affinity": {"analyst": 0.9, "executor": 0.8, "advisor": 0.7},
        "mode_affinity": {"deliberative": 0.9, "procedural": 0.8},
        "composability": {"complements": ["gap-analysis", "holistic-validation"], "conflicts": []},
        "system_prompt": (
            "Test whether filling the gap produces a coherent whole:\n"
            "1. STATE the gap being filled and the proposed fill.\n"
            "2. SIMULATE the filled state: imagine the system with this gap filled. What does it look like?\n"
            "3. CHECK coherence: do all other components still work correctly with the filled gap in place? Are there new integration points that need attention?\n"
            "4. FIND secondary gaps: does filling this gap reveal other gaps that were previously hidden behind it?\n"
            "5. VERDICT: filling this gap produces completeness / reveals more work / creates new problems.\n"
            "Output: filled_state_description, coherence_check, secondary_gaps_revealed, completeness_verdict"
        ),
    },
    # GAP-04
    {
        "slug": "urgency-distribution",
        "name": "Urgency Distribution",
        "family": "evaluative",
        "tier": "built-in",
        "description": "Allocate urgency levels across identified gaps to distinguish blocking gaps from nice-to-have improvements.",
        "activation_signals": [
            "urgent gaps",
            "blocking vs nice to have",
            "gap urgency",
            "which gaps block",
            "prioritize by urgency",
            "timeline for gaps",
        ],
        "archetype_affinity": {"advisor": 0.9, "analyst": 0.8},
        "mode_affinity": {"deliberative": 0.9, "procedural": 0.8},
        "composability": {"complements": ["absence-ranking", "gap-analysis"], "conflicts": []},
        "system_prompt": (
            "Distribute urgency levels across identified gaps:\n"
            "1. LIST all identified gaps.\n"
            "2. CLASSIFY each gap by urgency: blocking (prevents forward progress), degrading (reduces quality but work continues), latent (will matter eventually but not now), cosmetic (minor polish).\n"
            "3. ALLOCATE attention: blocking gaps get immediate action. Degrading get scheduled. Latent get tracked. Cosmetic get a backlog entry.\n"
            "4. CHECK for urgency bias: are you classifying more things as urgent than are actually urgent? Apply the 'what actually blocks' test.\n"
            "5. PRODUCE the work order: blocking gaps first, then degrading by impact, then latent by strategic value.\n"
            "Output: urgency_classification (gap, urgency_level, justification), work_order, urgency_inflation_check"
        ),
    },
    # GAP-05
    {
        "slug": "meta-gap-analysis",
        "name": "Meta-Gap Analysis",
        "family": "adversarial",
        "tier": "built-in",
        "description": "Critique the gap analysis itself for systematic blind spots: what categories of gap were not searched, and what analysis methods were not applied.",
        "activation_signals": [
            "gaps in the gap analysis",
            "did we miss gaps",
            "meta analysis",
            "blind spots in assessment",
            "second-order gaps",
            "gap analysis quality",
        ],
        "archetype_affinity": {"analyst": 0.9, "advisor": 0.8, "researcher": 0.7},
        "mode_affinity": {"reflective": 0.9, "deliberative": 0.8},
        "composability": {"complements": ["gap-analysis", "meta-evaluation"], "conflicts": []},
        "system_prompt": (
            "Critique the gap analysis for its own gaps:\n"
            "1. AUDIT the analysis method: how were gaps identified? What systematic approaches were used?\n"
            "2. IDENTIFY method blind spots: what categories of gap does this method structurally miss? (e.g., gap analysis from code review misses process gaps)\n"
            "3. CHECK for domain coverage: were all 23 product disciplines examined, or only the obvious ones?\n"
            "4. ASSESS the analyst's bias: what would this analyst's background cause them to over-count or under-count?\n"
            "5. NAME the most likely missed gap: given all the above, what is the single most likely gap that was missed?\n"
            "Output: method_audit, structural_blind_spots, domain_coverage_check, analyst_bias_assessment, most_likely_missed_gap"
        ),
    },
    # ═══════════════════════════════════════════════════════════════
    # FEEDBACK (6)
    # ═══════════════════════════════════════════════════════════════
    # FBK-01
    {
        "slug": "progress-assessment",
        "name": "Progress Assessment",
        "family": "diagnostic",
        "tier": "built-in",
        "description": "Assess whether the current effort is on track by identifying specific success and failure signals, not just checking whether work is being done.",
        "activation_signals": [
            "am I on track",
            "progress check",
            "how are we doing",
            "success signals",
            "failure signals",
            "are we making progress",
        ],
        "archetype_affinity": {"advisor": 0.9, "analyst": 0.8, "executor": 0.7},
        "mode_affinity": {"deliberative": 0.9, "reflective": 0.8},
        "composability": {"complements": ["signal-triage", "incremental-checkpoint"], "conflicts": []},
        "system_prompt": (
            "Assess progress against the actual goal:\n"
            "1. STATE the goal and expected completion state: what does success look like?\n"
            "2. IDENTIFY success signals: what specific, observable indicators confirm we're on the right path?\n"
            "3. IDENTIFY failure signals: what would indicate the approach is failing, even if work is still being done?\n"
            "4. ASSESS current state: which signals are present? Success or failure signals are stronger right now?\n"
            "5. VERDICT: on track / at risk / off track. State the specific signal driving the assessment.\n"
            "Output: goal_statement, success_signals (present yes/no), failure_signals (present yes/no), progress_verdict"
        ),
    },
    # FBK-02
    {
        "slug": "signal-triage",
        "name": "Signal Triage",
        "family": "evaluative",
        "tier": "built-in",
        "description": "Triage feedback signals to distinguish those deserving immediate attention from noise, preventing over-reaction to irrelevant signals.",
        "activation_signals": [
            "signal vs noise",
            "feedback triage",
            "which feedback to act on",
            "important signal",
            "noise in feedback",
            "filter feedback",
        ],
        "archetype_affinity": {"advisor": 0.9, "analyst": 0.8},
        "mode_affinity": {"deliberative": 0.9, "reflective": 0.8},
        "composability": {"complements": ["progress-assessment", "self-calibration"], "conflicts": []},
        "system_prompt": (
            "Triage feedback signals by importance:\n"
            "1. LIST all incoming feedback signals.\n"
            "2. CLASSIFY each signal: high-signal (specific, actionable, from authoritative source), low-signal (vague, single data point, emotional), noise (irrelevant, biased, or contradicted by other evidence).\n"
            "3. IDENTIFY patterns: are multiple independent signals pointing in the same direction? That's a strong signal.\n"
            "4. ASSESS source quality: where does each signal come from? Is the source in a position to observe the actual outcome?\n"
            "5. PRODUCE the action list: only high-signal items get immediate action. Low-signal items go to monitoring. Noise is discarded.\n"
            "Output: signal_classification (signal, class, source_quality, action), pattern_observations, action_list"
        ),
    },
    # FBK-03
    {
        "slug": "approach-invalidation",
        "name": "Approach Invalidation",
        "family": "evaluative",
        "tier": "built-in",
        "description": "Evaluate whether the current approach is still viable given feedback, or whether a pivot is required.",
        "activation_signals": [
            "should we pivot",
            "is current approach still valid",
            "approach failing",
            "change direction",
            "approach viability",
            "stick or switch",
        ],
        "archetype_affinity": {"advisor": 0.9, "analyst": 0.8},
        "mode_affinity": {"deliberative": 0.9, "reflective": 0.9},
        "composability": {"complements": ["signal-triage", "sunk-cost-resistance"], "conflicts": []},
        "system_prompt": (
            "Evaluate whether the current approach is still viable:\n"
            "1. STATE the current approach and the assumption it was built on.\n"
            "2. ASSESS incoming evidence: what signals suggest the assumption was wrong or conditions have changed?\n"
            "3. DEFINE the invalidation threshold: what evidence, if present, would definitively invalidate this approach?\n"
            "4. TEST the threshold: is the evidence at or above the invalidation threshold?\n"
            "5. FORCE THE CHOICE: continue current approach / modify significantly / pivot to a new approach. State the reason.\n"
            "Do not continue an invalidated approach from momentum. Make the call."
        ),
    },
    # FBK-04
    {
        "slug": "incremental-checkpoint",
        "name": "Incremental Checkpoint",
        "family": "evaluative",
        "tier": "built-in",
        "description": "Test a specific assumption before building further on it, preventing cascading rework from undiscovered early errors.",
        "activation_signals": [
            "test before continuing",
            "validate assumption",
            "checkpoint",
            "before building more",
            "smoke test",
            "incremental validation",
        ],
        "archetype_affinity": {"executor": 0.9, "advisor": 0.8, "analyst": 0.7},
        "mode_affinity": {"procedural": 0.9, "deliberative": 0.8},
        "composability": {"complements": ["checkpoint-placement", "progress-assessment"], "conflicts": []},
        "system_prompt": (
            "Define and execute an incremental checkpoint:\n"
            "1. IDENTIFY the assumption being tested: what specific belief needs validation before proceeding?\n"
            "2. DEFINE the test: what is the minimal check that would confirm or deny this assumption?\n"
            "3. SET pass/fail criteria: what result confirms the assumption? What result falsifies it?\n"
            "4. EXECUTE the test: run the check and observe the result.\n"
            "5. GATE decision: assumption confirmed — proceed. Assumption denied — stop, diagnose, resolve before continuing.\n"
            "Output: assumption_statement, test_definition, pass_criteria, fail_criteria, test_result, gate_decision"
        ),
    },
    # FBK-05
    {
        "slug": "sunk-cost-resistance",
        "name": "Sunk Cost Resistance",
        "family": "adversarial",
        "tier": "built-in",
        "description": "Challenge continuation decisions that are driven by sunk cost rather than future value, forcing evaluation based on forward-looking merit only.",
        "activation_signals": [
            "already invested",
            "too far in to stop",
            "sunk cost",
            "we've come this far",
            "too much work to abandon",
            "can't waste the effort",
        ],
        "archetype_affinity": {"advisor": 0.9, "analyst": 0.8},
        "mode_affinity": {"deliberative": 0.9, "reflective": 0.9},
        "composability": {"complements": ["approach-invalidation", "optionality-assessment"], "conflicts": []},
        "system_prompt": (
            "Challenge sunk cost reasoning:\n"
            "1. IDENTIFY the sunk cost argument: 'We should continue because we've already invested X.'\n"
            "2. STRIP the sunk cost: pretend the investment never happened. Evaluate the current situation from scratch.\n"
            "3. ASK the forward question: given only future costs and future benefits, what decision would you make today if starting fresh?\n"
            "4. COMPARE to current plan: is the current plan justified by future value, or mainly by past investment?\n"
            "5. FORCE THE CALL: continue (future value justifies it) / stop (sunk cost is the only justification). State which.\n"
            "Sunk costs are not a reason to continue. Future value is the only reason."
        ),
    },
    # FBK-06
    {
        "slug": "self-calibration",
        "name": "Self-Calibration",
        "family": "adversarial",
        "tier": "built-in",
        "description": "Assess confidence calibration: is stated confidence proportional to evidence, or is it inflated or deflated by cognitive biases?",
        "activation_signals": [
            "how confident am I",
            "calibration",
            "overconfident",
            "underconfident",
            "confidence check",
            "am I right to be confident",
            "second-guess",
        ],
        "archetype_affinity": {"analyst": 0.9, "advisor": 0.8, "researcher": 0.7},
        "mode_affinity": {"reflective": 0.9, "deliberative": 0.8},
        "composability": {"complements": ["meta-evaluation", "signal-triage"], "conflicts": []},
        "system_prompt": (
            "Assess whether confidence is calibrated:\n"
            "1. STATE the claim and current confidence level (0-100%).\n"
            "2. AUDIT the evidence base: how much evidence supports this confidence level?\n"
            "3. CHECK for inflation sources: am I more confident because I want this to be true? Because I've invested? Because it matches my prior?\n"
            "4. CHECK for deflation sources: am I less confident than evidence warrants because of fear, unfamiliarity, or social pressure?\n"
            "5. RECALIBRATE: what confidence level is actually justified by the evidence? State the adjustment.\n"
            "Output: original_confidence, evidence_base_quality, inflation_factors, deflation_factors, recalibrated_confidence"
        ),
    },
    # ═══════════════════════════════════════════════════════════════
    # VERIFICATION (6)
    # ═══════════════════════════════════════════════════════════════
    # VER-01
    {
        "slug": "spec-compliance-framing",
        "name": "Spec Compliance Framing",
        "family": "diagnostic",
        "tier": "built-in",
        "description": "Frame what 'correct' means for the current task by deriving the verification criteria from the spec before running any checks.",
        "activation_signals": [
            "what does correct mean",
            "verification criteria",
            "spec compliance",
            "how to verify",
            "what am I checking for",
            "definition of done",
        ],
        "archetype_affinity": {"executor": 0.9, "analyst": 0.8, "advisor": 0.7},
        "mode_affinity": {"procedural": 0.9, "deliberative": 0.8},
        "composability": {"complements": ["test-strategy", "assumption-validation"], "conflicts": []},
        "system_prompt": (
            "Frame the verification criteria before checking anything:\n"
            "1. IDENTIFY the spec: what is the authoritative statement of what this should do?\n"
            "2. DERIVE correctness criteria: for each spec element, what observable outcome would confirm it's satisfied?\n"
            "3. DISTINGUISH functional from non-functional: what does correct behavior look like? What does acceptable performance, security, and maintainability look like?\n"
            "4. IDENTIFY ambiguities: where is the spec unclear about what 'correct' means? Resolve before testing.\n"
            "5. DEFINE done: what is the explicit, observable definition of 'verification complete'?\n"
            "Output: correctness_criteria (spec_element, observable_confirmation), nonfunctional_criteria, ambiguities, done_definition"
        ),
    },
    # VER-02
    {
        "slug": "test-strategy",
        "name": "Test Strategy",
        "family": "evaluative",
        "tier": "built-in",
        "description": "Design what to test and at what level based on risk, complexity, and reversibility rather than defaulting to full test coverage everywhere.",
        "activation_signals": [
            "what to test",
            "test strategy",
            "unit vs integration",
            "test coverage",
            "testing approach",
            "what level to test",
            "test design",
        ],
        "archetype_affinity": {"executor": 0.9, "analyst": 0.8, "advisor": 0.6},
        "mode_affinity": {"deliberative": 0.9, "procedural": 0.8},
        "composability": {"complements": ["spec-compliance-framing", "coverage-budget"], "conflicts": []},
        "system_prompt": (
            "Design the test strategy for this task:\n"
            "1. IDENTIFY what needs testing: which behaviors are new, changed, or at risk?\n"
            "2. ASSESS risk per component: which components have the highest failure cost?\n"
            "3. MATCH test level to risk: unit tests (logic, isolation, fast), integration tests (boundaries, contracts), manual tests (user flows, edge cases). High-risk components get more levels.\n"
            "4. IDENTIFY test gaps: what failure mode has no test coverage?\n"
            "5. ALLOCATE test effort: what percentage of testing effort goes to each level? Justify the split.\n"
            "Output: test_inventory (behavior, risk_level, test_level, test_type), coverage_gaps, effort_allocation"
        ),
    },
    # VER-03
    {
        "slug": "verification-approach",
        "name": "Verification Approach",
        "family": "evaluative",
        "tier": "built-in",
        "description": "Choose the verification method that fits this specific task: automated test, manual check, formal proof, canary, or observational.",
        "activation_signals": [
            "how to verify",
            "verification method",
            "automated vs manual",
            "test approach",
            "verify this",
            "how to check",
        ],
        "archetype_affinity": {"executor": 0.9, "analyst": 0.8, "advisor": 0.6},
        "mode_affinity": {"procedural": 0.9, "deliberative": 0.8},
        "composability": {"complements": ["test-strategy", "spec-compliance-framing"], "conflicts": []},
        "system_prompt": (
            "Choose the right verification method for this task:\n"
            "1. CHARACTERIZE the task: what type of output must be verified? (code behavior, data transformation, user flow, decision quality, text output)\n"
            "2. EVALUATE method options: automated test (repeatable, fast, limited to programmatic check), manual review (flexible, slow), canary/staged rollout (real traffic, delayed feedback), observational (log + metric analysis).\n"
            "3. MATCH method to output type: some outputs cannot be automatically verified — acknowledge this explicitly.\n"
            "4. CONSIDER cost vs. confidence: which method gives sufficient confidence at minimum verification cost?\n"
            "5. SELECT the method: state it, define what success looks like under this method, and define how long verification should take.\n"
            "Output: task_characterization, method_options (method, pros, cons), chosen_method, success_definition, time_budget"
        ),
    },
    # VER-04
    {
        "slug": "assumption-validation",
        "name": "Assumption Validation",
        "family": "evaluative",
        "tier": "built-in",
        "description": "Verify that the assumption the task was operating under actually held after execution, preventing silent divergence between expected and actual behavior.",
        "activation_signals": [
            "did the assumption hold",
            "validate assumption",
            "was this right",
            "assumption check",
            "did it work as expected",
            "post-execution check",
        ],
        "archetype_affinity": {"executor": 0.9, "analyst": 0.8, "advisor": 0.7},
        "mode_affinity": {"procedural": 0.9, "deliberative": 0.8},
        "composability": {"complements": ["spec-compliance-framing", "incremental-checkpoint"], "conflicts": []},
        "system_prompt": (
            "Validate that operating assumptions held after execution:\n"
            "1. LIST the assumptions the task was built on: what did you take for granted about the environment, inputs, or behavior?\n"
            "2. FOR EACH ASSUMPTION: what observable evidence confirms it held? What would indicate it didn't?\n"
            "3. CHECK the evidence: look at outputs, logs, error states, or test results. Did the assumption hold?\n"
            "4. CLASSIFY each assumption: confirmed / unconfirmed (no evidence either way) / violated.\n"
            "5. RESPOND to violations: violated assumptions require rework. Unconfirmed assumptions require monitoring.\n"
            "Output: assumption_validation_table (assumption, expected, observed, status), violations, required_rework"
        ),
    },
    # VER-05
    {
        "slug": "coverage-budget",
        "name": "Coverage Budget",
        "family": "evaluative",
        "tier": "built-in",
        "description": "Allocate testing effort across components and risk levels to ensure critical paths are well-covered without wasting effort on low-risk areas.",
        "activation_signals": [
            "test coverage budget",
            "where to test most",
            "coverage allocation",
            "testing effort",
            "what can be left untested",
            "test depth",
        ],
        "archetype_affinity": {"executor": 0.9, "analyst": 0.8},
        "mode_affinity": {"procedural": 0.9, "deliberative": 0.8},
        "composability": {"complements": ["test-strategy", "effort-distribution"], "conflicts": []},
        "system_prompt": (
            "Allocate coverage budget across the system:\n"
            "1. ENUMERATE testable components.\n"
            "2. SCORE each component by risk: how bad is it if this fails undetected? (1=low, 5=critical)\n"
            "3. ALLOCATE 100 coverage points: high-risk components get more coverage. Low-risk components get less.\n"
            "4. IDENTIFY under-coverage: which high-risk components have insufficient coverage given their score?\n"
            "5. IDENTIFY over-coverage: which low-risk components are consuming coverage budget that should go elsewhere?\n"
            "Output: coverage_allocation (component, risk_score, coverage_points, assessment), under_coverage_list, over_coverage_list"
        ),
    },
    # VER-06
    {
        "slug": "regression-detection",
        "name": "Regression Detection",
        "family": "adversarial",
        "tier": "built-in",
        "description": "Identify what existing behavior might have broken as a side effect of recent changes, by tracing the change's blast radius through dependent components.",
        "activation_signals": [
            "regression",
            "did I break something",
            "side effect",
            "what changed",
            "what else is affected",
            "backward compatibility",
            "existing behavior",
        ],
        "archetype_affinity": {"executor": 0.9, "analyst": 0.8, "advisor": 0.6},
        "mode_affinity": {"deliberative": 0.9, "procedural": 0.8},
        "composability": {"complements": ["failure-cascade", "integration-validation"], "conflicts": []},
        "system_prompt": (
            "Detect potential regressions from recent changes:\n"
            "1. IDENTIFY what changed: list all modified components, interfaces, and behaviors.\n"
            "2. MAP dependents: what components depend on what changed? Who calls this? Who reads this data?\n"
            "3. ASSESS change compatibility: for each dependent, does the change preserve the contract they rely on?\n"
            "4. IDENTIFY breakage candidates: which dependents are most likely to have broken? Rank by coupling strength.\n"
            "5. DEFINE regression tests: what specific checks would detect breakage in the top 3 candidates?\n"
            "Output: change_impact_map (changed_component, dependents, compatibility), top_breakage_candidates, regression_tests"
        ),
    },
    # ═══════════════════════════════════════════════════════════════
    # MEMORY (6)
    # ═══════════════════════════════════════════════════════════════
    # MEM-01
    {
        "slug": "memory-operation-type",
        "name": "Memory Operation Type",
        "family": "diagnostic",
        "tier": "built-in",
        "description": "Frame the memory operation: is this a capture (record new), consolidate (merge existing), or reconstruct (rebuild context from fragments)?",
        "activation_signals": [
            "save this",
            "remember",
            "capture",
            "update memory",
            "consolidate",
            "what do we know",
            "reconstruct context",
            "recall",
        ],
        "archetype_affinity": {"executor": 0.8, "analyst": 0.7, "researcher": 0.8},
        "mode_affinity": {"procedural": 0.9, "reflective": 0.8},
        "composability": {"complements": ["salience-detection", "staleness-check"], "conflicts": []},
        "system_prompt": (
            "Frame the memory operation type before executing:\n"
            "1. IDENTIFY the operation type:\n"
            "   - CAPTURE: recording new information that doesn't exist in memory\n"
            "   - CONSOLIDATE: merging new information with existing memory to update it\n"
            "   - RECONSTRUCT: rebuilding working context from fragmented or distributed memory\n"
            "2. VERIFY the type: if capture, check that it's actually new. If consolidate, locate the existing record. If reconstruct, define the needed context state.\n"
            "3. IDENTIFY the right memory tier: session (current task), working (current session), long-term (persists across sessions).\n"
            "4. DEFINE the operation precisely: what is being captured, what is being merged with, or what context is being rebuilt?\n"
            "Output: operation_type, memory_tier, operation_definition, existing_records_to_update"
        ),
    },
    # MEM-02
    {
        "slug": "salience-detection",
        "name": "Salience Detection",
        "family": "evaluative",
        "tier": "built-in",
        "description": "Determine what is worth keeping in memory by applying the salience hierarchy: decision > correction > pattern > fact.",
        "activation_signals": [
            "what to remember",
            "worth keeping",
            "important enough to save",
            "salience",
            "what matters",
            "memory value",
            "capture priority",
        ],
        "archetype_affinity": {"analyst": 0.9, "researcher": 0.8, "advisor": 0.7},
        "mode_affinity": {"deliberative": 0.9, "reflective": 0.8},
        "composability": {"complements": ["memory-operation-type", "keep-merge-discard"], "conflicts": []},
        "system_prompt": (
            "Determine memory salience using the hierarchy:\n"
            "1. APPLY the salience hierarchy: decisions (binding choices with rationale) > corrections (overrides of prior beliefs) > patterns (recurring structure) > facts (single observations).\n"
            "2. CLASSIFY the candidate memory: which tier does it belong to?\n"
            "3. ASSESS uniqueness: is this already captured? Would losing it cause repeated work or repeated mistakes?\n"
            "4. ASSESS applicability: is this likely to be relevant in future sessions? Or is it context-specific and disposable?\n"
            "5. VERDICT: capture with high salience / capture as low-salience fact / discard as session-specific / consolidate with existing record.\n"
            "Output: salience_tier, uniqueness_check, applicability_assessment, capture_verdict"
        ),
    },
    # MEM-03
    {
        "slug": "keep-merge-discard",
        "name": "Keep, Merge, or Discard",
        "family": "evaluative",
        "tier": "built-in",
        "description": "Decide for each memory candidate whether to keep it as new, merge it with existing knowledge, or discard it as redundant or superseded.",
        "activation_signals": [
            "keep or discard",
            "update existing",
            "merge knowledge",
            "redundant memory",
            "conflict with existing",
            "superseded",
        ],
        "archetype_affinity": {"analyst": 0.9, "researcher": 0.8},
        "mode_affinity": {"deliberative": 0.9, "procedural": 0.8},
        "composability": {"complements": ["salience-detection", "staleness-check"], "conflicts": []},
        "system_prompt": (
            "Decide whether to keep, merge, or discard each memory candidate:\n"
            "1. FOR EACH CANDIDATE: search for existing records that overlap or conflict.\n"
            "2. CLASSIFY conflict type: additive (adds new info), superseding (new info replaces old), contradicting (new info conflicts with old, both could be true in different contexts).\n"
            "3. APPLY the rule:\n"
            "   - KEEP: genuinely new with no overlap\n"
            "   - MERGE: additive or superseding — update the existing record\n"
            "   - DISCARD: exact duplicate or lower-quality version of existing knowledge\n"
            "4. FOR MERGES: state exactly what changes in the existing record.\n"
            "5. FOR CONTRADICTIONS: flag for human review rather than silently overwriting.\n"
            "Output: decision_table (candidate, conflict_type, decision, merge_changes), contradictions_for_review"
        ),
    },
    # MEM-04
    {
        "slug": "staleness-check",
        "name": "Staleness Check",
        "family": "evaluative",
        "tier": "built-in",
        "description": "Validate that memories retrieved from long-term storage are still valid given what has changed since they were captured.",
        "activation_signals": [
            "is this still valid",
            "outdated memory",
            "has this changed",
            "stale",
            "memory freshness",
            "still true",
            "recent changes affect this",
        ],
        "archetype_affinity": {"analyst": 0.9, "researcher": 0.8, "executor": 0.7},
        "mode_affinity": {"deliberative": 0.9, "procedural": 0.8},
        "composability": {"complements": ["keep-merge-discard", "freshness-assessment"], "conflicts": []},
        "system_prompt": (
            "Check whether retrieved memories are still valid:\n"
            "1. IDENTIFY the age of each retrieved memory: when was it captured or last updated?\n"
            "2. IDENTIFY change events: what has changed in the system, environment, or codebase since this memory was created?\n"
            "3. ASSESS impact: do any of the changes invalidate or significantly modify this memory?\n"
            "4. CLASSIFY: current (still valid) / potentially stale (needs verification) / stale (known to be outdated).\n"
            "5. ACTION: current — use. Potentially stale — verify before relying. Stale — update or discard.\n"
            "Output: memory_staleness_map (memory, age, change_events, classification, action), stale_memories_to_update"
        ),
    },
    # MEM-05
    {
        "slug": "context-reconstruction-budget",
        "name": "Context Reconstruction Budget",
        "family": "evaluative",
        "tier": "built-in",
        "description": "Allocate context reconstruction effort across memory types to balance completeness with token efficiency.",
        "activation_signals": [
            "reconstruct context",
            "what to load",
            "context budget",
            "memory loading",
            "what to recall",
            "loading context for task",
        ],
        "archetype_affinity": {"executor": 0.8, "analyst": 0.7},
        "mode_affinity": {"procedural": 0.9, "deliberative": 0.7},
        "composability": {"complements": ["context-budget", "memory-operation-type"], "conflicts": []},
        "system_prompt": (
            "Allocate context reconstruction budget by memory type:\n"
            "1. DEFINE the task requiring context: what is being reconstructed for?\n"
            "2. ENUMERATE memory types: decisions, corrections, patterns, facts, code context, external knowledge.\n"
            "3. ALLOCATE 100 budget points: suggested baseline (40% decisions, 30% corrections/patterns, 20% code context, 10% external facts).\n"
            "4. ADJUST for this task: which memory types are most relevant here? Shift budget accordingly.\n"
            "5. DEFINE the stopping point: at what level of reconstruction is context sufficient to begin the task without critical gaps?\n"
            "Output: reconstruction_allocation (memory_type, budget_percent, items_to_load), task_specific_adjustments, sufficiency_threshold"
        ),
    },
    # MEM-06
    {
        "slug": "reconstruction-completeness",
        "name": "Reconstruction Completeness",
        "family": "adversarial",
        "tier": "built-in",
        "description": "Critique whether context reconstruction has loaded the right memories for the task, or whether it is missing critical context that will cause errors.",
        "activation_signals": [
            "did we reconstruct the right context",
            "context complete",
            "missing context",
            "reconstruction check",
            "right memories loaded",
            "context gap",
        ],
        "archetype_affinity": {"analyst": 0.9, "researcher": 0.8, "executor": 0.7},
        "mode_affinity": {"reflective": 0.9, "deliberative": 0.8},
        "composability": {"complements": ["context-reconstruction-budget", "gap-detection"], "conflicts": []},
        "system_prompt": (
            "Critique context reconstruction completeness:\n"
            "1. REVIEW what was loaded: list all memories and context currently in the reconstruction.\n"
            "2. MAP to task requirements: for each requirement of the task, is there supporting context in the reconstruction?\n"
            "3. FIND critical gaps: what does the task need that is not in the reconstruction? Would proceeding without it cause errors or rework?\n"
            "4. CHECK for recency: are the most recent versions of relevant decisions and corrections loaded?\n"
            "5. VERDICT: reconstruction complete / retrieve these specific missing items / cannot proceed with current reconstruction.\n"
            "Output: reconstruction_inventory, requirement_coverage_map, critical_gaps, recency_check, completeness_verdict"
        ),
    },
    # ═══════════════════════════════════════════════════════════════
    # COORDINATION (6)
    # ═══════════════════════════════════════════════════════════════
    # COO-01
    {
        "slug": "work-splitting",
        "name": "Work Splitting",
        "family": "diagnostic",
        "tier": "built-in",
        "description": "Decompose work across agents with clean boundaries and minimal overlap to enable parallel execution without coordination overhead.",
        "activation_signals": [
            "split the work",
            "decompose for agents",
            "parallel agents",
            "divide work",
            "assign to agents",
            "work distribution",
        ],
        "archetype_affinity": {"advisor": 0.9, "analyst": 0.8, "executor": 0.7},
        "mode_affinity": {"deliberative": 0.9, "procedural": 0.8},
        "composability": {"complements": ["ownership-design", "conflict-anticipation"], "conflicts": []},
        "system_prompt": (
            "Decompose work for parallel agent execution:\n"
            "1. IDENTIFY the natural seams: where does the work divide into independent pieces with minimal data sharing?\n"
            "2. VERIFY independence: for each proposed split, what does Agent A need from Agent B? Minimize cross-dependencies.\n"
            "3. DEFINE interfaces: what are the exact outputs that agents must produce for the merge to work?\n"
            "4. SIZE the chunks: are work chunks roughly comparable in complexity? Avoid one agent waiting on another.\n"
            "5. IDENTIFY risks: where is the split most likely to cause integration problems at merge time?\n"
            "Output: work_chunks (agent, scope, inputs, outputs, dependencies), interface_definitions, split_risks"
        ),
    },
    # COO-02
    {
        "slug": "ownership-design",
        "name": "Ownership Design",
        "family": "evaluative",
        "tier": "built-in",
        "description": "Assign clear ownership boundaries to agents or teams to prevent overlapping work and conflicting changes.",
        "activation_signals": [
            "who owns what",
            "ownership",
            "responsibility assignment",
            "clear ownership",
            "prevent overlap",
            "who decides",
            "own this piece",
        ],
        "archetype_affinity": {"advisor": 0.9, "analyst": 0.8},
        "mode_affinity": {"deliberative": 0.9, "procedural": 0.8},
        "composability": {"complements": ["work-splitting", "conflict-anticipation"], "conflicts": []},
        "system_prompt": (
            "Design clear ownership boundaries:\n"
            "1. ENUMERATE all work items and system components requiring ownership.\n"
            "2. ASSIGN exactly one owner to each item: no shared ownership. If multiple parties want to own something, force a decision.\n"
            "3. DEFINE ownership rights: owner makes decisions about their component. Non-owners can propose but not decide.\n"
            "4. IDENTIFY contested areas: where will agents try to modify the same thing? Those are ownership conflicts.\n"
            "5. RESOLVE conflicts: for each contested area, assign single ownership and define how non-owners interface with it.\n"
            "Output: ownership_map (component, owner, decision_rights), contested_areas, conflict_resolutions"
        ),
    },
    # COO-03
    {
        "slug": "conflict-anticipation",
        "name": "Conflict Anticipation",
        "family": "evaluative",
        "tier": "built-in",
        "description": "Identify where parallel agents will collide on shared state or resources and choose a coordination design that prevents the conflict.",
        "activation_signals": [
            "where will agents conflict",
            "parallel conflict",
            "shared state",
            "race condition",
            "collision",
            "coordination conflict",
            "agents competing",
        ],
        "archetype_affinity": {"executor": 0.9, "analyst": 0.8, "advisor": 0.7},
        "mode_affinity": {"deliberative": 0.9, "exploratory": 0.7},
        "composability": {"complements": ["work-splitting", "deadlock-detection"], "conflicts": []},
        "system_prompt": (
            "Anticipate coordination conflicts before parallel execution:\n"
            "1. LIST all shared resources: files, DB tables, APIs, configuration, in-memory state that multiple agents will access.\n"
            "2. CLASSIFY access patterns: read-only (safe to share), write-once (safe if non-overlapping), read-write (conflict risk).\n"
            "3. IDENTIFY conflict points: shared resources with read-write access from multiple agents are conflict candidates.\n"
            "4. CHOOSE coordination design: lock/serialize access, partition the resource, use merge-friendly formats, or sequence the agents.\n"
            "5. VERIFY the design: does the chosen coordination design prevent the conflict without creating a bottleneck?\n"
            "Output: shared_resource_map, conflict_candidates, coordination_designs (resource, design, rationale), bottleneck_risks"
        ),
    },
    # COO-04
    {
        "slug": "merge-point-identification",
        "name": "Merge Point Identification",
        "family": "evaluative",
        "tier": "built-in",
        "description": "Identify where parallel streams must converge, define the merge conditions, and ensure merge points are clearly specified before parallel execution begins.",
        "activation_signals": [
            "merge point",
            "where do streams join",
            "convergence",
            "integration point",
            "parallel to sequential",
            "collect results",
            "join agents",
        ],
        "archetype_affinity": {"executor": 0.9, "advisor": 0.8, "analyst": 0.7},
        "mode_affinity": {"procedural": 0.9, "deliberative": 0.8},
        "composability": {"complements": ["work-splitting", "parallelization-assessment"], "conflicts": []},
        "system_prompt": (
            "Identify and define merge points for parallel streams:\n"
            "1. MAP parallel streams: what agents are running, and what are they producing?\n"
            "2. IDENTIFY merge points: where must parallel outputs be combined before work can continue?\n"
            "3. DEFINE merge conditions: what must each stream have produced before the merge can occur?\n"
            "4. DEFINE merge mechanics: how are outputs combined? (append, deduplicate, synthesize, vote, hand off to synthesizer)\n"
            "5. DEFINE merge failure response: what happens if one stream fails to produce its required output?\n"
            "Output: parallel_streams, merge_points (location, inputs_required, mechanics), merge_conditions, failure_responses"
        ),
    },
    # COO-05
    {
        "slug": "agent-load-balancing",
        "name": "Agent Load Balancing",
        "family": "evaluative",
        "tier": "built-in",
        "description": "Distribute work fairly across agents so no single agent becomes the bottleneck while others wait.",
        "activation_signals": [
            "load balance",
            "fair distribution",
            "agent overloaded",
            "workload balance",
            "not one agent doing all",
            "distribute evenly",
            "agent capacity",
        ],
        "archetype_affinity": {"advisor": 0.9, "analyst": 0.8, "executor": 0.7},
        "mode_affinity": {"procedural": 0.9, "deliberative": 0.8},
        "composability": {"complements": ["work-splitting", "bottleneck-analysis"], "conflicts": []},
        "system_prompt": (
            "Balance workload across agents:\n"
            "1. ESTIMATE effort for each work chunk: relative complexity and duration.\n"
            "2. MAP chunks to agents: which agent is assigned which chunk?\n"
            "3. COMPUTE load ratio: total effort per agent. Are they roughly comparable?\n"
            "4. IDENTIFY the bottleneck agent: which agent has the most work? Will it become the critical path?\n"
            "5. REBALANCE: can work be shifted from the overloaded agent to underloaded agents without creating dependencies?\n"
            "Output: effort_per_agent (agent, chunks, total_effort), load_ratio, bottleneck_agent, rebalancing_options"
        ),
    },
    # COO-06
    {
        "slug": "deadlock-detection",
        "name": "Deadlock Detection",
        "family": "adversarial",
        "tier": "built-in",
        "description": "Detect circular dependencies where agents are waiting on each other's outputs, which would halt all progress.",
        "activation_signals": [
            "deadlock",
            "circular dependency",
            "agents waiting on each other",
            "stuck",
            "circular wait",
            "agents blocked",
            "dependency cycle",
        ],
        "archetype_affinity": {"executor": 0.9, "analyst": 0.8, "advisor": 0.7},
        "mode_affinity": {"deliberative": 0.9, "reflective": 0.8},
        "composability": {"complements": ["conflict-anticipation", "dependency-ordering"], "conflicts": []},
        "system_prompt": (
            "Detect and resolve deadlocks in agent coordination:\n"
            "1. MAP wait dependencies: for each agent, what outputs from other agents does it need before it can proceed?\n"
            "2. BUILD the wait graph: draw directed edges from 'waiting agent' to 'agent being waited on.'\n"
            "3. DETECT cycles: is there any cycle in the wait graph? A cycle = a deadlock.\n"
            "4. FOR EACH CYCLE: identify which dependency can be broken. Which agent can produce a partial output that unblocks the cycle?\n"
            "5. RESOLVE: redesign the dependency to eliminate the cycle. Either reorder tasks, remove a dependency, or introduce a stub.\n"
            "Output: wait_graph, cycle_detection (cycle_exists yes/no, cycles_found), resolution_per_cycle, updated_dependency_design"
        ),
    },
    # ═══════════════════════════════════════════════════════════════
    # TOOL (6)
    # ═══════════════════════════════════════════════════════════════
    # TOO-01
    {
        "slug": "tool-inventory-assessment",
        "name": "Tool Inventory Assessment",
        "family": "diagnostic",
        "tier": "built-in",
        "description": "Frame available tools and their actual capabilities to prevent misuse of tools whose limitations aren't understood.",
        "activation_signals": [
            "what tools are available",
            "tool inventory",
            "what can I use",
            "available capabilities",
            "tool assessment",
            "what tools do I have",
        ],
        "archetype_affinity": {"executor": 0.9, "analyst": 0.7, "researcher": 0.7},
        "mode_affinity": {"procedural": 0.9, "deliberative": 0.7},
        "composability": {"complements": ["task-tool-matching", "limitation-awareness"], "conflicts": []},
        "system_prompt": (
            "Assess the available tool inventory:\n"
            "1. ENUMERATE all available tools: name, category, and primary function.\n"
            "2. CHARACTERIZE each tool's actual capabilities: what can it reliably do? Where does it produce unreliable or partial results?\n"
            "3. IDENTIFY tool gaps: is there a needed capability that no available tool provides?\n"
            "4. FLAG unfamiliar tools: which tools haven't been used before in this session? Their behavior under edge cases is uncertain.\n"
            "5. ESTABLISH tool priority: given the task ahead, rank tools by expected usefulness.\n"
            "Output: tool_inventory (tool, capabilities, limitations, familiarity), gap_list, priority_ranking"
        ),
    },
    # TOO-02
    {
        "slug": "task-tool-matching",
        "name": "Task-Tool Matching",
        "family": "evaluative",
        "tier": "built-in",
        "description": "Match tools to tasks explicitly to prevent using over-powered or inappropriate tools for simple operations.",
        "activation_signals": [
            "which tool for this",
            "right tool",
            "tool selection",
            "match tool to task",
            "don't use a hammer for",
            "appropriate tool",
        ],
        "archetype_affinity": {"executor": 0.9, "analyst": 0.7},
        "mode_affinity": {"procedural": 0.9, "deliberative": 0.7},
        "composability": {"complements": ["tool-inventory-assessment", "tool-chain-composition"], "conflicts": []},
        "system_prompt": (
            "Match tools to subtasks explicitly:\n"
            "1. ENUMERATE subtasks: break the overall task into specific operations.\n"
            "2. FOR EACH SUBTASK: identify the best tool. Apply the principle of minimal capability — use the simplest tool that works.\n"
            "3. FLAG mismatches: where is an over-powered tool being used for a simple operation? Where is an insufficient tool being used for a complex one?\n"
            "4. CHECK tool availability: is the best tool actually available, or does a fallback need to be identified?\n"
            "5. DOCUMENT the mapping: produce an explicit subtask→tool map before executing.\n"
            "Output: task_tool_map (subtask, best_tool, fallback, justification), mismatches, availability_check"
        ),
    },
    # TOO-03
    {
        "slug": "tool-chain-composition",
        "name": "Tool Chain Composition",
        "family": "evaluative",
        "tier": "built-in",
        "description": "Design the sequence of tool calls to complete a multi-step operation efficiently and correctly.",
        "activation_signals": [
            "tool chain",
            "sequence of tools",
            "tool pipeline",
            "order of tool calls",
            "multi-step tool use",
            "tool composition",
        ],
        "archetype_affinity": {"executor": 0.9, "analyst": 0.7},
        "mode_affinity": {"procedural": 0.9, "deliberative": 0.7},
        "composability": {"complements": ["task-tool-matching", "verification-approach"], "conflicts": []},
        "system_prompt": (
            "Design the tool chain for this multi-step operation:\n"
            "1. DEFINE the goal state: what does successful completion of this operation look like?\n"
            "2. IDENTIFY required steps: what must happen, in what order, to reach the goal state?\n"
            "3. ASSIGN tools: for each step, select the tool that best executes it.\n"
            "4. DEFINE data flow: what output does each step produce? Is that output in the right format for the next step?\n"
            "5. IDENTIFY failure points: where in the chain is a tool most likely to fail? Define what to do if it does.\n"
            "Output: tool_chain (step, tool, input, output, format), data_flow_map, failure_points, fallback_steps"
        ),
    },
    # TOO-04
    {
        "slug": "limitation-awareness",
        "name": "Limitation Awareness",
        "family": "evaluative",
        "tier": "built-in",
        "description": "Validate that the plan accounts for what tools cannot do, especially silent failure modes where incorrect output is returned without error.",
        "activation_signals": [
            "tool limitations",
            "what can't this tool do",
            "silent failure",
            "tool edge cases",
            "tool constraints",
            "where tools fail",
        ],
        "archetype_affinity": {"executor": 0.9, "analyst": 0.8, "researcher": 0.7},
        "mode_affinity": {"deliberative": 0.9, "procedural": 0.8},
        "composability": {"complements": ["tool-inventory-assessment", "fallback-strategy"], "conflicts": []},
        "system_prompt": (
            "Assess tool limitations before relying on them:\n"
            "1. LIST all tools being used in this operation.\n"
            "2. FOR EACH TOOL: identify what it CANNOT do reliably. Focus on silent failures (wrong output without error) over loud failures (exception or timeout).\n"
            "3. IDENTIFY silent failure modes: what inputs or conditions would cause this tool to return an incorrect result without indicating failure?\n"
            "4. DESIGN detection: how would you detect if a tool silently failed? Can output be validated against expected shape or bounds?\n"
            "5. UPDATE the plan: add explicit validation steps after any tool call prone to silent failure.\n"
            "Output: limitation_map (tool, cant_do, silent_failure_modes), detection_strategies, plan_updates"
        ),
    },
    # TOO-05
    {
        "slug": "tool-cost-budget",
        "name": "Tool Cost Budget",
        "family": "evaluative",
        "tier": "built-in",
        "description": "Allocate tool usage budget by deciding which API calls are worth their cost and which can be replaced by cheaper alternatives.",
        "activation_signals": [
            "tool cost",
            "API cost",
            "expensive call",
            "tool budget",
            "skip this call",
            "cost per tool call",
            "optimize tool usage",
        ],
        "archetype_affinity": {"advisor": 0.8, "executor": 0.9, "analyst": 0.7},
        "mode_affinity": {"procedural": 0.9, "deliberative": 0.7},
        "composability": {"complements": ["task-tool-matching", "cost-aware-routing"], "conflicts": []},
        "system_prompt": (
            "Budget tool usage by cost-value ratio:\n"
            "1. LIST all planned tool calls.\n"
            "2. ESTIMATE cost per call: relative cost (cheap / moderate / expensive).\n"
            "3. ESTIMATE value per call: how critical is this tool call to the overall task? (critical / useful / optional)\n"
            "4. APPLY the cut rule: expensive+optional calls are the first candidates for elimination or replacement.\n"
            "5. IDENTIFY cheaper alternatives: for each expensive call, is there a cheaper tool or cached result that provides sufficient quality?\n"
            "Output: tool_cost_table (tool_call, cost, value, cut_candidate), elimination_candidates, cheap_alternatives"
        ),
    },
    # TOO-06
    {
        "slug": "fallback-strategy",
        "name": "Fallback Strategy",
        "family": "adversarial",
        "tier": "built-in",
        "description": "Design a fallback plan for when the preferred tool fails, ensuring operations can continue even when tools are unavailable or producing errors.",
        "activation_signals": [
            "if the tool fails",
            "fallback",
            "backup plan",
            "tool failure",
            "what if unavailable",
            "contingency",
            "tool error handling",
        ],
        "archetype_affinity": {"executor": 0.9, "advisor": 0.8, "analyst": 0.6},
        "mode_affinity": {"deliberative": 0.9, "procedural": 0.8},
        "composability": {"complements": ["limitation-awareness", "tool-chain-composition"], "conflicts": []},
        "system_prompt": (
            "Design fallback strategies for tool failures:\n"
            "1. LIST all tools with single-point-of-failure risk in the current plan.\n"
            "2. FOR EACH TOOL: define the failure scenario (unavailable, timeout, wrong output, rate limited).\n"
            "3. DESIGN the fallback: what alternative can be used when this tool fails? Is there a degraded-but-functional path?\n"
            "4. DEFINE the trigger: what specifically triggers switching to the fallback? Don't switch prematurely.\n"
            "5. ASSESS fallback quality: is the fallback path acceptable, or does it produce results that would need to be discarded?\n"
            "Output: fallback_table (tool, failure_scenario, fallback, trigger_condition, fallback_quality), no_fallback_risks"
        ),
    },
    # ═══════════════════════════════════════════════════════════════
    # COMMUNICATION AGENTIC (6)
    # ═══════════════════════════════════════════════════════════════
    # AGC-01
    {
        "slug": "handoff-structuring",
        "name": "Handoff Structuring",
        "family": "diagnostic",
        "tier": "built-in",
        "description": "Structure what the next agent needs to know: the essential context that must transfer for the handoff to succeed.",
        "activation_signals": [
            "handoff",
            "what to pass",
            "next agent needs",
            "context transfer",
            "agent handoff",
            "pass to next",
            "what to include in handoff",
        ],
        "archetype_affinity": {"executor": 0.9, "advisor": 0.8, "analyst": 0.7},
        "mode_affinity": {"procedural": 0.9, "deliberative": 0.8},
        "composability": {"complements": ["context-passing", "expectation-framing"], "conflicts": []},
        "system_prompt": (
            "Structure the agent handoff:\n"
            "1. IDENTIFY the receiving agent: who receives this handoff, and what is their task?\n"
            "2. ENUMERATE required context: what background, decisions, constraints, and prior work does the receiver need to succeed?\n"
            "3. DISTINGUISH essential from useful: what is absolutely required vs. nice-to-have? Include only essential.\n"
            "4. DEFINE the output expected: what should the receiving agent produce? State the output format and success criteria.\n"
            "5. FLAG open questions: what is the receiving agent likely to be uncertain about? Surface these explicitly rather than leaving them to be discovered.\n"
            "Output: handoff_package (required_context, task_definition, output_format, success_criteria), open_questions"
        ),
    },
    # AGC-02
    {
        "slug": "context-passing",
        "name": "Context Passing",
        "family": "evaluative",
        "tier": "built-in",
        "description": "Select what context to include in an agent handoff: essential context vs noise, sized for the receiving agent's needs.",
        "activation_signals": [
            "what to include in context",
            "context for next agent",
            "pass context",
            "context size",
            "what to send",
            "minimal context transfer",
        ],
        "archetype_affinity": {"executor": 0.9, "analyst": 0.7},
        "mode_affinity": {"procedural": 0.9, "deliberative": 0.7},
        "composability": {"complements": ["handoff-structuring", "context-selection"], "conflicts": []},
        "system_prompt": (
            "Select context to pass in this agent handoff:\n"
            "1. IDENTIFY what the receiving agent needs: decisions made, constraints, scope, output format required.\n"
            "2. FILTER for signal: for each context item, would the receiving agent's output degrade without it? If not, cut it.\n"
            "3. APPLY conciseness: summarize where possible. The receiving agent doesn't need full transcripts — it needs synthesized facts.\n"
            "4. CHECK for inadvertent bias: is any included context framing the receiving agent's thinking in ways that limit their independence?\n"
            "5. SIZE the package: is the total context within the receiving agent's effective processing range?\n"
            "Output: context_package (item, reason_included), cuts (item, reason_excluded), total_size_assessment"
        ),
    },
    # AGC-03
    {
        "slug": "communication-channel",
        "name": "Communication Channel",
        "family": "evaluative",
        "tier": "built-in",
        "description": "Choose how to communicate with other agents: spinoff subagent, shared memory, direct message, or tool call.",
        "activation_signals": [
            "how to communicate with agent",
            "spinoff vs message",
            "shared memory",
            "agent communication",
            "how to send",
            "direct message vs subagent",
        ],
        "archetype_affinity": {"executor": 0.9, "advisor": 0.8, "analyst": 0.6},
        "mode_affinity": {"procedural": 0.9, "deliberative": 0.8},
        "composability": {"complements": ["handoff-structuring", "context-passing"], "conflicts": []},
        "system_prompt": (
            "Choose the right communication channel between agents:\n"
            "1. DEFINE the communication need: what must be conveyed, to whom, and with what timing?\n"
            "2. EVALUATE channel options:\n"
            "   - SPINOFF SUBAGENT: when the receiving agent needs to act independently and return results\n"
            "   - SHARED MEMORY: when multiple agents need read access to the same state over time\n"
            "   - DIRECT MESSAGE: when synchronous coordination is needed\n"
            "   - TOOL CALL: when a specific capability needs to be invoked\n"
            "3. MATCH need to channel: which channel fits the timing, dependency, and independence requirements?\n"
            "4. ASSESS overhead: is the chosen channel's coordination cost proportional to the value of the communication?\n"
            "Output: communication_need, channel_options (channel, fit_score), chosen_channel, overhead_assessment"
        ),
    },
    # AGC-04
    {
        "slug": "expectation-framing",
        "name": "Expectation Framing",
        "family": "evaluative",
        "tier": "built-in",
        "description": "Validate that the receiving agent understands what is expected: scope, output format, success criteria, and constraints.",
        "activation_signals": [
            "does the agent know what's expected",
            "expectation setting",
            "clear brief",
            "agent understands task",
            "spec for agent",
            "does it know the goal",
        ],
        "archetype_affinity": {"advisor": 0.9, "executor": 0.8, "analyst": 0.7},
        "mode_affinity": {"procedural": 0.9, "deliberative": 0.8},
        "composability": {"complements": ["handoff-structuring", "spec-quality"], "conflicts": []},
        "system_prompt": (
            "Frame expectations for the receiving agent:\n"
            "1. STATE the task: what exactly is the agent being asked to do? Single clear action, not a vague direction.\n"
            "2. DEFINE scope boundaries: what is explicitly in scope? What is out of scope?\n"
            "3. SPECIFY output format: what should the output look like? Structure, length, format, schema if applicable.\n"
            "4. STATE success criteria: how will the orchestrating agent evaluate whether the output is correct?\n"
            "5. IDENTIFY constraints: what must the agent NOT do? What resources, approaches, or areas are off-limits?\n"
            "Output: task_statement, scope_boundaries, output_format_spec, success_criteria, constraints"
        ),
    },
    # AGC-05
    {
        "slug": "status-granularity",
        "name": "Status Granularity",
        "family": "evaluative",
        "tier": "built-in",
        "description": "Calibrate status update detail to the recipient: PM/human gets outcome summary, peer agent gets operational detail, sub-agent gets specific instructions.",
        "activation_signals": [
            "status update",
            "how much detail in status",
            "update granularity",
            "what to report",
            "status for PM vs agent",
            "progress reporting",
        ],
        "archetype_affinity": {"executor": 0.8, "advisor": 0.9},
        "mode_affinity": {"procedural": 0.9, "deliberative": 0.7},
        "composability": {"complements": ["granularity-calibration", "communication-channel"], "conflicts": []},
        "system_prompt": (
            "Calibrate status update granularity to the recipient:\n"
            "1. IDENTIFY the recipient tier: PM/human (decision-making), orchestrating agent (coordination), peer agent (collaboration), sub-agent (instruction).\n"
            "2. APPLY granularity rule:\n"
            "   - PM/human: outcome + blockers + next milestone. No operational detail.\n"
            "   - Orchestrating agent: completion status + output location + unresolved dependencies.\n"
            "   - Peer agent: current state + what's needed from them.\n"
            "   - Sub-agent: precise state + specific next instruction.\n"
            "3. VERIFY necessity: does the recipient actually need this update now? If not, defer.\n"
            "4. CHECK for noise: is any included information not actionable for this recipient?\n"
            "Output: status_draft (outcome, blockers, next_step, recipient_specific_details), noise_removed"
        ),
    },
    # AGC-06
    {
        "slug": "feedback-loop-design",
        "name": "Feedback Loop Design",
        "family": "adversarial",
        "tier": "built-in",
        "description": "Critique the communication design for missing return paths: can the receiving agent ask for clarification, report errors, or signal completion?",
        "activation_signals": [
            "can the agent respond",
            "feedback loop",
            "return path",
            "can it ask questions",
            "two-way communication",
            "agent clarification",
            "how does agent report back",
        ],
        "archetype_affinity": {"advisor": 0.9, "executor": 0.8, "analyst": 0.7},
        "mode_affinity": {"deliberative": 0.9, "reflective": 0.8},
        "composability": {"complements": ["handoff-structuring", "communication-channel"], "conflicts": []},
        "system_prompt": (
            "Critique the communication design for missing feedback loops:\n"
            "1. AUDIT return paths: can the receiving agent send results back? Can it signal completion or failure?\n"
            "2. CHECK clarification path: if the receiving agent encounters ambiguity, can it ask a question? To whom?\n"
            "3. CHECK error reporting: if the receiving agent encounters a blocker, how does it escalate?\n"
            "4. ASSESS loop completeness: is there a mechanism for the orchestrator to know when the agent is done, stuck, or has produced output?\n"
            "5. IDENTIFY dead ends: where could an agent fail silently with no way for the orchestrator to detect it?\n"
            "Output: return_path_audit, clarification_path, error_path, loop_completeness_verdict, silent_failure_risks"
        ),
    },
    # ═══════════════════════════════════════════════════════════════
    # OPERATIONAL (6)
    # ═══════════════════════════════════════════════════════════════
    # OPS-01
    {
        "slug": "workflow-modeling",
        "name": "Workflow Modeling",
        "family": "diagnostic",
        "tier": "built-in",
        "description": "Map the process steps and gates to understand the workflow before optimizing or debugging it.",
        "activation_signals": [
            "map the process",
            "workflow",
            "process steps",
            "how does this work",
            "process modeling",
            "document the flow",
            "sequence of operations",
        ],
        "archetype_affinity": {"analyst": 0.9, "executor": 0.8, "advisor": 0.7},
        "mode_affinity": {"deliberative": 0.9, "exploratory": 0.7},
        "composability": {"complements": ["process-bottleneck", "handoff-completeness"], "conflicts": []},
        "system_prompt": (
            "Model the workflow to understand it before changing it:\n"
            "1. ENUMERATE all steps in the workflow: every action, decision point, and handoff.\n"
            "2. MAP the sequence: what is the order? Where are the branches and decision gates?\n"
            "3. IDENTIFY inputs and outputs: for each step, what comes in and what goes out?\n"
            "4. FIND the gates: where does work pause for review, approval, or validation before proceeding?\n"
            "5. CHARACTERIZE the workflow: is it linear, branching, iterative, or event-driven?\n"
            "Output: workflow_map (step, type, input, output, gate yes/no), structure_characterization"
        ),
    },
    # OPS-02
    {
        "slug": "process-bottleneck",
        "name": "Process Bottleneck",
        "family": "evaluative",
        "tier": "built-in",
        "description": "Identify where work gets stuck in a workflow to direct optimization effort at the actual constraint.",
        "activation_signals": [
            "where does work get stuck",
            "process slow",
            "workflow bottleneck",
            "what slows us down",
            "where does work pile up",
            "operational constraint",
        ],
        "archetype_affinity": {"analyst": 0.9, "advisor": 0.8, "executor": 0.7},
        "mode_affinity": {"deliberative": 0.9, "exploratory": 0.7},
        "composability": {"complements": ["workflow-modeling", "bottleneck-analysis"], "conflicts": []},
        "system_prompt": (
            "Identify where work gets stuck in the process:\n"
            "1. REVIEW the workflow map: at each step, what is the observed or estimated throughput?\n"
            "2. FIND accumulation points: where does work queue up waiting to be processed?\n"
            "3. IDENTIFY the primary bottleneck: which step has the lowest throughput? This limits the entire workflow.\n"
            "4. DISTINGUISH types: is this a capacity bottleneck (not enough resource), quality bottleneck (rework required), or coordination bottleneck (waiting for approvals/handoffs)?\n"
            "5. DESIGN the fix: what intervention would most improve overall workflow throughput? Address the bottleneck type.\n"
            "Output: throughput_per_step, accumulation_points, primary_bottleneck (step, type), intervention_design"
        ),
    },
    # OPS-03
    {
        "slug": "workflow-optimization",
        "name": "Workflow Optimization",
        "family": "evaluative",
        "tier": "built-in",
        "description": "Choose whether to parallelize, reorder, or eliminate steps to improve workflow efficiency.",
        "activation_signals": [
            "optimize workflow",
            "improve process",
            "faster workflow",
            "streamline",
            "eliminate steps",
            "reorder process",
            "workflow improvement",
        ],
        "archetype_affinity": {"analyst": 0.9, "advisor": 0.8, "executor": 0.7},
        "mode_affinity": {"deliberative": 0.9, "procedural": 0.8},
        "composability": {"complements": ["process-bottleneck", "parallelization-assessment"], "conflicts": []},
        "system_prompt": (
            "Optimize the workflow by choosing the right intervention:\n"
            "1. AUDIT the current workflow: list all steps with their purpose and estimated cost.\n"
            "2. CATEGORIZE optimization levers: ELIMINATE (step adds no value), PARALLELIZE (step can run concurrently with another), REORDER (step would cost less or block less if moved).\n"
            "3. APPLY each lever: for each step, which optimization applies? Can any step be eliminated without losing output quality?\n"
            "4. ESTIMATE improvement: for each proposed change, how much does it reduce total workflow duration or cost?\n"
            "5. SEQUENCE changes: which optimization to implement first? Start with the highest-impact, lowest-disruption changes.\n"
            "Output: step_audit (step, lever, rationale), optimized_workflow, improvement_estimates, implementation_sequence"
        ),
    },
    # OPS-04
    {
        "slug": "handoff-completeness",
        "name": "Handoff Completeness",
        "family": "evaluative",
        "tier": "built-in",
        "description": "Validate that the next step in a workflow has everything it needs to proceed without coming back for more information.",
        "activation_signals": [
            "does next step have what it needs",
            "handoff complete",
            "pass everything",
            "what's needed for next step",
            "workflow handoff",
            "complete transfer",
        ],
        "archetype_affinity": {"executor": 0.9, "advisor": 0.8, "analyst": 0.7},
        "mode_affinity": {"procedural": 0.9, "deliberative": 0.8},
        "composability": {"complements": ["workflow-modeling", "context-passing"], "conflicts": []},
        "system_prompt": (
            "Validate handoff completeness before passing to the next step:\n"
            "1. IDENTIFY the next step's inputs: what does it need to execute?\n"
            "2. AUDIT what's being handed off: does the current handoff contain all required inputs?\n"
            "3. CHECK for implicit requirements: what does the next step need that hasn't been explicitly stated? (context, format, naming conventions, prior decisions)\n"
            "4. IDENTIFY blockers: what missing input would cause the next step to stall or come back to ask?\n"
            "5. COMPLETE or DEFER: either add the missing input now or explicitly defer and document why.\n"
            "Output: required_inputs (item, present yes/no), implicit_requirements, blockers, completeness_verdict"
        ),
    },
    # OPS-05
    {
        "slug": "cadence-awareness",
        "name": "Cadence Awareness",
        "family": "evaluative",
        "tier": "built-in",
        "description": "Match rhythm to work type: sprint work versus daily standup work versus ad-hoc reactive work each require different scheduling and energy.",
        "activation_signals": [
            "cadence",
            "rhythm",
            "sprint vs daily",
            "scheduling",
            "when to do this",
            "work rhythm",
            "periodic vs ad-hoc",
        ],
        "archetype_affinity": {"advisor": 0.9, "analyst": 0.7},
        "mode_affinity": {"deliberative": 0.8, "procedural": 0.9},
        "composability": {"complements": ["effort-distribution", "attention-budget"], "conflicts": []},
        "system_prompt": (
            "Match work cadence to work type:\n"
            "1. CLASSIFY each work type: strategic (monthly/quarterly), project (sprint cadence), operational (daily/weekly), reactive (ad-hoc, interrupt-driven).\n"
            "2. ASSESS current scheduling: is each work type scheduled at the right cadence?\n"
            "3. IDENTIFY cadence mismatches: where is ad-hoc work disrupting project cadence? Where is strategic work being scheduled too frequently?\n"
            "4. DESIGN the cadence: allocate time blocks by work type. Protect project cadence from reactive interrupts.\n"
            "5. SET escalation rules: when should ad-hoc work be allowed to break project cadence? Define the threshold.\n"
            "Output: work_cadence_map (work_type, current_cadence, recommended_cadence), mismatches, cadence_design, escalation_rules"
        ),
    },
    # OPS-06
    {
        "slug": "process-debt",
        "name": "Process Debt",
        "family": "adversarial",
        "tier": "built-in",
        "description": "Critique whether the current process is adding value or whether it is ceremony that exists from inertia, consuming effort without improving outcomes.",
        "activation_signals": [
            "is this process helping",
            "process overhead",
            "unnecessary ceremony",
            "process debt",
            "workflow bloat",
            "cut process",
            "process value",
        ],
        "archetype_affinity": {"advisor": 0.9, "analyst": 0.8},
        "mode_affinity": {"deliberative": 0.9, "reflective": 0.8},
        "composability": {"complements": ["workflow-optimization", "scope-negotiation"], "conflicts": []},
        "system_prompt": (
            "Critique the process for ceremony versus value:\n"
            "1. LIST all process steps and their stated purpose.\n"
            "2. FOR EACH STEP: when did this step get added, and why? Has the reason it was added changed?\n"
            "3. TEST each step: if we removed this step for 30 days, what would break? If nothing would break, it's a candidate for removal.\n"
            "4. IDENTIFY ceremony: steps that produce artifacts nobody reads, gates that always approve, reviews that rubber-stamp.\n"
            "5. PROPOSE cuts: which 3 steps could be eliminated or merged without degrading outcomes?\n"
            "Output: step_audit (step, original_purpose, still_needed yes/no, test_result), ceremony_list, cut_proposals"
        ),
    },
    # ═══════════════════════════════════════════════════════════════
    # DOMAIN-SPECIFIC (6)
    # ═══════════════════════════════════════════════════════════════
    # DOM-01
    {
        "slug": "discipline-activation",
        "name": "Discipline Activation",
        "family": "diagnostic",
        "tier": "built-in",
        "description": "Identify which of the 18 ACE disciplines are relevant to the current task to ensure the right domain intelligence is loaded.",
        "activation_signals": [
            "which disciplines apply",
            "relevant disciplines",
            "domain activation",
            "ACE disciplines",
            "what domains are relevant",
            "discipline selection",
        ],
        "archetype_affinity": {"analyst": 0.9, "advisor": 0.8, "researcher": 0.7},
        "mode_affinity": {"deliberative": 0.9, "exploratory": 0.7},
        "composability": {"complements": ["depth-calibration", "specialty-budget"], "conflicts": []},
        "system_prompt": (
            "Identify which ACE disciplines apply to this task:\n"
            "1. REVIEW the 23 disciplines: security, testing, ux, performance, devops, data, accessibility, documentation, ai_ml (quality); architecture, api_design, data_modeling, business_logic, integration, product_strategy (product); error_handling, observability, configuration, deployment, versioning, scale (operational); code_conventions, dependency_management (team).\n"
            "2. APPLY relevance test: for each discipline, does this task create, modify, or affect the concerns of that discipline?\n"
            "3. RANK by relevance: which discipline is primary for this task? Which are secondary?\n"
            "4. IDENTIFY cross-cutting concerns: which disciplines apply to almost everything (e.g., security, testing) and should always be considered?\n"
            "5. CONFIRM the selection: are you over-including disciplines out of caution, or have you actually assessed relevance?\n"
            "Output: discipline_assessment (discipline, relevant yes/no, relevance_reason), primary_discipline, secondary_disciplines, cross_cutting"
        ),
    },
    # DOM-02
    {
        "slug": "depth-calibration",
        "name": "Depth Calibration",
        "family": "evaluative",
        "tier": "built-in",
        "description": "Determine how deeply to load domain intelligence for each applicable discipline, balancing thoroughness against context budget.",
        "activation_signals": [
            "how deep",
            "depth of knowledge",
            "intelligence depth",
            "how much to load",
            "shallow vs deep",
            "calibrate depth",
            "expert vs overview",
        ],
        "archetype_affinity": {"analyst": 0.9, "researcher": 0.8, "advisor": 0.7},
        "mode_affinity": {"deliberative": 0.9, "procedural": 0.7},
        "composability": {"complements": ["discipline-activation", "specialty-budget"], "conflicts": []},
        "system_prompt": (
            "Calibrate intelligence depth for each active discipline:\n"
            "1. FOR EACH ACTIVE DISCIPLINE: assess the task's depth requirement. Does this task require expert-level knowledge (rare edge cases, optimization), working knowledge (standard patterns, common pitfalls), or awareness (it's relevant but not the focus)?\n"
            "2. ASSIGN depth levels: deep (load full specialty + best practices), standard (load patterns + common pitfalls), shallow (load key principles only).\n"
            "3. APPLY the budget constraint: total deep-loaded disciplines should not exceed 2-3 per task. Everything else at standard.\n"
            "4. IDENTIFY the primary discipline: which one gets the deepest loading?\n"
            "5. FLAG depth mismatches: where is deep loading being assigned out of habit rather than need?\n"
            "Output: depth_assignment (discipline, depth_level, justification), primary_discipline_depth, budget_usage"
        ),
    },
    # DOM-03
    {
        "slug": "adjacent-reasoning",
        "name": "Adjacent Reasoning",
        "family": "evaluative",
        "tier": "built-in",
        "description": "Identify which adjacent disciplines can inform the primary discipline to create cross-domain insights that single-discipline analysis would miss.",
        "activation_signals": [
            "adjacent disciplines",
            "cross-domain",
            "what else informs",
            "related disciplines",
            "cross-disciplinary",
            "discipline overlap",
            "informed by another domain",
        ],
        "archetype_affinity": {"researcher": 0.9, "analyst": 0.8, "advisor": 0.7},
        "mode_affinity": {"exploratory": 0.9, "deliberative": 0.8},
        "composability": {"complements": ["discipline-activation", "depth-calibration"], "conflicts": []},
        "system_prompt": (
            "Identify adjacent disciplines that can inform the primary analysis:\n"
            "1. STATE the primary discipline for this task.\n"
            "2. MAP adjacencies: which other disciplines share concerns with the primary? (e.g., security + authentication touch api_design + architecture; ux + accessibility frequently overlap)\n"
            "3. IDENTIFY the specific contribution: what insight does each adjacent discipline offer that the primary discipline alone would miss?\n"
            "4. ASSESS transfer value: for each adjacency, is the cross-domain insight high-value or merely tangential?\n"
            "5. SELECT adjacencies: include only those with high transfer value. Over-inclusion dilutes focus.\n"
            "Output: primary_discipline, adjacency_map (discipline, shared_concerns, specific_contribution, transfer_value), selected_adjacencies"
        ),
    },
    # DOM-04
    {
        "slug": "knowledge-freshness",
        "name": "Knowledge Freshness",
        "family": "evaluative",
        "tier": "built-in",
        "description": "Validate that loaded domain intelligence is current and applicable to the technology stack and context in use.",
        "activation_signals": [
            "is this knowledge current",
            "outdated practices",
            "relevant to our stack",
            "knowledge freshness",
            "applicable to us",
            "still valid for this tech",
        ],
        "archetype_affinity": {"researcher": 0.9, "analyst": 0.8, "advisor": 0.7},
        "mode_affinity": {"deliberative": 0.9, "reflective": 0.8},
        "composability": {"complements": ["depth-calibration", "freshness-assessment"], "conflicts": []},
        "system_prompt": (
            "Validate that loaded domain knowledge is current and applicable:\n"
            "1. IDENTIFY the knowledge sources: which best practices, patterns, or intelligence are being applied?\n"
            "2. ASSESS currency: is this knowledge current for the framework, language, and version in use? Fast-moving areas (LLM APIs, cloud-native patterns) become stale quickly.\n"
            "3. ASSESS applicability: does this knowledge apply to our specific context (scale, team size, tech stack, business model)?\n"
            "4. FLAG stale or inapplicable knowledge: what advice is technically correct in general but wrong for this specific context?\n"
            "5. IDENTIFY knowledge gaps: where is the loaded intelligence thin or missing for this specific context?\n"
            "Output: knowledge_audit (source, currency, applicability, stale yes/no), context_mismatches, knowledge_gaps"
        ),
    },
    # DOM-05
    {
        "slug": "specialty-budget",
        "name": "Specialty Budget",
        "family": "evaluative",
        "tier": "built-in",
        "description": "Select the 3 specialties that matter most for this task from within the relevant disciplines, preventing context bloat from loading too many.",
        "activation_signals": [
            "which specialties",
            "load specialties",
            "specialty selection",
            "3 specialties",
            "most relevant specialties",
            "specialty priority",
        ],
        "archetype_affinity": {"analyst": 0.9, "researcher": 0.8, "executor": 0.7},
        "mode_affinity": {"deliberative": 0.9, "procedural": 0.8},
        "composability": {"complements": ["discipline-activation", "depth-calibration"], "conflicts": []},
        "system_prompt": (
            "Select the most relevant specialties within active disciplines:\n"
            "1. ENUMERATE available specialties within each active discipline.\n"
            "2. APPLY the 3-specialty maximum: loading more than 3 specialties dilutes focus and bloats context. Force selection.\n"
            "3. ASSESS task-specialty fit: for each specialty, how directly does it address the specific problem at hand?\n"
            "4. RANK by fit: top 3 specialties by direct relevance to this task. No ties.\n"
            "5. JUSTIFY cuts: for specialties ranked 4+, explain why they were excluded despite being within an active discipline.\n"
            "Output: available_specialties, specialty_ranking (specialty, discipline, fit_score, rank), top_3_selected, cuts_justified"
        ),
    },
    # DOM-06
    {
        "slug": "expertise-gap-detection",
        "name": "Expertise Gap Detection",
        "family": "adversarial",
        "tier": "built-in",
        "description": "Identify where domain knowledge is thin or missing and the analysis is proceeding on insufficient expertise.",
        "activation_signals": [
            "knowledge thin",
            "expertise gap",
            "not deep enough",
            "where is knowledge weak",
            "domain knowledge missing",
            "expertise check",
            "what I don't know",
        ],
        "archetype_affinity": {"analyst": 0.9, "researcher": 0.9, "advisor": 0.7},
        "mode_affinity": {"reflective": 0.9, "deliberative": 0.8},
        "composability": {"complements": ["depth-calibration", "knowledge-freshness"], "conflicts": []},
        "system_prompt": (
            "Identify where domain expertise is insufficient:\n"
            "1. REVIEW each active discipline and specialty: where is the knowledge basis thin, uncertain, or general rather than specific?\n"
            "2. IDENTIFY confidence mismatches: where is confidence in recommendations higher than the evidence base warrants?\n"
            "3. FLAG unknown unknowns: what aspects of this domain are you likely to be missing because you don't know what you don't know?\n"
            "4. ASSESS impact: for each expertise gap, how much does it affect the quality of the analysis or recommendation?\n"
            "5. RESPOND: for high-impact gaps, flag explicitly rather than proceeding as if knowledge is sufficient. Recommend loading more specific intelligence.\n"
            "Output: expertise_audit (domain, confidence, evidence_basis, gap_severity), unknown_unknown_risks, high_impact_gaps, recommended_knowledge_loads"
        ),
    },
    # ═══════════════════════════════════════════════════════════════
    # DOMAIN LAYER — LAYER 1: PRODUCT STRATEGY (6)
    # ═══════════════════════════════════════════════════════════════
    {
        "slug": "product-strategy-fit",
        "name": "Product Strategy Fit",
        "family": "evaluative",
        "tier": "built-in",
        "description": "Evaluate whether a proposed product or feature solves a real problem worth solving, using jobs-to-be-done analysis, pain severity scoring, and competitive gap analysis.",
        "activation_signals": [
            "should we build this",
            "is this the right feature",
            "problem-solution fit",
            "user pain",
            "why build this",
            "product direction",
            "is this worth it",
        ],
        "archetype_affinity": {"advisor": 0.9, "analyst": 0.8, "researcher": 0.7},
        "mode_affinity": {"deliberative": 0.9, "exploratory": 0.8},
        "composability": {
            "complements": ["market-positioning", "prioritization-sequencing", "jobs-to-be-done"],
            "conflicts": [],
        },
        "system_prompt": (
            "Evaluate product-solution fit before committing to build:\n"
            "1. PROBLEM REALITY: Is this problem real and frequent? Score it: frequency × severity × user awareness. Distinguish aspirational pain (nice to fix), active pain (annoying), and hair-on-fire pain (blocking). Only hair-on-fire problems justify building unprompted.\n"
            "2. JOBS-TO-BE-DONE: What job is the user hiring this product for? What are they doing today instead? Why does that workaround fall short? A valid JTBD has a clear functional job, emotional job, and social job.\n"
            "3. SOLUTION FIT: Is the proposed solution 10× better than the current alternative — not 2×? Marginal improvements capture the top 5% of early adopters. Transformative improvements capture the mainstream.\n"
            "4. SCOPE CHECK: What is the minimum experiment that proves the hypothesis? Distinguish: core value (must ship), table stakes (expected), differentiators (optional at MVP). Strip everything that isn't proving the core hypothesis.\n"
            "5. COMPETITIVE GAP: Map the feature vs. top 3 alternatives. Is this a gap in the market (genuinely missing) or a market with gaps (exists but poorly done)? Both can win, but require different GTM.\n"
            "6. VERDICT: Build now / Validate more first / Wrong problem / Not our problem. State exactly which assumption must be true for this to succeed and how you would falsify it.\n"
            "Output: pain_assessment (frequency, severity, type), jtbd_statement, solution_fit_score, mvp_scope, competitive_gap, verdict, key_assumptions"
        ),
    },
    {
        "slug": "market-positioning",
        "name": "Market Positioning",
        "family": "evaluative",
        "tier": "built-in",
        "description": "Evaluate where a product sits relative to alternatives, what moat exists, and what is defensible over time using Porter's Five Forces, Wardley mapping, and value proposition analysis.",
        "activation_signals": [
            "market positioning",
            "competitive advantage",
            "moat",
            "differentiation",
            "gtm strategy",
            "how do we win",
            "vs competitors",
        ],
        "archetype_affinity": {"advisor": 0.9, "analyst": 0.8, "researcher": 0.7},
        "mode_affinity": {"deliberative": 0.9, "exploratory": 0.7},
        "composability": {"complements": ["product-strategy-fit", "blue-ocean", "porter-forces"], "conflicts": []},
        "system_prompt": (
            "Evaluate market positioning and defensibility:\n"
            "1. COMPETITIVE LANDSCAPE: Who are the direct, indirect, and future competitors? Plot a 2×2 competitive matrix on the axes that matter most to users. Where is the white space?\n"
            "2. VALUE PROPOSITION: What specific promise do we make that alternatives cannot match? Distill to one sentence: 'For [user] who [need], we provide [value] unlike [alternative] because [differentiator].'\n"
            "3. MOAT ASSESSMENT: Which moats exist or could exist? Data network effects (each user makes product smarter), direct network effects (more users → more value), switching costs (data, integrations, habits), economies of scale, brand trust. Rate each 1–5 on current strength and potential ceiling.\n"
            "4. FIVE FORCES SNAPSHOT: Threat of new entrants (capital/tech barriers?), supplier power (LLM/cloud dependency?), buyer power (enterprise vs. SMB?), substitute threat (adjacent tools?), competitive rivalry (fragmented vs. dominated market?).\n"
            "5. WARDLEY EVOLUTION: Plot key components on the genesis→custom→product→commodity axis. Where are we betting on custom-built things becoming commodities? Is that bet sound?\n"
            "6. DEFENSIBILITY TIMELINE: In 12/24/48 months, how does the moat change? What would a well-funded competitor need to do to neutralize it?\n"
            "Output: competitive_matrix, value_proposition_statement, moat_scores, five_forces_summary, defensibility_timeline"
        ),
    },
    {
        "slug": "business-model-analysis",
        "name": "Business Model Analysis",
        "family": "evaluative",
        "tier": "built-in",
        "description": "Evaluate revenue models, unit economics, pricing architecture, and value capture mechanisms including usage-based, seat-based, tier-based, and marketplace models.",
        "activation_signals": [
            "business model",
            "pricing",
            "monetization",
            "unit economics",
            "ltv cac",
            "revenue model",
            "how does this make money",
        ],
        "archetype_affinity": {"advisor": 0.9, "analyst": 0.9, "researcher": 0.7},
        "mode_affinity": {"deliberative": 0.9, "exploratory": 0.7},
        "composability": {
            "complements": ["market-positioning", "growth-retention-design", "cost-benefit"],
            "conflicts": [],
        },
        "system_prompt": (
            "Evaluate the business model and unit economics:\n"
            "1. REVENUE MODEL FIT: Which model matches the value delivery? Seat-based (value scales with users), usage-based (value scales with consumption, aligns incentives, higher ceiling), tier-based (land-and-expand, low friction entry), marketplace (network effect, high take-rate risk), outcome-based (highest trust, hardest to measure). State which and why others are weaker fits.\n"
            "2. UNIT ECONOMICS: Calculate or estimate: CAC (blended, by channel), LTV (revenue per customer × gross margin × retention period), LTV/CAC ratio (target >3:1), payback period (target <18 months for B2B, <12 for SMB). Flag which assumption most affects these numbers.\n"
            "3. COST STRUCTURE: Fixed costs (infra, headcount), variable costs (per-user, per-request, per-GB), marginal cost at 10× scale. Identify the highest-leverage cost to reduce.\n"
            "4. PRICING ARCHITECTURE: What is the good/better/best tier split? What is the expansion motion (what causes revenue growth without sales touch)? What is the land metric (easy to start with) vs. the expand metric (grows with usage)?\n"
            "5. MARGIN PROFILE: At current scale, gross margin %. At 10× scale, expected gross margin %. What drives the delta? Infrastructure, support, or COGS?\n"
            "6. RISKS: Which unit economics assumption is most fragile? What does a successful competitor's pricing do to your model?\n"
            "Output: revenue_model_choice, unit_economics_estimate, cost_structure, pricing_architecture, margin_profile, key_risk"
        ),
    },
    {
        "slug": "prioritization-sequencing",
        "name": "Prioritization and Sequencing",
        "family": "evaluative",
        "tier": "built-in",
        "description": "Determine what to build next and in what order using RICE/ICE scoring, dependency mapping, critical path analysis, and constraint theory — sequencing matters as much as selection.",
        "activation_signals": [
            "what should we build next",
            "roadmap planning",
            "prioritize features",
            "sequencing",
            "what comes first",
            "sprint planning",
            "what's most important",
        ],
        "archetype_affinity": {"advisor": 0.9, "analyst": 0.8, "executor": 0.7},
        "mode_affinity": {"deliberative": 0.9, "procedural": 0.8},
        "composability": {
            "complements": ["product-strategy-fit", "rice-prioritization", "dependency-mapping"],
            "conflicts": [],
        },
        "system_prompt": (
            "Prioritize and sequence the work:\n"
            "1. SCORE each item using RICE: Reach (how many users affected per quarter), Impact (effect per user: 3=massive, 2=high, 1=medium, 0.5=low, 0.25=minimal), Confidence (% certainty in estimates: 100/80/50/20), Effort (person-weeks). RICE = (Reach × Impact × Confidence) / Effort.\n"
            "2. DEPENDENCY MAP: Which items unblock other items? Which must happen before others can start? Draw the dependency graph. Items that unblock multiple downstream items get sequencing priority regardless of RICE score.\n"
            "3. CRITICAL PATH: What is the minimum sequence of items that delivers the most user value earliest? Identify items that are NOT on the critical path and could be deferred.\n"
            "4. CONSTRAINT CHECK: What is the actual constraint — developer capacity, design bandwidth, infrastructure readiness, external dependency, regulatory approval? The bottleneck determines the real sequence, not the RICE scores.\n"
            "5. REVERSIBILITY FILTER: Which decisions are reversible (bias toward speed) vs. irreversible (bias toward getting it right)? Schema choices, public API contracts, and security architecture are irreversible. UI and copy are reversible.\n"
            "6. SEQUENCE RECOMMENDATION: Provide the ordered list. For each item, state: why this order, what it unblocks, and what the cost of deferral is.\n"
            "Output: rice_scores, dependency_graph, critical_path, constraint_identified, sequence_with_rationale"
        ),
    },
    {
        "slug": "product-risk-assessment",
        "name": "Product Risk Assessment",
        "family": "adversarial",
        "tier": "built-in",
        "description": "Identify, score, and mitigate product-level risks using pre-mortem analysis, risk matrix, and reversibility assessment before committing resources.",
        "activation_signals": [
            "product risk",
            "what could go wrong",
            "pre-mortem",
            "risk assessment",
            "downside",
            "major bets",
            "launch risk",
        ],
        "archetype_affinity": {"advisor": 0.9, "analyst": 0.8, "researcher": 0.7},
        "mode_affinity": {"deliberative": 0.9, "reflective": 0.8},
        "composability": {"complements": ["product-strategy-fit", "tradeoff-analysis", "premortem"], "conflicts": []},
        "system_prompt": (
            "Assess product-level risks before committing:\n"
            "1. PRE-MORTEM: It is 12 months from now. This initiative has failed badly. What happened? List at least 5 specific failure modes — not generic risks but specific chains of causation (e.g., 'we built X but the market wanted Y because we assumed Z without validating it').\n"
            "2. RISK MATRIX: Score each risk on probability (1–5) × impact (1–5). Plot the matrix. Risks scoring >12 require mitigation plans. Risks scoring >16 require either the plan to change or explicit acceptance with escalation.\n"
            "3. ASSUMPTION AUDIT: Which assumptions are load-bearing for this to succeed? For each: what evidence do we have that it's true? What's the cheapest way to validate it?\n"
            "4. REVERSIBILITY CHECK: If this succeeds and we need to change course — how hard is it to undo? If this fails — what is the cleanup cost? Distinguish: recoverable failures (course-correct) vs. irreversible failures (data loss, user trust, sunk architecture).\n"
            "5. REGRET MINIMIZATION: In 10 years, which decision will we regret more — having tried and failed, or not having tried? This is a forcing function for bold bets that look risky but have acceptable downside.\n"
            "6. MITIGATION PLAN: For the top 3 risks, state the specific mitigation action, owner, and timeline.\n"
            "Output: premortem_failure_modes, risk_matrix, load_bearing_assumptions, reversibility_score, top_3_mitigations"
        ),
    },
    {
        "slug": "growth-retention-design",
        "name": "Growth and Retention Design",
        "family": "systemic",
        "tier": "built-in",
        "description": "Map growth loops, identify the activation metric, analyze retention curves, and design switching costs for sustainable product growth.",
        "activation_signals": [
            "growth strategy",
            "retention",
            "churn",
            "activation",
            "onboarding funnel",
            "growth loop",
            "network effects",
            "day 1 retention",
        ],
        "archetype_affinity": {"analyst": 0.9, "advisor": 0.8, "researcher": 0.7},
        "mode_affinity": {"deliberative": 0.9, "exploratory": 0.8},
        "composability": {
            "complements": ["product-strategy-fit", "onboarding-activation-design", "network-effects"],
            "conflicts": [],
        },
        "system_prompt": (
            "Design the growth and retention system:\n"
            "1. GROWTH LOOP MAPPING: Identify the primary loop type — viral (user invites user), content (content attracts user attracts more content), paid (revenue → ads → users → revenue), product-led (usage → value → expansion → referral). Map the loop: what is the input, the action, the output that feeds back into the input? Where does the loop leak?\n"
            "2. ACTIVATION METRIC: What single action in the first session most predicts long-term retention? (e.g., 'users who do X in the first 24 hours retain at 3× the rate'). This is the activation metric. Everything in onboarding should route to it.\n"
            "3. RETENTION CURVE ANALYSIS: Plot the retention curve (Day 1 / Day 7 / Day 30 / Day 90). Where is the steepest drop? Is there a flattening of the curve (retained core users)? Identify the retention intervention that targets the steepest drop.\n"
            "4. NETWORK EFFECTS: Does this product get more valuable as more people use it? Direct (more users → better for each user), indirect (more users → more content/liquidity → better), data (more usage → smarter product). If no network effect: what creates switching costs instead?\n"
            "5. SWITCHING COST INVENTORY: What makes it hard to leave? Data gravity (user data stored here), integrations (connected tools), habits (learned workflows), network (colleagues here), sunk cost (already trained the model on their data). Which to invest in?\n"
            "6. GROWTH LEVERS: Rank the top 3 growth levers by: current performance, ceiling, and ease of improvement. What would move the metric most?\n"
            "Output: primary_growth_loop, activation_metric, retention_curve_analysis, network_effects_type, switching_cost_map, top_3_growth_levers"
        ),
    },
    # ═══════════════════════════════════════════════════════════════
    # DOMAIN LAYER — LAYER 3: SYSTEM DESIGN (12)
    # ═══════════════════════════════════════════════════════════════
    {
        "slug": "requirements-analysis",
        "name": "Requirements Analysis",
        "family": "diagnostic",
        "tier": "built-in",
        "description": "Define functional requirements, non-functional requirements, capacity estimates, and constraints before designing anything.",
        "activation_signals": [
            "requirements",
            "system requirements",
            "nfr",
            "non-functional requirements",
            "capacity estimation",
            "latency targets",
            "before we design",
            "what does the system need to do",
        ],
        "archetype_affinity": {"analyst": 0.9, "advisor": 0.8, "executor": 0.7},
        "mode_affinity": {"deliberative": 0.9, "procedural": 0.8},
        "composability": {
            "complements": ["service-architecture", "data-architecture", "tradeoff-analysis"],
            "conflicts": [],
        },
        "system_prompt": (
            "Define requirements and constraints before designing:\n"
            "1. FUNCTIONAL REQUIREMENTS: Use cases and user stories — what does the system do? Domain modeling — key entities, relationships, invariants, business rules. Feature decomposition — MVP vs. full scope. Bounded contexts (DDD) — where do concepts mean different things across subdomains?\n"
            "2. NON-FUNCTIONAL REQUIREMENTS: Specify with numbers, not adjectives. Latency: p50/p95/p99 targets per endpoint. Throughput: requests/sec, messages/sec at peak. Availability: 99.9% = 8.7h downtime/year, 99.99% = 52min/year. Durability: RPO (max data loss) and RTO (max recovery time). Consistency: strong/eventual/causal — specify per-feature, not globally.\n"
            "3. CAPACITY ESTIMATION: DAU/MAU projections (realistic, not aspirational). Read/write ratio (most systems are 100:1 read-heavy). QPS per endpoint (peak vs. average, burst patterns). Storage growth: per-user per-month × DAU × 12 months + 3× headroom. Bandwidth: upload/download × DAU × actions/day.\n"
            "4. CONSTRAINT IDENTIFICATION: Budget (infra/team ceiling), timeline (forcing function on scope), team size (cognitive load per engineer), regulatory (GDPR/HIPAA/SOC2/PCI), existing systems (what must integrate). Constraints are not negotiable — design within them.\n"
            "5. TRADEOFF DECLARATION: State explicitly which CAP theorem tradeoff is made: AP (available + partition-tolerant, eventual consistency) or CP (consistent + partition-tolerant, possible unavailability). State latency vs. correctness decisions per-feature: can stale data be shown while fetching fresh?\n"
            "6. ACCEPTANCE CRITERIA: How do we know the system meets requirements? Observable behavior at system boundaries. Sentinel values that prove each NFR is met. Not 'tests pass' — 'p99 latency <200ms under 10k concurrent users'.\n"
            "Output: functional_requirements, nfr_with_numbers, capacity_estimates, constraints, tradeoff_declarations, acceptance_criteria"
        ),
    },
    {
        "slug": "data-architecture",
        "name": "Data Architecture",
        "family": "systemic",
        "tier": "built-in",
        "description": "Design data modeling, database selection, caching strategy, replication topology, search architecture, and data pipelines based on access patterns and scale requirements.",
        "activation_signals": [
            "data architecture",
            "database selection",
            "which database",
            "data model",
            "caching strategy",
            "data pipeline",
            "search architecture",
            "replication",
        ],
        "archetype_affinity": {"analyst": 0.9, "executor": 0.8, "advisor": 0.7},
        "mode_affinity": {"deliberative": 0.9, "exploratory": 0.7},
        "composability": {
            "complements": ["requirements-analysis", "scaling-architecture", "service-architecture"],
            "conflicts": [],
        },
        "system_prompt": (
            "Design the data architecture:\n"
            "1. ACCESS PATTERN ANALYSIS: Before choosing a database, define the queries. What are the 5 most frequent read patterns? Write patterns? What joins are required? Schema should be designed around reads, not around normalization purity. Different access patterns often require different storage engines.\n"
            "2. DATABASE SELECTION: Match engine to pattern — Relational (PostgreSQL/MySQL): ACID, complex joins, mature ecosystem, vertical scale. Document (MongoDB): flexible schema, embedded documents, horizontal scale. Graph (Neo4j, SurrealDB): traversal-heavy, relationship queries, multi-hop paths. Key-Value (Redis, DynamoDB): sub-ms reads, session/cache, simple access. Time-Series (TimescaleDB, ClickHouse): metrics/events/analytics, append-heavy. Vector (pgvector, Qdrant): similarity search, embeddings, RAG. Polyglot persistence: when multiple engines serve different access patterns for the same data.\n"
            "3. CACHING STRATEGY: L1 (in-process, sub-ms, limited size) → L2 (Redis, ms, shared) → L3 (CDN, 10-100ms, geographic). Cache-aside (app manages), write-through (write to cache + DB together), write-behind (async flush). Cache stampede prevention: probabilistic early expiration or locking. Cache invalidation strategy: TTL vs. event-driven. What must NOT be cached (auth tokens, user permissions)?\n"
            "4. REPLICATION TOPOLOGY: Leader-follower (simple, read scale, failover latency), multi-leader (write scale, conflict resolution required), leaderless (Dynamo-style, eventual consistency, no single point of failure). Cross-region: active-active vs. active-passive. Data residency requirements.\n"
            "5. SEARCH AND INDEXING: Database B-tree indexes (covering indexes, partial indexes for sparse data). Full-text search: inverted index, tokenization, stemming. Vector search: embeddings + ANN (HNSW algorithm for accuracy, IVF for speed). Hybrid: BM25 keyword + vector semantic combined with reranking. When does native DB search suffice vs. dedicated search engine (Elasticsearch, Typesense, Meilisearch)?\n"
            "6. DATA LIFECYCLE: Hot (active, expensive storage) → warm (recent, cheaper) → cold (archive, cheapest). Retention policies per data type. Soft deletes vs. hard deletes (audit trail requirements). Right-to-deletion: cascade planning, backup purging.\n"
            "Output: access_patterns, database_selection_with_rationale, caching_strategy, replication_topology, search_architecture, lifecycle_policy"
        ),
    },
    {
        "slug": "service-architecture",
        "name": "Service Architecture",
        "family": "systemic",
        "tier": "built-in",
        "description": "Design service decomposition, communication patterns, API gateway, BFF, and bounded context boundaries using DDD and modern architectural patterns.",
        "activation_signals": [
            "service architecture",
            "monolith vs microservices",
            "service boundaries",
            "bounded context",
            "service decomposition",
            "api gateway",
            "backend for frontend",
            "communication patterns",
        ],
        "archetype_affinity": {"analyst": 0.9, "executor": 0.8, "advisor": 0.8},
        "mode_affinity": {"deliberative": 0.9, "exploratory": 0.8},
        "composability": {
            "complements": ["requirements-analysis", "scaling-architecture", "data-architecture"],
            "conflicts": [],
        },
        "system_prompt": (
            "Design the service architecture:\n"
            "1. DECOMPOSITION DECISION: Monolith (single deployment, simple ops, hard team scale) vs. Microservices (independent deployment, team autonomy, operational complexity) vs. Modular monolith (clear boundaries, single deployment — best of both for most teams under 50 engineers). Decision criteria: team size, deployment independence requirements, different scaling needs per service. Default to modular monolith; decompose only when team or scaling forces it.\n"
            "2. BOUNDED CONTEXT MAPPING: Where do domain concepts mean different things? 'User' in auth context ≠ 'User' in billing context ≠ 'User' in analytics context. Each bounded context should have its own model, its own data store. Cross-context communication via explicit contracts, not shared database tables.\n"
            "3. COMMUNICATION PATTERNS: Synchronous (REST, gRPC, GraphQL): direct, creates temporal coupling. Asynchronous (message queues, pub/sub, events): decoupled, resilient, complex debugging. Rule: use sync for query (need answer now), async for command (fire and forget or eventual). Choreography (services react to events) vs. orchestration (one service directs others).\n"
            "4. API GATEWAY DESIGN: Single entry point for clients — routing, auth, rate limiting, request transformation, response aggregation. BFF pattern: tailored API per client type (mobile needs different payload than web, data scientists need different endpoints than end users).\n"
            "5. SIDECAR AND MESH: Service mesh (Istio, Linkerd) handles cross-cutting: mTLS, retries, circuit breaking, observability — without library code per service. Appropriate at 10+ services. Below that: overhead exceeds benefit.\n"
            "6. STRANGLER FIG MIGRATION: Migrating from monolith incrementally — route traffic to new service, verify, strangle old code. Never big-bang rewrites. Each migration step must be: independently deployable, independently rollbackable.\n"
            "7. BACKGROUND PROCESSING PATTERNS: For multi-step distributed transactions: Saga pattern — choreography (each service publishes events, others react) vs. orchestration (saga orchestrator drives sequence). Compensating transactions for rollback. Outbox pattern: write event to local DB table atomically with business data; relay picks it up and publishes — guarantees no lost events. Transactional inbox: idempotent consumer deduplicates. Workflow engines (Temporal, Conductor): durable execution, built-in retry, visibility — use when saga complexity exceeds 3 steps or compensations are complex.\n"
            "8. REAL-TIME SYSTEMS: WebSockets for bidirectional, persistent connections (chat, live cursors, collaborative editing). SSE for server-push only (feeds, notifications). Long-polling fallback when WebSockets blocked. At scale: fan-out via pub/sub (Redis Streams, Kafka) — don't hold 100k connections on one server. CRDTs for conflict-free collaborative editing (Yjs, Automerge) — operational transforms are error-prone at scale. Presence tracking: heartbeat + TTL in Redis, not database writes per event.\n"
            "Output: decomposition_decision, bounded_context_map, communication_pattern_per_interaction, gateway_design, background_processing_approach, realtime_strategy_if_applicable, strangler_fig_plan_if_applicable"
        ),
    },
    {
        "slug": "scaling-architecture",
        "name": "Scaling and Performance Architecture",
        "family": "systemic",
        "tier": "built-in",
        "description": "Design horizontal/vertical scaling, load balancing, rate limiting, connection pooling, backpressure, and auto-scaling to handle current and projected load.",
        "activation_signals": [
            "scaling",
            "load balancing",
            "rate limiting",
            "backpressure",
            "connection pooling",
            "auto-scaling",
            "throughput",
            "high traffic",
            "performance architecture",
        ],
        "archetype_affinity": {"analyst": 0.9, "executor": 0.8, "advisor": 0.7},
        "mode_affinity": {"deliberative": 0.9, "exploratory": 0.7},
        "composability": {
            "complements": ["requirements-analysis", "reliability-design", "data-architecture"],
            "conflicts": [],
        },
        "system_prompt": (
            "Design the scaling and performance architecture:\n"
            "1. HORIZONTAL vs. VERTICAL: Vertical (bigger machine) is simpler but has a ceiling and creates SPOF. Horizontal (more machines) scales further but requires stateless services — no in-memory session, all state in shared storage. Design stateless first; add statefulness only when measured.\n"
            "2. LOAD BALANCING: L4 (TCP level, fast, no HTTP awareness) vs. L7 (HTTP level, path/header routing, SSL termination, healthcheck intelligence). Algorithms: round-robin (uniform load), least connections (uneven load), consistent hashing (session affinity, cache locality). Auto-scaling triggers: CPU/memory thresholds, queue depth, custom metrics. Scale-up lag: provision before you need it (predictive) or tolerate 60–90s lag (reactive).\n"
            "3. RATE LIMITING: Per-user, per-IP, per-tenant, per-API-key. Algorithms: token bucket (allows bursts, smooths averages), sliding window (precise, more memory), leaky bucket (strict output rate). Where to enforce: API gateway (distributed enforcement) vs. service level (simpler, per-instance). Return 429 with Retry-After header and remaining quota.\n"
            "4. CONNECTION POOLING: Database connections are expensive — PgBouncer/connection pooler limits concurrent connections to database capacity. HTTP keep-alive: reuse connections between services. gRPC channels: multiplex requests over one connection. Rule: pool size = (cores × 2) + effective spindle count for most workloads.\n"
            "5. BACKPRESSURE: When consumers are overwhelmed, slow down producers. Queue depth limits: reject new work when queue exceeds threshold (fail fast). Circuit breaker: stop sending requests to failing downstream. Load shedding: drop lowest-priority requests under extreme load. Graceful shutdown: drain in-flight requests before terminating.\n"
            "6. HOT SPOTS: Uneven load — hot keys in cache (use key sharding), hot partitions in DB (use partition by random suffix), hot services (use fan-out). Thundering herd on cache miss — use probabilistic early expiration, request coalescing, or mutex-locked regeneration.\n"
            "Output: scaling_strategy, load_balancer_design, rate_limit_configuration, connection_pool_sizing, backpressure_design, hot_spot_mitigations"
        ),
    },
    {
        "slug": "reliability-design",
        "name": "Reliability and Fault Tolerance Design",
        "family": "adversarial",
        "tier": "built-in",
        "description": "Design system behavior under failure using circuit breakers, bulkheads, retry policies, graceful degradation, chaos engineering targets, and RPO/RTO planning.",
        "activation_signals": [
            "reliability",
            "fault tolerance",
            "circuit breaker",
            "retry policy",
            "graceful degradation",
            "disaster recovery",
            "rpo rto",
            "chaos engineering",
            "resilience",
        ],
        "archetype_affinity": {"analyst": 0.9, "executor": 0.8, "advisor": 0.8},
        "mode_affinity": {"deliberative": 0.9, "reflective": 0.8},
        "composability": {
            "complements": ["scaling-architecture", "observability-architecture", "deployment-strategy"],
            "conflicts": [],
        },
        "system_prompt": (
            "Design reliability and fault tolerance:\n"
            "1. FAILURE MODE ANALYSIS: What can break? For every external dependency and internal component: probability of failure, impact of failure, detection time, recovery time. Prioritize mitigations by (impact × probability) / recovery_cost.\n"
            "2. CIRCUIT BREAKER PLACEMENT: Wrap every external call (downstream service, third-party API, database). States: closed (normal), open (failing, reject fast), half-open (probe for recovery). Thresholds: open after N failures in M seconds. Benefits: fail fast instead of queue exhaustion, allow downstream recovery time.\n"
            "3. RETRY POLICY DESIGN: Exponential backoff with jitter (not synchronized retries that cause thundering herd). Max retries + retry budget (total retry time ceiling). Only retry idempotent operations. Differentiate: transient failures (retry) vs. permanent failures (dead letter queue, alert).\n"
            "4. GRACEFUL DEGRADATION: Define what still works when each dependency is down. Cache last-known-good for read operations. Serve degraded but functional responses (show stale data rather than error). Feature flags disable non-critical features during incidents. Bulkheads: isolate failure in one subsystem from contaminating others.\n"
            "5. CHAOS ENGINEERING: Define gameday targets — what would you inject? (Kill a pod, introduce network latency, drop a message, exhaust connection pool). The goal: find failure modes before users do. Start with paper chaos (walk through failure scenarios), then automate with tools (Chaos Monkey, Gremlin).\n"
            "6. DISASTER RECOVERY: RPO (Recovery Point Objective) — max data loss tolerable. RTO (Recovery Time Objective) — max downtime tolerable. Backup strategy aligned to RPO. Runbook to achieve RTO. Test recovery quarterly — untested runbooks fail in real incidents.\n"
            "7. DISTRIBUTED STATE MANAGEMENT: Distributed locks (Redis SETNX with TTL, Redlock for multi-node): use for critical sections across services. Never hold a distributed lock across an I/O call — deadlock risk. Leader election (Raft, etcd/ZooKeeper elections): one active node for tasks that can't run concurrently (cron, leader writes). Consensus algorithms: Raft (understandable, modern: etcd, CockroachDB) vs. Paxos (complex, foundational). Know when you need consensus (shared truth across nodes) vs. when eventual consistency suffices (read your own writes, monotonic reads with vector clocks).\n"
            "Output: failure_mode_map, circuit_breaker_placements, retry_policies, degradation_matrix, chaos_targets, rpo_rto_plan, distributed_state_strategy_if_applicable"
        ),
    },
    {
        "slug": "security-architecture",
        "name": "Security Architecture",
        "family": "adversarial",
        "tier": "built-in",
        "description": "Design authentication, authorization, encryption, secrets management, threat model, and compliance mapping for a system.",
        "activation_signals": [
            "security architecture",
            "authentication design",
            "authorization",
            "rbac",
            "jwt",
            "oauth",
            "encryption",
            "secrets management",
            "threat model",
        ],
        "archetype_affinity": {"analyst": 0.9, "advisor": 0.8, "executor": 0.7},
        "mode_affinity": {"deliberative": 0.9, "reflective": 0.8},
        "composability": {
            "complements": ["requirements-analysis", "integration-design", "data-governance"],
            "conflicts": [],
        },
        "system_prompt": (
            "Design the security architecture:\n"
            "1. THREAT MODEL (STRIDE): Spoofing (impersonating identity) — mitigate with strong auth. Tampering (modifying data) — mitigate with integrity checks, HMAC, signed payloads. Repudiation (denying actions) — mitigate with audit logs. Information Disclosure (unauthorized read) — mitigate with encryption + access controls. Denial of Service — mitigate with rate limiting, input size limits. Elevation of Privilege — mitigate with least privilege, RBAC enforcement.\n"
            "2. AUTH ARCHITECTURE: OAuth2 + OIDC for federated identity. JWT access tokens (short-lived, 15min) + refresh tokens (long-lived, rotated on use). RBAC (role-based) for coarse access vs. ABAC (attribute-based) for fine-grained access (tenant isolation, row-level). Service-to-service: mTLS or JWT with service-scoped claims.\n"
            "3. ENCRYPTION ARCHITECTURE: In transit: TLS 1.3 minimum, no TLS 1.0/1.1. At rest: AES-256 for sensitive data, envelope encryption for large datasets. Application-level: field-level encryption for PII (encrypt before storing, decrypt only when serving). Key management: HSM or KMS — never hardcoded keys.\n"
            "4. SECRETS MANAGEMENT: HashiCorp Vault / AWS Secrets Manager / Azure Key Vault for secrets at rest. Dynamic secrets: generate credentials on demand, expire after use. No secrets in code, env vars in repo, or config files checked in. Rotation policy: auto-rotate every 30/90 days.\n"
            "5. INPUT VALIDATION AND INJECTION PREVENTION: Validate at every trust boundary — API endpoints, message consumers, file uploads. Parameterized queries — never string interpolation for SQL. Output encoding — escape HTML, JSON, URLs at the rendering layer. File upload: validate type (not just extension), virus scan, size limits, separate storage from app.\n"
            "6. COMPLIANCE MAPPING: GDPR (consent, right-to-deletion, data residency, DPA), SOC 2 Type II (access controls, availability, confidentiality), HIPAA (PHI encryption, audit logs, BAAs), PCI-DSS (cardholder data — never store CVV, tokenize PANs).\n"
            "Output: stride_threat_model, auth_architecture, encryption_plan, secrets_management_design, input_validation_map, compliance_coverage"
        ),
    },
    {
        "slug": "integration-design",
        "name": "Integration Architecture",
        "family": "systemic",
        "tier": "built-in",
        "description": "Design API contracts, webhook patterns, OAuth flows, idempotency, and schema contracts for integrating with and being integrated by external systems.",
        "activation_signals": [
            "integration",
            "third party api",
            "webhook",
            "oauth integration",
            "idempotency",
            "api design",
            "partner integration",
            "sdk design",
        ],
        "archetype_affinity": {"executor": 0.9, "analyst": 0.8, "advisor": 0.7},
        "mode_affinity": {"deliberative": 0.9, "procedural": 0.8},
        "composability": {
            "complements": ["service-architecture", "security-architecture", "backward-compatibility"],
            "conflicts": [],
        },
        "system_prompt": (
            "Design the integration architecture:\n"
            "1. API DESIGN: REST (resource-oriented, stateless, cacheable), gRPC (binary, streaming, generated clients, low latency), GraphQL (client-driven queries, schema stitching, federation). Match protocol to use case. REST for CRUD-heavy, gRPC for high-throughput service-to-service, GraphQL for client-flexible data fetching.\n"
            "2. WEBHOOK DESIGN: Delivery guarantees — at-least-once delivery (idempotency keys required on receiver), retry with exponential backoff, dead letter queue for failed deliveries. Payload signing: HMAC-SHA256 signature in header, receiver validates before processing. Schema versioning: include event version in payload.\n"
            "3. OAUTH INTEGRATION: Scopes: minimum required (principle of least privilege). Token storage: never in localStorage (XSS risk), use httpOnly secure cookies or server-side session. PKCE for public clients (SPAs, mobile). Refresh token rotation: invalidate old token on use.\n"
            "4. IDEMPOTENCY: For any mutating operation exposed to external callers — accept an idempotency key, deduplicate by key for a time window (24h). Return cached response for duplicate keys without re-executing. Critical for: payments, emails, webhook handlers, any at-least-once messaging.\n"
            "5. SCHEMA CONTRACTS: Define explicit contracts between producer and consumer. Schema registry for event-driven systems. Data contracts specify: shape, semantics, SLAs, versioning policy. Consumer-driven contract testing: consumer defines what it needs, provider proves it delivers.\n"
            "6. THIRD-PARTY ISOLATION: Wrap every third-party dependency behind an adapter interface. Changes to the third-party API should only require changes in the adapter, not in business logic. Circuit breaker around every external call. Never expose third-party SDK types in your public interface.\n"
            "Output: api_protocol_selection, webhook_design, oauth_flow, idempotency_implementation, schema_contracts, third_party_adapters"
        ),
    },
    {
        "slug": "multi-tenancy-design",
        "name": "Multi-Tenancy Design",
        "family": "systemic",
        "tier": "built-in",
        "description": "Design tenant isolation strategy, noisy neighbor prevention, resource quotas, tenant-scoped configuration, and data residency compliance.",
        "activation_signals": [
            "multi-tenancy",
            "tenant isolation",
            "noisy neighbor",
            "tenant data",
            "data residency",
            "resource quotas",
            "tenant scoping",
        ],
        "archetype_affinity": {"analyst": 0.9, "executor": 0.8, "advisor": 0.7},
        "mode_affinity": {"deliberative": 0.9, "exploratory": 0.7},
        "composability": {
            "complements": ["data-architecture", "security-architecture", "scaling-architecture"],
            "conflicts": [],
        },
        "system_prompt": (
            "Design the multi-tenancy architecture:\n"
            "1. ISOLATION STRATEGY SELECTION: Namespace isolation (shared schema, tenant_id column, cheapest, noisy-neighbor risk), schema-per-tenant (full DB isolation, migration complexity, 10–100 tenants), database-per-tenant (maximum isolation, highest cost, enterprise/regulated tenants). Hybrid: shared schema for self-service, dedicated for enterprise with data residency requirements.\n"
            "2. DATA LAYER ENFORCEMENT: Row-level security in database (Postgres RLS policies) vs. application-layer filtering. Database RLS: cannot be bypassed by application bugs. Application filtering: faster, more flexible, but requires every query to include tenant filter. For security-critical isolation: database-level is non-negotiable.\n"
            "3. NOISY NEIGHBOR PREVENTION: Resource quotas per tenant: API rate limits (per-tenant not just per-IP), query timeout limits, storage quotas, connection pool limits. Queue priority: tenant traffic classes (paid vs. trial). Dedicated infrastructure for high-value tenants.\n"
            "4. TENANT-SCOPED CONFIGURATION: Feature flags per tenant (beta features for opted-in tenants), limits per tier (API rate, storage, users), customization (branding, domain), compliance settings (data retention, encryption requirements). Configuration should be hierarchical: system defaults → tier defaults → tenant overrides.\n"
            "5. TENANT ROUTING: How is the tenant identified per request? Subdomain (tenant.app.com — easiest), path prefix (/api/tenant123 — flexible), JWT claim (preferred for APIs — stateless), header (internal microservices). Routing must happen before any business logic.\n"
            "6. DATA RESIDENCY: Which tenants require data in specific regions (EU data stays in EU, HIPAA data in US)? Router must enforce region affinity. Active-active per-region with tenant-to-region mapping. Cross-region data transfer must be audited.\n"
            "Output: isolation_strategy, data_enforcement_mechanism, quota_design, configuration_hierarchy, routing_mechanism, data_residency_plan"
        ),
    },
    {
        "slug": "infrastructure-design",
        "name": "Infrastructure and Deployment Design",
        "family": "systemic",
        "tier": "built-in",
        "description": "Design container strategy, orchestration, IaC, environment management, and cost optimization for production infrastructure.",
        "activation_signals": [
            "infrastructure",
            "kubernetes",
            "docker",
            "iac",
            "terraform",
            "container design",
            "environment setup",
            "cloud architecture",
            "cost optimization",
        ],
        "archetype_affinity": {"executor": 0.9, "analyst": 0.8, "operator": 0.9},
        "mode_affinity": {"deliberative": 0.9, "procedural": 0.8},
        "composability": {
            "complements": ["deployment-strategy", "scaling-architecture", "observability-architecture"],
            "conflicts": [],
        },
        "system_prompt": (
            "Design the infrastructure architecture:\n"
            "1. COMPUTE STRATEGY: Containers (Docker/OCI) — reproducible, portable, good local/prod parity. Serverless (Lambda, Cloud Functions) — no infra management, cold starts, execution time limits, event-driven. Kubernetes — full control, complex ops, appropriate at 10+ services or when custom scheduling needed. VMs — simplest, appropriate for single stateful workloads. Choose the simplest option that meets reliability and scaling requirements.\n"
            "2. ORCHESTRATION DESIGN: Kubernetes: deployment (stateless, rolling update), statefulset (databases, ordered startup), daemonset (logging/monitoring per node), job/cronjob (batch). Resource requests vs. limits: always set both — requests drive scheduling, limits prevent OOM. Liveness vs. readiness probes: liveness restarts crashed containers, readiness removes from load balancer rotation.\n"
            "3. IaC STRATEGY: Terraform (mature, large ecosystem, statefile management) vs. Pulumi (code-first, TypeScript/Python, easier testing) vs. CloudFormation (AWS-only, native integration). Principles: environments as code (dev/staging/prod from same templates with variable overrides), no manual changes in production, state in remote backend with locking.\n"
            "4. ENVIRONMENT MANAGEMENT: dev (local or shared) → staging (production parity, used for QA) → production. Production parity rule: staging must have same config, same secret shape (not values), same network topology. Environment-specific config via environment variables, never in code.\n"
            "5. COST OPTIMIZATION: Right-sizing: start with recommendations from cloud advisor, measure actual utilization, resize. Reserved instances: 1-year commitment for baseline load (40–60% savings), spot/preemptible for batch/background (70–90% savings). Auto-off for dev/staging environments outside business hours. LLM cost: token usage tracking per feature, cache LLM responses where appropriate.\n"
            "6. MULTI-CLOUD vs. SINGLE CLOUD: Single cloud: simpler ops, better integrated services, vendor-managed services. Multi-cloud: avoid lock-in, best-of-breed services, significantly more complex. Pragmatic middle ground: one primary cloud, cloud-agnostic containers, avoid vendor-specific services for critical paths.\n"
            "Output: compute_strategy, orchestration_design, iac_tooling, environment_matrix, cost_optimization_plan, cloud_strategy"
        ),
    },
    {
        "slug": "observability-architecture",
        "name": "Observability Architecture",
        "family": "systemic",
        "tier": "built-in",
        "description": "Design the full observability stack: golden signals, structured logging, distributed tracing, SLI/SLO definition, alerting strategy, and error budget policy.",
        "activation_signals": [
            "observability",
            "monitoring",
            "logging",
            "tracing",
            "slo",
            "sli",
            "alerting",
            "golden signals",
            "opentelemetry",
        ],
        "archetype_affinity": {"analyst": 0.9, "executor": 0.8, "operator": 0.9},
        "mode_affinity": {"deliberative": 0.9, "procedural": 0.8},
        "composability": {
            "complements": ["reliability-design", "infrastructure-design", "incident-response"],
            "conflicts": [],
        },
        "system_prompt": (
            "Design the observability architecture:\n"
            "1. GOLDEN SIGNALS: Instrument these four for every service — Latency (p50/p95/p99, not average — averages hide bimodal distributions), Traffic (requests/sec, by endpoint, by status code), Errors (error rate %, by type: 4xx vs. 5xx vs. timeout), Saturation (CPU %, memory %, queue depth, connection pool usage). Alert on saturation before it becomes an error.\n"
            "2. STRUCTURED LOGGING: JSON format, consistent schema across services. Required fields: timestamp (ISO 8601), level, service, trace_id, span_id, user_id, request_id. Log levels: DEBUG (development only), INFO (key business events, request start/end), WARN (recoverable errors, degraded operation), ERROR (unhandled exceptions, data loss risk). Never log PII in cleartext.\n"
            "3. DISTRIBUTED TRACING: OpenTelemetry as standard (vendor-agnostic). Trace every cross-service call. Sampling: 100% for errors and slow requests (>p95 threshold), 1–10% for normal traffic. Trace parent propagation via W3C Trace Context headers. Correlate logs to traces via trace_id.\n"
            "4. SLI/SLO DESIGN: SLI (what we measure): availability (successful requests / total), latency (% requests under threshold), error rate (errors / total). SLO (what we promise): e.g., 99.9% of requests succeed in <200ms over 30 days. Error budget = 100% - SLO = budget for experiments, deployments, and failures. Error budget burn rate alert: alert at 2× burn rate (will exhaust in 15 days if sustained).\n"
            "5. ALERTING STRATEGY: Alert on symptoms (user impact), not causes (CPU high — CPU high doesn't wake someone up unless it causes user impact). Alert routing: P1 (data loss, complete outage) → page immediately. P2 (degraded, error rate elevated) → page during business hours. P3 (warning threshold) → ticket. No alert without runbook. Review alert-to-action rate monthly — silence alerts nobody acts on.\n"
            "6. DASHBOARDS: Per-service: golden signals, top errors, latency heatmap. Per-user-journey: funnel completion rate, per-step success rate. Operational: deployment frequency, error budget remaining, on-call load. Executive: uptime SLO compliance, incident frequency trend.\n"
            "Output: golden_signals_instrumentation, logging_schema, tracing_strategy, sli_slo_definitions, alerting_rules, dashboard_design"
        ),
    },
    {
        "slug": "data-governance",
        "name": "Data Governance and Compliance",
        "family": "evaluative",
        "tier": "built-in",
        "description": "Design data classification, retention policies, right-to-deletion, consent management, data lineage, and compliance mapping for GDPR/HIPAA/SOC2.",
        "activation_signals": [
            "data governance",
            "gdpr",
            "compliance",
            "data retention",
            "right to deletion",
            "pii",
            "data lineage",
            "data classification",
            "privacy",
        ],
        "archetype_affinity": {"analyst": 0.9, "advisor": 0.8, "executor": 0.7},
        "mode_affinity": {"deliberative": 0.9, "procedural": 0.8},
        "composability": {
            "complements": ["security-architecture", "data-architecture", "i18n-architecture"],
            "conflicts": [],
        },
        "system_prompt": (
            "Design the data governance and compliance architecture:\n"
            "1. DATA CLASSIFICATION: Categorize all data — PII (directly identifying: name, email, SSN, IP), sensitive (financial, health, auth credentials), internal (business data, logs), public (published content). Map classification to: storage requirements (encryption level), retention limits, access controls, deletion requirements.\n"
            "2. RETENTION POLICY: Per data category — how long do we retain? Legal minimums (financial records: 7 years), regulatory maximums (GDPR: no longer than necessary), business requirements. Automated deletion at retention boundary — not manual, not ad-hoc. Backup purging must align to retention policy.\n"
            "3. RIGHT-TO-DELETION (GDPR Art. 17): When a user requests deletion — what must be deleted? Direct data (profile, content), derived data (recommendations, analytics events), backup data (must be purged from backups within reasonable timeframe). Cascade planning: deletion from primary DB, caches, CDN, search indexes, analytics warehouse, third-party integrations. Hard to do retroactively — design deletion pathways at build time.\n"
            "4. DATA LINEAGE: Where did this data come from? What systems derived from it? Lineage enables: impact analysis (if we delete this, what breaks?), audit trails (prove compliance), debugging (why did this recommendation appear?). Implement as metadata graph — each dataset records upstream sources and downstream consumers.\n"
            "5. CONSENT MANAGEMENT: What consent is required before data processing? Granular consent per purpose (marketing, analytics, personalization). Consent record: timestamp, version of privacy policy, specific purposes. Withdrawal of consent must propagate to all downstream processing within 24 hours.\n"
            "6. CROSS-BORDER TRANSFER: Can EU personal data be sent to US systems? Mechanisms: Standard Contractual Clauses (SCCs), Binding Corporate Rules, adequacy decisions. Data residency enforcement: tenant data stays in tenant's region, enforce at infrastructure layer.\n"
            "Output: data_classification_map, retention_schedule, deletion_pathway, lineage_graph_design, consent_implementation, cross_border_transfer_mechanism"
        ),
    },
    {
        "slug": "i18n-architecture",
        "name": "Internationalization Architecture",
        "family": "systemic",
        "tier": "built-in",
        "description": "Design string externalization, locale detection, RTL support, date/time/currency formatting, and translation management workflow for multi-locale products.",
        "activation_signals": [
            "internationalization",
            "i18n",
            "localization",
            "l10n",
            "multi-language",
            "rtl",
            "locale",
            "translation",
        ],
        "archetype_affinity": {"executor": 0.9, "analyst": 0.7, "creator": 0.8},
        "mode_affinity": {"deliberative": 0.9, "procedural": 0.8},
        "composability": {
            "complements": ["data-governance", "content-copy-design", "visual-interface-design"],
            "conflicts": [],
        },
        "system_prompt": (
            "Design the internationalization architecture:\n"
            "1. STRING EXTERNALIZATION: Zero hardcoded strings in UI code. All user-facing text via i18n key lookup (react-i18next, vue-i18n, gettext). Key naming: namespace.component.description (e.g., 'auth.login.submit_button'). Audit: grep for string literals in UI components — every match is a gap.\n"
            "2. LOCALE DETECTION CHAIN: User preference (explicit setting in account) → browser Accept-Language header → geographic IP → fallback to default. Persist preference in user settings. Never use a single global locale — different users in same session can have different locales.\n"
            "3. RTL SUPPORT: Arabic, Hebrew, Persian, Urdu are RTL. CSS logical properties (margin-inline-start, not margin-left) for RTL-aware layouts. Test: add dir='rtl' to html element and verify layout mirrors correctly. Common failures: absolute positioning, hardcoded border-left, text-align: left.\n"
            "4. LOCALE-AWARE FORMATTING: Dates (MM/DD/YYYY vs DD/MM/YYYY vs YYYY-MM-DD), times (12h vs 24h, timezone display), numbers (1,000.50 vs 1.000,50 vs 1 000,50), currencies (symbol position, decimal places), pluralization rules (English: 1/many, Arabic: 6 plural forms, Russian: 3). Use Intl API or i18n library — never manual formatting.\n"
            "5. TEXT EXPANSION: German is 30% longer than English. Japanese is 30% shorter but wider characters. UI layouts must accommodate ±40% text size variation. Test with longest expected translations before visual design approval.\n"
            "6. TRANSLATION WORKFLOW: Source string in code → extract to translation files → send to translation management system (Phrase, Lokalise, Crowdin) → translated → review → merge. Missing translation fallback chain: locale → language (en-GB → en) → default locale. Track translation completeness per locale.\n"
            "Output: string_externalization_audit, locale_detection_chain, rtl_checklist, formatting_implementation, text_expansion_test_results, translation_workflow"
        ),
    },
    # ═══════════════════════════════════════════════════════════════
    # DOMAIN LAYER — LAYER 2: PRODUCT DESIGN (8)
    # ═══════════════════════════════════════════════════════════════
    {
        "slug": "user-flow-design",
        "name": "User Flow Design",
        "family": "generative",
        "tier": "built-in",
        "description": "Map the complete user journey through a feature including happy path, error paths, edge cases, and friction points using user journey mapping and flow state analysis.",
        "activation_signals": [
            "user flow",
            "user journey",
            "happy path",
            "error path",
            "onboarding flow",
            "checkout flow",
            "navigation flow",
            "ux flow",
        ],
        "archetype_affinity": {"creator": 0.9, "analyst": 0.8, "advisor": 0.7},
        "mode_affinity": {"deliberative": 0.9, "exploratory": 0.8},
        "composability": {
            "complements": ["information-architecture", "interaction-design", "onboarding-activation-design"],
            "conflicts": [],
        },
        "system_prompt": (
            "Design the complete user flow:\n"
            "1. HAPPY PATH: Map the ideal sequence from entry point to value delivery. Every screen, every decision point. Be specific — not 'user logs in' but 'user enters email → validation → success → redirect to dashboard with welcome state'.\n"
            "2. ERROR PATHS: For every step that can fail, map the error path. What does the user see? What action can they take? Rule: every error path must have a recovery action. Dead ends are design failures.\n"
            "3. EDGE CASES: Enumerate the boundary conditions — empty state (no data yet), first use (no history), max state (data limits), concurrent edit (another session made changes), permission boundary (user lacks access), network failure (mid-action). At least one design decision per edge case.\n"
            "4. PIRATE FUNNEL CHECK: Map the flow to Awareness → Activation → Retention → Revenue → Referral. Where in the funnel does this flow live? Where are the leakage points?\n"
            "5. FRICTION AUDIT: For each step, score friction (1–5: 1=frictionless, 5=high effort). Steps scoring 4+ require justification — is this friction necessary or removable? Unnecessary friction compounds.\n"
            "6. FLOW STATE: Where does focus break? Modal interruptions, context switches, loading waits longer than 300ms, multi-step confirmations. Mark each flow-breaker and propose an alternative.\n"
            "Output: flow_map (steps, decisions, error_recovery), edge_case_designs, friction_audit, flow_breakers"
        ),
    },
    {
        "slug": "information-architecture",
        "name": "Information Architecture",
        "family": "generative",
        "tier": "built-in",
        "description": "Design how information is organized, labeled, and navigated using card sorting principles, tree testing, content hierarchy analysis, and mental model alignment.",
        "activation_signals": [
            "information architecture",
            "navigation design",
            "content hierarchy",
            "menu structure",
            "how to organize",
            "users can't find",
            "nav redesign",
        ],
        "archetype_affinity": {"creator": 0.9, "analyst": 0.8, "advisor": 0.7},
        "mode_affinity": {"deliberative": 0.9, "exploratory": 0.8},
        "composability": {
            "complements": ["user-flow-design", "interaction-design", "content-copy-design"],
            "conflicts": [],
        },
        "system_prompt": (
            "Design or audit the information architecture:\n"
            "1. CONTENT INVENTORY: List all content types and functional areas in this product/feature. Group by user mental model, not by internal system structure. Ask: how would a user describe what they're looking for, not how do we organize our database.\n"
            "2. HIERARCHY DEPTH: Apply the 2-click rule — can users reach any core function in ≤2 clicks from any location? Map where violations exist. Deeper nesting requires stronger navigation affordances.\n"
            "3. LABEL AUDIT: Are labels in user language or system language? Test each label: would a user unfamiliar with the product understand what's behind this label? Replace system jargon with task-oriented language.\n"
            "4. PROGRESSIVE DISCLOSURE: What must be visible immediately? What can be revealed on demand? Apply the 80/20 rule — 80% of users use 20% of features. The 20% should be instantly accessible; the 80% should be findable but not in the way.\n"
            "5. NAVIGATION PATTERNS: Primary nav (most important destinations), secondary nav (contextual options), utility nav (settings, account, help). Are these properly separated? Does the nav reflect the actual user journey, not the sitemap?\n"
            "6. MENTAL MODEL ALIGNMENT: How do users currently think about this domain before using our product? Where does our organization match their model? Where does it conflict? Conflicts require extra UI affordance or onboarding.\n"
            "Output: content_hierarchy, depth_violations, label_audit, disclosure_map, navigation_pattern_recommendation"
        ),
    },
    {
        "slug": "interaction-design",
        "name": "Interaction Design",
        "family": "generative",
        "tier": "built-in",
        "description": "Design interactive element behavior using state machine modeling, Fitts's Law, Hick's Law, and direct manipulation principles.",
        "activation_signals": [
            "interaction design",
            "ui states",
            "component behavior",
            "form design",
            "input design",
            "button states",
            "loading states",
            "feedback patterns",
        ],
        "archetype_affinity": {"creator": 0.9, "analyst": 0.7, "executor": 0.8},
        "mode_affinity": {"deliberative": 0.9, "procedural": 0.8},
        "composability": {
            "complements": ["user-flow-design", "accessibility-design", "visual-interface-design"],
            "conflicts": [],
        },
        "system_prompt": (
            "Design the interaction model for this UI:\n"
            "1. STATE MACHINE COMPLETENESS: For every interactive element, enumerate all states: default, hover, focused, active/pressed, loading, success, error, disabled, empty. Missing states become UX debt discovered in production. Each state needs a defined visual treatment.\n"
            "2. FITTS'S LAW APPLICATION: Are target sizes appropriate for the interaction cost? Minimum touch target: 44×44pt. Are the most-used actions the largest/closest targets? Are destructive actions smaller/further than confirmatory actions?\n"
            "3. HICK'S LAW CHECK: How many choices does the user face at any decision point? Decision time scales with log(n) options. More than 5–7 choices requires grouping or progressive disclosure. Is every choice necessary?\n"
            "4. FEEDBACK TIMING: What happens in 0–100ms (immediate feedback — color change), 100–300ms (loading indicator not yet needed), 300ms–1s (spinner), 1–3s (progress indicator), 3s+ (background task + notification on completion)? Map every async action to a feedback pattern.\n"
            "5. ERROR RECOVERY: For every error state — what exactly went wrong (not 'error occurred'), why it happened, and what the user should do next. Error messages should be: specific, blame-free, and actionable.\n"
            "6. DIRECT MANIPULATION vs. INDIRECT: Can users interact with objects directly (drag, resize, inline edit) rather than through modals and forms? Where is the complexity of direct manipulation worth the reduction in steps?\n"
            "Output: state_machine_per_component, fitts_audit, choice_counts, feedback_timing_map, error_message_designs"
        ),
    },
    {
        "slug": "visual-interface-design",
        "name": "Visual Interface Design",
        "family": "generative",
        "tier": "built-in",
        "description": "Evaluate and design visual hierarchy, design token architecture, accessibility compliance, and responsive behavior using WCAG 2.2, gestalt principles, and token pipeline design.",
        "activation_signals": [
            "visual design",
            "ui design",
            "design tokens",
            "visual hierarchy",
            "color system",
            "typography",
            "spacing system",
            "responsive design",
        ],
        "archetype_affinity": {"creator": 0.9, "analyst": 0.7, "executor": 0.8},
        "mode_affinity": {"deliberative": 0.9, "exploratory": 0.7},
        "composability": {
            "complements": ["design-system-reasoning", "accessibility-design", "interaction-design"],
            "conflicts": [],
        },
        "system_prompt": (
            "Evaluate or design the visual interface:\n"
            "1. TOKEN ARCHITECTURE: Are design decisions encoded as tokens or hardcoded? Token hierarchy: primitive tokens (exact values: #1A73E8, 16px) → semantic tokens (brand-primary, spacing-md) → component tokens (button-bg, card-padding). Changes at the primitive level should propagate automatically. Hardcoded values are design debt.\n"
            "2. VISUAL HIERARCHY AUDIT: Does the eye travel in the intended sequence? Use size, weight, color, and position to signal importance. Test: cover the design and describe what stands out first. If that's not the most important element, the hierarchy is wrong.\n"
            "3. WCAG 2.2 COMPLIANCE: Text contrast ratio ≥4.5:1 (AA) for normal text, ≥3:1 for large text and UI components. Non-text elements (icons, borders, form inputs) ≥3:1. Use actual contrast checker values, not estimates.\n"
            "4. GESTALT CHECK: Are related elements grouped (proximity)? Do similar-looking elements behave similarly (similarity)? Does the layout suggest completion even with gaps (closure)? Are line flows guiding attention (continuity)?\n"
            "5. RESPONSIVE BEHAVIOR: How does this scale across breakpoints — mobile (320–767px), tablet (768–1023px), desktop (1024+), ultrawide (1440+)? Does the layout reflow or simply shrink? Are touch targets adequate at mobile sizes?\n"
            "6. DARK MODE + THEMING: Are color choices dark-mode compatible? Are semantic tokens sufficient to theme this without redesigning? Test: invert the palette — does the hierarchy hold?\n"
            "Output: token_architecture_assessment, hierarchy_flow, wcag_scores, gestalt_violations, responsive_breakpoints"
        ),
    },
    {
        "slug": "design-system-reasoning",
        "name": "Design System Reasoning",
        "family": "systemic",
        "tier": "built-in",
        "description": "Evaluate and design the systematic approach to UI — tokens, components, patterns, governance, and multi-brand architecture.",
        "activation_signals": [
            "design system",
            "component library",
            "design tokens",
            "figma tokens",
            "component api",
            "theming",
            "multi-brand",
            "style dictionary",
        ],
        "archetype_affinity": {"creator": 0.9, "analyst": 0.8, "advisor": 0.7},
        "mode_affinity": {"deliberative": 0.9, "exploratory": 0.7},
        "composability": {
            "complements": ["visual-interface-design", "accessibility-design", "information-architecture"],
            "conflicts": [],
        },
        "system_prompt": (
            "Evaluate or design the design system architecture:\n"
            "1. TOKEN PIPELINE: Where do tokens originate (Figma/design tool) and how do they reach code (Style Dictionary, Supernova, Theo)? Is the pipeline automated or manual? Manual pipeline = guaranteed drift. Map the token flow: design tool → token file → build step → CSS/TS variables → component consumption.\n"
            "2. COMPONENT API DESIGN: For each component, evaluate: props surface (minimal — only expose what callers need to control), variants (predefined configurations vs. free-form customization), slots/composition (can content be injected without forking?), polymorphism (can the root element be overridden for semantic HTML?). A bloated prop surface is harder to maintain than multiple focused components.\n"
            "3. PATTERN DOCUMENTATION: Is there a decision guide for when to use which component? A component without 'when to use' and 'when NOT to use' documentation will be misused. Anti-pattern documentation prevents future drift.\n"
            "4. ADOPTION MEASUREMENT: What percentage of shipped UI uses system components vs. one-offs? One-off rate above 20% indicates the system is either missing components or too rigid to cover real use cases.\n"
            "5. MULTI-BRAND/THEMING: Can the system support multiple visual themes from one component set? This requires strict semantic token discipline — component tokens reference semantic tokens, never primitive tokens directly.\n"
            "6. GOVERNANCE: Who can add components? What is the contribution process? What happens to one-offs that should be promoted? Without governance, design systems entropy into component soup.\n"
            "Output: token_pipeline_health, component_api_scores, pattern_coverage, adoption_rate, theming_capability, governance_process"
        ),
    },
    {
        "slug": "onboarding-activation-design",
        "name": "Onboarding and Activation Design",
        "family": "generative",
        "tier": "built-in",
        "description": "Design the first-run experience to minimize time-to-value, identify the activation metric, audit setup friction, and design empty states and sample data strategy.",
        "activation_signals": [
            "onboarding",
            "first run experience",
            "activation",
            "time to value",
            "setup flow",
            "empty state",
            "new user experience",
            "day 1 retention",
        ],
        "archetype_affinity": {"creator": 0.9, "analyst": 0.8, "advisor": 0.7},
        "mode_affinity": {"deliberative": 0.9, "procedural": 0.8},
        "composability": {
            "complements": ["user-flow-design", "growth-retention-design", "content-copy-design"],
            "conflicts": [],
        },
        "system_prompt": (
            "Design the onboarding and activation experience:\n"
            "1. ACTIVATION METRIC: What single action in the first session predicts long-term retention? This is the north star of onboarding design — everything should route to this action. It must be: specific (a concrete action, not a vague engagement metric), achievable in session 1, and predictive of 30-day retention.\n"
            "2. TIME-TO-VALUE AUDIT: Map every step between account creation and the user achieving the activation metric. Score each step: Is this step necessary for value delivery, or is it friction we impose on users for our own convenience (marketing opt-in, profile completion, tutorial)? Every unnecessary step has a drop rate cost.\n"
            "3. PROGRESSIVE ONBOARDING vs. UPFRONT TUTORIAL: When does explaining before doing help vs. hurt? Rule: show, don't tell. An empty dashboard with a 'get started' wizard is worse than a pre-populated demo showing what value looks like.\n"
            "4. EMPTY STATE DESIGN: What do users see when they first arrive with no data? An empty state is a conversion opportunity. Best empty state design: explains what goes here, shows what it looks like when populated (screenshot or sample data), and provides the action to get there.\n"
            "5. SAMPLE DATA STRATEGY: Should first-time users see real emptiness or sample data? Sample data lets users evaluate the product before committing to setup. But it must be clearly labeled as sample and easy to clear.\n"
            "6. SETUP FRICTION REDUCTION: For each required setup step, ask: Can we defer this until the user actually needs it? Can we infer it from available signals? Can we provide a sensible default? Required-before-any-value setup is the highest-risk drop point.\n"
            "Output: activation_metric, tta_value_steps, progressive_disclosure_plan, empty_state_designs, sample_data_recommendation, setup_friction_reduction"
        ),
    },
    {
        "slug": "content-copy-design",
        "name": "Content and Copy Design",
        "family": "generative",
        "tier": "built-in",
        "description": "Evaluate and improve the words in a product — labels, errors, empty states, notifications, help text — for clarity, tone consistency, and actionability.",
        "activation_signals": [
            "copy",
            "error messages",
            "microcopy",
            "labels",
            "empty states",
            "notification text",
            "help text",
            "content design",
        ],
        "archetype_affinity": {"creator": 0.9, "analyst": 0.7, "advisor": 0.8},
        "mode_affinity": {"deliberative": 0.9, "procedural": 0.8},
        "composability": {
            "complements": ["user-flow-design", "onboarding-activation-design", "information-architecture"],
            "conflicts": [],
        },
        "system_prompt": (
            "Evaluate and improve product copy:\n"
            "1. CLARITY AUDIT: Would a 12-year-old understand every label and message? Test each piece of copy: can you explain it in simpler language? If yes, simplify. Technical jargon costs comprehension without adding precision.\n"
            "2. ERROR MESSAGE QUALITY: Every error message must have three parts — what happened (specific, not 'An error occurred'), why it happened (if knowable and useful to the user), and what to do next (actionable, not 'contact support'). Vague error messages generate support tickets; clear error messages generate self-service recovery.\n"
            "3. TONE CONSISTENCY: Does the copy voice match across: onboarding, in-product labels, error states, notifications, marketing? Inconsistent tone (formal in settings, casual in errors, clinical in notifications) creates cognitive dissonance and reduces trust.\n"
            "4. TERMINOLOGY CONSISTENCY: Does the product use one word for one concept throughout? Synonyms create confusion (are 'workspace' and 'organization' the same thing?). Audit: create a glossary of key terms and verify each is used exactly one way.\n"
            "5. EMPTY STATE COPY: Empty states are high-visibility, often neglected. Does each empty state explain what goes here, what the user gets when it's populated, and how to populate it?\n"
            "6. NOTIFICATION HIERARCHY: Are notifications actionable or informational? Can users distinguish urgency levels? Is there a systematic approach to when to notify (vs. when to show in-app vs. silently update)?\n"
            "Output: clarity_issues, error_message_redesigns, tone_consistency_score, terminology_glossary, empty_state_rewrites"
        ),
    },
    {
        "slug": "accessibility-design",
        "name": "Accessibility Design",
        "family": "evaluative",
        "tier": "built-in",
        "description": "Evaluate and design accessible interfaces using WCAG 2.2 AA compliance, keyboard navigation flow, screen reader quality, focus management, and ARIA usage.",
        "activation_signals": [
            "accessibility",
            "a11y",
            "wcag",
            "screen reader",
            "keyboard navigation",
            "focus management",
            "aria",
            "color contrast",
        ],
        "archetype_affinity": {"analyst": 0.9, "creator": 0.8, "advisor": 0.7},
        "mode_affinity": {"deliberative": 0.9, "procedural": 0.8},
        "composability": {
            "complements": ["interaction-design", "visual-interface-design", "content-copy-design"],
            "conflicts": [],
        },
        "system_prompt": (
            "Evaluate accessibility compliance and design:\n"
            "1. WCAG 2.2 AA CHECKLIST: Perceivable — text alternatives for non-text content, captions for video, color not the only differentiator, contrast ratios met. Operable — all functionality via keyboard, no seizure triggers, sufficient time limits. Understandable — readable labels, consistent navigation, error identification. Robust — valid HTML, name/role/value for all components.\n"
            "2. KEYBOARD NAVIGATION: Can a keyboard-only user access all functionality? Map the Tab order — does it follow the visual reading order? Are all interactive elements reachable? Is there a skip-to-main-content link? Are modal focus traps implemented correctly (focus stays inside modal until dismissed)?\n"
            "3. SCREEN READER QUALITY: Are all images described (alt text)? Are form inputs associated with labels (not just placeholder text)? Are dynamic updates announced (aria-live regions for status messages)? Are decorative images marked as presentation?\n"
            "4. FOCUS MANAGEMENT: After a modal opens, does focus move to the modal? After it closes, does focus return to the trigger? After a page transition, where does focus land? Poor focus management forces screen reader users to search for their position.\n"
            "5. ARIA USAGE AUDIT: Is ARIA used only when HTML semantics are insufficient? Misused ARIA (aria-label on non-interactive elements, incorrect roles) is worse than no ARIA. Rule: the first rule of ARIA is don't use ARIA when a native HTML element would work.\n"
            "6. COGNITIVE ACCESSIBILITY: Is the reading level appropriate? Are instructions clear before users encounter forms? Are timeouts warned and extendable? Are animations reducible via prefers-reduced-motion?\n"
            "Output: wcag_compliance_matrix, keyboard_navigation_gaps, screen_reader_issues, focus_management_failures, aria_misuse, cognitive_accessibility_score"
        ),
    },
    # ═══════════════════════════════════════════════════════════════
    # LAYER 4 — CODE DESIGN (7)
    # Domain knowledge: module structure, patterns, interfaces, state
    # ═══════════════════════════════════════════════════════════════
    # L4-01
    {
        "slug": "module-architecture",
        "name": "Module Architecture",
        "family": "generative",
        "tier": "built-in",
        "description": "Design module and package structure using vertical slicing, hexagonal architecture, dependency direction rules, and cohesion principles.",
        "activation_signals": [
            "module structure",
            "package design",
            "how to organize code",
            "folder structure",
            "hexagonal architecture",
            "ports and adapters",
            "vertical slice",
            "cohesion",
        ],
        "archetype_affinity": {"executor": 0.9, "analyst": 0.8},
        "mode_affinity": {"deliberative": 0.9, "generative": 0.8},
        "composability": {"complements": ["design-pattern-selection", "dependency-design"], "conflicts": []},
        "system_prompt": (
            "Design the module and package architecture:\n"
            "1. CHOOSE the primary structure axis: by layer (horizontal slice: controllers/services/repos) or by feature (vertical slice: user/, order/, payment/). Vertical slicing wins for teams >2 or features >10 — it co-locates change and reduces merge conflicts.\n"
            "2. APPLY hexagonal architecture principles: separate the domain core (pure business logic, no I/O) from infrastructure (DB, API, file system) via ports (interfaces) and adapters (implementations). The core must be testable without any infrastructure running.\n"
            "3. ENFORCE dependency direction: dependencies must always point inward (toward the domain) or downward (higher abstraction → lower abstraction). A domain module must never import from an infrastructure module. Violations create tightly coupled, untestable code.\n"
            "4. ASSESS cohesion: things that change together should live together. Modules that require coordinated changes across 3+ files to add a single feature have cohesion failure — refactor toward feature co-location.\n"
            "5. IDENTIFY boundary candidates: which modules are good candidates for extraction into separate services or packages? Signals: different deployment frequency, different team ownership, different scaling characteristics, or a clean API boundary already exists.\n"
            "6. CHECK for circular dependencies: does any dependency cycle exist? Cycles indicate abstraction failure — something that should be a shared dependency is embedded in a consumer.\n"
            "Output: structure_axis (layer vs. feature, justification), hexagonal_boundary_map, dependency_direction_violations, cohesion_assessment, boundary_candidates, circular_dependency_check"
        ),
    },
    # L4-02
    {
        "slug": "design-pattern-selection",
        "name": "Design Pattern Selection",
        "family": "evaluative",
        "tier": "built-in",
        "description": "Select appropriate design patterns for the problem at hand while detecting over-engineering, premature abstraction, and pattern misfit.",
        "activation_signals": [
            "design pattern",
            "which pattern",
            "factory",
            "observer",
            "strategy pattern",
            "over-engineering",
            "abstraction",
            "pattern selection",
            "best pattern for",
        ],
        "archetype_affinity": {"executor": 0.9, "analyst": 0.8},
        "mode_affinity": {"deliberative": 0.9, "procedural": 0.8},
        "composability": {"complements": ["module-architecture", "code-interface-design"], "conflicts": []},
        "system_prompt": (
            "Select design patterns for this problem:\n"
            "1. IDENTIFY the structural problem: what is the core design challenge? Map to the canonical problem categories:\n"
            "   - Creational: object creation complexity → Factory, Builder, Singleton (use sparingly — global state)\n"
            "   - Structural: composing objects/classes → Adapter (incompatible interfaces), Decorator (add behavior without subclass), Facade (simplify complex subsystem), Proxy (controlled access)\n"
            "   - Behavioral: algorithms and object interaction → Strategy (interchangeable algorithms), Observer (event propagation), Command (encapsulate operations), Template Method (skeleton + hooks)\n"
            "   - Architectural: system organization → Repository (data access), CQRS (read/write separation), Event Sourcing (audit trail + replay), Saga (distributed transaction)\n"
            "2. APPLY the pattern fit test: does this pattern solve the exact problem, or are we forcing the problem to fit the pattern? The latter is the most common form of over-engineering.\n"
            "3. CHECK for premature abstraction: is the pattern justified by current complexity, or by hypothetical future complexity? Rule of Three — abstract only when the third instance appears, not the first or second.\n"
            "4. ASSESS the indirection cost: every pattern adds indirection. More files, more jumps to understand the code. The pattern must deliver more value in flexibility or testability than it costs in cognitive overhead.\n"
            "5. PREFER composition over inheritance: inheritance couples subclass to superclass implementation. Favor interface composition — it's safer, more testable, and more flexible.\n"
            "Output: problem_category, candidate_patterns, fit_assessment (pattern, solves_exact_problem yes/no, indirection_cost), recommended_pattern, over_engineering_check"
        ),
    },
    # L4-03
    {
        "slug": "code-interface-design",
        "name": "Code Interface Design",
        "family": "generative",
        "tier": "built-in",
        "description": "Design module and function interfaces for minimal surface area, backward compatibility, opaque types, and clear caller contracts.",
        "activation_signals": [
            "interface design",
            "API surface",
            "function signature",
            "public API",
            "backward compatibility",
            "breaking change",
            "minimal interface",
            "caller contract",
        ],
        "archetype_affinity": {"executor": 0.9, "analyst": 0.8},
        "mode_affinity": {"deliberative": 0.9, "generative": 0.8},
        "composability": {"complements": ["type-system-design", "design-pattern-selection"], "conflicts": []},
        "system_prompt": (
            "Design the code interface for this module or function:\n"
            "1. MINIMIZE the public surface: expose only what callers need. Every public function, type, or constant is a commitment. Rule: make everything private by default, make public only when a caller needs it.\n"
            "2. DESIGN for the caller's mental model: the interface should express what the caller wants to accomplish, not how the implementation works. Good function names read like sentences: `getActiveUsersByTeam(teamId)`, not `queryUsersWhere(filters)`.\n"
            "3. ENFORCE opaque types: don't expose raw primitives where domain types are appropriate. `UserId` vs `string`, `Email` vs `string`, `Percentage` vs `number`. Opaque types catch category errors at compile time that string types would miss at runtime.\n"
            "4. APPLY backward compatibility discipline: any change to a public interface is a breaking change for callers. For every proposed change, identify: (a) is it additive (safe) or breaking (requires migration), (b) what is the migration path, (c) can the old interface be preserved as a deprecated wrapper?\n"
            "5. DEFINE the error contract: what errors can this interface throw/return? Should they be typed (checked) or untyped (runtime)? The caller contract must be explicit about the error surface — callers shouldn't need to read implementation to know what can fail.\n"
            "6. CHECK for interface bloat: count the public methods on this module. If >7, assess whether multiple smaller interfaces would be clearer (Interface Segregation Principle).\n"
            "Output: public_surface_audit, caller_mental_model_check, opaque_type_opportunities, breaking_change_assessment, error_contract, interface_bloat_check"
        ),
    },
    # L4-04
    {
        "slug": "state-architecture",
        "name": "State Architecture",
        "family": "generative",
        "tier": "built-in",
        "description": "Design state management: single source of truth, state machine design, client/server state separation, and derived state vs. stored state.",
        "activation_signals": [
            "state management",
            "state machine",
            "where to store state",
            "client state",
            "server state",
            "single source of truth",
            "derived state",
            "reactive state",
        ],
        "archetype_affinity": {"executor": 0.9, "analyst": 0.8},
        "mode_affinity": {"deliberative": 0.9, "generative": 0.8},
        "composability": {"complements": ["module-architecture", "error-architecture"], "conflicts": []},
        "system_prompt": (
            "Design the state architecture for this system or component:\n"
            "1. ENFORCE single source of truth (SSOT): every piece of state should have exactly one canonical location. Identify all current state duplications — they are synchronization bugs waiting to happen.\n"
            "2. SEPARATE state by origin:\n"
            "   - Server state: data that lives on the server (fetch, cache, sync) — use a server-state manager (React Query, SWR, Apollo) not local state\n"
            "   - Client UI state: ephemeral UI state (open/closed, selected tab, form draft) — local component state is correct\n"
            "   - Shared client state: state that multiple components need — context or a state manager (Zustand, Redux, Pinia)\n"
            "   - URL state: state that should survive refresh or sharing (filters, pagination, selected item) — put in URL params\n"
            "3. IDENTIFY derived state: what state can be computed from other state? Derived state should never be stored — it should always be computed. Stored derived state is a consistency bug in waiting.\n"
            "4. DESIGN state machines for complex transitions: any entity with >3 states that can't all transition to each other needs an explicit state machine. State machines prevent impossible states and document valid transitions. Identify the states, events, and guards.\n"
            "5. ASSESS mutation patterns: where does state mutate? Is mutation co-located (pure reducers, immutable updates) or distributed (mutable objects passed by reference)? Distributed mutation is the primary cause of hard-to-trace bugs.\n"
            "6. CHECK for stale state: what caches exist? What invalidation strategy do they use? Stale cache + mutation without invalidation = silent data corruption.\n"
            "Output: ssot_violations, state_separation_map, derived_state_candidates, state_machine_designs, mutation_pattern_audit, cache_invalidation_strategy"
        ),
    },
    # L4-05
    {
        "slug": "error-architecture",
        "name": "Error Architecture",
        "family": "generative",
        "tier": "built-in",
        "description": "Design error handling: error taxonomy, structured error types, propagation strategy, blast radius containment, and recovery paths.",
        "activation_signals": [
            "error handling",
            "error types",
            "exception design",
            "error propagation",
            "blast radius",
            "error taxonomy",
            "recovery",
            "structured errors",
        ],
        "archetype_affinity": {"executor": 0.9, "analyst": 0.8},
        "mode_affinity": {"deliberative": 0.9, "procedural": 0.8},
        "composability": {"complements": ["state-architecture", "type-system-design"], "conflicts": []},
        "system_prompt": (
            "Design the error architecture for this system:\n"
            "1. BUILD the error taxonomy: classify all errors the system can encounter:\n"
            "   - Validation errors: user input is invalid — recoverable, user can fix\n"
            "   - Business logic errors: valid input but rule violation — recoverable with explanation\n"
            "   - Infrastructure errors: network, DB, external API failures — recoverable with retry or fallback\n"
            "   - Programming errors: null dereference, type mismatch, assertion failure — unrecoverable, indicates a bug\n"
            "   - Security errors: authentication, authorization, rate limit — recoverable with proper response\n"
            "2. DESIGN structured error types: errors should carry: error code (machine-readable), message (human-readable), context (request ID, affected entity, stack for debugging), and recovery hint (what the caller should do). String error messages are not errors — they're noise.\n"
            "3. DEFINE propagation strategy: should errors propagate as exceptions (fast-fail, easy to miss) or as result types (explicit handling, verbose)? Choose one strategy per layer — mixing creates inconsistency. Result types (Result<T, E>) are safer for domain boundaries; exceptions are acceptable for truly unrecoverable programming errors.\n"
            "4. CONTAIN blast radius: wrap third-party and infrastructure calls in circuit breakers or bulkheads. A third-party API failure should not crash the entire request. Identify the blast radius of each failure point and add containment at each boundary.\n"
            "5. DESIGN recovery paths: for each infrastructure error, what is the retry strategy (exponential backoff with jitter), fallback (cached data, degraded response), or circuit breaker state? Retrying without backoff causes thundering herd.\n"
            "6. AUDIT error swallowing: search for bare `except: pass`, empty catch blocks, and errors logged but not handled. Each is a reliability blind spot.\n"
            "Output: error_taxonomy, structured_error_design, propagation_strategy (per layer), blast_radius_containment, recovery_paths, error_swallowing_audit"
        ),
    },
    # L4-06
    {
        "slug": "type-system-design",
        "name": "Type System Design",
        "family": "generative",
        "tier": "built-in",
        "description": "Design the type system to make illegal states unrepresentable, use parse-don't-validate, branded types, and discriminated unions to catch errors at compile time.",
        "activation_signals": [
            "type design",
            "type system",
            "make illegal states unrepresentable",
            "parse dont validate",
            "branded types",
            "discriminated unions",
            "type safety",
            "TypeScript types",
            "Pydantic models",
        ],
        "archetype_affinity": {"executor": 0.9, "analyst": 0.8},
        "mode_affinity": {"deliberative": 0.9, "procedural": 0.8},
        "composability": {"complements": ["error-architecture", "code-interface-design"], "conflicts": []},
        "system_prompt": (
            "Design the type system for this domain:\n"
            "1. MAKE ILLEGAL STATES UNREPRESENTABLE: identify all invariants in the domain. For each invariant, ask: does the type system enforce this, or can invalid data be constructed? Replace primitive types with domain types that encode their own invariants (e.g., a `PositiveInt` cannot be negative by construction).\n"
            "2. APPLY PARSE-DON'T-VALIDATE: validation functions that return `bool` allow the validity information to be lost. Instead, parse at the boundary — return a typed success value or a structured error. Once inside the system, data should be trusted by type. Validation at the boundary once beats repeated null checks everywhere.\n"
            "3. USE BRANDED TYPES for primitive obsession: a function that takes `(userId: string, orderId: string)` can be called with arguments reversed. Branded types (`UserId`, `OrderId`) prevent this class of bug entirely at zero runtime cost in TypeScript.\n"
            "4. DESIGN DISCRIMINATED UNIONS for state: represent states as a union of structs rather than a struct with optional fields. `type State = Loading | Error | Success<T>` forces callers to handle each case. A struct with `data?: T, error?: Error, loading?: boolean` allows 8 combinations, most of which are invalid.\n"
            "5. ASSESS nullability: where does null/undefined/None propagate through the system? Explicit `Option<T>` or nullable types are better than implicit nullability. Map all nullable boundaries and ensure callers handle None explicitly.\n"
            "6. CHECK for type aliases vs. nominal types: type aliases (`type UserId = string`) provide documentation but not safety — they are structurally equivalent. Use nominal types (branded or newtype patterns) where category confusion causes bugs.\n"
            "Output: illegal_state_analysis, parse_boundary_map, branded_type_candidates, discriminated_union_designs, nullability_map, nominal_vs_alias_audit"
        ),
    },
    # L4-07
    {
        "slug": "dependency-design",
        "name": "Dependency Design",
        "family": "evaluative",
        "tier": "built-in",
        "description": "Design dependency injection strategy, stable dependency principle, third-party isolation, and dependency inversion to enable testability and change.",
        "activation_signals": [
            "dependency injection",
            "DI",
            "dependency inversion",
            "testability",
            "third-party isolation",
            "stable dependency",
            "inversion of control",
            "seam",
        ],
        "archetype_affinity": {"executor": 0.9, "analyst": 0.8},
        "mode_affinity": {"deliberative": 0.9, "procedural": 0.8},
        "composability": {"complements": ["module-architecture", "code-interface-design"], "conflicts": []},
        "system_prompt": (
            "Design the dependency strategy for this module or system:\n"
            "1. APPLY dependency inversion: high-level modules should not depend on low-level modules. Both should depend on abstractions (interfaces). If a service directly imports a specific database client, it cannot be tested without that database. Inject an interface instead.\n"
            "2. DESIGN injection strategy:\n"
            "   - Constructor injection: for required dependencies that define the object's identity — preferred for services\n"
            "   - Method injection: for optional or request-scoped dependencies\n"
            "   - Property injection: for optional dependencies with sensible defaults — use sparingly\n"
            "   - Service locator: an anti-pattern — it hides dependencies and makes testing hard\n"
            "3. ENFORCE stable dependency principle: packages should depend on packages that are more stable than themselves. An unstable module (changes often) should never be depended upon by a stable module. Map stability scores (abstract + stable > concrete + unstable).\n"
            "4. ISOLATE third-party dependencies: wrap every third-party library in an adapter interface. This creates a seam — the code can be tested without the third party, the third party can be swapped without changing callers, and the integration surface is explicit and auditable.\n"
            "5. IDENTIFY hidden dependencies: global variables, singletons, class-level state, and module-level side effects are hidden dependencies. They make tests order-dependent and mutation hard to track. Identify and externalize them.\n"
            "6. AUDIT circular dependencies: any cycle in the dependency graph indicates an abstraction failure. Extract the shared dependency into its own module with no upward dependencies.\n"
            "Output: inversion_opportunities, injection_strategy (per dependency type), stability_map, third_party_adapters, hidden_dependency_audit, circular_dependency_check"
        ),
    },
    # ═══════════════════════════════════════════════════════════════
    # LAYER 5 — CODE CRAFT (8)
    # Domain knowledge: readability, function design, performance,
    # security coding, concurrency, testing, refactoring
    # ═══════════════════════════════════════════════════════════════
    # L5-01
    {
        "slug": "readability-naming",
        "name": "Readability & Naming",
        "family": "evaluative",
        "tier": "built-in",
        "description": "Evaluate code readability: naming quality, scope-matched names, domain language usage, comment quality, and cognitive complexity.",
        "activation_signals": [
            "readability",
            "naming",
            "variable names",
            "function names",
            "comments",
            "cognitive complexity",
            "code clarity",
            "self-documenting",
        ],
        "archetype_affinity": {"executor": 0.9, "analyst": 0.8},
        "mode_affinity": {"deliberative": 0.9, "reflective": 0.8},
        "composability": {"complements": ["function-design", "refactoring-strategy"], "conflicts": []},
        "system_prompt": (
            "Evaluate code readability and naming quality:\n"
            "1. ASSESS naming against intent: every name should reveal intent. Test: can you understand what a function does from its name alone without reading the body? Can you understand what a variable holds without reading how it's assigned? Rename anything that fails this test.\n"
            "2. APPLY scope-matched naming: short names (x, i, n) are appropriate for small scopes (2-3 lines). Long names (userAccountActivationEmailTemplate) are appropriate for large scopes (module-level). Mismatch in either direction creates confusion.\n"
            "3. USE domain language: names should use the vocabulary of the business domain, not technical implementation details. `processUserData` is technical. `activateTrialAccount` is domain language. Domain names make code readable by non-engineers and reveal when implementation drifts from intent.\n"
            "4. AUDIT comments for staleness: comments that explain WHAT the code does are code smell — the code should explain itself. Comments that explain WHY a non-obvious choice was made are valuable. Audit all comments: is this explaining why, or compensating for unclear code?\n"
            "5. MEASURE cognitive complexity: count decision points (if, for, while, &&, ||, ternary, catch). Cognitive complexity > 10 in a function is a smell. > 15 is a refactor candidate. High complexity is the primary readability killer.\n"
            "6. CHECK for abbreviations and acronyms: abbreviations save keystrokes at the cost of comprehension. `usr`, `cfg`, `msg` are acceptable only in contexts where every developer knows the abbreviation. Unknown abbreviations are bugs waiting to be introduced by misinterpretation.\n"
            "Output: naming_failures (name, problem, suggested_rename), scope_mismatches, domain_language_gaps, comment_audit (explaining_what vs. explaining_why), cognitive_complexity_map, abbreviation_risks"
        ),
    },
    # L5-02
    {
        "slug": "function-design",
        "name": "Function Design",
        "family": "evaluative",
        "tier": "built-in",
        "description": "Evaluate function design: single responsibility, size, pure vs. impure separation, guard clauses, and parameter design.",
        "activation_signals": [
            "function design",
            "function size",
            "single responsibility",
            "pure functions",
            "side effects",
            "guard clauses",
            "parameter design",
            "function too long",
        ],
        "archetype_affinity": {"executor": 0.9, "analyst": 0.8},
        "mode_affinity": {"deliberative": 0.9, "procedural": 0.8},
        "composability": {"complements": ["readability-naming", "refactoring-strategy"], "conflicts": []},
        "system_prompt": (
            "Evaluate function design quality:\n"
            "1. TEST single responsibility: a function should do ONE thing at ONE level of abstraction. If the function's name requires 'and' to describe it, it's doing two things. If it mixes high-level coordination (calling other functions) with low-level details (string parsing), it violates single level of abstraction.\n"
            "2. ASSESS function size: functions longer than 20 lines are suspect; longer than 40 lines are almost always wrong. Long functions accumulate complexity over time. Identify extraction candidates: any logic block that could be named is a candidate for extraction.\n"
            "3. SEPARATE pure from impure: pure functions (same input → same output, no side effects) are deterministic, testable, and composable. Impure functions (I/O, mutation, randomness, time) are harder to test. Identify all impure functions. Push impurity to the edges — the core domain should be pure.\n"
            "4. APPLY guard clauses: deep nesting (if → if → if) is a readability failure. Replace with early returns that guard the main logic. The happy path should be the unindented path. Guard clauses also catch precondition violations explicitly rather than letting them cause confusing failures downstream.\n"
            "5. DESIGN parameters: functions with >3 parameters are harder to call correctly. Options: group related parameters into an object (parameter object pattern), use builder pattern for complex construction, or decompose the function. Positional parameters are dangerous when multiple parameters have the same type.\n"
            "6. CHECK for boolean parameters: a boolean parameter is almost always a sign that the function should be two functions. `sendEmail(user, isReminder: boolean)` → `sendWelcomeEmail(user)` and `sendReminderEmail(user)`. Boolean parameters hide intent at the call site.\n"
            "Output: srp_violations, size_assessment, pure_impure_map, nesting_depth_issues, parameter_count_violations, boolean_parameter_flags"
        ),
    },
    # L5-03
    {
        "slug": "core-tradeoffs",
        "name": "Core Engineering Tradeoffs",
        "family": "evaluative",
        "tier": "built-in",
        "description": "Apply the 10 canonical software engineering tradeoff pairs: simplicity/power, speed/correctness, coupling/cohesion, consistency/availability, and 6 others — with defaults and shift conditions.",
        "activation_signals": [
            "tradeoffs",
            "engineering tradeoffs",
            "simplicity vs power",
            "speed vs correctness",
            "coupling vs cohesion",
            "consistency vs availability",
            "CAP theorem",
            "what should we optimize for",
            "tradeoff analysis",
        ],
        "archetype_affinity": {"analyst": 0.9, "advisor": 0.9, "executor": 0.7},
        "mode_affinity": {"deliberative": 0.9, "reflective": 0.8},
        "composability": {"complements": ["design-pattern-selection", "module-architecture"], "conflicts": []},
        "system_prompt": (
            "Apply the canonical engineering tradeoff pairs to this decision:\n\n"
            "TRADEOFF 1 — SIMPLICITY vs POWER\n"
            "Default: simplicity. A simple solution that works is always better than a powerful solution that adds complexity the team can't manage.\n"
            "Shift toward power when: the simple solution genuinely cannot handle the scale, and you have measured evidence of that limit.\n\n"
            "TRADEOFF 2 — SPEED vs CORRECTNESS\n"
            "Default: correctness. Speed is recoverable. Data corruption and security failures are not.\n"
            "Shift toward speed when: the domain is inherently approximate (recommendations, search ranking, analytics), and users understand estimates.\n\n"
            "TRADEOFF 3 — COUPLING vs COHESION\n"
            "Default: high cohesion, low coupling. Co-locate what changes together; separate what changes independently.\n"
            "Shift toward more coupling when: the overhead of communication between decoupled components exceeds the benefit (micro-services too early is a common error).\n\n"
            "TRADEOFF 4 — CONSISTENCY vs AVAILABILITY (CAP theorem)\n"
            "Default: depends on domain. Financial data → strong consistency. User preferences → eventual consistency is fine.\n"
            "Shift toward availability when: brief inconsistency is tolerable and the system must serve requests even during network partitions.\n\n"
            "TRADEOFF 5 — LATENCY vs THROUGHPUT\n"
            "Default: depends on user-facing vs. batch. User-facing → optimize latency (p99 matters). Batch → optimize throughput (total volume matters).\n"
            "Shift when: the system is mixed and you need to segment traffic (priority queues, separate endpoints).\n\n"
            "TRADEOFF 6 — PREMATURE OPTIMIZATION vs PROVEN BOTTLENECK\n"
            "Default: don't optimize until you have profiler evidence. 'Premature optimization is the root of all evil' — Knuth.\n"
            "Shift toward optimization when: profiling shows that a specific code path consumes >20% of total time or cost.\n\n"
            "TRADEOFF 7 — ABSTRACTION vs SPECIFICITY\n"
            "Default: specific. Abstractions carry a cost: indirection, learning curve, and premature generalization. Abstract only when the third instance appears (Rule of Three).\n"
            "Shift toward abstraction when: a pattern has appeared 3+ times in different contexts with clear generalization.\n\n"
            "TRADEOFF 8 — SYNCHRONOUS vs ASYNCHRONOUS\n"
            "Default: synchronous. Async adds complexity: race conditions, error propagation, debugging difficulty. Use async when the benefit (parallelism, decoupling) clearly outweighs the cost.\n"
            "Shift toward async when: operations are genuinely independent and parallelism provides measurable benefit, or decoupling via a queue is architecturally required.\n\n"
            "TRADEOFF 9 — BUILD vs BUY vs BORROW\n"
            "Default: borrow (use open-source). Buy when total cost of ownership (including integration and ops) is lower than alternatives. Build only when the component is a core differentiator that no external solution can match.\n"
            "Shift toward build when: the problem is genuinely novel, existing solutions impose unacceptable constraints, or the component is strategic IP.\n\n"
            "TRADEOFF 10 — FLEXIBILITY vs CONSTRAINTS\n"
            "Default: constraints. Constraints eliminate entire categories of bugs. Constraints make systems easier to reason about. Flexibility is expensive to maintain and often goes unused.\n"
            "Shift toward flexibility when: the requirements are genuinely unknown and an extension point is the only way to accommodate future change without breaking the system.\n\n"
            "FOR THIS DECISION: identify which tradeoffs are active, state the current position on each axis, assess whether the default is appropriate for the context, and explain what evidence would justify shifting from the default.\n"
            "Output: active_tradeoffs, current_positions, default_appropriateness, shift_conditions, recommended_positions"
        ),
    },
    # L5-04
    {
        "slug": "performance-coding",
        "name": "Performance Coding",
        "family": "evaluative",
        "tier": "built-in",
        "description": "Apply performance engineering: algorithmic complexity, N+1 detection, memory allocation patterns, I/O batching, caching strategy, and profiling-first discipline.",
        "activation_signals": [
            "performance",
            "slow",
            "Big-O",
            "N+1",
            "caching",
            "batching",
            "memory",
            "profiling",
            "optimization",
            "latency",
        ],
        "archetype_affinity": {"executor": 0.9, "analyst": 0.8},
        "mode_affinity": {"deliberative": 0.9, "procedural": 0.8},
        "composability": {"complements": ["core-tradeoffs", "concurrency-design"], "conflicts": []},
        "system_prompt": (
            "Apply performance engineering discipline to this code:\n"
            "1. PROFILE FIRST: identify the specific bottleneck with evidence before optimizing. Gut-feel optimization is as likely to create complexity as to improve performance. Performance work without a profiler is speculation.\n"
            "2. ASSESS algorithmic complexity: what is the Big-O of the hot path? O(n²) in a tight loop with n>1000 is usually unacceptable. O(n log n) is usually fine. O(n) is the target for real-time paths. O(1) is the target for per-request overhead.\n"
            "3. DETECT N+1 queries: a loop that executes a database or network call per iteration is an N+1 problem. Always batch: collect all IDs, fetch in one query with IN clause or batch API call. N+1 patterns are the single most common source of production performance regressions.\n"
            "4. AUDIT memory allocation: in hot paths, avoid allocating large objects in loops, avoid unnecessary copies, and reuse buffers where possible. In garbage-collected languages, excessive allocation creates GC pressure that manifests as latency spikes.\n"
            "5. DESIGN caching strategy: identify what can be cached and for how long. Cache at the highest layer possible (CDN > API gateway > application > database). Every cache needs: a key strategy, an invalidation strategy, and a TTL. Caches without invalidation strategies are correctness bugs.\n"
            "6. IDENTIFY I/O batching opportunities: any sequential I/O operations that could be parallelized or batched should be. For database writes, use batch inserts. For external API calls, use bulk endpoints. For independent I/O, use concurrent execution (Promise.all, asyncio.gather).\n"
            "Output: profiling_evidence_requirement, algorithmic_complexity_assessment, n_plus_1_locations, memory_allocation_audit, caching_strategy, io_batching_opportunities"
        ),
    },
    # L5-05
    {
        "slug": "security-coding",
        "name": "Security Coding",
        "family": "adversarial",
        "tier": "built-in",
        "description": "Apply OWASP Top 10 coding defenses: injection prevention, authentication hardening, access control, XSS/CSRF, sensitive data handling, and security misconfiguration.",
        "activation_signals": [
            "security",
            "injection",
            "SQL injection",
            "XSS",
            "CSRF",
            "authentication",
            "authorization",
            "OWASP",
            "input validation",
            "sensitive data",
        ],
        "archetype_affinity": {"analyst": 0.9, "executor": 0.8},
        "mode_affinity": {"deliberative": 0.9, "procedural": 0.8},
        "composability": {"complements": ["error-architecture", "type-system-design"], "conflicts": []},
        "system_prompt": (
            "Apply security engineering defenses to this code (OWASP Top 10):\n"
            "1. INJECTION (A03): never concatenate user input into SQL, shell commands, LDAP queries, or HTML. Use parameterized queries for SQL (no string interpolation — ever). Use allow-list validation for all external input. Treat all data from outside the trust boundary as hostile until proven safe.\n"
            "2. AUTHENTICATION FAILURES (A07): passwords must be hashed with bcrypt/argon2/scrypt — never MD5, SHA-1, or reversible encryption. Session tokens must be cryptographically random (min 128 bits). Implement rate limiting on auth endpoints. Never log passwords, tokens, or secrets.\n"
            "3. ACCESS CONTROL (A01): every endpoint must verify authorization, not just authentication. Implement deny-by-default — grant specific permissions, not broad access. Check ownership on every data access: can this authenticated user actually access this specific record? IDOR (Insecure Direct Object Reference) is the most common access control failure.\n"
            "4. XSS (A03): escape all user-controlled data before rendering in HTML (entity encoding). Use Content Security Policy headers. Never use innerHTML with user data — use textContent or a safe DOM API. For React/Vue/Angular, avoid dangerouslySetInnerHTML with user data.\n"
            "5. SENSITIVE DATA (A02): identify what counts as sensitive (PII, credentials, financial, health). Sensitive data must be encrypted at rest and in transit. Never log sensitive data. Apply data minimization — don't collect what you don't need. Apply retention limits — don't keep what you don't need anymore.\n"
            "6. SECURITY MISCONFIGURATION (A05): disable debug mode in production. Remove default credentials. Apply least-privilege principles to service accounts. Validate TLS configuration (no TLS 1.0/1.1). Set security headers: HSTS, X-Frame-Options, X-Content-Type-Options, Referrer-Policy.\n"
            "Output: injection_risks, auth_failures, access_control_gaps, xss_risks, sensitive_data_exposure, misconfiguration_checklist"
        ),
    },
    # L5-06
    {
        "slug": "concurrency-design",
        "name": "Concurrency Design",
        "family": "evaluative",
        "tier": "built-in",
        "description": "Design concurrent systems: race condition prevention, deadlock avoidance, async correctness, idempotency, and distributed concurrency patterns.",
        "activation_signals": [
            "concurrency",
            "race condition",
            "deadlock",
            "async",
            "parallel",
            "thread safety",
            "idempotency",
            "distributed lock",
            "mutex",
        ],
        "archetype_affinity": {"executor": 0.9, "analyst": 0.8},
        "mode_affinity": {"deliberative": 0.9, "procedural": 0.8},
        "composability": {"complements": ["state-architecture", "error-architecture"], "conflicts": []},
        "system_prompt": (
            "Design for correct concurrent behavior:\n"
            "1. IDENTIFY shared mutable state: shared state is the root of most concurrency bugs. For each piece of shared mutable state, identify: who reads it, who writes it, and what invariants must hold across read-write sequences. If an invariant must hold across two operations, they must be atomic.\n"
            "2. PREVENT race conditions: a race condition exists when the correctness of the program depends on the relative timing of events. Common forms: check-then-act (read-modify-write without atomicity), lost update (two writers overwrite each other), time-of-check-to-time-of-use (TOCTOU). Use atomic operations, transactions, or optimistic locking to prevent each type.\n"
            "3. AVOID deadlock: deadlock requires four conditions simultaneously (Coffman): mutual exclusion, hold-and-wait, no preemption, circular wait. Break any one. Most practical approach: impose a consistent lock ordering — always acquire locks in the same order across all code paths.\n"
            "4. DESIGN async correctly: in async/await code, identify: (a) where are the await points, (b) what state can change between awaits, (c) are there any operations that must be atomic across awaits? If state can change between two awaits in a sequence, the logic is potentially incorrect without re-validation.\n"
            "5. ENFORCE idempotency: any operation that can be retried (network calls, queue consumers, webhook handlers) must be idempotent. Design: use idempotency keys, use upsert instead of insert, check-before-apply patterns. Idempotent operations can be safely retried without side effects.\n"
            "6. DESIGN for distributed concurrency: if multiple instances can run concurrently, identify: (a) operations that must be exclusive across instances (use distributed locks, leader election, or pessimistic DB locking), (b) operations that must be ordered (use sequence numbers, vector clocks, or append-only event logs).\n"
            "Output: shared_state_map, race_condition_risks, deadlock_prevention_design, async_correctness_audit, idempotency_design, distributed_concurrency_strategy"
        ),
    },
    # L5-07
    {
        "slug": "testing-strategy",
        "name": "Testing Strategy",
        "family": "evaluative",
        "tier": "built-in",
        "description": "Design a testing strategy: test pyramid balance, behavior-not-implementation testing, test double selection, contract testing, and identifying what must be tested vs. what is noise.",
        "activation_signals": [
            "testing strategy",
            "test design",
            "what to test",
            "test pyramid",
            "unit vs integration",
            "mocking",
            "test doubles",
            "contract testing",
            "what tests to write",
        ],
        "archetype_affinity": {"executor": 0.9, "analyst": 0.8},
        "mode_affinity": {"deliberative": 0.9, "procedural": 0.8},
        "composability": {"complements": ["function-design", "error-architecture"], "conflicts": []},
        "system_prompt": (
            "Design the testing strategy for this code:\n"
            "1. APPLY the test pyramid: unit tests (fast, isolated, many) form the base; integration tests (slower, cross-module, fewer) form the middle; E2E tests (slowest, full system, very few) form the top. Inverted pyramid (many E2E, few units) is slow, brittle, and hard to maintain. Identify the current pyramid shape and whether it's appropriate.\n"
            "2. TEST BEHAVIOR, NOT IMPLEMENTATION: tests that test implementation details break whenever the code is refactored, even when behavior is unchanged. Test what the code produces (output, state change, side effect), not how it does it (internal calls, intermediate state). Avoid testing private methods.\n"
            "3. SELECT test doubles appropriately:\n"
            "   - Stub: provide canned responses, use when you don't care about calls made\n"
            "   - Mock: verify calls were made with expected arguments, use when the call IS the behavior being tested\n"
            "   - Fake: a working but simplified implementation (in-memory DB), use for integration tests\n"
            "   - Spy: record calls without replacing behavior, use for observability in tests\n"
            "   Warning: over-mocking creates tests that pass even when behavior is broken.\n"
            "4. DESIGN contract tests: at service boundaries, define contracts (expected request/response shapes). Contract tests verify both sides honor the contract. They catch integration failures earlier than E2E tests with less brittleness.\n"
            "5. IDENTIFY test coverage value: not all code needs the same test coverage. Prioritize: business logic (must be tested), error handling (must be tested), integration points (must be tested), data transformations (must be tested). De-prioritize: framework boilerplate, getters/setters, logging.\n"
            "6. CHECK for test quality anti-patterns: tests that never fail, tests that test the test framework, tests with no assertions, tests that share mutable state, and tests that depend on execution order.\n"
            "Output: pyramid_assessment, behavior_test_opportunities, test_double_selection, contract_test_boundaries, coverage_priority_map, anti_pattern_audit"
        ),
    },
    # L5-08
    {
        "slug": "refactoring-strategy",
        "name": "Refactoring Strategy",
        "family": "evaluative",
        "tier": "built-in",
        "description": "Plan safe refactoring: code smell identification, safe prerequisites (tests + types), strangler fig for large rewrites, and technical debt classification.",
        "activation_signals": [
            "refactoring",
            "code smells",
            "technical debt",
            "how to refactor",
            "safe refactor",
            "strangler fig",
            "rewrite vs refactor",
            "cleanup",
        ],
        "archetype_affinity": {"executor": 0.9, "analyst": 0.8},
        "mode_affinity": {"deliberative": 0.9, "reflective": 0.8},
        "composability": {"complements": ["readability-naming", "function-design"], "conflicts": []},
        "system_prompt": (
            "Plan a safe refactoring approach:\n"
            "1. IDENTIFY code smells (catalog):\n"
            "   - Bloaters: long method (>40 lines), large class (>500 lines), long parameter list (>3), data clumps (groups of data that travel together)\n"
            "   - OO Abusers: switch statements on type (use polymorphism), parallel inheritance hierarchies\n"
            "   - Change Preventers: divergent change (class changes for multiple reasons), shotgun surgery (single change requires modifications in many places), parallel inheritance hierarchy\n"
            "   - Dispensables: comments (compensating for unclear code), duplicate code, dead code, speculative generality (YAGNI)\n"
            "   - Couplers: feature envy (method uses another class's data more than its own), inappropriate intimacy, message chains\n"
            "2. VERIFY safe prerequisites: refactoring without tests is rewriting. Before any refactoring: ensure test coverage of the behavior being changed, ensure types capture the current contracts, and run the tests to establish a green baseline.\n"
            "3. APPLY strangler fig for large rewrites: never do a big-bang rewrite. Strangle the old system: (a) create the new implementation alongside the old, (b) route a subset of traffic to the new path, (c) verify equivalence, (d) expand routing, (e) remove the old path. This keeps the system running throughout.\n"
            "4. CLASSIFY technical debt:\n"
            "   - Reckless intentional: 'we don't have time for design' (repay immediately — it costs more every day)\n"
            "   - Prudent intentional: 'we'll ship now and refactor later' (schedule explicitly — unscheduled prudent debt becomes reckless)\n"
            "   - Inadvertent: 'we didn't know about this pattern' (refactor on next touch)\n"
            "   - Reckless inadvertent: 'what's layering?' (team education required)\n"
            "5. SEQUENCE the refactoring: which smells have the highest leverage? Start with the smells that block other work or that are in the highest-churn code. Refactoring rarely-touched code is low ROI.\n"
            "6. APPLY the boy scout rule: always leave the code cleaner than you found it. Small, incremental improvements compound over time without the risk of large refactoring sessions.\n"
            "Output: smell_catalog (smell, location, severity), prerequisite_checklist, strangler_fig_plan (if applicable), debt_classification, refactoring_sequence, high_leverage_targets"
        ),
    },
    # ═══════════════════════════════════════════════════════════════
    # LAYER 6 — OPERATIONS & INFRASTRUCTURE (6)
    # Domain knowledge: deployment, observability, incidents,
    # migration, cost, capacity
    # ═══════════════════════════════════════════════════════════════
    # L6-01
    {
        "slug": "deployment-strategy",
        "name": "Deployment Strategy",
        "family": "evaluative",
        "tier": "built-in",
        "description": "Design deployment strategy: blue/green, canary, feature flags, rollback gates, and progressive delivery to safely ship changes.",
        "activation_signals": [
            "deployment strategy",
            "blue green",
            "canary deployment",
            "feature flags",
            "rollout strategy",
            "rollback",
            "progressive delivery",
            "how to deploy",
        ],
        "archetype_affinity": {"executor": 0.9, "analyst": 0.8},
        "mode_affinity": {"deliberative": 0.9, "procedural": 0.8},
        "composability": {"complements": ["observability-operations", "migration-evolution"], "conflicts": []},
        "system_prompt": (
            "Design the deployment strategy for this change:\n"
            "1. ASSESS change risk: how much of the system does this change affect? What is the blast radius if it fails? High-risk changes (schema migrations, auth changes, pricing changes) need more conservative deployment than low-risk changes (copy changes, new isolated features).\n"
            "2. SELECT deployment pattern:\n"
            "   - Big bang: deploy to all at once. Acceptable only for low-risk, easily rollbackable changes.\n"
            "   - Blue/green: maintain two identical environments, route traffic between them. Zero-downtime, instant rollback. High infra cost.\n"
            "   - Canary: route a small % of traffic to new version, monitor, expand. Best for high-risk changes. Requires good observability to detect regression in canary traffic.\n"
            "   - Feature flags: deploy code disabled, enable per user/cohort/% . Decouples deploy from release. Best for new features. Requires flag cleanup discipline.\n"
            "3. DEFINE rollback criteria: before deploying, specify the exact metrics that would trigger a rollback. Error rate > X%, p99 latency > Yms, conversion drop > Z%. Rollback decisions made in an incident are made under pressure and without clear criteria — define them upfront.\n"
            "4. DESIGN database migration compatibility: does this deploy include a schema migration? Schema migrations and application deploys must be independent. Pattern: expand-migrate-contract — add new columns before removing old ones, support both schemas simultaneously during transition.\n"
            "5. PLAN smoke tests: what is the minimal set of checks that confirm the deploy is healthy? These run automatically after deploy and trigger rollback if they fail. Smoke tests cover the happy path only — they're for fast failure detection, not comprehensive testing.\n"
            "6. DEFINE the deployment runbook: who approves production deploy, what time window is allowed (avoid Friday deploys), what is the rollback procedure, and who is on call during the deploy window.\n"
            "Output: risk_assessment, deployment_pattern_choice, rollback_criteria, migration_compatibility_plan, smoke_test_checklist, deployment_runbook"
        ),
    },
    # L6-02
    {
        "slug": "observability-operations",
        "name": "Observability Operations",
        "family": "generative",
        "tier": "built-in",
        "description": "Design observability: structured logging, metrics selection, distributed tracing, alerting thresholds, and runbooks for the three pillars.",
        "activation_signals": [
            "observability",
            "logging",
            "metrics",
            "tracing",
            "alerting",
            "monitoring",
            "dashboards",
            "SLO",
            "SLA",
            "what to instrument",
        ],
        "archetype_affinity": {"executor": 0.9, "analyst": 0.8},
        "mode_affinity": {"deliberative": 0.9, "procedural": 0.8},
        "composability": {"complements": ["deployment-strategy", "incident-response"], "conflicts": []},
        "system_prompt": (
            "Design the observability architecture for this system:\n"
            "1. DESIGN structured logging: logs must be machine-parseable (JSON), include correlation IDs (trace_id, request_id, user_id), log at appropriate levels (DEBUG for development, INFO for significant state transitions, WARN for recoverable errors, ERROR for failures requiring attention). Never log sensitive data.\n"
            "2. SELECT metrics: instrument with the USE method (Utilization, Saturation, Errors) for resources and the RED method (Rate, Errors, Duration) for services. Key metrics: request rate (RPS), error rate (%), latency (p50, p95, p99), saturation (queue depth, connection pool usage). Avoid metric explosion — fewer, more meaningful metrics beat many noisy ones.\n"
            "3. IMPLEMENT distributed tracing: every request should carry a trace ID from entry to all downstream calls. Trace spans should include: service name, operation name, duration, status code, and key business identifiers. Tracing enables root-cause analysis for distributed failures that logs and metrics alone cannot explain.\n"
            "4. DEFINE SLOs and alerting thresholds: set SLOs for availability (e.g., 99.9% uptime) and latency (e.g., p99 < 500ms). Alert on SLO burn rate, not individual threshold violations — burn rate alerts are more actionable and create fewer false positives. Pages should be for things that require immediate human action.\n"
            "5. DESIGN dashboards: one overview dashboard (system health at a glance), one per-service dashboard (USE + RED for each service), one business metrics dashboard (conversion, revenue, activation). Dashboards are read by humans in incidents — optimize for at-a-glance comprehension, not data density.\n"
            "6. WRITE runbooks: for every alert, there must be a runbook. Minimum: what does this alert mean, what is the immediate mitigation (not root-cause fix, just stop the bleeding), who to escalate to. Runbooks reduce MTTR and remove the cognitive load of incident response.\n"
            "Output: logging_design, metric_selection (USE/RED), tracing_plan, slo_definitions, alerting_strategy, dashboard_specs, runbook_templates"
        ),
    },
    # L6-03
    {
        "slug": "incident-response",
        "name": "Incident Response",
        "family": "adversarial",
        "tier": "built-in",
        "description": "Design incident response playbooks: detection, triage, mitigation, communication, post-mortem, and blameless culture.",
        "activation_signals": [
            "incident response",
            "on-call",
            "outage",
            "post-mortem",
            "runbook",
            "triage",
            "escalation",
            "blameless",
            "incident process",
        ],
        "archetype_affinity": {"advisor": 0.9, "analyst": 0.8},
        "mode_affinity": {"deliberative": 0.9, "procedural": 0.8},
        "composability": {"complements": ["observability-operations", "deployment-strategy"], "conflicts": []},
        "system_prompt": (
            "Design the incident response process:\n"
            "1. DESIGN detection: incidents that require human escalation should be detected automatically by alerting systems, not discovered by customers first. What is the current alert coverage? Which failure modes are not covered by alerts? Detection time is the first component of MTTR.\n"
            "2. DEFINE severity levels and triage: classify incidents by customer impact (SEV1: complete outage, SEV2: major degradation, SEV3: partial degradation, SEV4: minor issue). Each severity level needs: response time SLA, escalation path, and communication template.\n"
            "3. DESIGN the mitigation playbook: for each known failure mode, document the mitigation steps. Mitigation (stopping the bleeding) comes before root-cause analysis. During an incident: (a) mitigate, (b) communicate, (c) understand, (d) prevent recurrence. Doing root cause during active incident delays mitigation.\n"
            "4. DESIGN incident communication: internal (team) and external (customers) communication must be on separate channels. Customer communication: acknowledge quickly (within 5 minutes for SEV1), communicate impact (not technical details), give ETAs when known, update on progress. Never promise an ETA you can't keep.\n"
            "5. DESIGN the post-mortem process: post-mortems should be blameless (individuals made reasonable decisions given what they knew at the time — systems and processes failed, not people). Structure: timeline, contributing factors, impact, action items. Action items have owners and due dates or they don't get done.\n"
            "6. APPLY the GameDay principle: the best preparation for incidents is practicing them. GameDay: intentionally cause known failure modes in a controlled environment and practice the response. Systems that have never been failed are not reliable — they're untested.\n"
            "Output: detection_coverage_gap, severity_classification_system, mitigation_playbooks, communication_templates, postmortem_template, gameday_plan"
        ),
    },
    # L6-04
    {
        "slug": "migration-evolution",
        "name": "Migration & Evolution",
        "family": "generative",
        "tier": "built-in",
        "description": "Plan database and API migrations: backward-compatible changes, expand-migrate-contract, API versioning, and zero-downtime migration patterns.",
        "activation_signals": [
            "migration",
            "schema change",
            "API versioning",
            "backward compatibility",
            "database migration",
            "zero downtime migration",
            "breaking change",
            "deprecation",
        ],
        "archetype_affinity": {"executor": 0.9, "analyst": 0.8},
        "mode_affinity": {"deliberative": 0.9, "procedural": 0.8},
        "composability": {"complements": ["deployment-strategy", "backward-compatibility"], "conflicts": []},
        "system_prompt": (
            "Plan the migration or evolution strategy:\n"
            "1. CLASSIFY the change: additive (new column/endpoint, backward compatible, deploy freely), subtractive (remove column/endpoint, breaking, requires migration), transformative (rename, restructure, requires translate-and-migrate).\n"
            "2. APPLY expand-migrate-contract for database migrations:\n"
            "   - Expand: add new columns/tables, keep old structure running\n"
            "   - Migrate: backfill data to new structure, run both simultaneously\n"
            "   - Contract: remove old structure once all consumers use new\n"
            "   Never drop a column in the same deploy that adds its replacement — they must be in separate deploys.\n"
            "3. DESIGN API versioning strategy: choose a versioning approach and apply it consistently:\n"
            "   - URL path versioning (/v1/, /v2/): explicit, cacheable, but creates parallel code trees\n"
            "   - Header versioning (Accept: application/v2+json): cleaner URLs, harder to test in browser\n"
            "   - Parameter versioning (?version=2): simple but pollutes query strings\n"
            "   Maintain previous version until all consumers have migrated. Never remove a version without a deprecation period with client notification.\n"
            "4. DESIGN zero-downtime migrations for large tables: for tables with >1M rows, avoid locking migrations. Use: (a) background migration jobs, (b) shadow tables with dual-write, (c) pt-online-schema-change / gh-ost for MySQL. Migrations that lock tables create outages.\n"
            "5. PLAN client migration: who are the consumers of this API/schema? Can you control them (internal consumers, easy migration) or not (external consumers, need longer deprecation window)? Design the migration in terms of consumer readiness, not just server readiness.\n"
            "6. DEFINE rollback: for every migration step, what is the rollback procedure? Rollback from a schema migration after data has been written is harder than rollback from a code deploy — plan for it explicitly.\n"
            "Output: change_classification, expand_migrate_contract_plan, versioning_strategy, large_table_migration_plan, consumer_migration_plan, rollback_procedures"
        ),
    },
    # L6-05
    {
        "slug": "cost-engineering",
        "name": "Cost Engineering",
        "family": "evaluative",
        "tier": "built-in",
        "description": "Analyze and optimize cloud/infrastructure cost: cost per unit, right-sizing, waste identification, cost attribution, and build-vs-managed tradeoffs.",
        "activation_signals": [
            "cost optimization",
            "cloud cost",
            "infrastructure cost",
            "cost per user",
            "right-sizing",
            "cost attribution",
            "AWS cost",
            "spend",
            "budget",
        ],
        "archetype_affinity": {"analyst": 0.9, "advisor": 0.8},
        "mode_affinity": {"deliberative": 0.9, "reflective": 0.8},
        "composability": {"complements": ["capacity-planning", "deployment-strategy"], "conflicts": []},
        "system_prompt": (
            "Analyze and optimize infrastructure cost:\n"
            "1. CALCULATE cost per unit: what is the cost per user, per request, or per unit of value delivered? Cost without a denominator is not useful for decision-making. If you can't calculate cost per unit, identify what data you need to do so.\n"
            "2. IDENTIFY waste: unused resources, over-provisioned instances, idle services, data stored beyond retention requirements. Common waste sources: development/staging environments running 24/7 (schedule them), over-provisioned reserved instances (right-size before reserving), unused storage (lifecycle policies), orphaned snapshots and backups.\n"
            "3. APPLY right-sizing: most services are over-provisioned. Analyze CPU and memory utilization over 2-4 weeks. Target: average CPU at 40-60%, memory at 60-80%. Resources consistently below 20% utilization are strong right-sizing candidates.\n"
            "4. DESIGN cost attribution: every cost should be attributable to a product, team, feature, or customer segment. Unattributed costs can't be optimized. Use tagging (AWS/GCP/Azure resource tags) to enable cost breakdowns by dimension.\n"
            "5. EVALUATE build vs. managed: managed services (RDS, ElastiCache, Kafka) cost more per unit than self-managed equivalents but eliminate operations overhead. The real cost is engineering time + operations burden, not just the cloud bill. Calculate total cost of ownership for each significant managed service vs. self-managed alternative.\n"
            "6. APPLY spot/preemptible strategy: batch workloads and fault-tolerant services (workers, ML training, test suites) should run on spot/preemptible instances at 60-90% discount. Services requiring SLA (user-facing APIs, databases) should use on-demand or reserved.\n"
            "Output: cost_per_unit, waste_identification, rightsizing_recommendations, cost_attribution_design, build_vs_managed_analysis, spot_preemptible_candidates"
        ),
    },
    # L6-06
    {
        "slug": "capacity-planning",
        "name": "Capacity Planning",
        "family": "predictive",
        "tier": "built-in",
        "description": "Plan infrastructure capacity: growth projection, bottleneck identification, scaling thresholds, headroom requirements, and load testing.",
        "activation_signals": [
            "capacity planning",
            "scaling",
            "how much capacity",
            "growth projection",
            "load testing",
            "scaling thresholds",
            "headroom",
            "when will we hit limits",
        ],
        "archetype_affinity": {"analyst": 0.9, "advisor": 0.8},
        "mode_affinity": {"deliberative": 0.9, "reflective": 0.8},
        "composability": {"complements": ["cost-engineering", "observability-operations"], "conflicts": []},
        "system_prompt": (
            "Plan infrastructure capacity:\n"
            "1. ESTABLISH current capacity baseline: what is the current throughput (RPS, concurrent users, data volume)? What is the current headroom (current usage vs. maximum capacity)? Headroom below 30% requires immediate attention — it's one viral event from an outage.\n"
            "2. PROJECT growth: extrapolate current growth trend over 3, 6, and 12 months. Apply the growth model: linear growth (predictable, safe to plan for), exponential growth (requires step-function capacity increases), spike-driven growth (events, launches — plan for 10× normal capacity).\n"
            "3. IDENTIFY bottlenecks: in any system, there is exactly one bottleneck at any given time. Use the USE method to identify it: which resource (CPU, memory, network, I/O, database connections) is the first to saturate as load increases? All other optimization is secondary to the bottleneck.\n"
            "4. DEFINE scaling thresholds: at what capacity utilization does each component need to scale? Set automatic scaling triggers at 60-70% utilization — reactive scaling (at 90%+) is too late. Include scale-in thresholds to avoid over-provisioning after spikes.\n"
            "5. DESIGN load testing: load tests must reflect realistic traffic patterns, not just peak load. Include: gradual ramp (find breaking points), sustained load (find degradation over time), spike test (find cold start and burst behavior). Load test in an environment that mirrors production — different hardware gives different results.\n"
            "6. PLAN for failure: at what load does the system degrade gracefully vs. fail hard? Design shedding (reject requests above threshold) before cascading failure. Graceful degradation (slower responses, reduced features) is always preferable to complete failure.\n"
            "Output: capacity_baseline, growth_projection (3/6/12 months), bottleneck_identification, scaling_thresholds, load_test_plan, failure_mode_design"
        ),
    },
    # ═══════════════════════════════════════════════════════════════
    # CROSS-LAYER INSTRUMENTS (6)
    # Concerns that cut across all layers — activate at any depth
    # ═══════════════════════════════════════════════════════════════
    # CL-01
    {
        "slug": "tradeoff-analysis",
        "name": "Tradeoff Analysis",
        "family": "evaluative",
        "tier": "built-in",
        "description": "Systematically surface and evaluate architectural and engineering tradeoffs in a decision, making implicit assumptions explicit and quantifying competing pressures.",
        "activation_signals": [
            "what are the tradeoffs",
            "pros and cons",
            "decision analysis",
            "compare options",
            "which approach",
            "tradeoff",
            "evaluate options",
        ],
        "archetype_affinity": {"analyst": 0.9, "advisor": 0.9},
        "mode_affinity": {"deliberative": 0.9, "reflective": 0.8},
        "composability": {"complements": ["core-tradeoffs", "pairwise-comparison"], "conflicts": []},
        "system_prompt": (
            "Perform systematic tradeoff analysis for this decision:\n"
            "1. ENUMERATE the decision options: list all viable options including the status quo (doing nothing is always an option). Incomplete option sets lead to false choices.\n"
            "2. IDENTIFY the evaluation axes: what are the 3-5 dimensions that matter most for this decision? (e.g., development speed, operational complexity, cost, correctness, team expertise, reversibility) Make the axes explicit — hidden evaluation criteria lead to debates where participants talk past each other.\n"
            "3. SCORE each option on each axis: use a consistent scale (1-5 or qualitative: poor/acceptable/good/excellent). The scoring should surface the tradeoffs, not predetermine the answer.\n"
            "4. WEIGHT the axes: not all dimensions are equally important. Apply explicit weights based on the current context (team stage, product maturity, risk tolerance). A startup weights development speed differently than an enterprise with SLA commitments.\n"
            "5. SURFACE implicit assumptions: what must be true for each option's score to be valid? Hidden assumptions are where decisions fail. The option that looks best on paper often has an assumption that doesn't hold in the specific context.\n"
            "6. APPLY the reversibility lens: prefer reversible options when uncertainty is high. A decision that can be changed in 2 weeks costs much less to be wrong about than a decision that locks you in for 2 years. When scores are close, reversibility is the tiebreaker.\n"
            "Output: options_enumerated, evaluation_axes, scored_matrix, weighted_scores, implicit_assumptions_surfaced, reversibility_assessment, recommended_option"
        ),
    },
    # CL-02
    {
        "slug": "backward-compatibility",
        "name": "Backward Compatibility",
        "family": "evaluative",
        "tier": "built-in",
        "description": "Evaluate backward compatibility impact of a change: what breaks, who is affected, what migration is required, and what the deprecation strategy should be.",
        "activation_signals": [
            "backward compatibility",
            "breaking change",
            "deprecation",
            "migration required",
            "API breaking",
            "will this break",
            "existing users",
        ],
        "archetype_affinity": {"analyst": 0.9, "executor": 0.8},
        "mode_affinity": {"deliberative": 0.9, "procedural": 0.8},
        "composability": {"complements": ["migration-evolution", "code-interface-design"], "conflicts": []},
        "system_prompt": (
            "Evaluate backward compatibility for this change:\n"
            "1. ENUMERATE the change surface: list every public interface, API endpoint, schema field, configuration option, and behavior that is changing. Breaking changes are not limited to APIs — behavior changes, configuration changes, and performance characteristic changes are breaking changes for consumers who depend on them.\n"
            "2. CLASSIFY each change:\n"
            "   - Safe additions: new optional fields, new endpoints, new optional parameters, wider return types\n"
            "   - Safe removals: removing never-called endpoints (verify with logs), removing fields never returned\n"
            "   - Breaking: required parameter added, field removed or renamed, type narrowed, behavior semantics changed, error codes changed\n"
            "3. MAP affected consumers: who currently uses the interfaces being changed? For internal code, search the codebase. For external APIs, check API usage logs. For DB schema, check all query sites. Never assume a field is unused without checking.\n"
            "4. DESIGN the migration path: for each breaking change, provide a migration path. Expand-then-contract: add the new interface alongside the old, migrate consumers, then remove the old. This keeps consumers functional throughout.\n"
            "5. DEFINE the deprecation window: how long will the old interface be maintained? Minimum: one version cycle for internal code, 6 months for external APIs, 12 months for public APIs with third-party consumers.\n"
            "6. COMMUNICATE changes: breaking changes require release notes, migration guides, and ideally tooling (codemods, migration scripts) that automates the upgrade. Changes with poor documentation cost consumers more in migration time than well-documented ones.\n"
            "Output: change_surface, classification_matrix, affected_consumers, migration_path, deprecation_window, communication_plan"
        ),
    },
    # CL-03
    {
        "slug": "accessibility-cross",
        "name": "Accessibility (Cross-Layer)",
        "family": "evaluative",
        "tier": "built-in",
        "description": "Cross-layer accessibility audit: catch accessibility regressions introduced by architecture, API design, and implementation decisions before they compound.",
        "activation_signals": [
            "accessibility impact",
            "a11y regression",
            "does this affect accessibility",
            "accessibility review",
            "cross-layer accessibility",
        ],
        "archetype_affinity": {"analyst": 0.9, "executor": 0.8},
        "mode_affinity": {"deliberative": 0.9, "reflective": 0.8},
        "composability": {"complements": ["accessibility-design", "interaction-design"], "conflicts": []},
        "system_prompt": (
            "Audit this change for cross-layer accessibility impact:\n"
            "1. ASSESS architectural impact: does this change affect how content is loaded (async loading can break screen reader reading order), how routing works (SPA navigation must manage focus), or how state updates are communicated (dynamic updates need aria-live regions)?\n"
            "2. REVIEW API design: do API responses include all information needed to render accessible interfaces? (e.g., alt text stored server-side, accessible labels available in response, error codes that can be translated to user-readable messages)\n"
            "3. CHECK data model: does the data model support accessibility metadata? (alt text fields, language fields, caption fields) Retrofitting accessibility data into a data model is expensive — design it in from the start.\n"
            "4. AUDIT implementation touchpoints: for every UI component affected by this change, verify keyboard accessibility, focus management, and screen reader compatibility are maintained.\n"
            "5. IDENTIFY regression risk: which accessibility features currently working are most at risk of regression from this change?\n"
            "Output: architectural_a11y_impact, api_a11y_gaps, data_model_a11y_support, implementation_touchpoints, regression_risks"
        ),
    },
    # CL-04
    {
        "slug": "security-cross",
        "name": "Security (Cross-Layer)",
        "family": "adversarial",
        "tier": "built-in",
        "description": "Cross-layer security threat model: trace a change across architecture, data model, API, and implementation to identify where security boundaries are crossed.",
        "activation_signals": [
            "security impact",
            "security review",
            "threat model",
            "does this affect security",
            "security boundary",
            "cross-layer security",
            "attack surface",
        ],
        "archetype_affinity": {"analyst": 0.9, "advisor": 0.8},
        "mode_affinity": {"deliberative": 0.9, "reflective": 0.8},
        "composability": {"complements": ["security-coding", "security-architecture"], "conflicts": []},
        "system_prompt": (
            "Threat model this change across all layers:\n"
            "1. IDENTIFY trust boundaries crossed: at which points does data or control flow cross a trust boundary (external user → API, API → database, service → service, user → admin)? Every trust boundary crossing is a potential security control point.\n"
            "2. APPLY STRIDE at each boundary:\n"
            "   - Spoofing: can an attacker impersonate a legitimate actor at this boundary?\n"
            "   - Tampering: can an attacker modify data in transit or at rest?\n"
            "   - Repudiation: can an actor deny having performed an action?\n"
            "   - Information Disclosure: can an attacker access data they shouldn't?\n"
            "   - Denial of Service: can an attacker degrade availability?\n"
            "   - Elevation of Privilege: can an attacker gain higher permissions than authorized?\n"
            "3. TRACE the attack surface change: does this change increase, decrease, or maintain the attack surface? New endpoints, new parameters, new data types, new integrations all expand the attack surface.\n"
            "4. ASSESS authentication and authorization changes: does this change affect who can authenticate, what they can access, or how permissions are evaluated? Auth changes are the highest-risk changes and require the most careful review.\n"
            "5. CHECK data flow security: trace sensitive data from ingestion to storage to retrieval to display. At each step: is it encrypted, is access logged, is access authorized, could it be accidentally exposed?\n"
            "Output: trust_boundary_map, stride_analysis (per boundary), attack_surface_delta, auth_change_risk, data_flow_security_trace"
        ),
    },
    # CL-05
    {
        "slug": "performance-cross",
        "name": "Performance (Cross-Layer)",
        "family": "evaluative",
        "tier": "built-in",
        "description": "Cross-layer performance impact: trace latency budget, throughput constraints, and resource consumption from architecture through to implementation.",
        "activation_signals": [
            "performance impact",
            "latency budget",
            "performance review",
            "does this affect performance",
            "cross-layer performance",
            "throughput impact",
        ],
        "archetype_affinity": {"analyst": 0.9, "executor": 0.8},
        "mode_affinity": {"deliberative": 0.9, "reflective": 0.8},
        "composability": {"complements": ["performance-coding", "capacity-planning"], "conflicts": []},
        "system_prompt": (
            "Trace performance impact across all layers:\n"
            "1. ESTABLISH the latency budget: what is the end-to-end latency target for the user-facing operation this change touches? Break down the budget by layer: network (client→server), API processing, business logic, database, external calls. Where does this change consume budget?\n"
            "2. TRACE the critical path: what is the sequence of operations that determines total latency? This change adds/modifies which operations on the critical path? Off-critical-path changes cannot improve end-to-end latency, even if they're fast.\n"
            "3. ASSESS data layer impact: does this change add or modify database queries? For each new or modified query: (a) estimated execution plan, (b) index usage, (c) data volume accessed, (d) lock contention potential. A single missing index can change O(log n) to O(n) query performance.\n"
            "4. CHECK for amplification: does this change cause a single user action to generate multiple downstream requests? (N+1, fan-out patterns) Amplification patterns create superlinear scaling characteristics — 10× users can produce 100× load.\n"
            "5. IDENTIFY resource consumption changes: how does this change affect CPU, memory, network I/O, and disk I/O per request? Changes that seem fast in development can create resource pressure at scale.\n"
            "Output: latency_budget_allocation, critical_path_impact, data_layer_assessment, amplification_risks, resource_consumption_delta"
        ),
    },
    # CL-06
    {
        "slug": "i18n-cross",
        "name": "Internationalization (Cross-Layer)",
        "family": "evaluative",
        "tier": "built-in",
        "description": "Cross-layer internationalization audit: identify i18n gaps introduced at architecture, data model, API, and implementation level before they create expensive retrofits.",
        "activation_signals": [
            "internationalization",
            "i18n",
            "localization",
            "multiple languages",
            "locale",
            "currency",
            "date formats",
            "RTL",
            "global users",
        ],
        "archetype_affinity": {"analyst": 0.9, "executor": 0.8},
        "mode_affinity": {"deliberative": 0.9, "reflective": 0.8},
        "composability": {"complements": ["i18n-architecture", "accessibility-design"], "conflicts": []},
        "system_prompt": (
            "Audit this change for internationalization readiness:\n"
            "1. AUDIT string handling: are all user-visible strings externalized to a translation system? Hardcoded strings in code, database, or API responses are i18n debt. Every string that could be shown to a non-English user must be in a translation key system.\n"
            "2. CHECK data model: does the data model support locale-specific data? (translated content fields, locale preference storage, locale-aware sorting) Retrofitting multi-language support into a data model designed for one language is expensive.\n"
            "3. REVIEW date/time handling: are dates stored in UTC and converted to user locale at display time? Storing dates in local time is a bug for any multi-timezone system. Is the timezone stored with each user? Is date formatting locale-aware (MM/DD/YYYY vs DD/MM/YYYY)?\n"
            "4. ASSESS number and currency: are numbers formatted with locale-appropriate separators (1,234.56 vs 1.234,56)? Are currencies stored as the minor unit (cents, not dollars) with explicit currency codes? Never store currency as a float — rounding errors compound.\n"
            "5. CHECK RTL support: does this change touch layout or text rendering? Right-to-left languages (Arabic, Hebrew) require mirrored layouts. CSS logical properties (margin-inline-start instead of margin-left) support RTL without media queries.\n"
            "6. IDENTIFY i18n regression risk: what currently-working i18n features are at risk from this change?\n"
            "Output: string_externalization_audit, data_model_i18n_gaps, datetime_handling_check, number_currency_audit, rtl_impact, regression_risks"
        ),
    },
]


async def seed_frameworks() -> None:
    """Seed new instrument frameworks to the framework table.

    Uses create-or-update semantics: new frameworks are created with their seed
    system_prompt; existing frameworks get metadata updated but their system_prompt
    is preserved so Wave-6 (demonstration-mode) rewrites are never overwritten.
    """
    print(f"Seeding {len(NEW_FRAMEWORKS)} new instrument frameworks...")
    created = updated = errors = 0

    async with pool.connection() as db:
        for fw in NEW_FRAMEWORKS:
            existing = await db.query(
                "SELECT id FROM framework WHERE slug = $slug AND product IS NONE LIMIT 1",
                {"slug": fw["slug"]},
            )
            record = (existing or [{}])[0] if not isinstance(existing, str) else None

            if record and record.get("id"):
                # Update metadata only — preserve any existing system_prompt.
                result = await db.query(
                    """
                    UPDATE framework SET
                        name = $name,
                        family = $family,
                        tier = $tier,
                        description = $description,
                        activation_signals = $activation_signals,
                        archetype_affinity = $archetype_affinity,
                        mode_affinity = $mode_affinity,
                        composability = $composability
                    WHERE slug = $slug AND product IS NONE
                    """,
                    fw,
                )
                if isinstance(result, str):
                    print(f"  ERROR (update) {fw['slug']}: {result[:80]}")
                    errors += 1
                else:
                    updated += 1
            else:
                result = await db.query(
                    """
                    CREATE framework SET
                        slug = $slug,
                        name = $name,
                        family = $family,
                        tier = $tier,
                        description = $description,
                        system_prompt = $system_prompt,
                        activation_signals = $activation_signals,
                        archetype_affinity = $archetype_affinity,
                        mode_affinity = $mode_affinity,
                        composability = $composability
                    """,
                    fw,
                )
                if isinstance(result, str):
                    print(f"  ERROR (create) {fw['slug']}: {result[:80]}")
                    errors += 1
                else:
                    created += 1

    print(f"✓ {created} created, {updated} updated, {errors} errors")


async def seed_meta_skills() -> None:
    """Seed meta-skill definitions to the meta_skill table."""
    print("Seeding 23 meta-skills...")
    async with pool.connection() as db:
        for slug, module_path in _RECIPE_MODULES.items():
            try:
                mod = importlib.import_module(module_path)
                skill = mod.get_meta_skill()

                phases = []
                for phase in skill.recipe.phases:
                    phases.append(
                        {
                            "cognitive_function": phase.cognitive_function,
                            "instruments": [
                                {
                                    "slug": inst.slug,
                                    "family_hint": inst.family_hint,
                                    "fallback_slug": inst.fallback_slug,
                                    "task_affinity": inst.task_affinity,
                                }
                                for inst in phase.instruments
                            ],
                            "min_depth": phase.min_depth,
                            "output_schema": phase.output_schema,
                            "pattern": phase.pattern,
                        }
                    )

                await db.query(
                    "DELETE meta_skill WHERE slug = $slug",
                    {"slug": slug},
                )
                await db.query(
                    """
                CREATE meta_skill SET
                    slug = $slug,
                    name = $name,
                    description = $description,
                    domain_intelligences = $domain_intelligences,
                    recipe = $recipe,
                    created_at = time::now()
                """,
                    {
                        "slug": skill.slug,
                        "name": skill.name,
                        "description": skill.description,
                        "domain_intelligences": skill.domain_intelligences,
                        "recipe": {"phases": phases},
                    },
                )
            except Exception as exc:
                print(f"  ⚠ Failed to seed meta-skill {slug}: {exc}")
                continue
    print("✓ 23 meta-skills seeded")


async def seed_all() -> None:
    """Seed all frameworks and meta-skills. Safe to call from a running event loop."""
    await seed_frameworks()
    await seed_meta_skills()


async def main() -> None:
    await seed_all()


if __name__ == "__main__":
    asyncio.run(main())
