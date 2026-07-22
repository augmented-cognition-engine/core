# engine/cognition/multiphase.py
"""MultiPhaseExecutor — executes depth 3-4 CognitiveCompositions as sequential LLM calls.

Each RecipePhase becomes a separate LLM call. The output of phase N is
passed as context to phase N+1 via the user prompt. The final output is
the concatenation of all phase outputs (or just the last phase for depth 3).

At depth 4, a three-mode-critique loop runs after all phases complete.

Usage:
    executor = MultiPhaseExecutor(llm_call=my_async_llm_fn)
    result = await executor.execute(description, composition, framework_prompts)
"""

from __future__ import annotations

import json
import logging
from typing import Awaitable, Callable

from core.engine.cognition import moa
from core.engine.cognition.best_of_n import BestOfNSampler, PhaseCandidate
from core.engine.cognition.confidence_gate import ConfidenceGate
from core.engine.cognition.fusion import render_context_sections
from core.engine.cognition.models import CaptureSpec, CognitiveComposition, ContextQuery
from core.engine.cognition.phase_evaluator import PhaseEvaluator
from core.engine.cognition.phase_output import PhaseOutput
from core.engine.cognition.tool_catalog import render_phase_tools
from core.engine.core.error_buffer import error_buffer

logger = logging.getLogger(__name__)

_CONFIDENCE_FLOOR = 0.08  # accumulated product floor — ~3 phases at 0.45 each ≈ 0.09

LLMCallFn = Callable[[str | list[dict], str], Awaitable[str]]
RetrievalFn = Callable[[list[str]], Awaitable[str]]


def resolve_moa_config(settings) -> "tuple[list[str] | None, str | None]":
    """Resolve the MoA proposer set + aggregator from settings (MoA Part 2 production wiring).

    Empty ``moa_models`` → ``(None, None)`` = MoA off (the default; behavior unchanged). When proposers
    are configured, the aggregator defaults to the strong reasoning model (``settings.llm_model``) so a
    Claude synthesizes the diverse (including local-Ollama) proposals — never a weak local proposer by
    accident — unless ``moa_aggregator_model`` is set explicitly.
    """
    models = list(settings.moa_models) if getattr(settings, "moa_models", None) else None
    if not models:
        return None, None
    # Aggregator: explicit > the strong reasoning model > the first Claude proposer > last proposer.
    # The Claude-proposer fallback STRUCTURALLY prevents a weak LOCAL model becoming the synthesizer if
    # llm_model were ever unset (otherwise MultiPhaseExecutor's own `moa_models[-1]` fallback could pick
    # a local proposer). A local aggregator results only when NO Claude is configured anywhere — an
    # explicit operator choice, never an accident.
    aggregator = (
        getattr(settings, "moa_aggregator_model", None)
        or getattr(settings, "llm_model", None)
        or next((m for m in models if m.startswith("claude")), models[-1])
    )
    return models, aggregator


def _format_prior_phase(idx: int, raw_output: str) -> str:
    """Format prior phase output for next-phase context.

    Tries to parse as PhaseOutput JSON and inject evidence/gaps structurally.
    Falls back to plain text if parsing fails (non-fatal).
    """
    try:
        data = json.loads(raw_output)
        po = PhaseOutput.model_validate(data)
        parts = [f"Phase {idx} analysis: {po.output}"]
        if po.evidence:
            parts.append(f"Established facts: {'; '.join(po.evidence)}")
        if po.gaps:
            parts.append(f"Open gaps to address: {'; '.join(po.gaps)}")
        return "\n".join(parts)
    except Exception:
        return f"Phase {idx}: {raw_output}"


