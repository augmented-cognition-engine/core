"""Spec Generator — produce agent-executable specs from gaps, ideas, or human requests.

The PM identifies work to do. The spec generator turns that into a document
an agent-engineer can execute without ambiguity.
"""

import logging
import re
import uuid
from collections import Counter
from pathlib import Path

from core.engine.core.db import parse_one, parse_record_id, parse_rows
from core.engine.core.exceptions import ValidationError
from core.engine.core.llm import get_llm
from core.engine.core.model_costs import alternative_model_for, cost_for_call
from core.engine.orchestration.composition_scorer import (
    graph_tension_lenses,
    inject_tension_lenses,
    resolve_committee_lenses,
    score_lens_composition,
)
from core.engine.orchestration.deep_committee import (
    CommitteeResult,
    resolve_lenses,
    run_deep_committee,
)
from core.engine.orchestrator.budgets import estimate_call_budget
from core.engine.orchestrator.classifier import classify_task
from core.engine.product.decisions import create_decision
from core.engine.product.map import ProductMap

logger = logging.getLogger(__name__)


class SpecGenerator:
    """Generate agent-executable specs from gaps, ideas, or human requests."""

    def __init__(self, db_pool):
        self._pool = db_pool
        self._product_map = ProductMap(db_pool)
        self._llm = get_llm()

    def _validate_spec_inputs(
        self,
        product_id: str,
        capability_slug: str | None = None,
        request: str | None = None,
    ) -> None:
        """Validate inputs before spec generation to fail fast with clear errors.

        Raises ValidationError if product_id is malformed, capability_slug is
        empty when required, or a free-text request is blank.
        """
        if not product_id or ":" not in product_id:
            raise ValidationError(f"Invalid product_id: {product_id!r}")
        if capability_slug is not None and not capability_slug.strip():
            raise ValidationError("capability_slug must be non-empty")
        if request is not None and not request.strip():
            raise ValidationError("request must be non-empty text")

    async def _load_tech_context(self, product_id: str) -> dict:
        """Load tech stack context from the code graph to ground spec generation.

        Queries graph_file (populated by ace_scan_repo) for language distribution,
        file paths, and key directories. Without this, the LLM defaults to its
        training-data priors (typically TypeScript) instead of the actual stack.

        Returns empty dict gracefully if graph has not been scanned yet.
        """
        try:
            async with self._pool.connection() as db:
                result = await db.query(
                    "SELECT path, language FROM graph_file WHERE graph_id = 'default' LIMIT 150",
                )
            files = parse_rows(result)

            if not files:
                return {}

            paths = [f["path"] for f in files if f.get("path")]
            languages = [f["language"] for f in files if f.get("language")]

            lang_counts = Counter(languages)
            ext_counts = Counter(Path(p).suffix for p in paths if Path(p).suffix)
            primary_lang = lang_counts.most_common(1)[0][0] if lang_counts else "unknown"

            # Top-level directories (e.g. "engine", "portal", "tests")
            top_dirs = sorted({p.split("/")[0] for p in paths if "/" in p})

            file_convention = "snake_case .py files" if primary_lang == "Python" else "camelCase .ts files"

            return {
                "primary_language": primary_lang,
                "language_distribution": dict(lang_counts.most_common(5)),
                "file_extensions": dict(ext_counts.most_common(5)),
                "key_directories": top_dirs[:10],
                "sample_files": paths[:20],
                "file_convention": file_convention,
            }
        except Exception:
            logger.warning("Failed to load tech context for spec generation", exc_info=True)
            return {}

    async def _find_related_files(self, request: str, product_id: str) -> list[str]:
        """Find existing files related to the request topic.

        Scores capabilities by keyword overlap with the request text, then loads
        the realized files for the top matches. Included in prompts as "EXISTING
        RELATED FILES — extend these, do not recreate them."

        This prevents the LLM from proposing new files that already exist under
        different (correct) names, and prevents duplicate implementations.
        """
        try:
            # Extract meaningful keywords (skip short words)
            words = {w.lower().strip(".,()") for w in request.split() if len(w) > 4}
            if not words:
                return []

            async with self._pool.connection() as db:
                caps_result = await db.query(
                    "SELECT id, slug, name, description FROM capability WHERE product = <record>$product LIMIT 200",
                    {"product": product_id},
                )
            caps = parse_rows(caps_result)

            # Score capabilities by keyword overlap with name + slug + description
            scored: list[tuple[int, dict]] = []
            for cap in caps:
                cap_text = " ".join(
                    [
                        cap.get("slug", ""),
                        cap.get("name", ""),
                        cap.get("description", ""),
                    ]
                ).lower()
                score = sum(1 for w in words if w in cap_text)
                if score > 0:
                    scored.append((score, cap))

            if not scored:
                return []

            scored.sort(key=lambda x: x[0], reverse=True)
            top_caps = [c for _, c in scored[:3]]

            # Load realized files for top matching capabilities
            file_paths: list[str] = []
            for cap in top_caps:
                cap_detail = await self._product_map.get_capability(cap["slug"], product_id)
                if cap_detail:
                    for f in cap_detail.get("realized_files", []):
                        fp = f.get("file_path")
                        if fp:
                            file_paths.append(fp)

            # Deduplicate while preserving order
            seen: set[str] = set()
            unique: list[str] = []
            for fp in file_paths:
                if fp not in seen:
                    seen.add(fp)
                    unique.append(fp)

            return unique[:30]
        except Exception:
            logger.warning("Failed to find related files for spec generation", exc_info=True)
            return []

    # ------------------------------------------------------------------
    # Team-authored build path (T3)
    # ------------------------------------------------------------------

    async def from_request_with_team(
        self,
        request: str,
        product_id: str,
        event_callback=None,
    ) -> dict:
        """Team-authored build path: research → deep committee → risk → synthesize.

        Each build run gets a unique `build_run_id` carried on every event_callback
        payload. The BATS call-budget (estimate_call_budget(classification)) caps total
        agent.phase.end events: when exceeded, the risk pass is skipped (synthesis
        still runs). Designed to prevent runaway builds while preserving spec output.
        """
        self._validate_spec_inputs(product_id, request=request)

        build_run_id = uuid.uuid4().hex
        ctx = await self._gather_build_context(request, product_id)  # stage 1
        classification = await classify_task(request, product_id)
        call_budget = estimate_call_budget(classification)

        # Mutable state shared with _augmented_callback for budget tracking.
        budget_state: dict = {"phase_count": 0, "exceeded": False}

        async def _augmented_callback(event_type: str, payload: dict) -> None:
            if event_callback is not None:
                enriched = {"build_run_id": build_run_id, **payload}
                await event_callback(event_type, enriched)
            # Count phase.end events; set the flag when we hit the budget.
            if event_type == "agent.phase.end":
                budget_state["phase_count"] += 1
                if budget_state["phase_count"] >= call_budget and not budget_state["exceeded"]:
                    budget_state["exceeded"] = True
                    logger.warning(
                        "from_request_with_team: call budget exceeded (%d/%d) — risk pass will be skipped",
                        budget_state["phase_count"],
                        call_budget,
                    )

        # Phase B: scorer-driven lens adjustment.
        # resolve_committee_lenses consumes the learned composition signal — a proven
        # winning tentacle-combination (preferred_lens_set) outranks per-lens weighting;
        # otherwise down-weighted lenses are dropped and effective ones injected. Fail-open.
        scored = await score_lens_composition(classification, product_id)
        base_lenses = resolve_lenses(classification)
        lenses = resolve_committee_lenses(base_lenses, scored, classification)
        if scored.adjustments:
            logger.info("Phase B scorer adjustments: %s", "; ".join(scored.adjustments))

        # Graph-informed committee selection (membership-side of Graph Tensions): convene the lenses on
        # the other side of any LIVE tension/consequence edge with this discipline, so the committee
        # deliberates the contradiction. Fail-open ([] on cold graph / error → committee unchanged).
        tension_lenses = await graph_tension_lenses(classification, product_id)
        if tension_lenses:
            from core.engine.orchestration.deep_committee import MAX_LENSES

            lenses = inject_tension_lenses(
                lenses, tension_lenses, classification.get("discipline"), max_lenses=MAX_LENSES
            )
            logger.info("Graph-informed committee: tension lenses convened: %s", tension_lenses)

        # Emit team_resolved so the canvas can spawn placeholder lens shapes upfront,
        # before per-lens phase events start streaming.
        await _augmented_callback("build.team_resolved", {"lenses": list(lenses)})

        committee = await run_deep_committee(  # stage 2
            request,
            lenses,
            product_id,
            base_classification=classification,
            event_callback=_augmented_callback,
        )

        # Stage 3 — skipped when call budget exceeded.
        if budget_state["exceeded"]:
            risk = {"risk": "(skipped: call budget exceeded)", "blast_radius": {}}
        else:
            risk = await self._assess_risk(request, product_id, committee)

        prompt = self._build_team_spec_prompt(request, ctx, committee, risk)  # stage 4
        spec_data = await self._llm.complete_json(prompt)
        if not isinstance(spec_data, dict):
            return {"error": "LLM returned invalid spec format"}

        spec_data.update(
            {
                "authored_by": "build_team",
                "team_roster": lenses,
                "team_lineage": committee.lens_outputs,
                "risk": risk.get("risk"),
                "build_run_id": build_run_id,
                "call_budget_estimated": call_budget,
                "call_count_used": budget_state["phase_count"],
            }
        )
        spec = await self._persist_spec(spec_data, "human", None, product_id)
        await self._capture_spec_decision(spec_data, "human", product_id)
        await self._emit_team_signals(
            product_id=product_id,
            build_run_id=build_run_id,
            classification=classification,
            lenses=lenses,
            committee=committee,
            budget_state={
                "call_budget": call_budget,
                "phase_count": budget_state["phase_count"],
            },
            spec_id=spec.get("id"),
        )
        return spec

    async def _gather_build_context(self, request: str, product_id: str) -> dict:
        """Stage 1: research — pull health, vision, tech context, related files, prior decisions.

        Each loader is best-effort and wrapped individually so a single failure
        cannot crash the build — research must never be a hard gate.
        """
        health: dict = {}
        try:
            health = await self._product_map.health_summary(product_id) or {}
        except Exception:
            logger.warning("_gather_build_context: health_summary failed", exc_info=True)

        vision = None
        try:
            vision = await self._product_map.get_vision(product_id)
        except Exception:
            logger.warning("_gather_build_context: get_vision failed", exc_info=True)

        tech_context: dict = {}
        try:
            tech_context = await self._load_tech_context(product_id) or {}
        except Exception:
            logger.warning("_gather_build_context: _load_tech_context failed", exc_info=True)

        related_files: list = []
        try:
            related_files = await self._find_related_files(request, product_id) or []
        except Exception:
            logger.warning("_gather_build_context: _find_related_files failed", exc_info=True)

        prior_decisions: list = []
        try:
            from core.engine.product.decisions import list_decisions

            prior_decisions = await list_decisions(product_id, limit=10, pool=self._pool) or []
        except Exception:
            logger.warning("_gather_build_context: list_decisions failed", exc_info=True)

        return {
            "health": health,
            "vision": vision,
            "tech_context": tech_context,
            "related_files": related_files,
            "prior_decisions": prior_decisions,
        }

    async def _assess_risk(self, request: str, product_id: str, committee: CommitteeResult) -> dict:
        """Stage 3: risk — a single budget-model call assessing what the team's
        plan could break, paired with a deterministic blast-radius lookup.

        Risk is a check, not a build — so this is intentionally ONE LLM call
        (budget model, pure compute), not a multi-phase recipe. The committee
        has already done the deep reasoning; risk just stress-tests the plan.

        Never raises — risk is a stage, not a gate.
        """
        from core.engine.core.config import settings

        risk_text = ""
        try:
            prompt = (
                "Identify the top concrete risks if we ship this plan. "
                "Be specific: what breaks, who's affected, what to watch. "
                "Output 3-6 bullets, no preamble.\n\n"
                f"REQUEST: {request}\n\n"
                f"TEAM PLAN:\n{committee.synthesis or '(no team output)'}"
            )
            risk_text = await self._llm.complete(
                prompt,
                model=settings.llm_budget_model,
                system="You are a risk-assessment partner. Pure analysis — no tools, no follow-up questions.",
            )
        except Exception:
            logger.warning("_assess_risk: risk LLM call failed", exc_info=True)

        blast: dict = {}
        try:
            m = re.search(r"[\w/.-]+\.\w+", request)
            if m:
                from core.engine.mcp.tools import ace_blast_radius

                blast = await ace_blast_radius(m.group(0), product_id) or {}
        except Exception:
            logger.warning("_assess_risk: ace_blast_radius failed", exc_info=True)

        return {"risk": risk_text, "blast_radius": blast}

    def _build_team_spec_prompt(
        self,
        request: str,
        ctx: dict,
        committee: CommitteeResult,
        risk: dict,
    ) -> str:
        """Stage 4 prompt: mirrors _build_request_prompt schema, adds team voices and risk."""
        health = ctx.get("health") or {}
        vision = ctx.get("vision")
        tech_context = ctx.get("tech_context") or {}
        related_files = ctx.get("related_files") or []
        prior_decisions = ctx.get("prior_decisions") or []

        vision_text = (
            f"Vision: {vision.get('name', '')} — {vision.get('description', '')}" if vision else "No vision set"
        )
        tech_section = self._build_tech_section(tech_context)
        existing_section = self._build_existing_files_section(related_files)

        # Prior decisions — up to 5
        decisions_lines = [f"- {d.get('title', '')}: {d.get('rationale', '')}" for d in prior_decisions[:5]]
        decisions_section = "\nPRIOR DECISIONS:\n" + "\n".join(decisions_lines) if decisions_lines else ""

        # Team deliberation — synthesis + per-lens conclusions
        lens_lines = "\n\n".join(f"### {lens}\n{conclusion}" for lens, conclusion in committee.lens_outputs.items())
        team_section = f"\nTEAM DELIBERATION:\nSynthesis: {committee.synthesis}\n\nPer-lens conclusions:\n{lens_lines}"

        # Risk section
        risk_text = risk.get("risk", "") or ""
        blast = risk.get("blast_radius") or {}
        blast_summary = f"Blast radius: {blast}" if blast else ""
        risk_section = f"\nRISK:\n{risk_text}\n{blast_summary}".rstrip() if (risk_text or blast_summary) else ""

        return f"""Generate an agent-executable spec for this request.

REQUEST: {request}
{vision_text}
PRODUCT HEALTH: {health}
{tech_section}
{existing_section}
{decisions_section}
{team_section}
{risk_section}

Generate a JSON spec with: objective, acceptance_criteria (array of {{criterion, verification, automated}}), constraints, integration_points, estimated_files, test_requirements, best_practices.

GROUNDING RULES — strict:
- This spec is for an agent-engineer to execute autonomously on this codebase. Output CONCRETE code-and-file actions only.
- Do NOT include conversational prose, tool-authentication flows, "/mcp" instructions, or asks for the user to take an action.
- Every acceptance_criterion must be verifiable against the code/files in this repo alone. No "user authenticates X" or "operator runs slash command Y" criteria.
- If the team's deliberation drifted into external-tool or chat-style framing (e.g., Google Drive OAuth for a local file edit), ignore that framing and ground the spec in the request's literal files and changes.
- All file paths must use the project's actual language and conventions shown above.

Be specific and actionable. Synthesize the team's deliberation and risk findings into the spec."""

    async def from_gap(self, gap: dict, capability_slug: str, product_id: str) -> dict:
        """Generate a spec from a quality gap.

        gap: {dimension, score, gaps: [specific gaps], evidence: [what was checked]}
        """
        self._validate_spec_inputs(product_id, capability_slug=capability_slug)

        # Load capability context
        capability = await self._product_map.get_capability(capability_slug, product_id)
        if not capability:
            return {"error": f"Capability '{capability_slug}' not found"}

        # Load best practice insights for this dimension
        practices = await self._load_practices(gap.get("dimension", ""), product_id)

        # Load realized files from capability
        files = capability.get("realized_files", []) or capability.get("files", [])
        file_paths = [f.get("file_path", "") for f in files if f.get("file_path")]

        # Load tech stack context to ground file path generation
        tech_context = await self._load_tech_context(product_id)

        # Build LLM prompt
        prompt = self._build_gap_prompt(gap, capability, practices, file_paths, tech_context)

        # Generate spec via LLM
        spec_data = await self._llm.complete_json(prompt)
        if not isinstance(spec_data, dict):
            return {"error": "LLM returned invalid spec format"}

        # Write to database
        spec = await self._persist_spec(spec_data, "gap", capability_slug, product_id)

        # Record spec creation as a decision (best-effort)
        await self._capture_spec_decision(spec_data, "gap", product_id)

        # Create addresses edge (WORK -> PRODUCT: this spec addresses this gap)
        if spec.get("id") and capability_slug:
            try:
                async with self._pool.connection() as db:
                    cq = parse_one(
                        await db.query(
                            """SELECT id FROM capability_quality
                        WHERE capability = (SELECT id FROM capability WHERE product = <record>$product AND slug = <string>$slug LIMIT 1)[0].id
                          AND dimension = <string>$dim
                        LIMIT 1""",
                            {"product": product_id, "slug": capability_slug, "dim": gap.get("dimension", "")},
                        )
                    )
                    if cq:
                        await db.query(
                            "RELATE $spec -> addresses -> $cq SET created_at = time::now()",
                            {"spec": parse_record_id(spec["id"]), "cq": parse_record_id(cq["id"])},
                        )
            except Exception:
                pass

        return spec

    async def from_idea(self, idea: dict, product_id: str) -> dict:
        """Generate a spec from a qualified idea."""
        capability_slug = idea.get("capability_slug")
        context = {}

        if capability_slug:
            capability = await self._product_map.get_capability(capability_slug, product_id)
            if capability:
                context["capability"] = capability

        # Load tech stack context and related files to ground generation
        tech_context = await self._load_tech_context(product_id)
        related_files = await self._find_related_files(idea.get("title", idea.get("raw_input", "")), product_id)

        prompt = self._build_idea_prompt(idea, context, tech_context, related_files)
        spec_data = await self._llm.complete_json(prompt)
        if not isinstance(spec_data, dict):
            return {"error": "LLM returned invalid spec format"}

        spec = await self._persist_spec(spec_data, "idea", capability_slug, product_id)

        # Record spec creation as a decision (best-effort)
        await self._capture_spec_decision(spec_data, "idea", product_id)

        # Create specified_by edge: spec -> idea (best-effort)
        if spec.get("id") and idea.get("id"):
            try:
                from core.engine.graph.edge_writer import create_edge

                await create_edge("specified_by", str(spec["id"]), str(idea["id"]), pool=self._pool)
            except Exception:
                pass

        return spec

    async def from_request(self, request: str, product_id: str, source: str = "human") -> dict:
        """Generate a spec from a natural-language request. `source` tags provenance (e.g.
        'discover' for an explored vision candidate vs the default 'human' for a direct request)
        so speculative candidates are filterable from deliberate specs."""
        self._validate_spec_inputs(product_id, request=request)

        # Load product context for the LLM
        health = await self._product_map.health_summary(product_id)
        vision = await self._product_map.get_vision(product_id)

        # Ground the LLM in the actual codebase before generation.
        # Without this, the LLM defaults to TypeScript for Python projects and
        # proposes files that already exist under different names.
        tech_context = await self._load_tech_context(product_id)
        related_files = await self._find_related_files(request, product_id)

        prompt = self._build_request_prompt(request, health, vision, tech_context, related_files)
        spec_data = await self._llm.complete_json(prompt)
        if not isinstance(spec_data, dict):
            return {"error": "LLM returned invalid spec format"}

        spec = await self._persist_spec(spec_data, source, None, product_id)

        # Record spec creation as a decision (best-effort)
        await self._capture_spec_decision(spec_data, source, product_id)

        return spec

    async def _load_practices(self, dimension: str, product_id: str) -> list[dict]:
        """Load best practice insights for a dimension."""
        async with self._pool.connection() as db:
            result = await db.query(
                "SELECT content, confidence FROM insight WHERE tags CONTAINS $dim AND tags CONTAINS 'best_practice' AND confidence > 0.5 ORDER BY confidence DESC LIMIT 10",
                {"dim": dimension},
            )
            return parse_rows(result)

    def _build_tech_section(self, tech_context: dict) -> str:
        """Render the TECH STACK section for inclusion in any prompt.

        Centralised so all three prompt builders emit identical grounding text.
        An empty tech_context produces an empty string — no visible impact when
        the graph hasn't been scanned yet.
        """
        if not tech_context:
            return ""
        primary = tech_context.get("primary_language", "unknown")
        dirs = ", ".join(tech_context.get("key_directories", [])[:8])
        convention = tech_context.get("file_convention", "")
        return (
            f"\nTECH STACK (use these conventions in all generated file paths):\n"
            f"  Primary language: {primary}\n"
            f"  Key directories: {dirs}\n"
            f"  File convention: {convention}"
        )

    def _build_existing_files_section(self, related_files: list[str]) -> str:
        """Render the EXISTING RELATED FILES section for inclusion in any prompt.

        Files listed here already exist — the spec should extend them, not
        recreate them under new names. Empty list produces an empty string.
        """
        if not related_files:
            return ""
        lines = "\n".join(f"  - {f}" for f in related_files)
        return f"\nEXISTING RELATED FILES (extend these — do not recreate):\n{lines}"

    def _build_gap_prompt(
        self,
        gap: dict,
        capability: dict,
        practices: list,
        files: list,
        tech_context: dict,
    ) -> str:
        dimension = gap.get("dimension", "unknown")
        gaps_list = gap.get("gaps", [])
        gaps_text = "\n".join(f"- {g}" for g in gaps_list)
        files_text = "\n".join(f"- {f}" for f in files[:20]) if files else "(no files mapped — check ace_scan_repo)"
        practices_text = "\n".join(f"- {p['content']}" for p in practices) if practices else "(no practices loaded)"
        tech_section = self._build_tech_section(tech_context)

        return f"""Generate an agent-executable spec to close this quality gap.

CAPABILITY: {capability.get("name", "")} ({capability.get("slug", "")})
DESCRIPTION: {capability.get("description", "")}
DIMENSION: {dimension}
CURRENT SCORE: {gap.get("score", 0)}
SPECIFIC GAPS:
{gaps_text}

FILES IN THIS CAPABILITY:
{files_text}
{tech_section}

BEST PRACTICES FOR {dimension.upper()}:
{practices_text}

Generate a JSON spec with:
- objective: one clear sentence of what to build/fix
- acceptance_criteria: array of {{"criterion": "...", "verification": "...", "automated": true/false}}
- constraints: array of things NOT to do or to preserve
- integration_points: array of {{"component": "...", "integration": "..."}} for files to modify
- estimated_files: array of file paths using the project's actual language and conventions above
- test_requirements: array of tests to write
- best_practices: array of relevant practices to follow

Be specific and actionable. An agent should be able to execute this without asking questions.
All file paths must use the project's actual language ({tech_context.get("primary_language", "see above")})."""

    def _build_idea_prompt(
        self,
        idea: dict,
        context: dict,
        tech_context: dict,
        related_files: list[str],
    ) -> str:
        tech_section = self._build_tech_section(tech_context)
        existing_section = self._build_existing_files_section(related_files)

        return f"""Generate an agent-executable spec for this idea.

IDEA: {idea.get("title", idea.get("raw_input", ""))}
DESCRIPTION: {idea.get("description", "")}
CONTEXT: {context}
{tech_section}
{existing_section}

Generate a JSON spec with: objective, acceptance_criteria (array of {{criterion, verification, automated}}), constraints, integration_points, estimated_files, test_requirements, best_practices.

All file paths must use the project's actual language and conventions shown above.
Be specific and actionable."""

    def _build_request_prompt(
        self,
        request: str,
        health: dict,
        vision: dict | None,
        tech_context: dict,
        related_files: list[str],
    ) -> str:
        vision_text = (
            f"Vision: {vision.get('name', '')} — {vision.get('description', '')}" if vision else "No vision set"
        )
        tech_section = self._build_tech_section(tech_context)
        existing_section = self._build_existing_files_section(related_files)

        return f"""Generate an agent-executable spec for this request.

REQUEST: {request}
{vision_text}
PRODUCT HEALTH: {health}
{tech_section}
{existing_section}

Generate a JSON spec with: objective, acceptance_criteria (array of {{criterion, verification, automated}}), constraints, integration_points, estimated_files, test_requirements, best_practices.

All file paths must use the project's actual language and conventions shown above.
Be specific and actionable. Consider the product's current health and vision."""

    async def _capture_spec_decision(self, spec_data: dict, source_type: str, product_id: str) -> None:
        """Record spec creation as a decision. Best-effort, never fails spec generation."""
        try:
            objective = spec_data.get("objective", "Unknown spec")
            constraints = spec_data.get("constraints", [])
            integration = spec_data.get("integration_points", [])
            rationale_parts = []
            if constraints:
                rationale_parts.append(f"Constraints: {'; '.join(str(c) for c in constraints[:3])}")
            if integration:
                rationale_parts.append(f"Integration: {'; '.join(str(i) for i in integration[:3])}")
            rationale = " | ".join(rationale_parts) if rationale_parts else f"Spec generated from {source_type}"

            await create_decision(
                title=f"Spec: {objective[:80]}",
                decision_type="architecture",
                rationale=rationale,
                product_id=product_id,
                source="spec_generator",
                pool=self._pool,
            )
        except Exception:
            logger.warning("Failed to capture spec decision", exc_info=True)

    async def _emit_team_signals(
        self,
        product_id: str,
        build_run_id: str,
        classification: dict,
        lenses: list[str],
        committee,  # CommitteeResult (avoid import cycle)
        budget_state: dict,
        spec_id: str | None,
    ) -> None:
        """Write one composition_signal row per lens after a team build.

        Best-effort. Logs any failure; does NOT raise — signal-write errors
        must never crash the build path."""
        try:
            from core.engine.core.config import settings

            mode_conf = classification.get("mode_confidence")
            routing_uncertain = bool(mode_conf is not None and float(mode_conf) < 0.5)
            specialties = classification.get("specialties", []) or []
            archetype = classification.get("archetype", "")
            mode = classification.get("mode", "")
            complexity = classification.get("complexity", "moderate")
            engagement = classification.get("engagement", {}) or {}
            perspectives = engagement.get("perspectives", []) or []
            perspective_weights = classification.get("perspective_weights") or {p: 1.0 for p in perspectives}
            budget_estimated = classification.get("token_budget")
            model_used = settings.llm_model

            async with self._pool.connection() as db:
                for lens in lenses:
                    # Phase-confidence proxy → outcome_confidence
                    phases = committee.lens_lineage.get(lens, []) or []
                    confidences = [float(p.get("confidence", 0.0)) for p in phases if p.get("confidence") is not None]
                    outcome_confidence = sum(confidences) / len(confidences) if confidences else None

                    # Length-based token proxy (~4 chars / token)
                    output_text = committee.lens_outputs.get(lens, "") or ""
                    token_output = max(0, len(output_text) // 4)
                    token_input = 0  # not measurable per-lens today
                    token_total = token_output

                    cost_usd = cost_for_call(model_used, token_input, token_output)
                    alt_model = alternative_model_for(model_used)
                    estimated_alt = cost_for_call(alt_model, token_input, token_output) if alt_model else None
                    # Overthinking check (mirrors hook logic).
                    overthinking_flag = False
                    if token_input > 0 and token_output > 0 and cost_usd > 0 and estimated_alt is not None:
                        ratio = token_output / token_input
                        if ratio > 5.0 and cost_usd > estimated_alt:
                            overthinking_flag = True

                    recipe_slug = committee.recipe_slugs.get(lens, lens)
                    phase_fns = [p.get("cognitive_function") for p in phases if p.get("cognitive_function")]

                    try:
                        await db.query(
                            """
                            CREATE composition_signal SET
                                task_id = $task_id,
                                discipline = $discipline,
                                perspectives = $perspectives,
                                perspective_weights = $perspective_weights,
                                engagement_type = $engagement_type,
                                archetype = $archetype,
                                mode = $mode,
                                complexity = $complexity,
                                specialties_loaded = $specialties,
                                frameworks_used = $frameworks,
                                skill_used = $skill_used,
                                spin_count = $spin_count,
                                token_input = $token_input,
                                token_output = $token_output,
                                token_total = $token_total,
                                outcome_confidence = $outcome_confidence,
                                discipline_confidence = $discipline_confidence,
                                mode_confidence = $mode_confidence,
                                archetype_confidence = $archetype_confidence,
                                routing_uncertain = $routing_uncertain,
                                model_used = $model_used,
                                budget_estimated = $budget_estimated,
                                budget_used = $budget_used,
                                call_budget_estimated = $call_budget_estimated,
                                call_count_used = $call_count_used,
                                cost_usd = $cost_usd,
                                estimated_alternative_cost_usd = $estimated_alternative_cost_usd,
                                overthinking_flag = $overthinking_flag,
                                lens = $lens,
                                lens_set = $lens_set,
                                recipe_slug = $recipe_slug,
                                build_run_id = $build_run_id
                            """,
                            {
                                "task_id": build_run_id,
                                "discipline": lens,
                                "perspectives": perspectives,
                                "perspective_weights": perspective_weights,
                                "engagement_type": "deep_committee",
                                "archetype": archetype,
                                "mode": mode,
                                "complexity": complexity,
                                "specialties": specialties,
                                "frameworks": phase_fns,
                                "skill_used": recipe_slug,
                                "spin_count": 1,
                                "token_input": token_input,
                                "token_output": token_output,
                                "token_total": token_total,
                                "outcome_confidence": outcome_confidence,
                                "discipline_confidence": classification.get("discipline_confidence"),
                                "mode_confidence": mode_conf,
                                "archetype_confidence": classification.get("archetype_confidence"),
                                "routing_uncertain": routing_uncertain,
                                "model_used": model_used,
                                "budget_estimated": budget_estimated,
                                "budget_used": token_output,
                                "call_budget_estimated": budget_state.get("call_budget"),
                                "call_count_used": budget_state.get("phase_count"),
                                "cost_usd": cost_usd if cost_usd > 0 else None,
                                "estimated_alternative_cost_usd": estimated_alt,
                                "overthinking_flag": overthinking_flag,
                                "lens": lens,
                                "lens_set": list(lenses),
                                "recipe_slug": recipe_slug,
                                "build_run_id": build_run_id,
                            },
                        )
                    except Exception as inner_exc:
                        logger.warning(
                            "_emit_team_signals: row write failed for lens=%s: %s",
                            lens,
                            inner_exc,
                        )
        except Exception as exc:
            logger.warning("_emit_team_signals failed: %s", exc, exc_info=True)

    async def _persist_spec(self, spec_data: dict, source: str, capability_slug: str | None, product_id: str) -> dict:
        """Write spec to database."""
        async with self._pool.connection() as db:
            # Resolve capability ID if slug provided
            cap_ref = None
            if capability_slug:
                cap_result = await db.query(
                    "SELECT id FROM capability WHERE product = <record>$product AND slug = <string>$slug",
                    {"product": product_id, "slug": capability_slug},
                )
                cap = parse_one(cap_result)
                if cap:
                    cap_ref = str(cap["id"])

            # Build acceptance criteria (normalize to dicts)
            criteria = []
            for c in spec_data.get("acceptance_criteria", []):
                if isinstance(c, dict):
                    criteria.append(c)
                elif isinstance(c, str):
                    criteria.append({"criterion": c, "verification": "", "automated": False})

            # Normalize test_requirements to strings (schema is array<string>)
            raw_tests = spec_data.get("test_requirements") or []
            test_reqs = []
            for t in raw_tests:
                if isinstance(t, dict):
                    test_reqs.append(f"{t.get('name', '')}: {t.get('description', '')}")
                else:
                    test_reqs.append(str(t))

            # Normalize constraints and best_practices to strings
            raw_constraints = spec_data.get("constraints") or []
            constraints = [str(c) for c in raw_constraints]
            raw_bp = spec_data.get("best_practices") or []
            best_practices = [str(b) for b in raw_bp]
            raw_files = spec_data.get("estimated_files") or []
            estimated_files = [str(f) for f in raw_files]

            # Team-authored fields (only present when from_request_with_team ran).
            # Default to "solo"/empty so the column is always populated and clients
            # can tell apart team-built vs solitary specs.
            authored_by = spec_data.get("authored_by") or "solo"
            team_roster = spec_data.get("team_roster") or []
            team_lineage = spec_data.get("team_lineage") or {}
            risk = spec_data.get("risk") or ""

            # Build query — use NONE for null capability, <record> cast for non-null
            if cap_ref:
                result = await db.query(
                    """CREATE agent_spec SET
                        capability = <record>$capability,
                        source = $source,
                        objective = $objective,
                        context = $context,
                        acceptance_criteria = $criteria,
                        constraints = $constraints,
                        integration_points = $integration_points,
                        estimated_files = $estimated_files,
                        test_requirements = $test_requirements,
                        best_practices = $best_practices,
                        authored_by = $authored_by,
                        team_roster = $team_roster,
                        team_lineage = $team_lineage,
                        risk = $risk,
                        status = 'draft'""",
                    {
                        "product": product_id,
                        "capability": cap_ref,
                        "source": source,
                        "objective": spec_data.get("objective", ""),
                        "context": spec_data.get("context"),
                        "criteria": criteria,
                        "constraints": constraints,
                        "integration_points": spec_data.get("integration_points"),
                        "estimated_files": estimated_files,
                        "test_requirements": test_reqs,
                        "best_practices": best_practices,
                        "authored_by": authored_by,
                        "team_roster": team_roster,
                        "team_lineage": team_lineage,
                        "risk": risk,
                    },
                )
            else:
                result = await db.query(
                    """CREATE agent_spec SET
                        capability = NONE,
                        source = $source,
                        objective = $objective,
                        context = $context,
                        acceptance_criteria = $criteria,
                        constraints = $constraints,
                        integration_points = $integration_points,
                        estimated_files = $estimated_files,
                        test_requirements = $test_requirements,
                        best_practices = $best_practices,
                        authored_by = $authored_by,
                        team_roster = $team_roster,
                        team_lineage = $team_lineage,
                        risk = $risk,
                        status = 'draft'""",
                    {
                        "product": product_id,
                        "source": source,
                        "objective": spec_data.get("objective", ""),
                        "context": spec_data.get("context"),
                        "criteria": criteria,
                        "constraints": constraints,
                        "integration_points": spec_data.get("integration_points"),
                        "estimated_files": estimated_files,
                        "test_requirements": test_reqs,
                        "best_practices": best_practices,
                        "authored_by": authored_by,
                        "team_roster": team_roster,
                        "team_lineage": team_lineage,
                        "risk": risk,
                    },
                )
            spec = parse_one(result)
            out = spec if spec else spec_data

        # Emit spec.created event
        try:
            from core.engine.events.bus import bus

            await bus.emit(
                "spec.created",
                {
                    "product_id": product_id,
                    "source": source,
                    "capability_slug": capability_slug,
                    "objective": spec_data.get("objective", ""),
                    "spec_id": str(out.get("id", "")),
                },
            )
        except Exception:
            pass

        return out
