"""Guard that the previously-dormant sentinel engines are both registered AND scheduler-wired.

Registration (@register_engine) is necessary but NOT sufficient: the scheduler builds cron jobs from
engine_registry, populated ONLY by the explicit import block in api/main.py (pkgutil discovery is
lazy/post-start). An engine imported nowhere registers but never runs — the dormancy that left these
four loops cold. See the C-lesson precedent (test_roadmap_reconciler.py).
"""

from __future__ import annotations

import pathlib

import pytest

# (module, registered-engine-name)
_ACTIVATED = [
    ("embedding_reconciler", "embedding_reconciler"),
    ("edge_inference_sweeper", "edge_inference_sweeper"),
    ("decision_capability_backfill", "decision_capability_backfill"),
]


@pytest.mark.parametrize("module,name", _ACTIVATED)
def test_engine_registered(module, name):
    __import__(f"core.engine.sentinel.engines.{module}")
    from core.engine.sentinel.registry import get_engine

    assert get_engine(name) is not None, f"{name} did not register via @register_engine"


@pytest.mark.parametrize("module,name", _ACTIVATED)
def test_engine_wired_into_main(module, name):
    main_src = pathlib.Path("core/engine/api/main.py").read_text()
    assert f"engines.{module}" in main_src, (
        f"{module} is registered but not imported in api/main.py lifespan — it will register but "
        f"never be scheduled (the dormant-engine gap)"
    )


def test_skill_emergence_stays_deliberately_off():
    """skill_emergence's decorator is commented out on purpose — it must NOT be wired (documents the
    distinction between forgotten-wiring and intentional-disable)."""
    main_src = pathlib.Path("core/engine/api/main.py").read_text()
    assert "engines.skill_emergence" not in main_src, "skill_emergence is intentionally disabled"


def test_every_registered_engine_takes_product_id_first():
    """The scheduler invokes every engine as fn(product_id) — a single positional product-id string
    (scheduler.py _execute_engine_inner). An engine whose first param is `pool`/`db`/anything else
    silently AttributeErrors on EVERY cron fire (the decision_capability_backfill bug — registered
    as (pool), called with the product string). Guard the contract for ALL engines at CI.

    AST-based on purpose: parsing source (not importing) checks every engine WITHOUT caching modules,
    so it can't break the order-dependent `engine_registry.pop()+reimport` tests elsewhere. Commented
    decorators (e.g. skill_emergence) are naturally ignored — they aren't in the AST."""
    import ast
    import pathlib

    eng_dir = pathlib.Path("core/engine/sentinel/engines")
    offenders = []
    for f in sorted(eng_dir.glob("*.py")):
        tree = ast.parse(f.read_text(), filename=str(f))
        for node in ast.walk(tree):
            if not isinstance(node, (ast.AsyncFunctionDef, ast.FunctionDef)):
                continue
            decorated = False
            for dec in node.decorator_list:
                target = dec.func if isinstance(dec, ast.Call) else dec
                dec_name = getattr(target, "id", None) or getattr(target, "attr", None)
                if dec_name == "register_engine":
                    decorated = True
                    break
            if not decorated:
                continue
            args = node.args.args
            first = args[0].arg if args else None
            if first != "product_id":
                offenders.append((f.name, node.name, first))

    assert not offenders, (
        f"these engines violate the scheduler contract fn(product_id) and will AttributeError on "
        f"every cron run: {offenders}"
    )
