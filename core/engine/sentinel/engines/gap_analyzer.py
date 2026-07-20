# engine/sentinel/engines/gap_analyzer.py
"""Gap analyzer engine — compare product map against best practices.

Runs nightly at 3 AM. For each capability with status in [built, partial, building]:
1. Select relevant disciplines (not all 18 — LLM picks the 5-8 that matter)
2. Load code evidence from graph (function/class names, not just file paths)
3. Batch-assess multiple disciplines per LLM call (3-5 per call)
4. Update quality scores on capability_quality table
5. Generate product_question records for significant gaps (score < 0.4)
"""

import asyncio
import fnmatch
import json
import logging

from core.engine.core.db import parse_rows, pool
from core.engine.core.exceptions import ValidationError
from core.engine.core.llm import llm
from core.engine.product.seed_packs import ALL_DISCIPLINES
from core.engine.sentinel.registry import register_engine
from core.engine.sentinel.triggers import meaningful_change_since_last_run

logger = logging.getLogger(__name__)


def phase_aware_gap_severity(score: float, floor: float) -> float:
    """gap_severity normalized to [0, 1] against the phase floor.

    Returns max(0, floor − score) / max(0.01, floor). Above-floor scores yield 0;
    at-floor yields 0; below-floor yields a positive value scaled by gap depth.
    """
    if floor <= 0.0:
        return 0.0
    return max(0.0, floor - score) / max(0.01, floor)


# ── Phase-aware gap emit (item H) ──────────────────────────────────────────────
# A gap surfaces only when a dimension falls below the floor appropriate to the project's CURRENT
# stage and type. This INTENTIONALLY lowers the bar for low-priority pillars at early phases (a
# prototype shouldn't be nagged about security/ops) AND raises it for stage-relevant ones — but it is
# bounded so it never approaches silence: truly-absent capabilities always surface.
_FLAT_EMIT_FLOOR = 0.4  # conservative legacy bar — used when phase/pillar is UNKNOWN
_MIN_EMIT_FLOOR = 0.2  # known floors clamp UP to this: relevance may lower the bar, never toward 0


def _emit_floor(dimension: str, phase: str, product_type: str, scale: str) -> float:
    """Stage+type+scale-aware floor for deciding whether `dimension`'s score is a gap worth emitting.

    Maps the dimension to its pillar and composes effective_floor(pillar, phase, type, scale).
    Contract (honest — not "never lower the bar"):
    - Unmapped dimension OR unknown phase (effective_floor → 0.0) → conservative legacy 0.4. We never
      lower the bar due to MISSING config.
    - A KNOWN floor is honored down to _MIN_EMIT_FLOOR (0.2): low-priority pillars at early phases get
      a lower bar (fewer stage-irrelevant gaps), but a score below 0.2 ALWAYS surfaces regardless of
      pillar/phase — a truly-absent capability is never silenced (review C1: negative type/scale
      modifiers could otherwise drive the composed floor toward 0)."""
    from core.engine.product.phase_floors import effective_floor
    from core.engine.product.pillars import LEGACY_DIM_TO_PILLAR

    pillar = LEGACY_DIM_TO_PILLAR.get(dimension)
    if pillar is None:
        return _FLAT_EMIT_FLOOR
    floor = effective_floor(pillar, phase or "", product_type or "", scale or "")
    if floor <= 0.0:  # unknown phase key — don't lower the bar on missing config
        return _FLAT_EMIT_FLOOR
    return max(floor, _MIN_EMIT_FLOOR)


