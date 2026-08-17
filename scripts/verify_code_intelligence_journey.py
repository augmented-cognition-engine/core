"""Run the frozen ACE-on-ACE Code Intelligence acceptance journey."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parents[1]
if (_PROJECT_ROOT / "core" / "engine" / "code_intelligence").is_dir():
    # Deterministically import this checkout's own ``core`` package, not
    # whichever copy the interpreter's site-packages happen to resolve first
    # (e.g. an unrelated worktree's editable install). A script that ships
    # installed, with no sibling ``core`` package here, falls through to
    # normal installed-package resolution.
    sys.path[:] = [entry for entry in sys.path if entry not in ("", str(_PROJECT_ROOT))]
    sys.path.insert(0, str(_PROJECT_ROOT))

from core.engine.code_intelligence.journey import CodeIntelligenceJourney

if (_PROJECT_ROOT / "core" / "engine" / "code_intelligence").is_dir():
    _origin = Path(sys.modules[CodeIntelligenceJourney.__module__].__file__).resolve()
    if _PROJECT_ROOT not in _origin.parents:
        raise RuntimeError(
            "verify_code_intelligence_journey imported "
            f"core.engine.code_intelligence.journey from {_origin}, not this checkout "
            f"({_PROJECT_ROOT}); refusing to run against a different package copy."
        )

DEFAULT_QUERY = "What breaks if core.engine.mcp.tools.ace_impact changes, and why does this path exist?"
DEFAULT_TARGET = "core/engine/mcp/tools.py"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repository", default=".")
    parser.add_argument("--query", default=DEFAULT_QUERY)
    parser.add_argument("--target", default=DEFAULT_TARGET)
    parser.add_argument("--receiver", default="coding-agent:provider-neutral")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    result = CodeIntelligenceJourney(args.repository).run(
        query=args.query,
        target_path=args.target,
        receiver_ref=args.receiver,
    )
    payload = result.model_dump(mode="json")
    payload["identities"] = {
        "index_id": result.lens.index.index_id,
        "lens_id": result.lens.lens_id,
        "manifest_id": result.handoff.manifest.manifest_id,
        "handoff_id": result.handoff.receipt.handoff_id,
    }
    rendered = json.dumps(payload, indent=2, sort_keys=True) + "\n"
    if args.output is not None:
        args.output.write_text(rendered, encoding="utf-8")
    else:
        print(rendered, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
