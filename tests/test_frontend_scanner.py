# tests/test_frontend_scanner.py
"""Tests for the frontend impact scanner."""

from pathlib import Path


def test_css_var_pattern():
    from core.engine.scanner.frontend_scanner import CSS_VAR_PATTERN

    text = "background: var(--glass-card); color: var(--text-bright);"
    matches = CSS_VAR_PATTERN.findall(text)
    assert "glass-card" in matches
    assert "text-bright" in matches


def test_ts_import_pattern():
    from core.engine.scanner.frontend_scanner import TS_IMPORT_PATTERN

    text = """import { GlassPanel } from "@/components/glass/GlassPanel";
import React from "react";
import { api } from "@/lib/api";"""
    matches = TS_IMPORT_PATTERN.findall(text)
    assert "@/components/glass/GlassPanel" in matches
    assert "react" in matches
    assert "@/lib/api" in matches


def test_scan_file_dependencies():
    import tempfile

    from core.engine.scanner.frontend_scanner import scan_file_dependencies

    with tempfile.NamedTemporaryFile(mode="w", suffix=".tsx", delete=False) as f:
        f.write("""
import { GlassPanel } from "@/components/glass/GlassPanel";
import { useConversationStore } from "@/stores/conversation";

export function MyComponent() {
    const { messages } = useConversationStore();
    return (
        <GlassPanel style={{ background: "var(--glass-card)", color: "var(--text-bright)" }}>
            <Button>Click</Button>
        </GlassPanel>
    );
}
""")
        f.flush()
        result = scan_file_dependencies(f.name, str(Path(f.name).parent))

    assert "glass-card" in result["css_vars_used"]
    assert "text-bright" in result["css_vars_used"]
    assert "GlassPanel" in result["components_used"]
    assert "Button" in result["components_used"]
    assert "useConversationStore" in result["hooks_used"]

    Path(f.name).unlink()
