"""Tests for engine/learning/effectiveness.py

Covers: empty window, single observation, low-N smoothing, high-N stability, mixed labels.
Uses db_pool to insert real outcome_observation rows and verify compute output.
"""

from datetime import datetime, timedelta, timezone

import pytest


@pytest.fixture
async def clean_eff(db_pool):
    """Clean up test observations and effectiveness scores after each test."""
    yield db_pool
    async with db_pool.connection() as db:
        await db.query(
            "DELETE outcome_observation WHERE product = <record>$pid",
            {"pid": "product:platform"},
        )
        await db.query(
            "DELETE effectiveness_score WHERE product = <record>$pid",
            {"pid": "product:platform"},
        )


async def _insert_closed_observation(
    db_pool,
    *,
    emission_id: str,
    pillar: str,
    discipline: str,
    outcome_label: str,
    outcome_at: datetime | None = None,
) -> None:
    """Insert an observation with a closed outcome_label and outcome_at set."""

    now = datetime.now(timezone.utc)
    _outcome_at = outcome_at or now

    async with db_pool.connection() as db:
        await db.query(
            """CREATE outcome_observation CONTENT {
                product: <record>$pid,
                emission_id: <string>$eid,
                emission_kind: 'recommendation',
                emission_topic: $topic,
                pillar: <string>$pillar,
                discipline: <string>$discipline,
                emitted_at: time::now(),
                outcome_label: <string>$label,
                outcome_at: <datetime>$oat,
                action_evidence: NONE,
                window_expires_at: <datetime>$expires
            }""",
            {
                "pid": "product:platform",
                "eid": emission_id,
                "topic": f"recommendation:{pillar}.{discipline}",
                "pillar": pillar,
                "discipline": discipline,
                "label": outcome_label,
                "oat": _outcome_at.isoformat(),
                "expires": (now + timedelta(days=14)).isoformat(),
            },
        )


@pytest.mark.asyncio
async def test_empty_window_returns_no_scores(db_pool, clean_eff):
    """No observations → empty list returned."""
    from core.engine.learning.effectiveness import compute_effectiveness_scores

    scores = await compute_effectiveness_scores("product:platform")
    assert scores == []


@pytest.mark.asyncio
async def test_single_acted_on_observation(db_pool, clean_eff):
    """Single acted_on observation → score with raw_rate=1.0, smoothed < 1.0."""
    from core.engine.learning.effectiveness import compute_effectiveness_scores

    await _insert_closed_observation(
        db_pool,
        emission_id="eff-single-001",
        pillar="experience",
        discipline="ux",
        outcome_label="acted_on",
    )

    scores = await compute_effectiveness_scores("product:platform")
    assert len(scores) == 1
    s = scores[0]
    assert s.pillar == "experience"
    assert s.discipline == "ux"
    assert s.n_emissions == 1
    assert s.n_acted_on == 1
    assert s.raw_rate == 1.0
    # Laplace: (1+1)/(1+3) = 0.5
    assert abs(s.smoothed_rate - 0.5) < 1e-9
    # Confidence: 1/20 = 0.05
    assert abs(s.confidence - 0.05) < 1e-9


@pytest.mark.asyncio
async def test_single_ignored_observation(db_pool, clean_eff):
    """Single ignored observation → raw_rate=0.0, smoothed=0.25."""
    from core.engine.learning.effectiveness import compute_effectiveness_scores

    await _insert_closed_observation(
        db_pool,
        emission_id="eff-ignored-001",
        pillar="reliability",
        discipline="observability",
        outcome_label="ignored",
    )

    scores = await compute_effectiveness_scores("product:platform")
    assert len(scores) == 1
    s = scores[0]
    assert s.raw_rate == 0.0
    # Laplace: (0+1)/(1+3) = 0.25
    assert abs(s.smoothed_rate - 0.25) < 1e-9


@pytest.mark.asyncio
async def test_low_n_smoothing(db_pool, clean_eff):
    """With 2 acted_on, 1 ignored: smoothing pulls raw rate (0.67) toward neutral."""
    from core.engine.learning.effectiveness import compute_effectiveness_scores

    for i in range(2):
        await _insert_closed_observation(
            db_pool,
            emission_id=f"eff-low-acted-{i:03d}",
            pillar="security",
            discipline="security",
            outcome_label="acted_on",
        )
    await _insert_closed_observation(
        db_pool,
        emission_id="eff-low-ignored-001",
        pillar="security",
        discipline="security",
        outcome_label="ignored",
    )

    scores = await compute_effectiveness_scores("product:platform")
    # Find the security score
    s = next(x for x in scores if x.pillar == "security")
    assert s.n_emissions == 3
    assert abs(s.raw_rate - 2 / 3) < 1e-9
    # Laplace: (2+1)/(3+3) = 0.5
    assert abs(s.smoothed_rate - 0.5) < 1e-9
    # Confidence: 3/20 = 0.15
    assert abs(s.confidence - 0.15) < 1e-9


