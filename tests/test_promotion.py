from __future__ import annotations


class _FakeDB:
    def __init__(self):
        self.queries = []

    async def query(self, q, params=None):
        self.queries.append((q.strip(), params or {}))
        return []


class _FakePool:
    def __init__(self, db):
        self._db = db

    def connection(self):
        db = self._db

        class Ctx:
            async def __aenter__(self):
                return db

            async def __aexit__(self, *a):
                return False

        return Ctx()


class _WS:
    branch = "arm/scaffold-9f2"
    path = "/repo/.worktrees/arm-9f2"
    repo_root = "/repo"

    def diff(self):
        return "+1 -0"


def test_capture_records_workspace_path_and_repo_root():
    import asyncio

    from core.engine.arms.base import Action, ActionPlan, ArmResult, RiskTier, Verdict
    from core.engine.arms.outcome import capture_outcome
    from core.engine.solution import Solution

    db = _FakeDB()
    pool = _FakePool(db)
    res = ArmResult(
        plan=ActionPlan(summary="x"),
        performed=[Action(verb="write_file", args={}, risk=RiskTier.REVERSIBLE)],
        simulated=False,
        logs=[],
        workspace=_WS(),
    )
    sol = Solution(intent="build", spec_id="agent_spec:abc")
    asyncio.run(capture_outcome(sol, "scaffold", res, Verdict(passed=True, reason="ok"), "product:platform", pool=pool))

    create_q = next(q for q in db.queries if q[0].upper().startswith("CREATE"))
    assert create_q[1]["wpath"] == "/repo/.worktrees/arm-9f2"
    assert create_q[1]["wroot"] == "/repo"


import os
import subprocess


def _repo_with_arm_branch(root, *, conflict=False):
    """A git repo on 'main' with an 'arm/x' branch that adds new.txt (or, if
    conflict=True, edits the same line of f.txt as main does)."""
    os.makedirs(root, exist_ok=True)

    def g(*a):
        return subprocess.run(["git", "-C", root, *a], check=True, capture_output=True)

    subprocess.run(["git", "init", "-q", "-b", "main", root], check=True)
    g("config", "user.email", "t@t")
    g("config", "user.name", "t")
    with open(os.path.join(root, "f.txt"), "w") as fh:
        fh.write("base\n")
    g("add", "-A")
    g("commit", "-qm", "base")
    g("branch", "arm/x")
    g("checkout", "-q", "arm/x")
    if conflict:
        with open(os.path.join(root, "f.txt"), "w") as fh:
            fh.write("ARM EDIT\n")
    else:
        with open(os.path.join(root, "new.txt"), "w") as fh:
            fh.write("arm work\n")
    g("add", "-A")
    g("commit", "-qm", "arm change")
    g("checkout", "-q", "main")
    if conflict:
        with open(os.path.join(root, "f.txt"), "w") as fh:
            fh.write("MAIN EDIT\n")
        g("add", "-A")
        g("commit", "-qm", "main change")


def test_merge_and_validate_happy(tmp_path):
    from core.engine.arms.promotion import _merge_and_validate

    repo = str(tmp_path / "r")
    _repo_with_arm_branch(repo)
    out = _merge_and_validate(repo, "arm/x", ["true"])
    assert out["ok"] is True
    assert os.path.exists(os.path.join(repo, "new.txt"))
    assert out["merge_sha"] != out["pre_sha"]


