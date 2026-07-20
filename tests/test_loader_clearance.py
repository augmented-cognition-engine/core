# tests/test_loader_clearance.py
"""Clearance-based domain isolation has been removed from the loader.

The loader now uses discipline + specialty tags for filtering.
This file retains a smoke test confirming no clearance import exists in loader.
"""

import pathlib


def test_loader_does_not_import_clearance():
    """loader.py must NOT import clearance_where_clause (domain model removed)."""
    src = pathlib.Path("core/engine/orchestrator/loader.py").read_text()
    assert "clearance_where_clause" not in src
    assert "clearance" not in src
