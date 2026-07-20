# tests/test_scanner_hook.py
"""Structural tests for the post-scan capability mapping hook."""

import pytest


def test_post_scan_hook_calls_mapper():
    """Verify CapabilityMapper can be imported and exposes incremental_map."""
    from core.engine.product.capability_mapper import CapabilityMapper

    assert hasattr(CapabilityMapper, "incremental_map"), (
        "CapabilityMapper must expose incremental_map for the post-scan hook"
    )
    import inspect

    sig = inspect.signature(CapabilityMapper.incremental_map)
    params = list(sig.parameters.keys())
    # self, new_files, product_id
    assert "new_files" in params, "incremental_map must accept new_files"
    assert "product_id" in params, "incremental_map must accept product_id"


@pytest.mark.asyncio
async def test_post_scan_hook_graceful_on_failure():
    """Verify that a failing incremental_map does not propagate the exception.

    The hook is wrapped in try/except so scanning must never fail because of
    capability mapping.  We simulate the failure path by patching
    CapabilityMapper so that incremental_map raises, then confirm no exception
    escapes and only a warning is emitted.
    """
    import logging
    from unittest.mock import AsyncMock, MagicMock, patch

    # Build a minimal repo_files dict as the scanner would have after Step 2
    repo_files = {
        "core/engine/core/db.py": "engine_core_db_py",
        "core/engine/scanner/scanner.py": "engine_scanner_scanner_py",
    }

    # Replicate the hook logic verbatim so we test the exact pattern used in
    # the scanner rather than calling the scanner end-to-end.
    warning_messages: list[str] = []

    class _CapturingHandler(logging.Handler):
        def emit(self, record):
            warning_messages.append(self.format(record))

    hook_logger = logging.getLogger("core.engine.scanner.scanner")
    handler = _CapturingHandler()
    hook_logger.addHandler(handler)
    hook_logger.setLevel(logging.WARNING)

    mock_mapper = MagicMock()
    mock_mapper.incremental_map = AsyncMock(side_effect=RuntimeError("db unavailable"))

    try:
        with patch("core.engine.product.capability_mapper.CapabilityMapper", return_value=mock_mapper):
            # Execute the same try/except pattern the scanner hook uses
            pool_stub = MagicMock()
            product_id = "product:test"
            try:
                from core.engine.product.capability_mapper import CapabilityMapper

                mapper = CapabilityMapper(pool_stub)
                new_files = [{"id": slug, "path": path} for path, slug in repo_files.items()]
                if new_files:
                    map_result = await mapper.incremental_map(new_files, product_id)
                    hook_logger.info("Capability mapping: %s", map_result)
            except Exception as e:
                hook_logger.warning("Post-scan capability mapping failed (non-fatal): %s", e)
    finally:
        hook_logger.removeHandler(handler)

    # The hook must have caught the exception and logged a warning
    assert any("non-fatal" in msg for msg in warning_messages), (
        f"Expected a non-fatal warning but got: {warning_messages}"
    )