async def _load_floor_context(db, product_id) -> tuple[str, str, str]:
    """(phase, product_type, scale) for phase-aware floors. Non-fatal.

    Phase defaults to "" when ambition is absent — and "" makes effective_floor return 0.0, which
    _emit_floor maps to the conservative legacy 0.4. So an unset-ambition product keeps the legacy
    flat behavior (review IMPORTANT-3: do NOT default to lenient 'poc' and under-surface a product
    that may actually be further along). scale reads `product_scale` (the real schema field — review
    C2: `scale` does not exist), defaulting to the neutral 'application' like other readers."""
    phase, ptype, scale = "", "", "application"
    try:
        amb = parse_rows(
            await db.query("SELECT phase_json FROM ambition WHERE product = <record>$p LIMIT 1", {"p": product_id})
        )
        if amb:
            pj = amb[0].get("phase_json") or {}
            cur = pj.get("current") if isinstance(pj, dict) else None
            phase = cur or ""
        prod = parse_rows(
            await db.query(
                "SELECT product_type, product_scale FROM product WHERE id = <record>$p LIMIT 1", {"p": product_id}
            )
        )
        if prod:
            ptype = prod[0].get("product_type") or ""
            scale = prod[0].get("product_scale") or "application"
    except Exception as exc:
        logger.warning("_load_floor_context failed (non-fatal, legacy flat floor): %s", exc)
    return phase, ptype, scale


async def _create_gap_question(db, slug: str, gap: str, cap_id: str) -> None:
    """Persist a downward gap as a product_question.

    MUST set `question` (a required `string` field): omitting it makes the SCHEMAFULL CREATE fail to
    persist on SurrealDB v3 (a field-coercion error / empty result depending on the path) — and the
    failure was swallowed, so gap_analyzer reported questions_generated while persisting nothing
    (item I). Keep `question = $q` in the SET or the gap pipeline goes dark."""
    await db.query(
        """CREATE product_question SET
            question = $q, category = 'downward', source = 'gap_analyzer',
            capability = <record>$cap_id, priority = 'high', status = 'open'""",
        {"q": f"{slug}: {gap}", "cap_id": cap_id},
    )


SCORING_RUBRIC = """Score 0.0-1.0 based on OBSERVABLE EVIDENCE:
0.0 = Clearly absent — no relevant functions, classes, or patterns visible
0.2 = Minimal — some relevant code exists but clearly incomplete
0.4 = Partial — reasonable functions/classes present, likely gaps in coverage
0.6 = Adequate — good function/class coverage, standard patterns visible
0.8 = Good — comprehensive coverage visible, well-structured
1.0 = Excellent — thorough coverage with advanced patterns

IMPORTANT SCORING CALIBRATION:
- You are seeing function/class NAMES, not full implementations. Score based on what you CAN observe.
- If test files exist (test_*.py), score testing at 0.4+ minimum. If many test functions exist, score 0.6+.
- If relevant functions exist (e.g., health_check, validate_input, rate_limit), score the relevant discipline at 0.4+ minimum.
- Score 0.0 ONLY when there is genuinely zero evidence of any effort in that area.
- When in doubt between two scores, choose the higher one. Under-scoring is worse than over-scoring — it creates noise that obscures real gaps."""

# Map capability tiers/tags to relevant discipline subsets
DISCIPLINE_RELEVANCE = {
    "intelligence": ["testing", "architecture", "data_modeling", "error_handling", "observability", "performance"],
    "execution": ["testing", "architecture", "error_handling", "performance", "observability", "integration"],
    "product_awareness": ["testing", "architecture", "data_modeling", "documentation", "api_design"],
    "project_management": ["testing", "business_logic", "error_handling", "documentation"],
    "portal": ["testing", "ux", "accessibility", "performance", "security", "error_handling"],
    "platform": ["testing", "security", "architecture", "devops", "configuration", "observability", "deployment"],
}

# Fallback: core disciplines that apply to everything
CORE_DISCIPLINES = ["testing", "security", "architecture", "error_handling", "documentation"]


def _glob_match(path: str, pattern: str) -> bool:
    """Match a path against a glob pattern, handling ** correctly.

    fnmatch doesn't support ** (recursive). We convert ** to a prefix match:
    'engine/api/**/*.py' -> path starts with 'engine/api/' and ends with '.py'
    'engine/api/*.py' -> fnmatch works directly
    """
    if "**" not in pattern:
        return fnmatch.fnmatch(path, pattern)

    # Split on the first **/ to get prefix and suffix parts.
    # "engine/capture/**/*.py" → prefix="engine/capture/", suffix="*.py"
    # Semantics: ** means zero-or-more path segments, so the suffix must
    # match at ANY depth below the prefix — including zero depth.
    prefix, _, suffix = pattern.partition("**/")
    if not suffix:
        # Pattern ends with ** — match everything under prefix
        return path.startswith(prefix.rstrip("/"))

    # Path must start with prefix
    if prefix and not path.startswith(prefix):
        return False

    remainder = path[len(prefix) :]  # portion after the prefix

    # Try matching suffix against every trailing sub-path of remainder
    # so both "file.py" and "subdir/file.py" match against "*.py"
    parts = remainder.split("/")
    for i in range(len(parts)):
        if fnmatch.fnmatch("/".join(parts[i:]), suffix):
            return True
    return False


