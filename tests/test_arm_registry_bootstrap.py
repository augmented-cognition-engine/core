from __future__ import annotations


def test_route_autoloads_builtin_arms_without_explicit_import():
    """route() must find the built-in arms even if the caller never imported their modules
    (the production path: dispatch_solution -> route, no arm import)."""
    import core.engine.arms.registry as reg
    from core.engine.solution import Solution

    # Simulate a fresh process: clear the registry + reset the loaded flag.
    reg._registry.clear()
    reg._loaded = False

    arms = reg.route(Solution(intent="write some code", domain_hint="code"))
    domains = [a.domain for a in arms]
    assert "code" in domains, f"CodeArm not auto-registered: {domains}"

    scaffold = reg.route(Solution(intent="scaffold a file", domain_hint="scaffold"))
    assert "scaffold" in [a.domain for a in scaffold], "ScaffoldArm not auto-registered"


def test_design_arm_autoloads():
    import core.engine.arms.registry as reg

    reg._registry.clear()
    reg._loaded = False
    from core.engine.solution import Solution

    arms = reg.route(Solution(intent="design a panel", domain_hint="design"))
    assert any(a.domain == "design" for a in arms), [a.domain for a in arms]


def test_data_arm_autoloads_and_routes():
    import core.engine.arms.registry as reg

    reg._registry.clear()
    reg._loaded = False
    from core.engine.solution import Solution

    arms = reg.route(Solution(intent="add a schema migration for widgets", domain_hint="data"))
    assert arms and arms[0].domain == "data", [a.domain for a in arms]
