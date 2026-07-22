"""apply_pending must surface per-statement migration errors, not swallow them.

A plain `DEFINE FIELD` on an existing field returns a per-statement ERR
('already exists') that the surrealdb client's db.query() does NOT raise on.
apply_pending previously ran statements via db.query and discarded the result,
so a failed migration statement was silently ignored — which masked the v113
SCHEMAFULL legacy-field bug for months. The runner now inspects query_raw
results and raises on any error.
"""

import pytest

from core.engine.core.schema import _assert_no_stmt_error, _check_stmt_result


def test_ok_result_does_not_raise():
    raw = {"id": "x", "result": [{"result": None, "status": "OK", "time": "1ms"}]}
    _assert_no_stmt_error(raw, source="v999.surql: DEFINE ...")  # no exception


def test_per_statement_err_raises():
    raw = {
        "id": "x",
        "result": [{"kind": "Internal", "result": "The field 'foo' already exists", "status": "ERR"}],
    }
    with pytest.raises(RuntimeError) as exc:
        _assert_no_stmt_error(raw, source="v999.surql: DEFINE FIELD foo ...")
    assert "already exists" in str(exc.value)
    assert "v999.surql" in str(exc.value)


def test_top_level_error_raises():
    raw = {"error": {"code": -32000, "message": "parse error near FOO"}}
    with pytest.raises(RuntimeError) as exc:
        _assert_no_stmt_error(raw, source="v999.surql")
    assert "parse error" in str(exc.value)


def test_mixed_ok_then_err_raises_on_the_err():
    raw = {
        "result": [
            {"status": "OK", "result": None},
            {"status": "ERR", "result": "coercion failed"},
        ]
    }
    with pytest.raises(RuntimeError) as exc:
        _assert_no_stmt_error(raw, source="v999.surql")
    assert "coercion failed" in str(exc.value)


def test_non_dict_input_is_tolerated():
    # Defensive: an unexpected shape must not crash the runner.
    _assert_no_stmt_error([], source="v999.surql")
    _assert_no_stmt_error(None, source="v999.surql")


def test_api_startup_accepts_only_audited_legacy_compatibility_event():
    raw = {"result": [{"status": "ERR", "result": "The field 'product' already exists"}]}
    event = _check_stmt_result(raw, version=6, source="v006_product_model.surql")
    assert event is not None and "already exists" in event


def test_api_startup_rejects_same_error_for_current_migration():
    raw = {"result": [{"status": "ERR", "result": "The field 'product' already exists"}]}
    with pytest.raises(RuntimeError, match="already exists"):
        _check_stmt_result(raw, version=142, source="v142_current.surql")


def test_api_startup_rejects_unknown_legacy_error():
    raw = {"result": [{"status": "ERR", "result": "permission denied"}]}
    with pytest.raises(RuntimeError, match="permission denied"):
        _check_stmt_result(raw, version=6, source="v006_product_model.surql")