async def _load_code_evidence(
    db,
    file_glob: str,
    graph_id: str = "default",
    limit: int = 40,
    label: str = "CODE EVIDENCE (functions/classes found in this capability)",
) -> str:
    """Load function/class names from graph for files matching glob pattern.

    Accepts a single glob pattern OR a comma-separated list of patterns/paths.
    Each entry is matched independently: entries containing '*' use glob matching,
    bare file paths use exact equality. This handles capability manifests that store
    multiple specific files as "a.py,b.py" alongside entries like "dir/**/*.py".

    Uses the product's associated graph_id (defaults to 'default' for the platform).
    External repos use their competitor graph_id so evidence reflects their code,
    not the platform's.

    ``label`` controls the header line so callers can distinguish code evidence
    from test evidence without confusing the LLM with nested conflicting headers.
    """
    if not file_glob:
        return ""

    patterns = [p.strip() for p in file_glob.split(",") if p.strip()]

    file_result = await db.query(
        "SELECT id, path FROM graph_file WHERE graph_id = $gid",
        {"gid": graph_id},
    )
    all_files = parse_rows(file_result)
    matching_ids = []
    for f in all_files:
        path = f.get("path", "")
        for pat in patterns:
            if ("*" in pat and _glob_match(path, pat)) or ("*" not in pat and path == pat):
                matching_ids.append(str(f["id"]))
                break

    if not matching_ids:
        return ""

    placeholders = ", ".join(f"<record>'{fid}'" for fid in matching_ids[:20])
    fn_result = await db.query(
        f"SELECT name, kind FROM graph_function WHERE file IN [{placeholders}] ORDER BY name LIMIT {limit}",
    )
    functions = parse_rows(fn_result)

    if not functions:
        return ""

    lines = [f"  {fn.get('kind', 'function')}: {fn.get('name', '?')}" for fn in functions]
    return f"{label}:\n" + "\n".join(lines)


async def _load_code_evidence_from_paths(db, file_paths: list[str], graph_id: str = "default", limit: int = 40) -> str:
    """Load function/class names from graph for specific file paths (no glob matching).

    Used when a capability has no file_glob but has reality.files populated by the
    capability mapper. Queries graph_function for the exact files the mapper assigned.
    """
    if not file_paths:
        return ""

    file_result = await db.query(
        "SELECT id FROM graph_file WHERE graph_id = $gid AND path IN $paths",
        {"gid": graph_id, "paths": list(file_paths)},
    )
    all_files = parse_rows(file_result)
    matching_ids = [str(f["id"]) for f in all_files if "id" in f]

    if not matching_ids:
        return ""

    placeholders = ", ".join(f"<record>'{fid}'" for fid in matching_ids[:20])
    fn_result = await db.query(
        f"SELECT name, kind FROM graph_function WHERE file IN [{placeholders}] ORDER BY name LIMIT {limit}",
    )
    functions = parse_rows(fn_result)

    if not functions:
        return ""

    lines = [f"  {fn.get('kind', 'function')}: {fn.get('name', '?')}" for fn in functions]
    return "CODE EVIDENCE (functions/classes found in this capability):\n" + "\n".join(
        lines
    )  # _from_paths always code evidence


