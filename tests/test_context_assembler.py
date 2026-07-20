# tests/test_context_assembler.py
"""Tests for engine/orchestrator/context_assembler.py — token-budget context builder."""

import pytest

from core.engine.orchestrator.context_assembler import ContextAssembler


@pytest.fixture
def assembler():
    return ContextAssembler(max_tokens=6000)


def test_empty_snapshot_returns_empty(assembler):
    assert assembler.build({}) == ""


def test_specialty_insights_rendered(assembler):
    snapshot = {
        "specialty_insights": [
            {"confidence": 0.9, "content": "Use async for all DB operations"},
            {"confidence": 0.8, "content": "Validate inputs at boundaries"},
        ]
    }
    result = assembler.build(snapshot)
    assert "Expert Knowledge" in result
    assert "Use async for all DB operations" in result
    assert "[0.90]" in result


def test_org_insights_rendered(assembler):
    snapshot = {
        "org_insights": [
            {"confidence": 0.75, "content": "We use SurrealDB v3 syntax"},
        ]
    }
    result = assembler.build(snapshot)
    assert "Team Context" in result
    assert "SurrealDB v3" in result


def test_specialty_before_org(assembler):
    """specialty_insights section must appear before org_insights."""
    snapshot = {
        "specialty_insights": [{"confidence": 0.9, "content": "Specialty fact"}],
        "org_insights": [{"confidence": 0.8, "content": "Org fact"}],
    }
    result = assembler.build(snapshot)
    assert result.index("Specialty fact") < result.index("Org fact")


def test_recent_signals_rendered(assembler):
    snapshot = {
        "recent_signals": [
            {"observation_type": "learning", "content": "Auth refactor in progress", "confidence": 0.7},
        ]
    }
    result = assembler.build(snapshot)
    assert "Recent Observations" in result
    assert "Auth refactor" in result
    assert "skepticism" in result


def test_legacy_insights_shown_when_no_dual_graph(assembler):
    """Legacy single-list format used only when specialty/org insights absent."""
    snapshot = {
        "insights": [
            {"insight_type": "pattern", "content": "Legacy insight here", "confidence": 0.6},
        ]
    }
    result = assembler.build(snapshot)
    assert "Established Intelligence" in result
    assert "Legacy insight here" in result


def test_legacy_insights_suppressed_when_dual_graph_present(assembler):
    """Legacy insights must NOT appear when specialty_insights are present."""
    snapshot = {
        "specialty_insights": [{"confidence": 0.9, "content": "Modern insight"}],
        "insights": [{"insight_type": "pattern", "content": "Old insight", "confidence": 0.5}],
    }
    result = assembler.build(snapshot)
    assert "Old insight" not in result
    assert "Modern insight" in result


def test_pm_context_decisions(assembler):
    snapshot = {
        "pm_context": {
            "decisions": [{"title": "Use CaptureService", "outcome": "approved", "decision_type": "architecture"}]
        }
    }
    result = assembler.build(snapshot)
    assert "Recent Decisions" in result
    assert "CaptureService" in result


def test_pm_context_initiatives(assembler):
    snapshot = {
        "pm_context": {
            "initiatives": [{"title": "Observability wave", "status": "executing", "cost_budget": 50, "cost_used": 12}]
        }
    }
    result = assembler.build(snapshot)
    assert "Active Initiatives" in result
    assert "Observability wave" in result
    assert "$12/$50" in result


def test_risk_context_blast_radius(assembler):
    snapshot = {
        "risk_context": {
            "blast_radius": [{"file": "core/engine/api/main.py", "direct": 3, "total": 12, "total_matched": 1}]
        }
    }
    result = assembler.build(snapshot)
    assert "Blast Radius" in result
    assert "core/engine/api/main.py" in result


def test_product_map_rendered(assembler):
    snapshot = {
        "product_context": {
            "total_capabilities": 42,
            "capabilities": [
                {"slug": "auth", "name": "Authentication", "status": "active", "description": "JWT auth"},
            ],
        }
    }
    result = assembler.build(snapshot)
    assert "Product Map" in result
    assert "Authentication" in result
    assert "42" in result


def test_token_budget_pins_org_insights_last():
    """Org insights are budget-reserved and always appear last, even under pressure."""
    assembler = ContextAssembler(max_tokens=20)  # very tight
    snapshot = {
        "specialty_insights": [{"confidence": 0.9, "content": "Specialty knowledge here"}],
        "org_insights": [{"confidence": 1.0, "content": "Should not appear"}],  # keep content for clarity
    }
    result = assembler.build(snapshot)
    # Org insights are now PINNED — they appear even under budget pressure
    assert "Should not appear" in result
    # And they appear AFTER specialty knowledge
    assert result.index("Specialty knowledge") < result.index("Should not appear")