class MultiPhaseExecutor:
    """Executes a non-fused CognitiveComposition as sequential LLM calls."""

    def __init__(
        self,
        llm_call: LLMCallFn,
        retrieval_fn: "RetrievalFn | None" = None,
        confidence_threshold: float = 0.6,
        phase_evaluator: "PhaseEvaluator | None" = None,
        branch_count: int = 3,
        self_refine_rounds: int = 0,
        on_phase: "Callable[[int, int, str, str, float, list[str]], Awaitable[None]] | None" = None,
        moa_models: "list[str] | None" = None,
        moa_aggregator_model: str | None = None,
        high_stakes_function: str = "choose",
    ) -> None:
        """
        Args:
            llm_call: async (system_prompt: str, user_prompt: str) -> str
            retrieval_fn: optional async (gap_terms: list[str]) -> str for mid-phase retrieval
            confidence_threshold: gate threshold below which retrieval/branching fires (default 0.6)
            phase_evaluator: optional PhaseEvaluator for lazy best-of-N branching
            branch_count: number of candidates to generate when gate fires (default 3)
            self_refine_rounds: number of self-refinement rounds per phase (default 0, disabled)
            on_phase: optional async callback fired once per completed phase:
                (phase_idx, total_phases, cognitive_function, output, confidence, gaps) -> None
            moa_models: list of model IDs for Mixture-of-Agents diverse proposers. When None
                (default), MoA is disabled and same-model best-of-N branching runs unchanged.
            moa_aggregator_model: model used to synthesize MoA proposals. Defaults to the last
                (strongest) proposer when unspecified.
            high_stakes_function: the cognitive_function value that triggers MoA when moa_models
                is set (default "choose").
        """
        self._llm_call = llm_call
        self._retrieval_fn = retrieval_fn
        self._confidence_gate = ConfidenceGate(confidence_threshold=confidence_threshold)
        self._phase_evaluator = phase_evaluator
        self._branch_count = branch_count
        self._sampler = BestOfNSampler()
        self._self_refine_rounds = self_refine_rounds
        self._on_phase = on_phase
        self._moa_models = moa_models
        # Aggregator defaults to the last (strongest) proposer when unspecified.
        self._moa_aggregator_model = moa_aggregator_model or (moa_models[-1] if moa_models else None)
        self._high_stakes_function = high_stakes_function
        self._last_trace: list[dict] = []  # populated by execute(), reset each call

    async def execute(
        self,
        description: str,
        composition: CognitiveComposition,
        framework_prompts: dict[str, str],
        intel_context: str = "",
        product_id: str = "product:platform",
    ) -> str:
        """Execute composition phases sequentially.

        intel_context: assembled intelligence string (specialty insights, code context,
            failure memory, decisions).  When provided, injected into phase 1's user
            prompt so the model reasons over codebase-specific context from the start.
            Subsequent phases inherit this via the phase_outputs chain.

        Returns "" if composition is fused (fusion_mode=True) or has no phases.
        The executor only handles this for depth 3-4 non-fused compositions.
        """
        if composition.fusion_mode or not composition.active_phases:
            return ""

        self._last_trace = []  # reset on each execution call

        phase_outputs: list[str] = []
        accumulated_confidence = 1.0  # Gap 3: tracks cross-phase quality decay
        _carry_violations: list[str] = []  # Gap 4: carries violated constraints to next phase

        # Composition-level grounding sections (e.g. the loop-context "What we
        # already know" block) sit at indices BEYOND active_phases in
        # prompt_sections — positional indexing below never reaches them. Render
        # them once into the stable prefix of every phase so the grounding
        # actually enters the LLM prompt on the deep path.
        composition_context_block = render_context_sections(composition.prompt_sections)

        for i, phase in enumerate(composition.active_phases):
            section = composition.prompt_sections[i] if i < len(composition.prompt_sections) else {}
            framework_slugs = section.get("framework_slugs", [])
            output_schema = section.get("output_schema", "")
            label = section.get("fusion_label", f"[{phase.cognitive_function.upper()}]")

            # Build system prompt for this phase
            fw_prompt = ""
            for slug in framework_slugs:
                fw_prompt = framework_prompts.get(slug, "")
                if fw_prompt:
                    break

            # Gap 2: warn when no framework loaded — bare fallback will fire in system prompt
            if not fw_prompt:
                logger.warning(
                    "Phase %d (%s): no framework loaded for slugs %s — using bare fallback",
                    i,
                    phase.cognitive_function,
                    framework_slugs,
                )

            constraint_lines: list[str] = []
            if phase.must_not:
                constraint_lines.append("\nMUST NOT:")
                for c in phase.must_not:
                    constraint_lines.append(f"  - {c}")
            if phase.must_verify:
                constraint_lines.append("\nMUST VERIFY:")
                for c in phase.must_verify:
                    constraint_lines.append(f"  - {c}")
            constraint_block = "\n".join(constraint_lines)

            # Gap 4: inject violated constraints from prior phase as negative context
            carry_block = ""
            if _carry_violations:
                carry_lines = ["\nPRIOR PHASE VIOLATIONS — do NOT repeat these in your output:"]
                carry_lines.extend(f"  - {v}" for v in _carry_violations)
                carry_block = "\n".join(carry_lines)

            # Graph context injection: run load_context queries before building system prompt
            graph_context_block = ""
            if phase.load_context is not None:
                graph_context_block = await self._load_phase_context(phase.load_context, product_id)

            # Stable prefix — same across calls for a given cognitive_function + framework.
            # Composition-level grounding (loop context) lives here too: it is
            # stable across all phases of this composition, so it stays in the
            # cacheable block rather than the dynamic suffix.
            stable_prefix = (
                f"You are executing the {label} phase of a structured cognitive process.\n\n"
                f"{fw_prompt or f'Apply {phase.cognitive_function} reasoning to this task.'}"
            )
            if composition_context_block:
                stable_prefix += f"\n\n{composition_context_block}"

            # Dynamic suffix — changes per task (constraints, carry violations, graph context)
            dynamic_parts = []
            if constraint_block:
                dynamic_parts.append(constraint_block)
            if carry_block:
                dynamic_parts.append(carry_block)
            dynamic_parts.append(f"\nFocus: {output_schema}")
            if graph_context_block:
                dynamic_parts.append(graph_context_block)
            dynamic_parts.append(PhaseOutput.schema_prompt())
            tool_block = render_phase_tools(section.get("tool_slugs", []))
            if tool_block:
                dynamic_parts.append(tool_block)
            dynamic_suffix = "\n".join(dynamic_parts)

            # Build cache-structured system prompt
            system_prompt = [
                {"type": "text", "text": stable_prefix, "cache_control": {"type": "ephemeral"}},
                {"type": "text", "text": dynamic_suffix},
            ]

            # User prompt includes prior phase outputs as context
            if phase_outputs:
                prior_context = "\n\n".join(_format_prior_phase(j, out) for j, out in enumerate(phase_outputs))
                user_prompt = (
                    f"Original task: {description}\n\n"
                    f"Prior phase outputs:\n{prior_context}\n\n"
                    f"Now execute the {phase.cognitive_function} phase."
                )
            else:
                # Phase 1: inject intelligence context once so the model reasons over
                # codebase-specific content from the start.  Subsequent phases inherit
                # this via the phase_outputs chain and don't need it repeated.
                if intel_context:
                    user_prompt = (
                        f"{intel_context}\n\n"
                        f"---\n\n"
                        f"The context above shows relevant source files and intelligence for this codebase. "
                        f"Ground your analysis in these specific files and components where applicable.\n\n"
                        f"Task: {description}"
                    )
                else:
                    user_prompt = description

            try:
                output = await self._llm_call(system_prompt, user_prompt)
                phase_outputs.append(output)
                winning_output = output
                winning_evaluation = None

                _carry_violations = []  # Gap 4: prior violations already injected above; reset
                # Trace entry for this phase (fields updated below as processing runs)
                _trace_entry: dict = {
                    "phase_idx": i,
                    "cognitive_function": phase.cognitive_function,
                    "confidence": 0.0,
                    "gaps": [],
                    "branched": False,
                    "branch_count": 0,
                    "pass_at_k_proxy": 1.0,  # default: 100% pass when no branching
                    "retrieved": False,
                    "self_refined": False,
                    "refine_rounds": 0,
                    "tainted": False,  # Gap 1/2: set True on exception failure
                    "framework_loaded": bool(fw_prompt),  # Gap 2: was a framework slug resolved?
                }

                # Wave 3: lazy best-of-N branching — fires only when gate fires + evaluator provided
                if self._phase_evaluator is not None:
                    try:
                        po = PhaseOutput.model_validate(json.loads(output))
                        if self._confidence_gate.should_retrieve(po):
                            initial_result = await self._phase_evaluator.evaluate(description, po, phase)
                            winning_evaluation = initial_result
                            candidates = [
                                PhaseCandidate(
                                    output=output,
                                    phase_output=po,
                                    score=initial_result.score,
                                    evaluation_result=initial_result,
                                )
                            ]
                            moa_used = False
                            if self._moa_models and phase.cognitive_function == self._high_stakes_function:
                                try:
                                    moa_prompt = f"{stable_prefix}\n\n{dynamic_suffix}\n\n{user_prompt}"
                                    proposals = await moa.propose(moa_prompt, PhaseOutput, self._moa_models)
                                    if proposals:
                                        agg = await moa.aggregate(
                                            proposals, description, PhaseOutput, self._moa_aggregator_model
                                        )
                                        candidates_before = len(candidates)
                                        for p in ([agg] if agg else []) + proposals:
                                            try:
                                                presult = await self._phase_evaluator.evaluate(
                                                    description, p.output, phase
                                                )
                                                candidates.append(
                                                    PhaseCandidate(
                                                        output=p.raw,
                                                        phase_output=p.output,
                                                        score=presult.score,
                                                        evaluation_result=presult,
                                                    )
                                                )
                                            except Exception:
                                                pass
                                        # Only suppress the same-model fallback when MoA actually
                                        # added a candidate. If every evaluate() raised (flaky
                                        # LLM-backed evaluator), candidates stays unchanged →
                                        # moa_used remains False → same-model branching takes over.
                                        if len(candidates) > candidates_before:
                                            moa_used = True
                                            _trace_entry["moa"] = True
                                            _trace_entry["moa_proposers"] = len(proposals)
                                except Exception:
                                    pass  # MoA failure → fall through to same-model branching

                            if not moa_used:
                                for _ in range(self._branch_count - 1):
                                    try:
                                        braw = await self._llm_call(system_prompt, user_prompt)
                                        bpo = PhaseOutput.model_validate(json.loads(braw))
                                        bresult = await self._phase_evaluator.evaluate(description, bpo, phase)
                                        candidates.append(
                                            PhaseCandidate(
                                                output=braw,
                                                phase_output=bpo,
                                                score=bresult.score,
                                                evaluation_result=bresult,
                                            )
                                        )
                                    except Exception:
                                        pass  # Non-fatal: skip failed branch
                            if len(candidates) > 1:
                                best = self._sampler.select_best(candidates)
                                winning_output = best.output
                                phase_outputs[-1] = best.output
                                _trace_entry["branched"] = True
                                _trace_entry["branch_count"] = len(candidates)
                                _trace_entry["winning_output"] = winning_output
                                _above = sum(
                                    1
                                    for c in candidates
                                    if c.phase_output.confidence >= self._confidence_gate._threshold
                                )
                                _trace_entry["pass_at_k_proxy"] = _above / len(candidates)
                                # Gap 4: carry winner's violated constraints into next phase
                                if best.evaluation_result:
                                    winning_evaluation = best.evaluation_result
                                    _carry_violations = best.evaluation_result.violated_constraints
                    except Exception:
                        pass  # Non-fatal: branching failure leaves initial output intact

                # Wave 5: EVALUATOR-GUIDED REFINEMENT (LLM-Modulo) — revise the winning
                # candidate against the evaluator's named violations; accept a revision
                # ONLY if the evaluator scores it no worse (non-regression → monotonic).
                # Requires the evaluator: its verdict is the external grounding signal that
                # makes single-model refinement help instead of degrade. No naive fallback.
                if self._self_refine_rounds > 0 and self._phase_evaluator is not None:
                    try:
                        _sr_po = PhaseOutput.model_validate(json.loads(winning_output))
                        if self._confidence_gate.should_retrieve(_sr_po):
                            _rounds_done = 0
                            # Wave 3 already evaluated this exact winning
                            # candidate. Reuse that verdict instead of making a
                            # stochastic duplicate critic call before refinement.
                            _result = winning_evaluation or await self._phase_evaluator.evaluate(
                                description, _sr_po, phase
                            )
                            _violations_before = len(_result.violated_constraints)
                            for _round in range(self._self_refine_rounds):
                                if not _result.violated_constraints and not self._confidence_gate.should_retrieve(
                                    _sr_po
                                ):
                                    break  # verifier satisfied
                                if _result.violated_constraints:
                                    _critique = "\n".join(f"- {v}" for v in _result.violated_constraints)
                                    _instruction = (
                                        "An evaluator found these constraint violations. Fix EACH one specifically:\n"
                                        f"{_critique}"
                                    )
                                else:
                                    _instruction = (
                                        "An evaluator judged this output low-confidence. Strengthen the weakest, "
                                        "least-evidenced claims and add the missing evidence."
                                    )
                                revised = await self._llm_call(
                                    system_prompt,
                                    f"{user_prompt}\n\nYour previous output:\n{winning_output}\n\n{_instruction}",
                                )
                                try:
                                    _rev_po = PhaseOutput.model_validate(json.loads(revised))
                                    _rev_result = await self._phase_evaluator.evaluate(description, _rev_po, phase)
                                except Exception:
                                    break  # unparseable / unscorable revision → keep prior
                                if _rev_result.score >= _result.score:  # NON-REGRESSION guard
                                    winning_output = revised
                                    phase_outputs[-1] = revised
                                    _sr_po, _result = _rev_po, _rev_result
                                    winning_evaluation = _rev_result
                                    _rounds_done += 1
                                else:
                                    break  # revision regressed → keep prior, stop
                            if _rounds_done > 0:
                                _trace_entry["self_refined"] = True
                                _trace_entry["refine_rounds"] = _rounds_done
                                _trace_entry["violations_before"] = _violations_before
                                _trace_entry["violations_after"] = len(_result.violated_constraints)
                    except Exception:
                        pass  # Non-fatal — refinement failure leaves winning_output intact

                # Wave 2: retrieval on the winning candidate (runs after branching)
                if self._retrieval_fn is not None:
                    try:
                        po = PhaseOutput.model_validate(json.loads(winning_output))
                        if self._confidence_gate.should_retrieve(po):
                            extra = await self._retrieval_fn(self._confidence_gate.retrieval_query(po))
                            if extra:
                                phase_outputs.append(f"[Mid-phase retrieval]\n{extra}")
                                _trace_entry["retrieved"] = True
                    except Exception:
                        pass  # Non-fatal: if parsing fails, skip retrieval

                # Finalize trace: extract confidence from winning output
                try:
                    _final_po = PhaseOutput.model_validate(json.loads(winning_output))
                    _trace_entry["confidence"] = _final_po.confidence
                    _trace_entry["gaps"] = list(_final_po.gaps)
                except Exception:
                    pass
                self._last_trace.append(_trace_entry)

                if self._on_phase is not None:
                    await self._on_phase(
                        i,
                        len(composition.active_phases),
                        phase.cognitive_function,
                        winning_output,
                        _trace_entry["confidence"],
                        _trace_entry["gaps"],
                    )

                # Auto-capture: persist phase output to product graph if capture_as is set
                if phase.capture_as is not None and not _trace_entry.get("tainted", False):
                    await self._capture_phase_output(phase.capture_as, winning_output, product_id, description)

                # Gap 3: halt pipeline if accumulated confidence product falls below floor
                accumulated_confidence *= _trace_entry["confidence"] or 1.0
                if accumulated_confidence < _CONFIDENCE_FLOOR and i < len(composition.active_phases) - 1:
                    logger.warning(
                        "MultiPhaseExecutor: accumulated confidence %.3f below floor — halting at phase %d",
                        accumulated_confidence,
                        i,
                    )
                    self._last_trace[-1]["early_exit"] = True
                    break

            except Exception as exc:
                # Gap 1: record to ErrorBuffer and append a taint trace entry so the phase
                # is visible in _last_trace rather than silently disappearing.
                logger.warning("Phase %d (%s) failed: %s", i, phase.cognitive_function, exc)
                error_buffer.record(
                    source="MultiPhaseExecutor",
                    error_type=type(exc).__name__,
                    message=str(exc),
                    context={"phase_idx": i, "cognitive_function": phase.cognitive_function},
                )
                phase_outputs.append(f"[Phase {phase.cognitive_function} failed]")
                self._last_trace.append(
                    {
                        "phase_idx": i,
                        "cognitive_function": phase.cognitive_function,
                        "confidence": 0.0,
                        "gaps": [],
                        "branched": False,
                        "branch_count": 0,
                        "pass_at_k_proxy": 0.0,
                        "retrieved": False,
                        "self_refined": False,
                        "refine_rounds": 0,
                        "tainted": True,
                        "framework_loaded": False,
                    }
                )
                if self._on_phase is not None:
                    await self._on_phase(
                        i,
                        len(composition.active_phases),
                        phase.cognitive_function,
                        phase_outputs[-1],
                        0.0,
                        [],
                    )

        # At depth 4, run critique loop on combined output — skip if all phases tainted
        all_tainted = self._last_trace and all(t.get("tainted", False) for t in self._last_trace)
        if composition.depth >= 4 and phase_outputs and not all_tainted:
            combined = "\n\n".join(phase_outputs)
            critique_prompt = framework_prompts.get("three-mode-critique", "Run a three-mode critique.")
            critique_output = await self._llm_call(
                f"You are running a final three-mode critique.\n\n{critique_prompt}",
                f"Review this analysis:\n\n{combined}",
            )
            return combined + "\n\n[CRITIQUE]\n" + critique_output

        # Return last phase output as the primary result
        return phase_outputs[-1] if phase_outputs else ""

    async def _load_phase_context(self, query: "ContextQuery", product_id: str) -> str:
        """Run graph queries and return a formatted context block for system prompt injection.

        Returns "" on any failure — never blocks phase execution.
        """
        from core.engine.core.db import parse_rows, pool

        if not isinstance(query, ContextQuery):
            return ""

        rows_parts: list[str] = []
        try:
            async with pool.connection() as db:
                for sql in query.queries:
                    try:
                        result = await db.query(sql, {"product": product_id})
                        rows = parse_rows(result)
                        if rows:
                            rows_parts.append(json.dumps(rows, default=str))
                    except Exception as exc:
                        logger.debug("load_phase_context query failed: %s", exc)
        except Exception as exc:
            logger.debug("load_phase_context pool.connection failed: %s", exc)
            return ""

        if not rows_parts:
            return ""

        context_text = "\n".join(rows_parts)
        return f"\n\n## {query.inject_as}\n{context_text[:2000]}\n"  # hard cap to protect token budget

    async def _capture_phase_output(
        self,
        spec: "CaptureSpec",
        output: str,
        product_id: str,
        description: str,
    ) -> None:
        """Extract phase output fields and write to the observation queue.

        Routes through the observation table so it's picked up by the existing
        synthesis pipeline (Observer → Synthesizer → insight). Never raises.
        """
        from core.engine.core.db import pool

        if not isinstance(spec, CaptureSpec):
            return

        try:
            # Try to extract structured fields from PhaseOutput JSON.
            # Note: PhaseOutput.output is always a str, never a nested dict —
            # so we look for each field_name directly on the parsed object.
            content_parts: list[str] = []
            try:
                data = json.loads(output)
                for field_name in spec.extract_fields:
                    value = data.get(field_name)
                    if value:
                        content_parts.append(f"{field_name}: {str(value)[:500]}")
            except (json.JSONDecodeError, AttributeError):
                # Not JSON — capture the whole output trimmed
                content_parts.append(output[:600])

            if not content_parts:
                content_parts.append(description[:200])

            content = "\n".join(content_parts)

            async with pool.connection() as db:
                await db.query(
                    """
                    CREATE observation SET
                        product = <record>$product,
                        observation_type = $type,
                        content = $content,
                        discipline_hint = $discipline_hint,
                        domain_path = $discipline_hint,
                        confidence = 0.75,
                        source = 'composition_phase',
                        status = 'pending',
                        created_at = time::now()
                    """,
                    {
                        "product": product_id,
                        "type": spec.type,
                        "content": content,
                        "discipline_hint": spec.discipline_hint,
                    },
                )
            logger.debug(
                "Captured phase output: type=%s discipline=%s chars=%d",
                spec.type,
                spec.discipline_hint,
                len(content),
            )
        except Exception as exc:
            logger.debug("_capture_phase_output failed (non-fatal): %s", exc)
