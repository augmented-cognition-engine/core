# tests/test_clearance_security.py
"""Security tests for clearance.py — SQL injection prevention."""


def test_clearance_rejects_sql_injection_in_domain():
    """SQL injection in task_domain is sanitized to 'unknown'."""
    from core.engine.flow.clearance import clearance_where_clause

    clause, params = clearance_where_clause("technology'; DROP TABLE insight; --")
    assert "DROP" not in clause
    assert params["task_domain"] == "unknown"


def test_clearance_rejects_sql_injection_in_specialty():
    """SQL injection in task_specialty is sanitized to None."""
    from core.engine.flow.clearance import clearance_where_clause

    clause, params = clearance_where_clause("technology", "'; DELETE FROM insight; --")
    assert "DELETE" not in clause
    assert "task_specialty" not in params


def test_clearance_accepts_valid_slug():
    """Valid slugs pass validation."""
    from core.engine.flow.clearance import clearance_where_clause

    clause, params = clearance_where_clause("architecture")
    assert params["task_domain"] == "architecture"


def test_clearance_accepts_dotted_slug():
    """Dotted domain paths pass validation."""
    from core.engine.flow.clearance import clearance_where_clause

    clause, params = clearance_where_clause("architecture.backend")
    assert params["task_domain"] == "architecture.backend"


def test_clearance_returns_parameterized_query():
    """clearance_where_clause returns (clause, params) tuple with $placeholders."""
    from core.engine.flow.clearance import clearance_where_clause

    clause, params = clearance_where_clause("technology", "specialty:abc")
    assert "$task_domain" in clause
    assert "$task_specialty" in clause
    assert "task_domain" in params
    assert "task_specialty" in params


def test_clearance_rejects_empty_domain():
    """Empty domain is sanitized to 'unknown'."""
    from core.engine.flow.clearance import clearance_where_clause

    clause, params = clearance_where_clause("")
    assert params["task_domain"] == "unknown"


def test_clearance_rejects_unicode_injection():
    """Unicode tricks in domain are rejected."""
    from core.engine.flow.clearance import clearance_where_clause

    clause, params = clearance_where_clause("tëchnölogy")
    assert params["task_domain"] == "unknown"