def _select_disciplines(cap: dict, active_discs: list[str]) -> list[str]:
    """Pick relevant disciplines for a capability based on its tier/tags."""
    tags = cap.get("tags", [])
    intent = cap.get("intent", {})
    tier = intent.get("tier", "") if intent else ""

    # Check tier mapping first
    if tier and tier in DISCIPLINE_RELEVANCE:
        relevant = DISCIPLINE_RELEVANCE[tier]
    else:
        # Check tags for tier info
        relevant = None
        for tag in tags:
            if tag in DISCIPLINE_RELEVANCE:
                relevant = DISCIPLINE_RELEVANCE[tag]
                break

    if relevant is None:
        relevant = CORE_DISCIPLINES

    # Filter by org's active disciplines
    if active_discs:
        return [d for d in relevant if d in active_discs]
    return relevant


async def _batch_assess(
    slug: str,
    description: str,
    file_text: str,
    code_evidence: str,
    disciplines: list[str],
    practices_by_dim: dict[str, str],
    test_evidence: str = "",
) -> list[dict]:
    """Assess multiple disciplines in a single LLM call. Returns list of assessments."""
    # Build per-discipline sections — include practices when available, otherwise
    # just the dimension name so the LLM can still score from code evidence alone.
    dim_sections = []
    for dim in disciplines:
        practices = practices_by_dim.get(dim, "")
        if practices:
            dim_sections.append(f"### {dim.upper()}\n{practices}")
        else:
            dim_sections.append(f"### {dim.upper()}\n(no practice hints — score from code evidence)")

    code_block = f"\n{code_evidence}\n" if code_evidence else ""
    # Include test file evidence when assessing the testing dimension so the
    # LLM can see actual test functions rather than scoring from implementation
    # code alone (which has no test functions and produces false 0.0 scores).
    # test_evidence already has its own label ("TEST FUNCTIONS (found in test suite):...").
    # Embed it directly — do NOT add another "TEST FILES:" header or the LLM sees
    # conflicting nested labels and concludes no test files exist (false 0.0 scores).
    test_block = f"\n{test_evidence}\n" if test_evidence and "testing" in disciplines else ""
    dims_text = "\n\n".join(dim_sections)

    prompt = f"""Assess the "{slug}" capability across these quality dimensions.

CAPABILITY: {description}
FILES: {file_text}
{code_block}{test_block}
BEST PRACTICES BY DIMENSION:
{dims_text}

{SCORING_RUBRIC}

IMPORTANT:
- You see function/class NAMES, not full code. Score based on what's observable.
- If a function exists that relates to a practice (e.g., "health_check" for observability), assume it works and score 0.4+.
- Only flag gaps where there is NO relevant function or class visible at all.
- Do NOT score 0.0 unless the entire area is genuinely unaddressed.
- The code evidence shows what EXISTS. Absence of a specific pattern does not mean 0 — it means inconclusive, which should score 0.3-0.5.
- For TESTING: if TEST FUNCTIONS are provided above, use them to score test coverage. Presence of test functions = at least 0.4.

Return JSON array — one object per dimension:
[{{"dimension": "<name>", "score": <float 0.0-1.0>, "confidence": <float 0.0-1.0>, "importance": <float 0.0-1.0 how critical this dimension is for THIS specific capability>, "gaps": [<specific gaps actually missing>], "evidence": [<what you checked>]}}]

For "importance": 1.0 means this dimension is critical for this capability (e.g., security for an auth system).
0.5 means moderately relevant. 0.2 means barely applies. Judge based on what this capability actually does.

For "confidence": how certain are you given the available evidence?
  1.0 = high (20+ relevant functions seen, clear patterns)
  0.7 = moderate (5-20 relevant functions, reasonable inference)
  0.4 = low (1-4 functions, limited visibility)
  0.2 = very low (no functions visible, scoring from file names only)"""

    try:
        result = await llm.complete_json(prompt)
        # Handle both array and wrapped responses
        if isinstance(result, list):
            return result
        if isinstance(result, dict):
            for key in ("assessments", "dimensions", "results"):
                if key in result and isinstance(result[key], list):
                    return result[key]
        return []
    except (json.JSONDecodeError, Exception) as e:
        logger.warning("Batch assessment failed for %s: %s", slug, e)
        return []


