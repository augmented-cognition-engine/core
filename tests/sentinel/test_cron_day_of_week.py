"""No sentinel may express its day-of-week as a number.

APScheduler's `CronTrigger.from_crontab()` reads day-of-week as 0=mon..6=sun. Standard
crontab — the thing everyone believes they are writing — is 0=sun..6=sat. It does not
translate between them, and it does not warn.

So every numeric DOW in this repo fired EXACTLY ONE DAY LATE for as long as it existed.
The weekly briefing (`0 6 * * 1`) was authored for Monday and ran on Tuesday. The Sunday
calibration ran Monday. The Saturday grading ran Sunday. Nothing failed and nothing
logged: each engine produced correct output, on the wrong day. Seven engines named their
intended day in their own docstring and all seven contradicted their own cron —
test_pm_optimizer even asserted `== "0 5 * * 0"  # Sunday 5 AM` while the thing ran Monday.

The fix was NAMES, not shifted numbers: `mon`/`sat`/`sun` mean the same thing in both
dialects, so the ambiguity cannot be expressed. This is the fence that keeps it that way.

AST-BASED ON PURPOSE — and the reason is the same one test_dormant_engines_wired.py gives:
parsing the source checks every engine WITHOUT importing it, so it does not populate the
module cache and cannot break the order-dependent `engine_registry.pop() + reimport` tests
elsewhere in this suite. An import-based version of this file did exactly that, and the
victim (test_perspective_gaps) had been passing only by virtue of importing first.

Parsing also reads decorators the registry never sees a literal for: two engines pass
their cron POSITIONALLY (`@register_engine("name", "0 4 * * 1", ...)`), which a sweep for
`cron="..."` misses entirely — and did.
"""

from __future__ import annotations

import ast
import pathlib
import re

import pytest

ENGINES_DIR = pathlib.Path(__file__).resolve().parents[2] / "core" / "engine" / "sentinel" / "engines"

#: A DOW field is legal only if it is `*` or made entirely of day NAMES.
_NAMED = {"mon", "tue", "wed", "thu", "fri", "sat", "sun"}
_NUMERIC = re.compile(r"\d")


def _registered_crons() -> list[tuple[str, str, str]]:
    """(file, engine, cron) for every @register_engine in the tree — by PARSING, not
    importing. Handles both keyword (`cron="…"`) and positional (`"name", "…"`) forms."""
    found: list[tuple[str, str, str]] = []
    for path in sorted(ENGINES_DIR.glob("*.py")):
        tree = ast.parse(path.read_text(), filename=str(path))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            fn = node.func
            name = fn.id if isinstance(fn, ast.Name) else getattr(fn, "attr", "")
            if name not in ("register_engine", "sentinel_engine"):
                continue

            def _str(n: ast.expr | None) -> str | None:
                return n.value if isinstance(n, ast.Constant) and isinstance(n.value, str) else None

            kw = {k.arg: _str(k.value) for k in node.keywords if k.arg}
            pos = [_str(a) for a in node.args]

            engine = kw.get("name") or (pos[0] if pos else None)
            cron = kw.get("cron") or (pos[1] if len(pos) > 1 else None)
            if engine and cron:
                found.append((path.name, engine, cron))
    return found


CRONS = _registered_crons()


@pytest.mark.parametrize("file,engine,cron", CRONS, ids=[f"{e}" for _f, e, _c in CRONS])
def test_day_of_week_is_never_numeric(file: str, engine: str, cron: str) -> None:
    parts = cron.split()
    assert len(parts) == 5, f"{engine} ({file}): a crontab has five fields, got {cron!r}"
    dow = parts[4]
    if dow == "*":
        return

    assert not _NUMERIC.search(dow), (
        f"{engine} ({file}) schedules on day-of-week {dow!r}. APScheduler reads "
        f"0=mon..6=sun, NOT the standard crontab 0=sun..6=sat, and does not translate — "
        f"so this fires ONE DAY LATER than whoever wrote it intended, silently, forever. "
        f"Use names ({', '.join(sorted(_NAMED))}), which mean the same in both dialects."
    )

    tokens = [t for t in re.split(r"[,\-]", dow.lower()) if t]
    unknown = [t for t in tokens if t not in _NAMED]
    assert not unknown, f"{engine} ({file}): unrecognized day name(s) {unknown} in {dow!r}"


def test_the_gate_is_actually_watching_something() -> None:
    """A parametrized test over an empty list passes vacuously and guards nothing. If the
    engines ever stop being discoverable, fail loudly rather than go quiet."""
    assert len(CRONS) > 10, f"expected the kernel's sentinel engines, found {len(CRONS)}"
    assert any(c.split()[4] != "*" for _f, _e, c in CRONS), (
        "no engine has a day-of-week at all — the gate would be watching nothing"
    )


def test_the_positional_form_is_actually_reachable() -> None:
    """Two engines pass their cron positionally. A sweep for `cron="..."` misses them —
    and did. If the parser ever silently stops seeing that form, this fails."""
    positional = {"self_optimizer", "template_detector"}
    seen = {e for _f, e, _c in CRONS}
    assert positional <= seen, (
        f"the positionally-registered engines are invisible to this gate: {sorted(positional - seen)}"
    )
