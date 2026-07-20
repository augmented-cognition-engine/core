# tests/test_intelligence_lsp_manager.py
"""Tests for the LSP server manager."""

from core.engine.intelligence.lsp_manager import LSPManager


def test_manager_creation():
    mgr = LSPManager()
    assert mgr is not None
    assert mgr.active_servers == []


def test_is_running_before_start():
    mgr = LSPManager()
    assert not mgr.is_running("python")


def test_supported_check():
    mgr = LSPManager()
    assert mgr.is_supported("python")
    assert mgr.is_supported("typescript")
    assert not mgr.is_supported("brainfuck")
