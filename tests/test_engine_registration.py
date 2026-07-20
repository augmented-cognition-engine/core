# tests/test_engine_registration.py
"""Verify all Phase 3b engines register with the sentinel scheduler."""


def _fires_on(cron: str) -> set[str]:
    """The days a cron ACTUALLY fires, in APScheduler's reading of it.

    Asserting the cron STRING is the weak form and it is how this bug lived: the old
    assertion here was `== "0 5 * * 0"  # Sunday 5 AM`, which passed for months while the
    engine ran on MONDAY. APScheduler reads day-of-week 0=mon..6=sun, not the standard
    crontab 0=sun, and does not translate. Assert the behaviour, not the literal.
    """
    from datetime import datetime
    from zoneinfo import ZoneInfo

    from apscheduler.triggers.cron import CronTrigger

    tz = ZoneInfo("UTC")
    trigger = CronTrigger.from_crontab(cron, timezone=tz)
    days, prev = set(), datetime(2026, 7, 12, tzinfo=tz)  # a Sunday
    for _ in range(7):
        nxt = trigger.get_next_fire_time(None, prev)
        days.add(nxt.strftime("%A"))
        prev = nxt.replace(hour=23, minute=59)
    return days


def test_all_phase3b_engines_registered():
    """All 4 Phase 3b engines should appear in the engine registry."""
    import core.engine.sentinel.engines.failure_analysis  # noqa: F401
    import core.engine.sentinel.engines.gap_researcher  # noqa: F401
    import core.engine.sentinel.engines.knowledge_verifier  # noqa: F401
    import core.engine.sentinel.engines.specialty_deepener  # noqa: F401
    from core.engine.sentinel.registry import engine_registry

    engine_names = set(engine_registry.keys())

    assert "failure_analysis" in engine_names
    assert "gap_researcher" in engine_names
    assert "knowledge_verifier" in engine_names
    assert "specialty_deepener" in engine_names


def test_failure_analysis_cron():
    import core.engine.sentinel.engines.failure_analysis  # noqa: F401
    from core.engine.sentinel.registry import engine_registry

    assert engine_registry["failure_analysis"]["cron"] == "0 3 * * *"


def test_gap_researcher_cron():
    import core.engine.sentinel.engines.gap_researcher  # noqa: F401
    from core.engine.sentinel.registry import engine_registry

    assert engine_registry["gap_researcher"]["cron"] == "30 3 * * *"


def test_knowledge_verifier_cron():
    import core.engine.sentinel.engines.knowledge_verifier  # noqa: F401
    from core.engine.sentinel.registry import engine_registry

    assert engine_registry["knowledge_verifier"]["cron"] == "0 4 * * *"


def test_specialty_deepener_cron():
    import core.engine.sentinel.engines.specialty_deepener  # noqa: F401
    from core.engine.sentinel.registry import engine_registry

    assert _fires_on(engine_registry["specialty_deepener"]["cron"]) == {"Monday", "Thursday"}