@pytest.mark.asyncio
async def test_high_n_stability(db_pool, clean_eff):
    """With 20 observations, confidence saturates at 1.0."""
    from core.engine.learning.effectiveness import compute_effectiveness_scores

    for i in range(15):
        await _insert_closed_observation(
            db_pool,
            emission_id=f"eff-high-acted-{i:03d}",
            pillar="architecture",
            discipline="architecture",
            outcome_label="acted_on",
        )
    for i in range(5):
        await _insert_closed_observation(
            db_pool,
            emission_id=f"eff-high-ignored-{i:03d}",
            pillar="architecture",
            discipline="architecture",
            outcome_label="ignored",
        )

    scores = await compute_effectiveness_scores("product:platform")
    s = next(x for x in scores if x.pillar == "architecture")
    assert s.n_emissions == 20
    assert s.confidence == 1.0
    assert abs(s.raw_rate - 0.75) < 1e-9
    # Laplace: (15+1)/(20+3) = 16/23
    assert abs(s.smoothed_rate - 16 / 23) < 1e-6


@pytest.mark.asyncio
async def test_mixed_labels_answered_counts_as_positive(db_pool, clean_eff):
    """'answered' outcome_label counts as positive (same as acted_on)."""
    from core.engine.learning.effectiveness import compute_effectiveness_scores

    await _insert_closed_observation(
        db_pool,
        emission_id="eff-answered-001",
        pillar="api_design",
        discipline="api_design",
        outcome_label="answered",
    )
    await _insert_closed_observation(
        db_pool,
        emission_id="eff-answered-ignored-001",
        pillar="api_design",
        discipline="api_design",
        outcome_label="ignored",
    )

    scores = await compute_effectiveness_scores("product:platform")
    s = next(x for x in scores if x.pillar == "api_design")
    # total=2, positive=1 (answered), raw=0.5, smoothed=(1+1)/(2+3)=0.4
    assert s.n_emissions == 2
    assert abs(s.raw_rate - 0.5) < 1e-9
    assert abs(s.smoothed_rate - 0.4) < 1e-9


@pytest.mark.asyncio
async def test_open_observations_excluded(db_pool, clean_eff):
    """outcome_label='open' is excluded from score computation."""
    from core.engine.learning.effectiveness import compute_effectiveness_scores

    now = datetime.now(timezone.utc)
    # Insert an open observation (not closed yet)
    async with db_pool.connection() as db:
        await db.query(
            """CREATE outcome_observation CONTENT {
                product: <record>$pid,
                emission_id: 'eff-open-001',
                emission_kind: 'recommendation',
                emission_topic: 'recommendation:experience.ux',
                pillar: 'experience',
                discipline: 'ux',
                emitted_at: time::now(),
                outcome_label: 'open',
                outcome_at: NONE,
                action_evidence: NONE,
                window_expires_at: <datetime>$expires
            }""",
            {
                "pid": "product:platform",
                "expires": (now + timedelta(days=14)).isoformat(),
            },
        )

    scores = await compute_effectiveness_scores("product:platform")
    # open rows have outcome_at=NONE so the WHERE outcome_at > cutoff filter excludes them
    assert len(scores) == 0


@pytest.mark.asyncio
async def test_outside_30day_window_excluded(db_pool, clean_eff):
    """Observations older than 30 days are excluded from the rolling window."""
    from core.engine.learning.effectiveness import compute_effectiveness_scores

    now = datetime.now(timezone.utc)
    old_date = now - timedelta(days=35)

    await _insert_closed_observation(
        db_pool,
        emission_id="eff-old-001",
        pillar="ux",
        discipline="ux",
        outcome_label="acted_on",
        outcome_at=old_date,
    )

    scores = await compute_effectiveness_scores("product:platform")
    assert len(scores) == 0


@pytest.mark.asyncio
async def test_persist_scores_writes_rows(db_pool, clean_eff):
    """persist_scores writes EffectivenessScore objects to effectiveness_score table."""
    from core.engine.core.db import parse_rows
    from core.engine.learning.effectiveness import EffectivenessScore, persist_scores

    now = datetime.now(timezone.utc)
    scores = [
        EffectivenessScore(
            product_id="product:platform",
            pillar="experience",
            discipline="ux",
            n_emissions=5,
            n_acted_on=4,
            n_ignored=1,
            n_rejected=0,
            raw_rate=0.8,
            smoothed_rate=0.625,
            confidence=0.25,
            computed_at=now,
        )
    ]
    await persist_scores(scores)

    async with db_pool.connection() as db:
        rows = parse_rows(
            await db.query(
                "SELECT * FROM effectiveness_score WHERE product = <record>$pid AND pillar = 'experience'",
                {"pid": "product:platform"},
            )
        )
    assert len(rows) >= 1
    row = rows[0]
    assert row["pillar"] == "experience"
    assert row["discipline"] == "ux"
    assert row["n_emissions"] == 5
    assert abs(row["raw_rate"] - 0.8) < 1e-6


@pytest.mark.asyncio
async def test_multiple_pillar_discipline_keys(db_pool, clean_eff):
    """Scores are computed per unique (pillar, discipline) combination."""
    from core.engine.learning.effectiveness import compute_effectiveness_scores

    for pillar, disc in [("experience", "ux"), ("reliability", "observability"), ("security", "security")]:
        await _insert_closed_observation(
            db_pool,
            emission_id=f"eff-multi-{pillar}-{disc}",
            pillar=pillar,
            discipline=disc,
            outcome_label="acted_on",
        )

    scores = await compute_effectiveness_scores("product:platform")
    pillars = {s.pillar for s in scores}
    assert "experience" in pillars
    assert "reliability" in pillars
    assert "security" in pillars
