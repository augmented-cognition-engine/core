"""Is this "the work was wrong" or "we never found out"?

One classifier, used everywhere an arm catches an exception, because the distinction is worthless
if each catch site decides it separately. A fail-open `except Exception` anywhere upstream of
dispatch LAUNDERS an environment failure into a work failure and defeats the parked state from
underneath — which is exactly what happened on the first live run:

    the model returned garbage → ship_planner caught it and returned zero concerns → the ship gate
    correctly refused a build with no concerns as "vacuous" → the session reported
    "ship gate surfaced no production-readiness concerns", needs_human=False, spec requeued.

Every word of that blamed the work. The model had simply never answered. The parked machinery,
built for precisely this case, never got to see the error.

So: catch broadly, but ASK before you swallow. Degrade on bad data; propagate on a dead environment.
"""

from __future__ import annotations

import asyncio
import json

from core.engine.core.exceptions import DatabaseError, LLMError

# Failures of the ENVIRONMENT, not of the work: the model never answered, the DB refused, the socket
# died, the disk filled. These park — keep the workspace, get a human, do not retry.
#
# JSONDecodeError earns its place here on evidence: complete_json gives up after THREE attempts at
# getting parseable output. A model that cannot manage that three times running is a broken model,
# not a hard question. We never found anything out, which is the definition of parked.
ENVIRONMENTAL: tuple[type[BaseException], ...] = (
    LLMError,
    DatabaseError,
    TimeoutError,
    asyncio.TimeoutError,
    ConnectionError,
    OSError,
    json.JSONDecodeError,
)


def is_environmental(exc: BaseException) -> bool:
    """True if this exception means 'we never found out', not 'the work was wrong'.

    ValueError, KeyError, AssertionError and friends are the arm getting it wrong: a normal,
    discardable, repairable failure. Everything in ENVIRONMENTAL is the ground giving way underneath
    it, and must never be reported as a bad build.
    """
    return isinstance(exc, ENVIRONMENTAL)
