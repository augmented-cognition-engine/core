"""Renderer protocol — each renderer consumes a DiagramIR and emits a string."""

from __future__ import annotations

from typing import Protocol

from core.engine.diagram.ir import DiagramIR


class Renderer(Protocol):
    def render(self, ir: DiagramIR) -> str: ...
