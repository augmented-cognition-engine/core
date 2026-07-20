"""Tests for retry with backoff and model fallback."""

from core.engine.runtime.retry import RetryPolicy


def test_default_policy():
    policy = RetryPolicy()
    assert policy.max_retries == 3
    assert policy.base_delay_ms == 500


def test_should_retry_first_attempt():
    policy = RetryPolicy()
    assert policy.should_retry(attempt=1, error_code=500)


def test_should_not_retry_after_max():
    policy = RetryPolicy(max_retries=3)
    assert not policy.should_retry(attempt=4, error_code=500)


def test_backoff_delay():
    policy = RetryPolicy(base_delay_ms=500)
    d1 = policy.get_delay_ms(attempt=1)
    d2 = policy.get_delay_ms(attempt=2)
    assert d2 > d1  # exponential backoff


def test_should_fallback_on_529():
    policy = RetryPolicy(max_529_before_fallback=3)
    assert not policy.should_fallback(consecutive_529=2)
    assert policy.should_fallback(consecutive_529=3)


def test_no_retry_on_400():
    policy = RetryPolicy()
    assert not policy.should_retry(attempt=1, error_code=400)


def test_retry_on_429():
    policy = RetryPolicy()
    assert policy.should_retry(attempt=1, error_code=429)