def _validate_gap_analyzer_inputs(product_id: str, budget: int = 100) -> None:
    """Validate inputs before running the gap analyzer engine.

    Raises ValidationError for malformed product_id or out-of-range budget
    so the engine fails fast rather than silently scanning zero capabilities.
    """
    if not product_id or ":" not in product_id:
        raise ValidationError(f"Invalid product_id: {product_id!r}")
    if not (1 <= budget <= 500):
        raise ValidationError(f"budget must be in [1, 500], got {budget}")


@register_engine(
    name="gap_analyzer",
    cron="0 3 * * *",
    description="Compare product map against best practice specialties. Updates quality scores, generates questions.",
    trigger=lambda product_id: meaningful_change_since_last_run("gap_analyzer", product_id),
)
async def run_gap_analyzer(product_id: str, budget: int = 30) -> dict:
    _validate_gap_analyzer_inputs(product_id, budget)
    results = {
        "capabilities_scanned": 0,
        "gaps_found": 0,
        "questions_generated": 0,
        "llm_calls": 0,
    }

    # Load setup data with short-lived connections
    async with pool.connection() as db:
        cap_result = await db.query(
            "SELECT * FROM capability WHERE product = <record>$product AND status IN ['built', 'partial', 'building', 'planned']",
            {"product": product_id},
        )
        capabilities = parse_rows(cap_result)

        disc_result = await db.query(
            "SELECT discipline FROM active_discipline WHERE product = <record>$product AND active = true",
            {"product": product_id},
        )
        active_discs = [d["discipline"] for d in parse_rows(disc_result)]
        if not active_discs:
            active_discs = ALL_DISCIPLINES

        practices_cache: dict[str, str] = {}
        for dim in active_discs:
            bp_result = await db.query(
                "SELECT content, confidence FROM insight WHERE tags CONTAINS $dim AND tags CONTAINS 'best_practice' AND confidence > 0.5 ORDER BY confidence DESC LIMIT 10",
                {"dim": dim},
            )
            practices = parse_rows(bp_result)
            if practices:
                practices_cache[dim] = "\n".join(
                    f"- {p['content']} (confidence: {p.get('confidence', 0.5):.1f})" for p in practices
                )

        # Resolve the graph_id for this product so code evidence loads from the
        # right graph (platform uses 'default'; external repos use their own graph_id).
        # The graph table's `product` field is not written by the scanner, so we
        # derive graph_id from the competitor record (written by external.py) instead.
        # For the platform product itself, always fall back to "default".
        _product_str = str(product_id)
        if _product_str.startswith("competitor:"):
            _comp_slug = _product_str.split(":", 1)[1]
            _comp_rows = parse_rows(
                await db.query(
                    "SELECT graph_id FROM competitor WHERE id = <record>$cid LIMIT 1",
                    {"cid": _product_str},
                )
            )
            product_graph_id = (
                _comp_rows[0].get("graph_id", f"competitor_{_comp_slug}") if _comp_rows else f"competitor_{_comp_slug}"
            )
        else:
            product_graph_id = "default"

        # Phase/type/scale for phase-aware gap floors — a gap surfaces only below the floor
        # appropriate to the project's CURRENT stage/type (no GA-level security bar on a poc).
        floor_phase, floor_type, floor_scale = await _load_floor_context(db, product_id)

    # Process each capability with a fresh connection per cap (avoids 120s lease timeout)
    for cap in capabilities[:budget]:
        cap_id = str(cap["id"])
        slug = cap.get("slug", "unknown")
        reality = cap.get("reality", {})
        files = reality.get("files", []) if reality else []
        # capability.graph_id overrides product-level graph_id (set for external caps)
        cap_graph_id = cap.get("graph_id") or product_graph_id
        file_glob = reality.get("file_glob", cap.get("file_glob", "")) if reality else cap.get("file_glob", "")

        test_glob = reality.get("test_glob", "") if reality else ""

        # Load code evidence with its own connection.
        # Prefer file_glob (broad pattern match) when set; fall back to exact paths
        # from reality.files when glob is absent (the common case for mapper-assigned caps).
        async with pool.connection() as db:
            if file_glob:
                code_evidence = await _load_code_evidence(db, file_glob, graph_id=cap_graph_id)
            elif files:
                code_evidence = await _load_code_evidence_from_paths(db, files[:20], graph_id=cap_graph_id)
            else:
                code_evidence = ""
            # Load test file evidence separately — used when testing dimension is in the batch.
            # Test files live in tests/ and aren't part of the implementation file_glob.
            # Use a distinct label so the LLM doesn't see conflicting "CODE EVIDENCE" vs "TEST FILES" headers.
            test_evidence = (
                await _load_code_evidence(db, test_glob, label="TEST FUNCTIONS (found in test suite)")
                if test_glob
                else ""
            )
        if files:
            file_text = "\n".join(f"- {f}" for f in files[:20])
        elif file_glob:
            file_text = "\n".join(f"- {p.strip()}" for p in file_glob.split(",") if p.strip())
        else:
            file_text = "(no files mapped)"

        relevant_discs = _select_disciplines(cap, active_discs)
        # practices_cache may be empty early on (no best-practice insights yet) —
        # don't gate on it; pass empty string as context if a disc has no practices.

        if not relevant_discs:
            results["capabilities_scanned"] += 1
            continue

        # Batch assess (LLM calls — no DB needed)
        batch_size = 4
        all_assessments: list[dict] = []
        for i in range(0, len(relevant_discs), batch_size):
            batch = relevant_discs[i : i + batch_size]
            batch_practices = {d: practices_cache.get(d, "") for d in batch}

            assessments = await _batch_assess(
                slug=slug,
                description=cap.get("description", slug),
                file_text=file_text,
                code_evidence=code_evidence,
                disciplines=batch,
                practices_by_dim=batch_practices,
                test_evidence=test_evidence,
            )
            results["llm_calls"] += 1
            all_assessments.extend(assessments)

        # Write results with a fresh connection
        async with pool.connection() as db:
            for assessment in all_assessments:
                if not isinstance(assessment, dict) or "score" not in assessment:
                    continue

                dimension = assessment.get("dimension", "").lower().replace(" ", "_")
                if dimension not in active_discs:
                    continue

                score = max(0.0, min(1.0, float(assessment["score"])))
                importance = max(0.0, min(1.0, float(assessment.get("importance", 0.5))))
                confidence = max(0.0, min(1.0, float(assessment.get("confidence", 0.5))))
                evidence_count = len(assessment.get("evidence", []))

                # Deterministic RecordID so UPSERT is idempotent across runs.
                # UPSERT table WHERE … behaves like UPDATE in SurrealDB v3 (no-op
                # when zero rows match), so we must key by RecordID instead.
                qual_slug = f"{slug}__{dimension}__{product_id.replace(':', '_')}"
                from surrealdb import RecordID as _RID

                # Capture old score before UPSERT for canvas emit
                old_score_result = await db.query(
                    "SELECT score FROM $rid",
                    {"rid": _RID("capability_quality", qual_slug)},
                )
                from core.engine.core.db import parse_one as _parse_one_local

                old_row = _parse_one_local(old_score_result)
                old_score = float(old_row.get("score", 0.0)) if old_row else 0.0

                await db.query(
                    # decision:8o4c6s8xxrxkov8xzbn1 — v061 REMOVE FIELD org ON
                    # TABLE capability_quality. The prior UPSERT included
                    # `org = <record>$product` and raised "Found field 'org',
                    # but no such field exists" on every nightly gap_analyzer
                    # run, silently swallowed by the cron error handler.
                    """UPSERT $rid SET
                        capability    = <record>$cap_id,
                        product       = <record>$product,
                        dimension     = $dim,
                        score         = $score,
                        importance    = $importance,
                        confidence    = $confidence,
                        evidence_count = $evidence_count,
                        gaps          = $gaps,
                        evidence      = $evidence,
                        assessed_by   = 'gap_analyzer',
                        assessed_at   = time::now()
                    """,
                    {
                        "rid": _RID("capability_quality", qual_slug),
                        "cap_id": cap_id,
                        "product": product_id,
                        "dim": dimension,
                        "score": score,
                        "importance": importance,
                        "confidence": confidence,
                        "evidence_count": evidence_count,
                        "gaps": assessment.get("gaps", []),
                        "evidence": assessment.get("evidence", []),
                    },
                )

                # D2: Append-only snapshot for trend tracking (does NOT replace UPSERT)
                await db.query(
                    """CREATE capability_quality_snapshot SET
                        capability  = <record>$cap_id,
                        product     = <record>$product,
                        dimension   = $dim,
                        score       = $score,
                        confidence  = $confidence,
                        gaps_count  = $gaps_count,
                        assessed_at = time::now()
                    """,
                    {
                        "cap_id": cap_id,
                        "product": product_id,
                        "dim": dimension,
                        "score": score,
                        "confidence": confidence,
                        "gaps_count": len(assessment.get("gaps", [])),
                    },
                )

                try:
                    from core.engine.events.bus import bus
                    from core.engine.events.canvas import emit_score_changed

                    await bus.emit(
                        "quality.score_changed",
                        {
                            "product_id": product_id,
                            "capability_id": cap_id,
                            "capability_slug": slug,
                            "dimension": dimension,
                            "new_score": score,
                            "gaps": assessment.get("gaps", []),
                        },
                    )
                    await emit_score_changed(
                        product_id=product_id,
                        capability_slug=slug,
                        dimension=dimension,
                        old_score=old_score,
                        new_score=score,
                        sentinel_name="gap_analyzer",
                    )
                except Exception:
                    pass

                gaps = assessment.get("gaps", [])
                results["gaps_found"] += len(gaps)

                if score < _emit_floor(dimension, floor_phase, floor_type, floor_scale) and gaps:
                    for gap in gaps[:2]:
                        await _create_gap_question(db, slug, gap, cap_id)
                        results["questions_generated"] += 1

        results["capabilities_scanned"] += 1
        logger.info("Assessed %s (%d/%d)", slug, results["capabilities_scanned"], min(budget, len(capabilities)))
        await asyncio.sleep(1)  # pace between caps to avoid CLIProvider rate limiting

    return results


