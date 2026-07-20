# tests/test_context_assembler_tensions.py
"""Proof that graph tensions reach the REAL prompt seam.

ContextAssembler.build() is the path the executor actually uses to construct the
LLM prompt (executor.py imports it). This test would have caught the orphaned
compile_context_blocks wire — it asserts the tension surfaces in the assembled
context the model sees, not in a parallel structured-blocks API.
"""

import pytest

from core.engine.orchestrator.context_assembler import ContextAssembler


@pytest.fixture
def assembler():
    return ContextAssembler(max_tokens=6000)


def test_graph_tensions_wired_into_build(assembler):
    snapshot = {
        "graph_tensions": {
            "tensions": [
                {
                    "insight_id": "insight:brk",
                    "content": "Redis caching choice",
                    "relationship": "breaks",
                    "via_insight": "insight:x",
                    "edge_confidence": 0.95,
                }
            ],
            "consequences": [
                {
                    "insight_id": "insight:cz",
                    "content": "session affinity bug",
                    "relationship": "causes",
                    "via_insight": "insight:x",
                    "edge_confidence": 0.8,
                }
            ],
        },
    }
    result = assembler.build(snapshot)
    assert "Tensions" in result
    assert "CONTRADICTS" in result
    assert "Redis caching choice" in result
    assert "CAUSED" in result
    assert "session affinity bug" in result


def test_graph_tensions_renders_last_for_recency(assembler):
    """Tensions are pinned-last — the LLM confronts contradictions right before reasoning."""
    snapshot = {
        "specialty_insights": [{"confidence": 0.9, "content": "Specialty fact"}],
        "graph_tensions": {
            "tensions": [{"insight_id": "insight:brk", "content": "Redis caching choice", "relationship": "breaks"}],
            "consequences": [],
        },
    }
    result = assembler.build(snapshot)
    assert result.index("Specialty fact") < result.index("Redis caching choice")


def test_empty_graph_tensions_no_section(assembler):
    snapshot = {"graph_tensions": {"tensions": [], "consequences": []}}
    result = assembler.build(snapshot)
    assert "Tensions" not in result
    assert result == ""


def test_missing_graph_tensions_no_section(assembler):
    result = assembler.build({"specialty_insights": [{"confidence": 0.9, "content": "fact"}]})
    assert "Tensions" not in result
