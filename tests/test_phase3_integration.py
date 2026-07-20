def test_reactive_simple_depth1_context_tokens():
    from core.engine.cognition.models import derive_depth
    from core.engine.intelligence.depth_budget import budget_for_depth

    depth = derive_depth("reactive", "simple")
    budget = budget_for_depth(depth)
    assert depth == 1
    assert budget.context_tokens == 400
    assert budget.recall_multiplier == 0.5
    assert budget.load_pm_context is False


def test_deliberative_complex_depth3_pm_auto_loaded():
    from core.engine.cognition.models import derive_depth
    from core.engine.intelligence.depth_budget import budget_for_depth

    depth = derive_depth("deliberative", "complex")
    budget = budget_for_depth(depth)
    assert depth == 3
    assert budget.context_tokens == 800
    assert budget.recall_multiplier == 1.0
    assert budget.load_pm_context is True


def test_exploratory_depth4_full_budget():
    from core.engine.cognition.models import derive_depth
    from core.engine.intelligence.depth_budget import budget_for_depth

    depth = derive_depth("exploratory", "complex")
    budget = budget_for_depth(depth)
    assert depth == 4
    assert budget.context_tokens == 1200


def test_context_assembler_depth1_budget_reduces_output():
    from core.engine.orchestrator.context_assembler import ContextAssembler

    snapshot = {
        "insights": [
            {
                "content": "a" * 500,
                "confidence": 0.9,
                "tier": "universal",
                "insight_type": "pattern",
                "id": f"insight:{i}",
                "source_graph": "specialty",
            }
            for i in range(10)
        ],
        "specialty_insights": [],
        "org_insights": [],
    }
    depth1_ctx = ContextAssembler(max_tokens=400).build(snapshot)
    depth4_ctx = ContextAssembler(max_tokens=1200).build(snapshot)
    assert len(depth1_ctx) < len(depth4_ctx)
    assert len(depth1_ctx) <= 1600


def test_all_phase3_modules_importable():
    import importlib

    importlib.import_module("core.engine.intelligence.depth_budget")
    from core.engine.cognition.models import derive_depth

    assert callable(derive_depth)
