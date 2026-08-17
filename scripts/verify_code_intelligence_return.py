"""Validate a coding-agent return against one exact Code Intelligence journey."""

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

from core.engine.code_intelligence.contracts import (
    CodeIntelligenceJourneyV1Alpha1,
    CodingAgentReturnV1Alpha1,
)
from core.engine.code_intelligence.handoff import validate_coding_agent_return

if (_PROJECT_ROOT / "core" / "engine" / "code_intelligence").is_dir():
    _origin = Path(sys.modules[validate_coding_agent_return.__module__].__file__).resolve()
    if _PROJECT_ROOT not in _origin.parents:
        raise RuntimeError(
            "verify_code_intelligence_return imported "
            f"core.engine.code_intelligence.handoff from {_origin}, not this checkout "
            f"({_PROJECT_ROOT}); refusing to run against a different package copy."
        )

MAX_CODING_AGENT_RETURN_JSON_BYTES = 128 * 1024


def load_bounded_return(path: Path) -> CodingAgentReturnV1Alpha1:
    """Read one return only after enforcing its serialized input boundary."""

    with path.open("rb") as stream:
        encoded = stream.read(MAX_CODING_AGENT_RETURN_JSON_BYTES + 1)
    byte_count = len(encoded)
    if byte_count > MAX_CODING_AGENT_RETURN_JSON_BYTES:
        raise ValueError(f"coding-agent return exceeds {MAX_CODING_AGENT_RETURN_JSON_BYTES} byte limit: {byte_count}")
    return CodingAgentReturnV1Alpha1.model_validate_json(encoded)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--journey", type=Path, required=True)
    parser.add_argument("--return", dest="return_path", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    journey_payload = json.loads(args.journey.read_text(encoding="utf-8"))
    journey_payload.pop("identities", None)
    journey = CodeIntelligenceJourneyV1Alpha1.model_validate(journey_payload)
    returned = load_bounded_return(args.return_path)
    receipt = validate_coding_agent_return(journey.handoff, returned)
    payload = {
        "return": returned.model_dump(mode="json"),
        "return_id": returned.return_id,
        "receipt": receipt.model_dump(mode="json"),
        "receipt_id": receipt.receipt_id,
    }
    rendered = json.dumps(payload, indent=2, sort_keys=True) + "\n"
    if args.output is None:
        print(rendered, end="")
    else:
        args.output.write_text(rendered, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
