"""Item H — gap_analyzer's gap-emit must be phase+type+scale aware, not a flat 0.4.

A prototype (poc) shouldn't be flagged for security/ops at GA-level bars ("security gap while
prototyping? meh"). The floor that decides whether a dimension's score is a gap comes from
phase_floors.effective_floor, mapped via the dimension's pillar. Fail-safe: missing config falls back
to the prior flat 0.4 — never silence a gap. See docs/superpowers/specs/2026-06-22-phase-aware-gap-emit-design.md.
"""

from __future__ import annotations


def test_emit_floor_phase_relative():
    """Security's bar rises with maturity; in a poc the bars favor what matters (experience/logic)
    over security/ops."""
    from core.engine.sentinel.engines.gap_analyzer import _emit_floor

    sec_poc = _emit_floor("security", "poc", "ai_native", "")
    sec_ga = _emit_floor("security", "ga", "ai_native", "")
    assert sec_ga > sec_poc, "security bar must be stricter at GA than at poc"

    exp_poc = _emit_floor("ux", "poc", "ai_native", "")  # ux -> EXPERIENCE
    ops_poc = _emit_floor("observability", "poc", "ai_native", "")  # -> OPERATIONS
    assert exp_poc > ops_poc, "at poc the experience bar should exceed the operations bar (relevance)"


def test_emit_floor_unmapped_dimension_falls_back():
    """A dimension with no pillar mapping falls back to the prior flat 0.4 (no silent zero)."""
    from core.engine.sentinel.engines.gap_analyzer import _emit_floor

    assert _emit_floor("totally_unknown_dim", "poc", "ai_native", "") == 0.4


def test_emit_floor_unknown_phase_falls_back_not_zero():
    """An unknown phase makes effective_floor return 0.0 — which would SILENCE all gaps. The fallback
    must coerce that to the legacy 0.4 (don't lower the bar on missing config), never 0.0."""
    from core.engine.sentinel.engines.gap_analyzer import _emit_floor

    floor = _emit_floor("security", "not_a_real_phase", "ai_native", "")
    assert floor == 0.4, "unknown phase must fall back to 0.4, not silence the gap with 0.0"


def test_emit_floor_clamped_to_min_never_approaches_silence():
    """Negative type/scale modifiers can drive a KNOWN composed floor toward 0 (review C1:
    security@poc + ecommerce + atomic composes to 0.05). It must clamp UP to _MIN_EMIT_FLOOR (0.2) so
    a near-absent capability is never silenced — the (0.0, 0.2) band must not escape the guard."""
    from core.engine.sentinel.engines.gap_analyzer import _MIN_EMIT_FLOOR, _emit_floor

    floor = _emit_floor("security", "poc", "ecommerce", "atomic")  # composes ~0.05
    assert floor == _MIN_EMIT_FLOOR == 0.2, f"sub-min floor must clamp to {_MIN_EMIT_FLOOR}, got {floor}"


def test_emit_floor_type_and_scale_modifiers_apply():
    """Product-type and scale modifiers compose into the floor."""
    from core.engine.sentinel.engines.gap_analyzer import _emit_floor

    # ai_native @poc adds +0.15 to EXPERIENCE over the base 0.55
    exp_ai = _emit_floor("ux", "poc", "ai_native", "")
    exp_plain = _emit_floor("ux", "poc", "", "")
    assert exp_ai > exp_plain, "ai_native poc must raise the experience bar via the type modifier"

    # platform scale adds +0.1 to TRUST
    trust_platform = _emit_floor("security", "poc", "ai_native", "platform")
    trust_noscale = _emit_floor("security", "poc", "ai_native", "")
    assert trust_platform > trust_noscale, "platform scale must raise the trust bar"


import pytest  # noqa: E402


@pytest.mark.asyncio
async def test_load_floor_context_defaults_to_legacy_when_no_ambition():
    """Missing ambition → phase '' (review IMPORTANT-3: do NOT default to lenient 'poc' and
    under-surface a possibly-further-along product). '' makes _emit_floor fall back to the legacy 0.4,
    so an unset-ambition product keeps the conservative flat behavior."""
    from core.engine.sentinel.engines import gap_analyzer

    class _DB:
        async def query(self, q, params=None):
            return []  # no ambition, no product rows

    phase, ptype, scale = await gap_analyzer._load_floor_context(_DB(), "product:platform")
    assert phase == "", "phase must be '' when ambition is absent (→ legacy 0.4 via _emit_floor)"
    # and that '' resolves to the conservative legacy bar, not silence:
    assert gap_analyzer._emit_floor("security", phase, ptype, scale) == 0.4


@pytest.mark.asyncio
async def test_load_floor_context_reads_product_scale():
    """Scale must read the real schema field `product_scale` (review C2: `scale` doesn't exist →
    modifiers were dead). A populated product row must propagate phase + type + scale."""
    from core.engine.sentinel.engines import gap_analyzer

    class _DB:
        async def query(self, q, params=None):
            u = q.upper()
            if "FROM AMBITION" in u:
                return [{"phase_json": {"current": "poc"}}]
            if "FROM PRODUCT" in u:
                return [{"product_type": "ai_native", "product_scale": "platform"}]
            return []

    phase, ptype, scale = await gap_analyzer._load_floor_context(_DB(), "product:platform")
    assert (phase, ptype, scale) == ("poc", "ai_native", "platform")
