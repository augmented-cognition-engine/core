"""CLI for reproducible evaluation reports."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from .harness import evaluate_suite, load_suite, render_markdown


def main() -> None:
    parser = argparse.ArgumentParser(description="Score recorded ACE baseline/ablation responses")
    parser.add_argument("suite", type=Path)
    parser.add_argument("--json-out", type=Path, required=True)
    parser.add_argument("--markdown-out", type=Path, required=True)
    parser.add_argument("--allow-paid-live", action="store_true")
    args = parser.parse_args()
    suite = load_suite(args.suite)
    if suite["run_kind"] == "live" and not (args.allow_paid_live and os.environ.get("ACE_EVAL_ALLOW_PAID") == "1"):
        parser.error("live evaluation requires --allow-paid-live and ACE_EVAL_ALLOW_PAID=1")
    result = evaluate_suite(suite)
    args.json_out.parent.mkdir(parents=True, exist_ok=True)
    args.markdown_out.parent.mkdir(parents=True, exist_ok=True)
    args.json_out.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    args.markdown_out.write_text(render_markdown(result), encoding="utf-8")


if __name__ == "__main__":
    main()
