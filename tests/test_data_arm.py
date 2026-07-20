from __future__ import annotations

import pytest

import core.engine.arms.data_planner as dp


class _FakeLLM:
    def __init__(self, payload):
        self._payload = payload

    async def complete_json(self, prompt):
        return self._payload


@pytest.mark.asyncio
async def test_codegen_returns_surql_none_testcmd_concerns(monkeypatch):
    monkeypatch.setattr(
        dp,
        "get_llm",
        lambda: _FakeLLM(
            {
                "files": [{"path": "core/schema/v127_widget.surql", "content": "DEFINE TABLE widget SCHEMALESS;\n"}],
                "concerns": ["additive new table"],
            }
        ),
    )
    files, test_cmd, concerns = await dp.default_codegen("add a widget table", "additive", {"max_version": 126})
    assert files and files[0]["path"].endswith(".surql")
    assert test_cmd is None
    assert concerns == ["additive new table"]


@pytest.mark.asyncio
async def test_critic_flags_planted_violation(monkeypatch, tmp_path):
    schema = tmp_path / "core" / "ui"  # wrong on purpose? no — use real path
    schema = tmp_path / "core" / "schema"
    schema.mkdir(parents=True)
    (schema / "v001_base.surql").write_text("DEFINE TABLE agent_spec SCHEMALESS;\n")
    (schema / "v002_bad.surql").write_text("DEFINE FIELD org ON agent_spec TYPE string;\n")  # required, no default

    class _WS:
        path = str(tmp_path)

    monkeypatch.setattr(dp, "get_llm", lambda: _FakeLLM({"uncovered": []}))
    ok, uncovered = await dp.default_critic(["additive"], _WS())
    assert ok is False
    assert any("org" in u and "DEFAULT" in u for u in uncovered), uncovered


@pytest.mark.asyncio
async def test_critic_passes_clean_additive(monkeypatch, tmp_path):
    schema = tmp_path / "core" / "schema"
    schema.mkdir(parents=True)
    (schema / "v001_base.surql").write_text("DEFINE TABLE agent_spec SCHEMALESS;\n")
    (schema / "v002_widget.surql").write_text(
        "DEFINE TABLE widget SCHEMALESS;\nDEFINE FIELD name ON widget TYPE string;\n"
    )

    class _WS:
        path = str(tmp_path)

    monkeypatch.setattr(dp, "get_llm", lambda: _FakeLLM({"uncovered": []}))
    ok, uncovered = await dp.default_critic([], _WS())
    assert ok is True and uncovered == [], uncovered


@pytest.mark.asyncio
async def test_critic_fails_closed_on_scan_error(monkeypatch, tmp_path):
    import core.engine.arms.migration_safety as ms

    def boom(*a, **k):
        raise RuntimeError("parser exploded")

    monkeypatch.setattr(ms, "parse_schema_dir", boom)
    monkeypatch.setattr(dp, "get_llm", lambda: _FakeLLM({"uncovered": []}))

    class _WS:
        path = str(tmp_path)

    ok, uncovered = await dp.default_critic([], _WS())
    assert ok is False
    assert any("did not run" in u for u in uncovered), uncovered


from core.engine.solution import Solution


def _stub_data_arm():
    from core.engine.arms.data_arm import DataArm

    async def classifier(s, c, o):
        from core.engine.arms.strategy.profile import WorkProfile

        return WorkProfile(scope="nearby", novelty="extend", risk="isolated", verify_depth="smoke")

    async def loader(i, product_id="product:platform"):
        return {"next_version": 127, "tables": ["agent_spec"]}

    async def reasoner(i, c, product_id="product:platform"):
        return "additive new table"

    async def codegen(i, r, c):
        return (
            [{"path": "core/schema/v127_widget.surql", "content": "DEFINE TABLE widget SCHEMALESS;\n"}],
            None,
            ["additive new table"],
        )

    async def critic(concerns, ws):
        return True, []

    return DataArm(classifier=classifier, loader=loader, reasoner=reasoner, codegen=codegen, critic=critic, scorer=None)


def test_data_can_handle_data_not_code_or_design():
    arm = _stub_data_arm()
    assert arm.can_handle(Solution(intent="add a migration for the widget table", domain_hint=None)) is True
    assert arm.can_handle(Solution(intent="x", domain_hint="data")) is True
    assert arm.can_handle(Solution(intent="fix a python bug", domain_hint="code")) is False
    assert arm.can_handle(Solution(intent="design a settings panel", domain_hint="design")) is False


@pytest.mark.asyncio
async def test_data_plan_writes_migration_no_test_cmd():
    arm = _stub_data_arm()
    plan = await arm.plan(Solution(intent="add the widget table", domain_hint="data"))
    assert plan.test_cmd is None
    assert plan.actions and plan.actions[0].args["path"].endswith(".surql")
    assert "additive new table" in plan.surfaced_concerns


def test_data_arm_default_wires_planner_and_classifier():
    import core.engine.arms.data_planner as dp
    from core.engine.arms.data_arm import DataArm
    from core.engine.arms.strategy.graph_classifier import graph_grounded_classifier

    arm = DataArm()
    assert arm._classifier is graph_grounded_classifier
    assert arm._critic is dp.default_critic