def test_merge_and_validate_gate_red_reverts(tmp_path):
    from core.engine.arms.promotion import _merge_and_validate

    repo = str(tmp_path / "r")
    _repo_with_arm_branch(repo)
    pre = subprocess.run(["git", "-C", repo, "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()
    out = _merge_and_validate(repo, "arm/x", ["false"])
    assert out["ok"] is False
    now = subprocess.run(["git", "-C", repo, "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()
    assert now == pre
    assert not os.path.exists(os.path.join(repo, "new.txt"))


def test_merge_and_validate_conflict_refuses(tmp_path):
    from core.engine.arms.promotion import _merge_and_validate

    repo = str(tmp_path / "r")
    _repo_with_arm_branch(repo, conflict=True)
    pre = subprocess.run(["git", "-C", repo, "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()
    out = _merge_and_validate(repo, "arm/x", ["true"])
    assert out["ok"] is False
    now = subprocess.run(["git", "-C", repo, "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()
    assert now == pre
    assert open(os.path.join(repo, "f.txt")).read() == "MAIN EDIT\n"


def test_merge_and_validate_gate_missing_reverts(tmp_path):
    from core.engine.arms.promotion import _merge_and_validate

    repo = str(tmp_path / "r")
    _repo_with_arm_branch(repo)
    pre = subprocess.run(["git", "-C", repo, "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()
    out = _merge_and_validate(repo, "arm/x", ["definitely_not_a_real_binary_xyz123"])
    assert out["ok"] is False  # no verdict → treated as red
    now = subprocess.run(["git", "-C", repo, "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()
    assert now == pre  # merge reverted, base intact
    assert not os.path.exists(os.path.join(repo, "new.txt"))


def test_merge_and_validate_empty_or_none_gate_no_merge(tmp_path):
    from core.engine.arms.promotion import _merge_and_validate

    repo = str(tmp_path / "r")
    _repo_with_arm_branch(repo)
    pre = subprocess.run(["git", "-C", repo, "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()
    for bad in ([], None):
        out = _merge_and_validate(repo, "arm/x", bad)
        assert out["ok"] is False  # rejected before any merge
        now = subprocess.run(["git", "-C", repo, "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()
        assert now == pre  # nothing merged
        assert not os.path.exists(os.path.join(repo, "new.txt"))


def test_merge_and_validate_reset_failure_is_reported(tmp_path, monkeypatch):
    import core.engine.arms.promotion as P

    repo = str(tmp_path / "r")
    _repo_with_arm_branch(repo)

    real_git = P._git

    def fake_git(repo_root, *args):
        if args[:1] == ("reset",):

            class R:
                returncode = 1
                stdout = ""
                stderr = "reset boom"

            return R()
        return real_git(repo_root, *args)

    monkeypatch.setattr(P, "_git", fake_git)

    out = P._merge_and_validate(repo, "arm/x", ["false"])  # gate red → revert path → reset fails
    assert out["ok"] is False
    assert "manual intervention" in out["reason"].lower()  # does NOT claim a clean revert


def test_promote_refuses_when_spec_not_built():
    import asyncio

    from core.engine.arms.promotion import promote

    class DB:
        async def query(self, q, params=None):
            if "FROM AGENT_SPEC" in q.upper():
                return [{"status": "building"}]  # not built
            return []

    out = asyncio.run(promote("agent_spec:abc", "product:platform", gate_cmd=["true"], pool=_FakePool(DB())))
    assert out["promoted"] is False
    assert "built" in out["reason"]


def test_promote_refuses_dirty_tree(tmp_path):
    import asyncio

    from core.engine.arms.promotion import promote

    repo = str(tmp_path / "r")
    _repo_with_arm_branch(repo)
    with open(os.path.join(repo, "dirty.txt"), "w") as fh:
        fh.write("wip\n")  # uncommitted change

    class DB:
        async def query(self, q, params=None):
            u = q.upper()
            if "FROM AGENT_SPEC" in u:
                return [{"status": "built"}]
            if "FROM ACTION_OUTCOME" in u:
                return [
                    {
                        "workspace_branch": "arm/x",
                        "workspace_path": repo + "/.worktrees/arm-x",
                        "workspace_repo_root": repo,
                        "created_at": "2026-06-20T00:00:00Z",
                    }
                ]
            return []

    out = asyncio.run(promote("agent_spec:abc", "product:platform", gate_cmd=["true"], pool=_FakePool(DB())))
    assert out["promoted"] is False
    assert "clean" in out["reason"].lower() or "stash" in out["reason"].lower()


def test_gate_for_domain_selects_design_data_vs_default():
    from core.engine.arms.promotion import _DATA_GATE, _DEFAULT_GATE, _DESIGN_GATE, _gate_for_domain

    assert _gate_for_domain("design") == _DESIGN_GATE
    assert "vitest" in " ".join(_gate_for_domain("design"))  # the TS enforcement battery
    assert "__enforcement__" in " ".join(_gate_for_domain("design"))
    assert _gate_for_domain("data") == _DATA_GATE  # data -> real migration apply
    assert "test_schema_idempotency" in " ".join(_gate_for_domain("data"))
    assert _gate_for_domain("code") == _DEFAULT_GATE
    assert _gate_for_domain(None) == _DEFAULT_GATE
    assert _gate_for_domain("other") == _DEFAULT_GATE


def _promote_capturing_gate(tmp_path, monkeypatch, *, arm_domain, gate_cmd=None):
    """Run promote on a clean real repo with _merge_and_validate mocked to capture the gate."""
    import asyncio

    import core.engine.arms.promotion as P

    repo = str(tmp_path / "r")
    _repo_with_arm_branch(repo)
    captured = {}

    def fake_merge(repo_root, branch, gate):
        captured["gate"] = tuple(gate)
        return {"ok": True, "merge_sha": "deadbeef", "pre_sha": "base"}

    monkeypatch.setattr(P, "_merge_and_validate", fake_merge)

    class DB:
        async def query(self, q, params=None):
            u = q.upper()
            if "FROM AGENT_SPEC" in u:
                return [{"status": "built"}]
            if "FROM ACTION_OUTCOME" in u:
                return [
                    {
                        "workspace_branch": "arm/x",
                        "workspace_path": repo + "/.worktrees/arm-x",
                        "workspace_repo_root": repo,
                        "arm_domain": arm_domain,
                        "created_at": "2026-06-21T00:00:00Z",
                    }
                ]
            return []

    out = asyncio.run(P.promote("agent_spec:abc", "product:platform", gate_cmd=gate_cmd, pool=_FakePool(DB())))
    return out, captured.get("gate")


def test_promote_derives_design_gate_when_none(tmp_path, monkeypatch):
    import core.engine.arms.promotion as P

    out, gate = _promote_capturing_gate(tmp_path, monkeypatch, arm_domain="design")
    assert out["promoted"] is True, out
    assert gate == P._DESIGN_GATE  # design spec -> TS enforcement battery


def test_promote_derives_default_gate_for_code(tmp_path, monkeypatch):
    import core.engine.arms.promotion as P

    out, gate = _promote_capturing_gate(tmp_path, monkeypatch, arm_domain="code")
    assert out["promoted"] is True, out
    assert gate == P._DEFAULT_GATE  # non-design -> Python fast suite


def test_promote_explicit_gate_overrides_derivation(tmp_path, monkeypatch):
    # An explicitly-passed gate wins even for a design spec (tests/advanced callers).
    out, gate = _promote_capturing_gate(tmp_path, monkeypatch, arm_domain="design", gate_cmd=["true"])
    assert out["promoted"] is True, out
    assert gate == ("true",)


def test_reject_requeues_spec_and_records():
    import asyncio

    from core.engine.arms.promotion import reject

    class DB:
        def __init__(self):
            self.writes = []

        async def query(self, q, params=None):
            u = q.upper()
            if u.startswith("UPDATE"):
                self.writes.append(("update", q))
                return []
            if u.startswith("CREATE"):
                self.writes.append(("create", q))
                return []
            if "FROM ACTION_OUTCOME" in u:
                return []  # no worktree to discard (keeps the test pure)
            return []

    db = DB()
    out = asyncio.run(reject("agent_spec:abc", "product:platform", pool=_FakePool(db)))
    assert out["rejected"] is True
    update = next(w for w in db.writes if w[0] == "update")
    assert "approved" in update[1]  # spec re-queued to 'approved'
    assert any(w[0] == "create" for w in db.writes)  # rejection recorded


def test_ace_promote_tool_delegates(monkeypatch):
    import asyncio

    import core.engine.mcp.tools as tools

    async def fake_promote(spec_id, product_id="product:platform", gate_cmd=("make", "test-fast"), pool=None):
        return {"promoted": True, "reason": "merged + shipped", "merge_sha": "abc123"}

    monkeypatch.setattr("core.engine.arms.promotion.promote", fake_promote)

    out = asyncio.run(tools.ace_promote("agent_spec:abc"))
    assert out["promoted"] is True
    assert out["merge_sha"] == "abc123"
