"""Calibration consumes the cross-model grader_score to un-starve its curves.

When no human feedback exists, the cross-model grade (keystone #1) becomes the calibration "actual"
outcome — so curves learn from automated grades instead of waiting for a human verdict. Human feedback
still wins when present. See docs/superpowers/specs/2026-06-23-calibration-consumer-cross-model-grades-design.md.
"""

from __future__ import annotations

from core.engine.intelligence.calibration import bucket_tasks


def test_bucket_uses_grader_score_when_no_human_feedback():
    tasks = [{"discipline": "security", "self_assessment": 0.7, "feedback_human": None, "grader_score": 0.9}]
    buckets = bucket_tasks(tasks)
    assert buckets["security"]["0.7"] == [{"predicted": 0.7, "actual": 0.9, "source": "grader"}]


def test_human_feedback_takes_precedence_over_grader():
    tasks = [{"discipline": "security", "self_assessment": 0.8, "feedback_human": "accepted", "grader_score": 0.2}]
    sample = bucket_tasks(tasks)["security"]["0.8"][0]
    assert sample["actual"] == 1.0, "human feedback (accepted=1.0) must win over the grader score"
    assert sample["source"] == "human"


def test_bucket_skips_non_coercible_self_assessment():
    # self_assessment was redefined float->object in v034; an object value must be skipped, never raise.
    tasks = [{"discipline": "security", "self_assessment": {"nested": 1}, "feedback_human": None, "grader_score": 0.9}]
    assert bucket_tasks(tasks) == {}


def test_bucket_skips_when_neither_human_nor_grader():
    tasks = [{"discipline": "security", "self_assessment": 0.7, "feedback_human": None, "grader_score": None}]
    assert bucket_tasks(tasks) == {}


def test_grader_score_bool_is_not_treated_as_number():
    # bool is an int subclass; a stray True must not silently become actual=1.0
    tasks = [{"discipline": "security", "self_assessment": 0.7, "feedback_human": None, "grader_score": True}]
    assert bucket_tasks(tasks) == {}


def test_grader_only_and_human_mix_buckets_together():
    tasks = [
        {"discipline": "x", "self_assessment": 0.6, "feedback_human": "rejected"},  # human → 0.0
        {"discipline": "x", "self_assessment": 0.62, "feedback_human": None, "grader_score": 0.8},  # grader → 0.8
    ]
    samples = bucket_tasks(tasks)["x"]["0.6"]
    assert len(samples) == 2
    assert {s["source"] for s in samples} == {"human", "grader"}