# ── D2: Trend tracking ────────────────────────────────────────────────────────


def _confidence_label(confidence: float) -> str:
    if confidence >= 0.75:
        return "high"
    if confidence >= 0.5:
        return "moderate"
    if confidence >= 0.3:
        return "low — limited code visibility"
    return "very low — manual review recommended"


async def get_score_trend(
    product_id: str,
    dimension: str,
    capability_slug: str | None = None,
    days: int = 90,
    db=None,
) -> dict:
    """Return score trend data for a dimension over the last N days.

    Queries capability_quality_snapshot for historical data.
    Returns "insufficient_data" when fewer than 2 snapshots exist.

    Returns:
    {
      "dimension": "security",
      "trend": "improving" | "declining" | "stable" | "insufficient_data",
      "delta": +0.12,
      "snapshots": [{"date": "2026-01-15", "avg_score": 0.18}, ...]
    }
    """
    import datetime

    cutoff = (datetime.datetime.now(datetime.UTC) - datetime.timedelta(days=days)).isoformat()

    cap_filter = ""
    params: dict = {"product": product_id, "dim": dimension, "cutoff": cutoff}

    if capability_slug:
        # decision:8vj092dt6wklp60xqfat — `WHERE field = (SELECT VALUE ... LIMIT 1)`
        # silently returns empty in SurrealDB v3 because the subquery yields a
        # 1-element array, not a scalar. This bug was latent here for an unknown
        # duration: the capability_slug filter has been returning zero rows every
        # time it's set. Discovered while running scripts/smoke_reconciler_queries.py.
        cap_filter = " AND capability IN (SELECT VALUE id FROM capability WHERE slug = <string>$slug AND product = <record>$product)"
        params["slug"] = capability_slug

    close_db = False
    if db is None:
        from core.engine.core.db import pool

        _ctx = pool.connection()
        db = await _ctx.__aenter__()
        close_db = True

    try:
        rows = parse_rows(
            await db.query(
                f"""SELECT score, assessed_at FROM capability_quality_snapshot
                    WHERE product = <record>$product
                    AND dimension = <string>$dim
                    AND assessed_at > <datetime>$cutoff
                    {cap_filter}
                    ORDER BY assessed_at ASC""",
                params,
            )
        )
    finally:
        if close_db:
            await _ctx.__aexit__(None, None, None)

    if len(rows) < 2:
        return {
            "dimension": dimension,
            "trend": "insufficient_data",
            "delta": 0.0,
            "snapshots": [],
        }

    # Group by date (day granularity) and average
    daily: dict[str, list[float]] = {}
    for r in rows:
        at = str(r.get("assessed_at", ""))[:10]
        daily.setdefault(at, []).append(float(r.get("score", 0.0)))

    snapshots = [{"date": d, "avg_score": round(sum(v) / len(v), 4)} for d, v in sorted(daily.items())]

    if len(snapshots) < 2:
        return {
            "dimension": dimension,
            "trend": "insufficient_data",
            "delta": 0.0,
            "snapshots": snapshots,
        }

    first_score = snapshots[0]["avg_score"]
    last_score = snapshots[-1]["avg_score"]
    delta = round(last_score - first_score, 4)

    if delta > 0.05:
        trend = "improving"
    elif delta < -0.05:
        trend = "declining"
    else:
        trend = "stable"

    return {
        "dimension": dimension,
        "trend": trend,
        "delta": delta,
        "snapshots": snapshots,
    }


