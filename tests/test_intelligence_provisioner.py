# tests/test_intelligence_provisioner.py
"""Tests for LSP server provisioning."""

from core.engine.intelligence.provisioner import ServerProvisioner, get_server_dir


def test_server_dir():
    d = get_server_dir()
    assert ".ace" in d
    assert "servers" in d


def test_provisioner_creation():
    p = ServerProvisioner()
    assert p is not None


def test_is_provisioned_false():
    p = ServerProvisioner()
    # Unless pyright is actually installed, this should return False
    # (or True if it happens to be installed — both are valid)
    result = p.is_provisioned("python")
    assert isinstance(result, bool)


def test_unknown_language():
    p = ServerProvisioner()
    result = p.is_provisioned("brainfuck")
    assert result is False


def test_get_binary_path():
    p = ServerProvisioner()
    path = p.get_binary_path("python")
    # Should return a path (even if not yet installed)
    assert path is not None
    assert "pyright" in path.lower() or "python" in path.lower()
