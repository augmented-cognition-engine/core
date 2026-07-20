# tests/test_egress_guard.py
"""Regression proof for the test-harness egress guard (OSS Task 8b, tests/conftest.py).

Without this file, the guard (_block_offbox_network_egress /
_block_cli_subprocess_egress in conftest.py) could silently no-op — e.g. a typo in
the family check, a patch that never applies, an exemption that's too broad — and
nothing would catch it. These tests deliberately trigger both halves of the guard
(socket connect, `claude` CLI subprocess spawn) and assert BlockedNetworkEgress
actually fires, then prove the guard's SCOPE is off-box-only (loopback still
reaches the real OS) and that @pytest.mark.allow_network actually lifts it.

No real network I/O happens anywhere in this file: the socket case is intercepted
by the guard before the OS syscall runs, the loopback case hits a real but
unlistened local port (instant, deterministic ConnectionRefusedError, no live
service required), and the allow_network exemption is proven by identity
comparison against the pristine functions captured at import time — never by
attempting a real off-box connection or spawning a real `claude` process (which
would be slow/flaky at best and could bill real tokens on a dev machine that has
the CLI on PATH at worst).
"""

from __future__ import annotations

import asyncio
import socket

import pytest

from tests.conftest import BlockedNetworkEgress

# RFC 5737 TEST-NET-3 — reserved for documentation, guaranteed non-routable.
# Using a real off-box-shaped address (rather than e.g. api.anthropic.com) keeps
# this test independent of DNS/network availability in the sandbox: the guard
# raises on the address family + loopback check alone, before any resolution or
# syscall would occur.
_OFFBOX_ADDRESS = ("203.0.113.1", 443)

# Captured at IMPORT time — before any test's autouse fixtures have run — so these
# are guaranteed to be the pristine, unpatched functions.
_PRISTINE_SOCKET_CONNECT = socket.socket.connect
_PRISTINE_CREATE_SUBPROCESS_EXEC = asyncio.create_subprocess_exec


def test_offbox_socket_connect_is_blocked():
    """Socket half of the guard: an unmocked off-box connect raises
    BlockedNetworkEgress instead of reaching the wire — the core regression proof."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        with pytest.raises(BlockedNetworkEgress):
            sock.connect(_OFFBOX_ADDRESS)
    finally:
        sock.close()


@pytest.mark.asyncio
async def test_claude_cli_subprocess_spawn_is_blocked():
    """Subprocess half of the guard: an unmocked spawn of the `claude` CLI raises
    BlockedNetworkEgress instead of shelling out for real — this is what closes the
    gap the socket guard alone can't (CLIProvider's subprocess makes its own
    connections in a child process, invisible to this process's patched socket)."""
    with pytest.raises(BlockedNetworkEgress):
        await asyncio.create_subprocess_exec(
            "claude",
            "-p",
            "hello",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )


def test_loopback_connect_is_not_blocked_by_the_guard():
    """The guard's scope is off-box only, not a blanket socket ban. Port 1 (TCPMUX)
    has no listener in any CI/dev environment, so the OS itself refuses the
    connection — a ConnectionRefusedError proves the REAL connect() ran (the guard
    let it through), not our synthetic block."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        with pytest.raises(ConnectionRefusedError):
            sock.connect(("127.0.0.1", 1))
    finally:
        sock.close()


def test_default_scope_has_the_socket_guard_installed():
    """Sanity check for the identity-comparison exemption tests below: outside of
    allow_network/e2e, socket.socket.connect really is the guard's wrapper, not the
    pristine function."""
    assert socket.socket.connect is not _PRISTINE_SOCKET_CONNECT


def test_default_scope_has_the_subprocess_guard_installed():
    """Same sanity check for the subprocess half."""
    assert asyncio.create_subprocess_exec is not _PRISTINE_CREATE_SUBPROCESS_EXEC


@pytest.mark.allow_network
def test_allow_network_marker_exempts_the_socket_guard():
    """@pytest.mark.allow_network must fully lift the socket guard — proven by
    identity, not by attempting a real (slow/flaky) off-box connection."""
    assert socket.socket.connect is _PRISTINE_SOCKET_CONNECT


@pytest.mark.allow_network
def test_allow_network_marker_exempts_the_subprocess_guard():
    """Same exemption proof for the subprocess half."""
    assert asyncio.create_subprocess_exec is _PRISTINE_CREATE_SUBPROCESS_EXEC