# ── D3: PR impact prediction ──────────────────────────────────────────────────


async def _assess_diff_impact(
    diff_summary: dict,
    capability: dict,
    current_scores: dict,
    disciplines: list[str],
) -> list[dict]:
    """LLM call: predict score changes from a code diff.

    Args:
        diff_summary:   {added_functions, removed_functions, modified_files}
        capability:     {name, slug}
        current_scores: {dimension: score} current scores for this capability
        disciplines:    Dimensions to assess

    Returns: list of {dimension, predicted_delta, reason}
    """
    import json as _json

    prompt = f"""Predict how this code change will affect quality scores.

CAPABILITY: {capability.get("name", capability.get("slug", "?"))} ({capability.get("slug", "?")})
CURRENT SCORES: {_json.dumps(current_scores)}

DIFF SUMMARY:
  Functions removed: {diff_summary.get("removed_functions", [])}
  Functions added:   {diff_summary.get("added_functions", [])}
  Files modified:    {diff_summary.get("modified_files", [])}

For each dimension listed below, predict whether the score will improve, decline, or stay stable.
Focus on:
- Removed functions that were providing coverage (score decline)
- Added test/validation functions (score improve)
- Removed input validation or security guards (security decline)
- Added error handling (error_handling improve)

Dimensions to assess: {disciplines}

Return JSON array:
[{{"dimension": "<name>", "predicted_delta": <float -1.0 to 1.0>, "reason": "<one sentence>"}}]

Only include dimensions where the delta is non-zero. Return [] if no impact detected."""

    try:
        result = await llm.complete_json(prompt)
        if isinstance(result, list):
            return result
        if isinstance(result, dict):
            for key in ("predictions", "assessments", "results"):
                if key in result and isinstance(result[key], list):
                    return result[key]
        return []
    except Exception as e:
        logger.warning("_assess_diff_impact failed: %s", e)
        return []


def _parse_diff_summary(diff: str) -> dict:
    """Extract added/removed functions and modified files from a git diff string.

    Returns: {added_functions, removed_functions, modified_files}
    """
    import re

    added_functions: list[str] = []
    removed_functions: list[str] = []
    modified_files: list[str] = []

    func_pattern = re.compile(r"^[+-]\s*(?:async\s+)?def\s+(\w+)\s*\(", re.MULTILINE)

    for line in diff.splitlines():
        if line.startswith("--- ") or line.startswith("+++ "):
            match = re.search(r"[ab]/(.+)$", line)
            if match:
                f = match.group(1)
                if f != "/dev/null" and f not in modified_files:
                    modified_files.append(f)
        elif line.startswith("+") and not line.startswith("+++"):
            m = func_pattern.match(line)
            if m:
                added_functions.append(m.group(1))
        elif line.startswith("-") and not line.startswith("---"):
            m = func_pattern.match(line)
            if m:
                removed_functions.append(m.group(1))

    return {
        "added_functions": list(set(added_functions)),
        "removed_functions": list(set(removed_functions)),
        "modified_files": modified_files[:20],
    }
