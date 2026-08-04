#!/usr/bin/env python3
"""Start the ACE Session Intelligence Worker."""

from __future__ import annotations

import logging
import os
import sys
from pathlib import Path

# The REPO ROOT, so `core.engine.*` resolves — the package root is `core`, and every
# import in the worker (and everything it pulls in) is spelled `core.engine.…`.
#
# This walked up one level too few after the tree moved to core/, landing on `.../ace/core`
# and putting the package's INSIDE on the path instead of its parent. The failure was
# quiet and misleading in equal measure: `engine.worker.app` then half-resolved (there IS a
# `core/engine/worker/app.py`), so uvicorn would find the module and the module's own
# `from core.engine…` imports would blow up somewhere else entirely.
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

os.environ.setdefault("SURREAL_NS", "ace")
os.environ.setdefault("SURREAL_DB", "ace")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)

if __name__ == "__main__":
    import uvicorn

    host = os.environ.get("ACE_WORKER_HOST", "0.0.0.0")
    try:
        port = int(os.environ.get("ACE_WORKER_PORT", "37778"))
    except ValueError as exc:
        raise SystemExit("ACE_WORKER_PORT must be an integer") from exc
    if not 1 <= port <= 65_535:
        raise SystemExit("ACE_WORKER_PORT must be between 1 and 65535")

    # core.engine.worker.app — NOT engine.worker.app, which is where this pointed before
    # the tree moved under core/ and is why every restart attempt died on import.
    uvicorn.run("core.engine.worker.app:app", host=host, port=port, reload=False)
