# tests/test_intelligence_lsp_client.py
"""Tests for the LSP JSON-RPC client."""

import json

from core.engine.intelligence.lsp_client import LSPClient, decode_header, encode_message


def test_encode_message():
    msg = {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}}
    encoded = encode_message(msg)
    assert b"Content-Length:" in encoded
    assert b"\r\n\r\n" in encoded
    # Verify the JSON body follows the header
    _, body = encoded.split(b"\r\n\r\n", 1)
    parsed = json.loads(body)
    assert parsed["method"] == "initialize"


def test_decode_header():
    header = b"Content-Length: 42\r\n\r\n"
    length = decode_header(header)
    assert length == 42


def test_decode_header_with_content_type():
    header = b"Content-Length: 100\r\nContent-Type: application/vscode-jsonrpc; charset=utf-8\r\n\r\n"
    length = decode_header(header)
    assert length == 100


def test_client_creation():
    """LSPClient should be instantiable (actual server tests are integration)."""
    # Just test the class exists and has the right interface
    assert hasattr(LSPClient, "request")
    assert hasattr(LSPClient, "notify")
    assert hasattr(LSPClient, "shutdown")
