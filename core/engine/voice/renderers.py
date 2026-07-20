"""Voice renderers — pure structured-input → partner-voice prose functions.

Each renderer is voice-rule-aware. None call DB or LLM (in v1).
v2: all renderers gain optional ctx: RenderContext = None for thread-aware branching.
"""

from __future__ import annotations

from datetime import datetime, timezone

from core.engine.voice.rules import VoiceRenderError, find_forbidden_strings

_LEDE_SENTENCE_MAX = 250
_BULLET_MAX = 200

# Discipline names that .title() butchers — acronyms and initialisms preserve their canonical case.
_DISCIPLINE_DISPLAY: dict[str, str] = {
    "ux": "UX",
    "ui": "UI",
    "aix": "AIX",
    "api": "API",
    "api_design": "API design",
    "ai": "AI",
    "qa": "QA",
    "ops": "Ops",
}


def _display_discipline(discipline: str) -> str:
    """Render a discipline name for human-readable prose. Preserves acronym case."""
    return _DISCIPLINE_DISPLAY.get(discipline.lower(), discipline.replace("_", " ").title())


def render_frame(phase: str, days_in_phase: int, days_to_demo: int | None) -> str:
    """Frame the briefing — phase, days in phase, days to demo."""
    phase_label = phase.upper() if len(phase) <= 4 else phase
    if days_to_demo is None:
        out = f"We're {days_in_phase} days into {phase_label} — no demo target set yet."
    else:
        out = f"We're {days_in_phase} days into {phase_label}; demo's in {days_to_demo}."
    return _validate(out, _LEDE_SENTENCE_MAX, "render_frame")


def render_drift(drift, ctx=None) -> str:
    """Partner-voice version of target-drift assessment.

    Input: TargetDriftAssessment dataclass (n_total, n_blocked, blocking_pillars).
    ctx: RenderContext | None — unused in v2.0; reserved for thread-aware branching in v2.1.
    Output: 1 sentence ≤ 250 chars in partner voice.
    """
    if drift.n_blocked == 0:
        out = f"We've got {drift.n_total} demo patterns clearing the current phase floor — no drift to flag this week."
    else:
        pillars = ", ".join(drift.blocking_pillars) if drift.blocking_pillars else "no specific pillar"
        out = f"We've got {drift.n_blocked} of {drift.n_total} demo patterns still blocked — the gaps are in {pillars}."
    return _validate(out, _LEDE_SENTENCE_MAX, "render_drift")


def render_recommendation(rec: dict, ctx=None) -> str | None:
    """Partner-voice rendering of a single ranked recommendation.

    Input: dict shaped like RankedRecommendation (pillar, discipline, score, floor,
    gap, blocking_patterns, etc.).
    ctx: RenderContext | None — when thread is present, uses thread-aware framing.
    Output: 1 sentence ≤ 200 chars (bullet body), or None when salience policy suppresses.
    """
    # `or ""` not `.get(k, "")` — a recommendation can carry an explicit pillar/discipline of None
    # (the default only applies to ABSENT keys), and `pillar.lower()` below would crash the whole
    # briefing render on that None. Coerce to "" so a malformed rec degrades, never crashes.
    pillar = rec.get("pillar") or ""
    discipline = rec.get("discipline") or ""
    gap = float(rec.get("gap") or 0.0)
    blocking = rec.get("blocking_patterns") or []

    # Salience: skip-when-clear policy
    if ctx is not None and ctx.salience_policy is not None and ctx.thread is not None:
        days_resolved = (
            (datetime.now(timezone.utc) - ctx.thread.last_state_changed_at).days
            if ctx.thread.status == "resolved"
            else 0
        )
        if days_resolved >= ctx.salience_policy.skip_when_above_floor_for_days:
            return None

    # Thread-aware branches
    if ctx is None or ctx.thread is None or ctx.thread.mention_count == 0:
        # First-time framing — capitalize the discipline since it leads the bullet.
        display = _display_discipline(discipline)
        if blocking:
            n = len(blocking)
            pat_phrase = f"blocks {n} demo pattern{'s' if n != 1 else ''}"
            out = (
                f"{display} ({pillar}) — gap of {gap:.2f} below floor; we should put this first since it {pat_phrase}."
            )
        else:
            out = (
                f"{display} ({pillar}) — gap of {gap:.2f} below floor; "
                f"doesn't block patterns directly, but blocks our ramp out of {pillar.lower()}."
            )
        return _validate(out, _BULLET_MAX, "render_recommendation")

    thread = ctx.thread
    payload_changed = ctx.fresh_payload_hash is not None and thread.current_payload_hash != ctx.fresh_payload_hash
    weeks = (datetime.now(timezone.utc) - thread.raised_at).days // 7

    if thread.status == "stale":
        return _validate(
            f"We've sat on {discipline} for {weeks} weeks — should we drop it from this week, or commit?",
            _BULLET_MAX,
            "render_recommendation",
        )
    if not payload_changed and thread.mention_count >= 3:
        return _validate(
            f"{_display_discipline(discipline)} is still where we left it — gap of {gap:.2f}, hasn't moved.",
            _BULLET_MAX,
            "render_recommendation",
        )
    if payload_changed:
        return _validate(
            f"{_display_discipline(discipline)} moved this week — gap is now {gap:.2f}.",
            _BULLET_MAX,
            "render_recommendation",
        )
    return _validate(
        f"We're still on {discipline} — gap of {gap:.2f} below floor.",
        _BULLET_MAX,
        "render_recommendation",
    )


def render_uncertainty(q: dict, ctx=None) -> str:
    """Partner-voice rendering of an open uncertainty query.

    Input: dict with at least 'question' and optionally 'scope' / 'fallback'.
    ctx: RenderContext | None — unused in v2.0; reserved for thread-aware branching in v2.1.
    Output: 1 sentence ≤ 250 chars.
    """
    question = q.get("question", "").strip()
    if question.endswith("?"):
        question = question[:-1]
    out = f"We're not yet sure — {question} — your call when you have a moment."
    return _validate(out, _LEDE_SENTENCE_MAX, "render_uncertainty")


def render_state_change(sc: dict, ctx=None) -> str:
    """Partner-voice rendering of a recent canvas state change.

    Input: dict with 'kind', 'description', optional 'target_ref'.
    ctx: RenderContext | None — unused in v2.0; reserved for thread-aware branching in v2.1.
    Output: 1 sentence ≤ 200 chars.
    """
    kind = sc.get("kind", "").lower()
    desc = sc.get("description", "").strip()
    if "capability.added" in kind:
        out = f"We've added a capability — {desc or 'new entry on the canvas'}."
    elif "decision.captured" in kind:
        out = f"We captured a decision — {desc or 'one more thing on the record'}."
    elif "sentinel.fired" in kind:
        out = f"Our overnight sentinel surfaced something — {desc or 'worth a glance'}."
    elif "handoff" in kind:
        verb = "started" if "started" in kind else "completed"
        out = f"Hand-off {verb} — {desc or 'we kept the thread'}."
    else:
        out = f"Our canvas state shifted — {desc or 'see logs for detail'}."
    return _validate(out, _BULLET_MAX, "render_state_change")


def _validate(text: str, max_len: int, source: str) -> str:
    if len(text) > max_len:
        raise VoiceRenderError(f"{source}: rendered text {len(text)} chars exceeds cap {max_len}: {text[:80]}...")
    if find_forbidden_strings(text):
        raise VoiceRenderError(f"{source}: forbidden strings in output: {text}")
    return text
