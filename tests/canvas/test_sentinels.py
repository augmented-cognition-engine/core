"""Sentinels — protect v1 backend architectural invariants from drift.

A2: surface-agnostic adapter (core/engine/canvas MUST NOT import hook code)
A4: no second decision ledger (no new decision_canvas table)
"""

from __future__ import annotations

import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]


def test_a2_canvas_engine_does_not_import_hooks():
    canvas_dir = REPO / "core/engine/canvas"
    for py in canvas_dir.glob("*.py"):
        src = py.read_text()
        forbidden = ["core.engine.capture.observer", ".claude/hooks", "claude_code"]
        for term in forbidden:
            assert term not in src, f"{py.name} imports `{term}` — violates §A2 surface-agnostic invariant"


def test_a4_no_separate_decision_canvas_table():
    schema_files = list((REPO / "schema").glob("v*.surql"))
    # Must NOT define a `decision_canvas` table — canvas decisions live in `decision`
    for f in schema_files:
        src = f.read_text()
        assert not re.search(r"DEFINE TABLE\s+decision_canvas\b", src), (
            f"{f.name} defines a separate decision_canvas table — violates §A4"
        )


def test_a4_canvas_decision_carries_surface_field():
    """A canvas-bridged decision MUST land with surface='canvas' so the existing
    capture pipeline can route it. If this assertion drifts, a downstream
    consumer will silently miss canvas decisions."""
    bridge = (REPO / "core/engine/canvas/ledger_bridge.py").read_text()
    assert "surface = 'canvas'" in bridge or '"surface": "canvas"' in bridge, (
        "ledger_bridge MUST stamp surface='canvas' on every decision (§A4)"
    )


def test_event_protocol_strings_match_surfaces_doc_promise():
    """If event-type string constants drift, non-Python surfaces (frontend,
    future IDE adapters) will silently fail to dispatch."""
    proto = (REPO / "core/engine/canvas/event_protocol.py").read_text()
    expected = {
        "session.opened",
        "artifact.placed",
        "framework.requested",
        "decision.made",
        "participant.state_changed",
    }
    for s in expected:
        assert f'"{s}"' in proto, f"Missing canonical event string `{s}` in event_protocol.py"


def test_framework_completed_payload_has_tldraw_shape_id():
    from core.engine.canvas.event_protocol import FrameworkCompletedPayload

    p = FrameworkCompletedPayload(
        tldraw_shape_id="shape:fw_abc",
        shape_kind="framework_artifact",
        framework_kind="trade_off_matrix",
        payload={"title": "Test"},
    )
    assert p.tldraw_shape_id == "shape:fw_abc"


def test_reasoning_step_payload_fields():
    from core.engine.canvas.event_protocol import ReasoningStepPayload

    p = ReasoningStepPayload(
        framework_kind="trade_off_matrix",
        framework_name="Trade-off Matrix",
        step_label="Checking",
        step_text="Examining options for funding path",
        step_index=0,
    )
    assert p.step_label == "Checking"
    assert p.framework_name == "Trade-off Matrix"
