"""Tests for engine/review/config.py."""

from __future__ import annotations

from core.engine.review.config import GateConfig, ReviewConfig

# ---------------------------------------------------------------------------
# test_default_config
# ---------------------------------------------------------------------------


def test_default_config():
    """Default config has sane values."""
    config = ReviewConfig.default()

    assert config.disciplines is None
    assert config.exclude_paths == []
    assert config.post_review is True
    assert config.post_status is True
    assert isinstance(config.gate, GateConfig)
    assert config.gate.critical_threshold == 0
    assert config.gate.high_threshold == 3
    assert config.gate.min_discipline_score == 0.5


# ---------------------------------------------------------------------------
# test_parse_yaml
# ---------------------------------------------------------------------------


def test_parse_yaml():
    """Parses a valid .ace.yaml with review section."""
    yaml_content = """
review:
  disciplines:
    - security
    - testing
  exclude_paths:
    - "tests/**"
    - "docs/**"
  post_review: true
  post_status: false
  gate:
    critical_threshold: 1
    high_threshold: 5
    min_discipline_score: 0.7
"""
    config = ReviewConfig.from_yaml(yaml_content)

    assert config.disciplines == ["security", "testing"]
    assert config.exclude_paths == ["tests/**", "docs/**"]
    assert config.post_review is True
    assert config.post_status is False
    assert config.gate.critical_threshold == 1
    assert config.gate.high_threshold == 5
    assert config.gate.min_discipline_score == 0.7


def test_parse_yaml_empty():
    """Empty .ace.yaml yields defaults."""
    config = ReviewConfig.from_yaml("")
    assert config.gate.critical_threshold == 0
    assert config.gate.high_threshold == 3
    assert config.disciplines is None


def test_parse_yaml_no_review_key():
    """YAML without a review key yields defaults."""
    yaml_content = """
other_config:
  foo: bar
"""
    config = ReviewConfig.from_yaml(yaml_content)
    assert config.gate.critical_threshold == 0
    assert config.disciplines is None


# ---------------------------------------------------------------------------
# test_parse_invalid_yaml
# ---------------------------------------------------------------------------


def test_parse_invalid_yaml():
    """Invalid YAML falls back to defaults rather than raising."""
    invalid_yaml = "review:\n  disciplines: [unclosed"
    config = ReviewConfig.from_yaml(invalid_yaml)

    # Should silently fall back to defaults
    assert config.gate.critical_threshold == 0
    assert config.gate.high_threshold == 3
    assert config.disciplines is None
    assert config.post_review is True


def test_parse_yaml_invalid_field_values():
    """Unknown fields in review section fall back to defaults (Pydantic extra='ignore' not set, so error -> defaults)."""
    # extra fields not in model trigger a ValidationError which is caught
    yaml_content = """
review:
  unknown_field: something
"""
    # Pydantic v2 by default raises on extra fields; from_yaml catches all exceptions
    config = ReviewConfig.from_yaml(yaml_content)
    # Falls back to defaults
    assert config.gate.critical_threshold == 0


# ---------------------------------------------------------------------------
# test_gate_thresholds_override
# ---------------------------------------------------------------------------


def test_gate_thresholds_override():
    """Gate thresholds parsed correctly from YAML override defaults."""
    yaml_content = """
review:
  gate:
    critical_threshold: 2
    high_threshold: 10
"""
    config = ReviewConfig.from_yaml(yaml_content)

    assert config.gate.critical_threshold == 2
    assert config.gate.high_threshold == 10
    # min_discipline_score stays at default
    assert config.gate.min_discipline_score == 0.5


def test_gate_thresholds_partial_override():
    """Partial gate config merges with defaults."""
    yaml_content = """
review:
  gate:
    critical_threshold: 0
"""
    config = ReviewConfig.from_yaml(yaml_content)

    assert config.gate.critical_threshold == 0
    assert config.gate.high_threshold == 3  # still default
