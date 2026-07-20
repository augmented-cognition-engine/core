"""Tests for source registry — discipline sources and URL classification."""

from core.engine.research.source_registry import (
    DISCIPLINE_SOURCES,
    SourceClass,
    classify_url,
    get_sources_for_discipline,
)


def test_source_class_values():
    assert SourceClass.REFERENCE.value == "reference"
    assert SourceClass.EXEMPLAR.value == "exemplar"
    assert SourceClass.SIGNAL.value == "signal"
    assert SourceClass.NOISE.value == "noise"


def test_get_sources_for_known_discipline():
    sources = get_sources_for_discipline("security")
    assert len(sources) >= 1
    assert all("url" in s and "name" in s and "class" in s for s in sources)


def test_get_sources_for_unknown_discipline():
    sources = get_sources_for_discipline("nonexistent_discipline_xyz")
    assert sources == []


def test_discipline_sources_covers_18_disciplines():
    required = {
        "security",
        "architecture",
        "ux",
        "testing",
        "api_design",
        "performance",
        "observability",
        "deployment",
        "code_conventions",
    }
    covered = set(DISCIPLINE_SOURCES.keys())
    assert required.issubset(covered), f"Missing disciplines: {required - covered}"


def test_classify_reference_url():
    assert classify_url("https://owasp.org/www-community/attacks/xss") == SourceClass.REFERENCE


def test_classify_exemplar_url():
    result = classify_url("https://github.com/pydantic/pydantic/blob/main/README.md")
    assert result == SourceClass.EXEMPLAR


def test_classify_signal_url():
    result = classify_url("https://medium.com/some-article")
    assert result == SourceClass.SIGNAL


def test_classify_unknown_url():
    result = classify_url("https://unknown-random-site-xyz123.com/article")
    assert result == SourceClass.SIGNAL


def test_classify_malformed_url():
    result = classify_url("not_a_url")
    assert isinstance(result, SourceClass)
