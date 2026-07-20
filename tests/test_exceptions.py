# tests/test_exceptions.py
"""Tests for ACE exception hierarchy."""

from __future__ import annotations

from core.engine.core.exceptions import (
    ACEError,
    ClassificationError,
    ConfigurationError,
    DatabaseError,
    LLMError,
    OrchestrationError,
    ValidationError,
)
from core.engine.core.log_context import set_correlation_id


def test_ace_error_captures_correlation_id_from_context():
    set_correlation_id("ctx123")
    err = ACEError("something failed")
    assert err.correlation_id == "ctx123"


def test_ace_error_str_includes_correlation_id():
    set_correlation_id("abc")
    err = ACEError("disk full")
    assert "[abc] disk full" == str(err)


def test_ace_error_str_without_correlation_id():
    set_correlation_id("")
    err = ACEError("plain error")
    assert str(err) == "plain error"


def test_explicit_correlation_id_overrides_context():
    set_correlation_id("ctx-cid")
    err = ACEError("test", correlation_id="explicit-cid")
    assert err.correlation_id == "explicit-cid"


def test_llm_error_is_ace_error():
    err = LLMError("timeout")
    assert isinstance(err, ACEError)
    assert isinstance(err, LLMError)


def test_database_error_is_ace_error():
    err = DatabaseError("connection refused")
    assert isinstance(err, ACEError)


def test_orchestration_error_is_ace_error():
    err = OrchestrationError("dispatch failed")
    assert isinstance(err, ACEError)


def test_classification_error_is_orchestration_error():
    err = ClassificationError("no discipline found")
    assert isinstance(err, OrchestrationError)
    assert isinstance(err, ACEError)


def test_validation_error_is_ace_error():
    err = ValidationError("missing required field")
    assert isinstance(err, ACEError)


def test_configuration_error_is_ace_error():
    err = ConfigurationError("SURREAL_URL not set")
    assert isinstance(err, ACEError)


def test_catch_by_subtype_not_base():
    """Callers can target specific subtypes — LLMError vs DatabaseError."""
    set_correlation_id("")

    def risky_llm():
        raise LLMError("timeout")

    caught_llm = False
    caught_db = False
    try:
        risky_llm()
    except DatabaseError:
        caught_db = True
    except LLMError:
        caught_llm = True

    assert caught_llm
    assert not caught_db