def test_graph_context_relevant_files(assembler):
    snapshot = {
        "graph_context": {
            "relevant_files": [{"path": "core/engine/capture/service.py", "function_count": 8, "dependent_count": 3}]
        }
    }
    result = assembler.build(snapshot)
    assert "Code Context" in result
    assert "core/engine/capture/service.py" in result
    assert "8 functions" in result


def test_build_via_wrapper_function():
    """_build_intel_context() wrapper in executor.py must still work."""
    from core.engine.orchestrator.executor import _build_intel_context

    result = _build_intel_context({"specialty_insights": [{"confidence": 0.9, "content": "Test insight"}]})
    assert "Test insight" in result


def _make_snapshot(specialty=True, org=True):
    return {
        "specialty_insights": [{"confidence": 0.9, "content": "token bucket best practice"}] if specialty else [],
        "org_insights": [{"confidence": 1.0, "content": "use user.get('sub') not user.get('id')"}] if org else [],
        "recent_signals": [],
    }


def test_org_insights_appear_after_specialty_insights():
    """Org conventions must appear LAST for recency bias (max model attention)."""
    assembler = ContextAssembler()
    context = assembler.build(_make_snapshot())
    specialty_pos = context.find("token bucket best practice")
    org_pos = context.find("use user.get('sub')")
    assert specialty_pos != -1
    assert org_pos != -1
    assert org_pos > specialty_pos, "org insights must appear after specialty insights"


def test_org_insights_not_starved_by_budget():
    """Org insights must appear even when budget is tight."""
    assembler = ContextAssembler(max_tokens=50)
    snapshot = _make_snapshot()
    context = assembler.build(snapshot)
    assert "use user.get('sub')" in context


def test_context_without_org_still_works():
    assembler = ContextAssembler()
    context = assembler.build(_make_snapshot(org=False))
    assert "token bucket best practice" in context
    assert "use user.get" not in context


def test_decisions_section_renders_when_no_pm_context(assembler):
    """_section_decisions renders when pm_context has no decisions."""
    snapshot = {
        "decisions": [
            {
                "title": "Use circuit breaker for async failures",
                "decision_type": "architecture",
                "rationale": "prevents cascade",
                "outcome": "adopted",
            }
        ]
    }
    result = assembler.build(snapshot)
    assert "Prior Decisions" in result
    assert "circuit breaker" in result
    assert "adopted" in result


def test_decisions_section_suppressed_when_pm_context_has_decisions(assembler):
    """_section_decisions skips rendering when pm_context already has decisions."""
    snapshot = {
        "decisions": [{"title": "Decision A", "decision_type": "architecture", "outcome": "adopted"}],
        "pm_context": {
            "decisions": [{"title": "Decision B", "decision_type": "direction", "outcome": "pending"}],
            "initiatives": [],
            "quality_gaps": [],
            "live_agents": 0,
        },
    }
    result = assembler.build(snapshot)
    assert "Prior Decisions" not in result


def test_decisions_section_empty_renders_nothing(assembler):
    """_section_decisions returns empty string when decisions list is empty."""
    result = assembler.build({"decisions": []})
    assert "Prior Decisions" not in result


def test_failure_memory_appears_before_org_insights():
    """Failure memory must render before org_insights (pinned last)."""
    assembler = ContextAssembler()
    snapshot = {
        "specialty_insights": [{"confidence": 0.9, "content": "specialty content"}],
        "org_insights": [{"confidence": 1.0, "content": "org convention content"}],
        "recent_signals": [],
        "failure_memory": [
            {"gaps": ["missing Retry-After header"], "verdict": "gaps_found", "discipline": "coding"},
        ],
    }
    context = assembler.build(snapshot)

    failure_pos = context.find("missing Retry-After header")
    org_pos = context.find("org convention content")
    assert failure_pos != -1, "failure memory must appear in context"
    assert org_pos != -1, "org insights must appear in context"
    assert failure_pos < org_pos, "failure memory must appear before org insights (org is pinned very last)"


def test_no_failure_section_when_empty():
    """Empty failure_memory list produces no failure section in context."""
    assembler = ContextAssembler()
    snapshot = {
        "specialty_insights": [{"confidence": 0.9, "content": "specialty"}],
        "org_insights": [],
        "recent_signals": [],
        "failure_memory": [],
    }
    context = assembler.build(snapshot)
    assert "Known Failure Patterns" not in context


def test_failure_memory_not_present_in_snapshot_still_works():
    """ContextAssembler must not crash if failure_memory key is absent."""
    assembler = ContextAssembler()
    snapshot = {
        "specialty_insights": [{"confidence": 0.9, "content": "specialty"}],
        "org_insights": [],
        "recent_signals": [],
        # No failure_memory key at all
    }
    context = assembler.build(snapshot)
    assert "specialty" in context


