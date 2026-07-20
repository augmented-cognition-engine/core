# engine/reports/generator.py
"""ReportGenerator — orchestrates assembly → narrative → HTML → PDF."""

from __future__ import annotations

import logging
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

from core.engine.reports.assembler import DataAssembler
from core.engine.reports.diagrams import DiagramGenerator
from core.engine.reports.narrative import NarrativeGenerator
from core.engine.reports.renderer import PdfRenderer

logger = logging.getLogger(__name__)

_TEMPLATE_DIR = Path(__file__).parent / "templates"
_STATIC_DIR = Path(__file__).parent / "static"
_MERMAID_JS = _STATIC_DIR / "mermaid.min.js"
_MERMAID_CDN = "https://cdn.jsdelivr.net/npm/mermaid@10/dist/mermaid.min.js"


class ReportGenerator:
    def __init__(self, pool) -> None:
        self._pool = pool
        self._env = Environment(
            loader=FileSystemLoader([str(_TEMPLATE_DIR)]),
            autoescape=select_autoescape(["html"]),
        )

    async def generate(
        self,
        product_id: str,
        report_type: str = "audit",
        client_name: str = "",
        consultant_name: str = "",
    ) -> bytes:
        """Assemble data, generate narrative, render PDF. Returns PDF bytes."""
        assembler = DataAssembler(self._pool)
        assembled = await assembler.assemble(
            product_id,
            report_type,
            client_name=client_name,
            consultant_name=consultant_name,
        )

        narrative_gen = NarrativeGenerator()
        narrative_data = await narrative_gen.generate(assembled)
        assembled.update(narrative_data)

        # Attach diagrams
        diag = DiagramGenerator()
        assembled["diagram_risk_heatmap"] = diag.svg_risk_heatmap(assembled.get("health_by_discipline", []))
        assembled["diagram_arch_map"] = diag.mermaid_architecture_map(assembled.get("capabilities", []))
        assembled["diagram_cap_graph"] = diag.mermaid_capability_graph(assembled.get("capabilities", []))

        # Mermaid.js — vendored preferred, CDN fallback
        if _MERMAID_JS.exists():
            assembled["mermaid_js_inline"] = _MERMAID_JS.read_text(encoding="utf-8")
            assembled["mermaid_js_src"] = ""
        else:
            logger.warning("mermaid.min.js not vendored — falling back to CDN")
            assembled["mermaid_js_inline"] = ""
            assembled["mermaid_js_src"] = _MERMAID_CDN

        template_name = f"{report_type}.html"
        try:
            template = self._env.get_template(template_name)
        except Exception:
            logger.warning("Template %s not found, falling back to audit.html", template_name)
            template = self._env.get_template("audit.html")

        html = template.render(**assembled)

        renderer = PdfRenderer()
        return await renderer.render(html)
