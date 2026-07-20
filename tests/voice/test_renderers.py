def test_render_frame_basic():
    from core.engine.voice.renderers import render_frame
    from core.engine.voice.rules import find_forbidden_strings, has_we_voice

    out = render_frame(phase="poc", days_in_phase=45, days_to_demo=51)
    assert isinstance(out, str)
    assert "45" in out
    assert "51" in out
    assert "POC" in out or "poc" in out
    assert has_we_voice(out)
    assert find_forbidden_strings(out) == []


def test_render_frame_no_demo_target():
    from core.engine.voice.renderers import render_frame

    out = render_frame(phase="poc", days_in_phase=45, days_to_demo=None)
    assert "45" in out
    assert "demo" not in out.lower() or "no" in out.lower()  # graceful handling


# --- render_drift ---


def test_render_drift_all_clear():
    from core.engine.product.briefing_payload import TargetDriftAssessment
    from core.engine.voice.renderers import render_drift
    from core.engine.voice.rules import has_we_voice

    out = render_drift(TargetDriftAssessment(n_total=15, n_blocked=0, blocking_pillars=[]))
    assert "15" in out
    assert "block" not in out.lower() or "0" in out
    assert has_we_voice(out)


def test_render_drift_blocked():
    from core.engine.product.briefing_payload import TargetDriftAssessment
    from core.engine.voice.renderers import render_drift
    from core.engine.voice.rules import has_we_voice

    drift = TargetDriftAssessment(n_total=15, n_blocked=11, blocking_pillars=["experience", "state"])
    out = render_drift(drift)
    assert "11" in out
    assert "15" in out
    assert "experience" in out
    assert "state" in out
    assert has_we_voice(out)


# --- render_recommendation ---


def test_render_recommendation_none_pillar_does_not_crash():
    """A recommendation with an explicit None pillar/discipline must degrade, not crash the whole
    briefing render (pillar.lower() would raise on None — the .get(k, default) trap)."""
    from core.engine.voice.renderers import render_recommendation

    rec = {"pillar": None, "discipline": None, "gap": 0.4, "blocking_patterns": []}
    out = render_recommendation(rec)
    assert isinstance(out, str)  # rendered without raising


def test_render_recommendation_basic():
    from core.engine.voice.renderers import render_recommendation
    from core.engine.voice.rules import has_we_voice

    rec = {
        "pillar": "experience",
        "discipline": "accessibility",
        "score": 0.20,
        "floor": 0.70,
        "gap": 0.50,
        "ambition_relevance": 1.0,
        "rank": 0.65,
        "blocking_patterns": ["living_canvas", "proactive_line"],
        "rationale": "experience below POC floor",
    }
    out = render_recommendation(rec)
    assert "accessibility" in out.lower()  # case-insensitive — first-time framing capitalizes the lead
    assert has_we_voice(out)
    # Carries quantitative anchor:
    assert "0.5" in out or "0.50" in out


def test_render_recommendation_no_blocking_patterns():
    from core.engine.voice.renderers import render_recommendation
    from core.engine.voice.rules import has_we_voice

    rec = {
        "pillar": "evolution",
        "discipline": "testing",
        "score": 0.0,
        "floor": 0.55,
        "gap": 0.55,
        "ambition_relevance": 0.067,
        "rank": 0.53,
        "blocking_patterns": [],
        "rationale": "evolution below POC floor",
    }
    out = render_recommendation(rec)
    assert "testing" in out.lower()  # case-insensitive — first-time framing capitalizes the lead
    assert has_we_voice(out)
    assert "block" not in out.lower() or "no" in out.lower() or "doesn't" in out.lower()


# --- render_uncertainty ---


def test_render_uncertainty_basic():
    from core.engine.voice.renderers import render_uncertainty
    from core.engine.voice.rules import has_we_voice

    q = {
        "id": "uq:1",
        "scope": "ambition",
        "question": "Should time_travel_by_default still be in scope for the June 19 demo?",
        "fallback": "default_safe",
    }
    out = render_uncertainty(q)
    assert "time_travel_by_default" in out or "scope" in out.lower()
    assert has_we_voice(out)


# --- render_state_change ---


def test_render_state_change_capability_added():
    from core.engine.voice.renderers import render_state_change
    from core.engine.voice.rules import has_we_voice

    sc = {
        "kind": "canvas.capability.added",
        "description": "auth capability registered",
        "target_ref": "capability:auth",
    }
    out = render_state_change(sc)
    assert "auth" in out.lower() or "capability" in out.lower()
    assert has_we_voice(out)


def test_render_state_change_decision_captured():
    from core.engine.voice.renderers import render_state_change
    from core.engine.voice.rules import has_we_voice

    sc = {
        "kind": "canvas.decision.captured",
        "description": "decided to drop time_travel_by_default",
        "target_ref": "decision:42",
    }
    out = render_state_change(sc)
    assert has_we_voice(out)


# --- v2 RenderContext-aware tests ---


def test_render_recommendation_first_time_unchanged_v1_path():
    """ctx=None => v1 behavior preserved."""
    from core.engine.voice.renderers import render_recommendation

    rec = {"pillar": "experience", "discipline": "ux", "gap": 0.3, "blocking_patterns": []}
    out = render_recommendation(rec)  # no ctx
    assert "ux" in out.lower()


def test_render_recommendation_stale_thread_uses_sat_on_framing():
    from datetime import datetime, timedelta, timezone
    from unittest.mock import MagicMock

    from core.engine.voice.render_context import RenderContext
    from core.engine.voice.renderers import render_recommendation

    thread = MagicMock(
        status="stale",
        mention_count=5,
        raised_at=datetime.now(timezone.utc) - timedelta(days=21),
        last_state_changed_at=datetime.now(timezone.utc) - timedelta(days=14),
        current_payload_hash="h1",
    )
    ctx = RenderContext(thread=thread, fresh_payload_hash="h1")
    rec = {"pillar": "experience", "discipline": "ux", "gap": 0.3, "blocking_patterns": []}
    out = render_recommendation(rec, ctx)
    assert "sat on" in out.lower() or "weeks" in out.lower()


def test_render_recommendation_payload_changed_uses_moved_framing():
    from datetime import datetime, timedelta, timezone
    from unittest.mock import MagicMock

    from core.engine.voice.render_context import RenderContext
    from core.engine.voice.renderers import render_recommendation

    thread = MagicMock(
        status="open",
        mention_count=2,
        raised_at=datetime.now(timezone.utc) - timedelta(days=7),
        last_state_changed_at=datetime.now(timezone.utc) - timedelta(days=2),
        current_payload_hash="old_hash",
    )
    ctx = RenderContext(thread=thread, fresh_payload_hash="new_hash")
    rec = {"pillar": "experience", "discipline": "ux", "gap": 0.3, "blocking_patterns": []}
    out = render_recommendation(rec, ctx)
    assert "moved" in out.lower() or "now" in out.lower()