# test_context_assembler_includes_star_traces: star_traces in snapshot → rendered as section
def test_context_assembler_includes_star_traces():
    from core.engine.orchestrator.context_assembler import ContextAssembler

    snapshot = {
        "star_traces": [
            {
                "task_description": "Add rate limiting to the API",
                "phase_traces": [{"phase_idx": 0, "cognitive_function": "analysis", "confidence": 0.9}],
                "final_output": "Token bucket algorithm chosen for its burst tolerance.",
            }
        ],
    }
    assembler = ContextAssembler()
    context = assembler.build(snapshot)
    assert "Proven Reasoning Patterns" in context
    assert "Add rate limiting" in context


# test_context_assembler_no_star_traces_section_when_empty: empty list → section omitted
def test_context_assembler_no_star_traces_section_when_empty():
    from core.engine.orchestrator.context_assembler import ContextAssembler

    snapshot = {"star_traces": []}
    assembler = ContextAssembler()
    context = assembler.build(snapshot)
    assert "Proven Reasoning Patterns" not in context


def test_code_context_section_renders_file_content(assembler):
    snapshot = {
        "code_context": {
            "files": [
                {
                    "path": "core/engine/cognition/multiphase.py",
                    "content": "class MultiPhaseExecutor:\n    def execute(self):\n        pass",
                    "reason": "matched: multiphase",
                },
            ]
        }
    }
    result = assembler.build(snapshot)
    assert "Relevant Code" in result
    assert "core/engine/cognition/multiphase.py" in result
    assert "MultiPhaseExecutor" in result


def test_code_context_section_empty_when_no_files(assembler):
    result = assembler.build({"code_context": {"files": []}})
    assert "Relevant Code" not in result


def test_code_context_before_failure_memory(assembler):
    """code_context is priority-ordered; failure_memory is pinned last."""
    snapshot = {
        "code_context": {"files": [{"path": "a.py", "content": "x = 1", "reason": "matched"}]},
        "failure_memory": [{"gaps": ["missing logs"], "verdict": "gaps_found"}],
    }
    result = assembler.build(snapshot)
    assert result.index("Relevant Code") < result.index("Known Failure")


def test_code_context_uses_correct_language_fence(assembler):
    """File extension determines the code fence language."""
    snapshot = {
        "code_context": {
            "files": [
                {"path": "core/engine/core/db.py", "content": "x = 1", "reason": "matched"},
                {"path": "portal/src/App.tsx", "content": "const x = 1", "reason": "matched"},
                {"path": "schema/v1.surql", "content": "DEFINE TABLE foo", "reason": "matched"},
            ]
        }
    }
    result = assembler.build(snapshot)
    assert "```python" in result
    assert "```typescript" in result
    assert "```sql" in result


def test_failure_memory_renders_aggregated_pattern_with_count(assembler):
    snapshot = {
        "failure_memory": [
            {"pattern": "missing error propagation", "count": 3},
            {"pattern": "no logging on async path", "count": 1},
        ]
    }
    result = assembler.build(snapshot)
    assert "Known Failure" in result
    assert "missing error propagation" in result
    assert "×3" in result


def test_failure_memory_supports_legacy_raw_format(assembler):
    """Legacy raw format {gaps: [...]} still renders without breaking."""
    snapshot = {"failure_memory": [{"gaps": ["missing Retry-After header"], "verdict": "gaps_found"}]}
    result = assembler.build(snapshot)
    assert "Known Failure" in result
    assert "missing Retry-After header" in result


def test_failure_memory_empty_list_renders_nothing(assembler):
    result = assembler.build({"failure_memory": []})
    assert "Known Failure" not in result


def test_arch_decisions_rendered(assembler):
    snapshot = {
        "arch_decisions": [
            {
                "title": "Judge-executor separation",
                "decision_type": "trade_off",
                "rationale": "Same model reviewing its own output creates blind spots",
                "outcome": "accepted",
                "discipline_hint": "coding",
            },
            {
                "title": "SurrealDB as primary store",
                "decision_type": "architecture",
                "rationale": "Schema flexibility + graph queries",
                "outcome": "accepted",
                "discipline_hint": "data",
            },
        ]
    }
    result = assembler.build(snapshot)
    assert "Architectural Memory" in result
    assert "Judge-executor separation" in result
    assert "SurrealDB as primary store" in result
    assert "[trade_off]" in result
    assert "[architecture]" in result


def test_arch_decisions_empty_renders_nothing(assembler):
    assert assembler._section_arch_decisions({"arch_decisions": []}) == ""
    assert assembler._section_arch_decisions({}) == ""


def test_cost_estimate_rendered(assembler):
    snapshot = {
        "cost_estimate": {
            "discipline": "coding",
            "p50_usd": 0.0042,
            "p90_usd": 0.0091,
            "sample_count": 37,
        }
    }
    result = assembler.build(snapshot)
    assert "Cost Estimate" in result
    assert "37" in result
    assert "0.0042" in result
    assert "0.0091" in result


def test_cost_estimate_hidden_when_no_samples(assembler):
    assert assembler._section_cost_estimate({"cost_estimate": {"sample_count": 0}}) == ""
    assert assembler._section_cost_estimate({}) == ""
