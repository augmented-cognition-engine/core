"""Integration tests for seam analyzer — full pipeline end-to-end."""

from __future__ import annotations

from textwrap import dedent

from core.engine.seam.backend_extractor import extract_backend_contracts
from core.engine.seam.frontend_extractor import extract_frontend_expectations
from core.engine.seam.matcher import match_and_compare


class TestSeamAnalyzerIntegration:
    def test_full_pipeline_detects_mismatch(self, tmp_path):
        """End-to-end: backend returns {nodes, in, out}, frontend expects {nodes, from, to}."""
        # Create mock backend file
        backend = tmp_path / "api_edges.py"
        backend.write_text(
            dedent("""\
            from fastapi import APIRouter

            router = APIRouter(prefix="/graph")

            @router.get("/edges")
            async def get_edges():
                return {"nodes": [], "in": "x", "out": "y"}
            """)
        )

        # Create mock frontend file
        frontend = tmp_path / "EdgeView.tsx"
        frontend.write_text(
            dedent("""\
            import { api } from "@/lib/api";

            const data = await api.get<{ nodes: any[]; from: string; to: string }>("/graph/edges");
            """)
        )

        # Run extractors
        contracts = extract_backend_contracts(str(backend))
        assert len(contracts) == 1
        assert contracts[0].route == "/graph/edges"

        expectations = extract_frontend_expectations(str(frontend))
        assert len(expectations) == 1
        assert expectations[0].route == "/graph/edges"

        # Match and compare
        gaps = match_and_compare(contracts, expectations)

        errors = [g for g in gaps if g.severity == "error"]
        assert len(errors) == 2, f"Expected 2 error gaps, got {len(errors)}: {[g.detail for g in errors]}"

        error_fields = {g.detail for g in errors}
        assert any("'from'" in d for d in error_fields)
        assert any("'to'" in d for d in error_fields)

        # Also expect warnings for unused backend fields
        warnings = [g for g in gaps if g.severity == "warning"]
        assert len(warnings) == 2
        warning_fields = {g.detail for g in warnings}
        assert any("'in'" in d for d in warning_fields)
        assert any("'out'" in d for d in warning_fields)

    def test_full_pipeline_no_issues(self, tmp_path):
        """No gaps when shapes match exactly."""
        backend = tmp_path / "api_items.py"
        backend.write_text(
            dedent("""\
            from fastapi import APIRouter

            router = APIRouter()

            @router.get("/items")
            async def list_items():
                return {"items": [], "total": 0}
            """)
        )

        frontend = tmp_path / "ItemList.tsx"
        frontend.write_text(
            dedent("""\
            import { api } from "@/lib/api";

            const data = await api.get<{ items: any[]; total: number }>("/items");
            """)
        )

        contracts = extract_backend_contracts(str(backend))
        expectations = extract_frontend_expectations(str(frontend))
        gaps = match_and_compare(contracts, expectations)

        errors = [g for g in gaps if g.severity == "error"]
        assert len(errors) == 0

    def test_full_pipeline_with_named_type(self, tmp_path):
        """Named interface type resolves fields correctly."""
        types_file = tmp_path / "types.ts"
        types_file.write_text(
            dedent("""\
            export interface UserResponse {
                id: string;
                name: string;
                email: string;
            }
            """)
        )

        backend = tmp_path / "api_users.py"
        backend.write_text(
            dedent("""\
            from fastapi import APIRouter

            router = APIRouter()

            @router.get("/users/me")
            async def get_me():
                return {"id": "abc", "name": "Alice", "email": "a@b.com"}
            """)
        )

        frontend = tmp_path / "Profile.tsx"
        frontend.write_text(
            dedent("""\
            import { api } from "@/lib/api";

            const user = await api.get<UserResponse>("/users/me");
            """)
        )

        contracts = extract_backend_contracts(str(backend))
        expectations = extract_frontend_expectations(str(frontend), [str(types_file)])
        gaps = match_and_compare(contracts, expectations)

        errors = [g for g in gaps if g.severity == "error"]
        assert len(errors) == 0

    def test_full_pipeline_unmatched_route(self, tmp_path):
        """Frontend calls a route with no backend contract."""
        frontend = tmp_path / "Dashboard.tsx"
        frontend.write_text(
            dedent("""\
            import { api } from "@/lib/api";

            const stats = await api.get<{ count: number }>("/dashboard/stats");
            """)
        )

        contracts = []
        expectations = extract_frontend_expectations(str(frontend))
        gaps = match_and_compare(contracts, expectations)

        assert len(gaps) == 1
        assert gaps[0].severity == "info"
        assert gaps[0].gap_type == "unmatched_route"
