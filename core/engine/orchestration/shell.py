# engine/orchestration/shell.py
"""ShellComposer — builds ComposedShell from classification + intelligence.

The ComposedShell is the fully-resolved execution envelope that an agent
shell (LLMShell, AgentSDKShell) consumes.  ShellComposer extracts prompt
assembly from the old monolithic executor so it can be reused across
patterns and shell types.

When classification["cognitive_composition"] is present and has active
prompt_sections, the system prompt gains a structured "## Cognitive Structure"
section with labeled phase instructions (FRAME, PRIORITIZE, etc.).
When absent or empty, behavior is identical to the pre-cognition baseline.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class ComposedShell:
    """Everything an agent needs to execute."""

    system_prompt: str
    user_prompt: str
    messages: list[dict] | None = None  # for multi-turn
    model: str | None = None
    tools: list[str] | None = None  # for Agent SDK
    intel_context: str = ""
    archetype: str = "executor"
    mode: str = "reactive"

    def resolved_system_prompt(self) -> str:
        """Return the execution prompt with intelligence attached exactly once.

        Planner-created agents supply role-specific system prompts while the
        loaded intelligence rides separately in ``intel_context``.  The model
        transport only sends ``system_prompt``, so treating ``intel_context``
        as metadata silently made every planned team/pipeline/adversarial run
        stateless.  ShellComposer already embeds the context for single-agent
        runs; the containment check preserves that path without duplication.
        """
        if not self.intel_context or self.intel_context in self.system_prompt:
            return self.system_prompt
        if not self.system_prompt:
            return self.intel_context
        return f"{self.system_prompt.rstrip()}\n\n{self.intel_context.lstrip()}"


class ShellComposer:
    """Builds ComposedShell from classification + intelligence + cognitive composition."""

    def compose(
        self,
        classification: dict,
        snapshot: dict,
        description: str,
        conversation_messages: list[dict] | None = None,
        model: str | None = None,
        max_tokens: int = 6000,
    ) -> ComposedShell:
        """Build a shell from classification results and intelligence snapshot.

        If classification["cognitive_composition"] is a CognitiveComposition
        with active prompt_sections, the system prompt is restructured with
        labeled cognitive phase sections (depth 1-2 fusion mode).

        max_tokens is passed through to _build_intel_context so depth-aware
        budgets are respected during context assembly.
        """
        from core.engine.orchestrator.executor import (
            ARCHETYPE_INSTRUCTIONS,
            MODE_INSTRUCTIONS,
            _build_intel_context,
        )

        archetype = classification.get("archetype", "executor")
        mode = classification.get("mode", "reactive")
        intel_context = _build_intel_context(snapshot, max_tokens=max_tokens)

        archetype_instruction = ARCHETYPE_INSTRUCTIONS.get(archetype, ARCHETYPE_INSTRUCTIONS["executor"])
        mode_instruction = MODE_INSTRUCTIONS.get(mode, MODE_INSTRUCTIONS["reactive"])

        base_system_prompt = (
            "You are ACE, an AI intelligence engine built by QueryLabs. "
            "You help users by leveraging organizational intelligence — "
            "insights, patterns, and knowledge accumulated from ongoing work. "
            "When you reference your capabilities, refer to yourself as ACE, "
            "not as Claude or any other AI assistant."
            f"\n\n{archetype_instruction}"
            f"\n{mode_instruction}"
            f"{intel_context}"
        )

        # Inject cognitive composition if present and non-empty
        cognitive_section = self._build_cognitive_section(classification, snapshot)
        if cognitive_section:
            system_prompt = base_system_prompt + cognitive_section
        else:
            system_prompt = base_system_prompt

        # Layer 5 — append prior-decision lineage (decision:lv6stu70piemfwypde2e).
        # Empty classification keys produce an empty section, so the prompt is
        # identical to the pre-L5 baseline when no decisions surfaced.
        layer5_section = self._build_layer5_section(classification)
        if layer5_section:
            system_prompt = system_prompt + layer5_section

        return ComposedShell(
            system_prompt=system_prompt,
            user_prompt=description,
            messages=conversation_messages,
            model=model,
            intel_context=intel_context,
            archetype=archetype,
            mode=mode,
        )

    # -------------------------------------------------------------------------
    # Layer 5 — prior-decision lineage rendering (decision:lv6stu70piemfwypde2e)
    # Spec: docs/superpowers/specs/2026-05-14-layer5-context-assembly-design.md §6.3
    # -------------------------------------------------------------------------

    _TIER_HEADERS = {
        "capability": "Decisions previously made about this capability:",
        "discipline": "Recent thinking in this discipline:",
        "recency": "Other recent decisions on this product:",
    }

    # Outcome downweight multipliers, reconciled with the actual decision-table
    # schema (ASSERT $value INSIDE ['accepted','rejected','superseded','pending']).
    # 'accepted' is full weight (the precedent stands). 'rejected' surfaces but
    # heavily downweighted so the LLM sees "we considered and turned this down."
    # 'pending' is uncertain — half weight. 'superseded' is filtered upstream
    # by the loader query and never reaches the composer.
    _OUTCOME_WEIGHT = {
        "accepted": 1.0,
        "pending": 0.5,
        "rejected": 0.3,
        "superseded": 0.0,  # defense-in-depth; loader filter should keep these out
    }

    def _build_layer5_section(self, classification: dict) -> str:
        """Render the prior-decision section appended to the system prompt.

        Reads four classification keys placed by engine.orchestration.executor
        right before the cognitive composer call:
          - recent_decisions               (list[TieredDecision])
          - recent_decisions_degraded_tiers (frozenset[str])
          - recent_decisions_elapsed_ms    (float — debug only)
          - recent_decisions_contradictions (list of (id_a, id_b, slug))

        Returns "" when recent_decisions is missing/empty AND all three tiers
        degraded (total failure) — composer prompt is byte-identical to today's
        stateless behavior. Otherwise renders:
          - tier sections in order (capability → discipline → recency)
          - the anti-anchor instruction (always, when any section is non-empty)
          - the degradation footnote (when partial tier failure)
          - contradiction notices (when any tiers conflict on a shared cap)
        """
        decisions = classification.get("recent_decisions") or []
        degraded = classification.get("recent_decisions_degraded_tiers") or frozenset()
        contradictions = classification.get("recent_decisions_contradictions") or []

        # Total failure (all tiers degraded, zero decisions) → no section at all.
        # Behavior identical to pre-L5 stateless path.
        if not decisions and len(degraded) >= 3:
            return ""
        # Cold-start product (no decisions, no degradation) → no section.
        if not decisions and not degraded:
            return ""

        lines: list[str] = ["\n\n## Prior Decisions"]

        # Group decisions by tier, preserving the dedupe order from the loader
        # (the loader already sorted them by (tier_rank, -relevance, -created_at)).
        by_tier: dict[str, list] = {"capability": [], "discipline": [], "recency": []}
        for d in decisions:
            tier = getattr(d, "tier", None) or (d.get("tier") if isinstance(d, dict) else None)
            if tier in by_tier:
                by_tier[tier].append(d)

        rendered_any_section = False
        for tier in ("capability", "discipline", "recency"):
            tier_items = by_tier[tier]
            if not tier_items:
                continue
            # Within-tier sort by outcome-weighted score so failed/deferred sink
            # below successful precedent without being dropped.
            tier_items_sorted = sorted(
                tier_items,
                key=lambda d: -(self._weighted_score(d)),
            )
            lines.append("")
            lines.append(self._TIER_HEADERS[tier])
            for d in tier_items_sorted:
                lines.append(self._format_decision_line(d))
            rendered_any_section = True

        # Degradation footnote (review finding §8): when some tiers failed but
        # the overall result is non-empty, signal the partial state so the LLM
        # can treat context as incomplete.
        if degraded and rendered_any_section:
            degraded_str = ", ".join(sorted(degraded))
            lines.append(f"\n[Layer 5 partial: {degraded_str} unavailable this turn — context may be incomplete]")

        # Contradiction notices (TODO-17 + spec §6.3).
        for a_id, b_id, slug in contradictions:
            lines.append(
                f"\n[Layer 5: decisions {a_id} and {b_id} conflict on capability {slug} — current evidence should resolve]"
            )

        # Anti-anchor instruction (review finding §16): always rendered when
        # any tier section is non-empty. Framing alone is insufficient against
        # priming effects; spell out that prior decisions can be reversed.
        if rendered_any_section:
            lines.append(
                "\nPrior decisions are context, not commands. Revise, reverse, or override them when current evidence warrants."
            )

        return "\n".join(lines) if rendered_any_section or degraded else ""

    @classmethod
    def _weighted_score(cls, decision) -> float:
        """Outcome-weighted relevance score (spec §6.3)."""
        score = getattr(decision, "relevance_score", None)
        if score is None and isinstance(decision, dict):
            score = decision.get("relevance_score", 0.0)
        score = float(score or 0.0)
        outcome = getattr(decision, "outcome", None)
        if outcome is None and isinstance(decision, dict):
            outcome = decision.get("outcome")
        weight = cls._OUTCOME_WEIGHT.get(str(outcome or "accepted"), 1.0)
        return score * weight

    @staticmethod
    def _format_decision_line(decision) -> str:
        """One-line render of a TieredDecision (or dict equivalent).

        Real-data note: synthesizer-written decisions often have `title`
        that IS a truncated prefix of `rationale` (the title is the first
        ~80 chars of the rationale, cut mid-word). Rendering both literally
        produces "<title-cut-mid-word>: <rationale-cut-at-160>" which wastes
        prompt tokens. When we detect that pathology, we render the rationale
        snippet only.
        """
        if isinstance(decision, dict):
            title = (decision.get("title") or "").strip()
            rationale = (decision.get("rationale") or "").strip()
            outcome = decision.get("outcome")
        else:
            title = (getattr(decision, "title", None) or "").strip()
            rationale = (getattr(decision, "rationale", None) or "").strip()
            outcome = getattr(decision, "outcome", None)

        # Detect title-is-prefix-of-rationale redundancy.
        title_redundant = bool(
            title and rationale and rationale.lower().startswith(title.lower()[: min(len(title), 60)])
        )

        if rationale and (title_redundant or not title):
            body = rationale[:200].strip()
        elif title and not rationale:
            body = title[:200].strip()
        else:
            body = f"{title[:80].strip()}: {rationale[:160].strip()}"

        outcome_tag = f" [{outcome}]" if outcome and outcome != "accepted" else ""
        return f"-{outcome_tag} {body}"

    def _build_cognitive_section(self, classification: dict, snapshot: dict) -> str:
        """Build the cognitive structure section from CognitiveComposition.

        Returns "" when:
        - cognitive_composition is not in classification
        - composition has no prompt_sections (empty / fallback)
        - fusion_mode is False (multi-phase mode — handled by executor, not here)
        """
        composition = classification.get("cognitive_composition")
        if not composition:
            return ""

        # Only inject in fusion mode (depth 1-2). Depth 3-4 is handled by the executor.
        if not composition.fusion_mode:
            return ""

        if not composition.prompt_sections:
            return ""

        # Load framework prompts from snapshot cache or empty dict
        framework_prompts: dict[str, str] = snapshot.get("_framework_prompts", {})

        from core.engine.cognition.fusion import PromptFusion

        return PromptFusion().fuse(composition, framework_prompts)

    def _build_intel_context_safe(self, snapshot: dict, max_tokens: int = 6000) -> str:
        """Build intel context, handling import errors gracefully."""
        try:
            from core.engine.orchestrator.executor import _build_intel_context

            return _build_intel_context(snapshot, max_tokens=max_tokens)
        except Exception:
            return ""

    def compose_for_evolution(
        self,
        system_prompt: str,
        task_prompt: str,
        tools: list[str] | None = None,
        model: str | None = None,
    ) -> ComposedShell:
        """Build a shell for evolution engine agents with custom prompts."""
        return ComposedShell(
            system_prompt=system_prompt,
            user_prompt=task_prompt,
            tools=tools,
            model=model,
        )
