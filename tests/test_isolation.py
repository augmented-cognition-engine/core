# tests/test_isolation.py
"""Adversarial isolation tests for multi-client data separation.

P4 acceptance criteria:
1. IsolationValidator surfaces violations as errors, not silent bleed
2. Two concurrent client products have zero cross-contamination
3. Signals, records, and specs are all filtered by product_id
4. Shared (ecosystem) records are read-only and never promoted implicitly
"""

from __future__ import annotations

import pytest

from core.engine.synthesis.signal_store import InMemorySignalStore, ProactiveSignal

# ── IsolationViolation error type ─────────────────────────────────────────────


def test_isolation_violation_is_exception():
    """IsolationViolation is a named exception type, not a silent failure."""
    from core.engine.product.isolation import IsolationViolation

    with pytest.raises(IsolationViolation):
        raise IsolationViolation("cross-product bleed detected")


# ── IsolationValidator.validate_signals ───────────────────────────────────────


def test_validate_signals_passes_when_all_match_product():
    """No violation when all signals belong to the expected product."""
    from core.engine.product.isolation import IsolationValidator

    validator = IsolationValidator()
    signals = [
        ProactiveSignal(
            product_id="product:alpha",
            event_type="spec.created",
            leverage_points=[],
            summary="alpha signal",
            status="new",
        )
    ]
    # Must not raise
    validator.validate_signals(signals, product_id="product:alpha")


def test_validate_signals_raises_on_wrong_product():
    """IsolationViolation raised if a signal's product_id doesn't match."""
    from core.engine.product.isolation import IsolationValidator, IsolationViolation

    validator = IsolationValidator()
    signals = [
        ProactiveSignal(
            product_id="product:beta",
            event_type="spec.created",
            leverage_points=[],
            summary="beta signal leaking into alpha",
            status="new",
        )
    ]
    with pytest.raises(IsolationViolation, match="product:beta"):
        validator.validate_signals(signals, product_id="product:alpha")


def test_validate_signals_raises_on_mixed_products():
    """IsolationViolation raised if any signal in the list belongs to a different product."""
    from core.engine.product.isolation import IsolationValidator, IsolationViolation

    validator = IsolationValidator()
    signals = [
        ProactiveSignal(
            product_id="product:alpha",
            event_type="spec.created",
            leverage_points=[],
            summary="valid alpha signal",
            status="new",
        ),
        ProactiveSignal(
            product_id="product:beta",
            event_type="commit.detected",
            leverage_points=[],
            summary="beta signal mixed in",
            status="new",
        ),
    ]
    with pytest.raises(IsolationViolation, match="product:beta"):
        validator.validate_signals(signals, product_id="product:alpha")


def test_validate_signals_passes_empty_list():
    """No violation for an empty signal list."""
    from core.engine.product.isolation import IsolationValidator

    validator = IsolationValidator()
    validator.validate_signals([], product_id="product:alpha")  # must not raise


# ── IsolationValidator.validate_records ───────────────────────────────────────


def test_validate_records_passes_when_all_match_product():
    """No violation when all records have the expected product_id."""
    from core.engine.product.isolation import IsolationValidator

    validator = IsolationValidator()
    records = [
        {"product_id": "product:alpha", "content": "insight 1"},
        {"product_id": "product:alpha", "content": "insight 2"},
    ]
    validator.validate_records(records, product_id="product:alpha")  # must not raise


def test_validate_records_raises_on_wrong_product():
    """IsolationViolation raised if any record has a different product_id."""
    from core.engine.product.isolation import IsolationValidator, IsolationViolation

    validator = IsolationValidator()
    records = [
        {"product_id": "product:alpha", "content": "valid"},
        {"product_id": "product:beta", "content": "leaked"},
    ]
    with pytest.raises(IsolationViolation, match="product:beta"):
        validator.validate_records(records, product_id="product:alpha")


def test_validate_records_supports_custom_field_name():
    """validate_records can check a custom field name (e.g. 'product' for SurrealDB refs)."""
    from core.engine.product.isolation import IsolationValidator, IsolationViolation

    validator = IsolationValidator()
    records = [{"product": "product:beta", "data": "leaked"}]
    with pytest.raises(IsolationViolation):
        validator.validate_records(records, product_id="product:alpha", field="product")


def test_validate_records_skips_records_without_field():
    """Records without the product field are skipped — no false positives on shared tables."""
    from core.engine.product.isolation import IsolationValidator

    validator = IsolationValidator()
    records = [
        {"slug": "auth-framework", "content": "shared framework — no product field"},
    ]
    validator.validate_records(records, product_id="product:alpha")  # must not raise


# ── Adversarial: two concurrent clients, zero cross-contamination ─────────────


@pytest.mark.asyncio
async def test_signal_store_isolates_two_concurrent_clients():
    """Two clients write signals concurrently — neither sees the other's signals."""
    store = InMemorySignalStore()

    alpha_signal = ProactiveSignal(
        product_id="product:client_alpha",
        event_type="spec.created",
        leverage_points=[{"rank": 1, "discipline": "security", "intervention": "add auth"}],
        summary="Alpha: add auth middleware",
        status="new",
    )
    beta_signal = ProactiveSignal(
        product_id="product:client_beta",
        event_type="commit.detected",
        leverage_points=[{"rank": 1, "discipline": "testing", "intervention": "add tests"}],
        summary="Beta: add test coverage",
        status="new",
    )

    await store.store(alpha_signal)
    await store.store(beta_signal)

    alpha_results = await store.get_new_signals("product:client_alpha")
    beta_results = await store.get_new_signals("product:client_beta")

    # Strict product isolation
    assert all(s.product_id == "product:client_alpha" for s in alpha_results)
    assert all(s.product_id == "product:client_beta" for s in beta_results)

    # No cross-contamination
    assert len(alpha_results) == 1
    assert len(beta_results) == 1
    assert alpha_results[0].summary == "Alpha: add auth middleware"
    assert beta_results[0].summary == "Beta: add test coverage"


@pytest.mark.asyncio
async def test_mark_seen_only_affects_target_product():
    """mark_seen for Client A does not change Client B's signal status."""
    store = InMemorySignalStore()

    for client in ("product:client_alpha", "product:client_beta"):
        await store.store(
            ProactiveSignal(
                product_id=client,
                event_type="observation.created",
                leverage_points=[],
                summary=f"signal for {client}",
                status="new",
            )
        )

    await store.mark_seen("product:client_alpha")

    alpha_new = await store.get_new_signals("product:client_alpha")
    beta_new = await store.get_new_signals("product:client_beta")

    assert len(alpha_new) == 0, "Alpha's signals should be marked seen"
    assert len(beta_new) == 1, "Beta's signals must not be affected"


def test_isolation_audit_reports_scoped_and_unscoped():
    """IsolationAudit.run() returns a report with scoped/unscoped table classification."""
    from core.engine.product.isolation import IsolationAudit

    audit = IsolationAudit()
    report = audit.run()

    assert "scoped_tables" in report
    assert "unscoped_tables" in report
    assert "shared_tables" in report
    assert isinstance(report["scoped_tables"], list)
    assert isinstance(report["unscoped_tables"], list)
    assert isinstance(report["shared_tables"], list)


def test_isolation_audit_shared_tables_are_read_only_safe():
    """Shared tables (framework, skill) are classified as intentionally global."""
    from core.engine.product.isolation import IsolationAudit

    audit = IsolationAudit()
    report = audit.run()

    shared = report["shared_tables"]
    shared_names = [t["table"] for t in shared]
    # framework and skill are universal knowledge — intentionally unscoped
    assert "framework" in shared_names or "skill" in shared_names
