# tests/test_context_blocks_tensions.py
from core.engine.orchestrator.context_blocks import compile_context_blocks


def test_tensions_block_first_and_formatted():
    intelligence = {
        "insights": [{"id": "insight:x", "content": "x", "insight_type": "fact", "confidence": 0.9}],
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
                    "content": "affinity bug",
                    "relationship": "causes",
                    "via_insight": "insight:x",
                    "edge_confidence": 0.8,
                }
            ],
        },
    }
    blocks = compile_context_blocks(intelligence, "product:test")
    assert blocks[0]["name"] == "graph_tensions"
    assert "TENSION" in blocks[0]["content"].upper()
    assert "Redis caching choice" in blocks[0]["content"]
    assert "affinity bug" in blocks[0]["content"]


def test_no_tensions_block_when_empty():
    intelligence = {
        "insights": [{"id": "insight:x", "content": "x", "insight_type": "fact", "confidence": 0.9}],
        "graph_tensions": {"tensions": [], "consequences": []},
    }
    blocks = compile_context_blocks(intelligence, "product:test")
    assert all(b["name"] != "graph_tensions" for b in blocks)
