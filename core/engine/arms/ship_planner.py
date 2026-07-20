"""ship_planner — the SHIP arm's production-readiness assessment.

One structured LLM pass that scores built/proposed work across the five production dimensions
(security · testing · observability · devops/deploy · scale) and returns the concrete GAPS that block a
safe ship, plus recommended hardening actions. Thin over get_llm(); reasoner-injectable for tests.
Non-fatal — a failed assessment returns ([], []) and the arm's verify flags the vacuous pass.
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

_ASSESS_PROMPT = (
    "Assess the PRODUCTION-READINESS of this work before it ships:\n\n{intent}\n\n"
    "Engineers systematically miss the unhappy path. Cover ALL FIVE dimensions and name CONCRETE gaps "
    "that would block a safe ship (skip a dimension only if genuinely N/A):\n"
    "- Security: authn/authz, injection vectors, secrets handling, dependency CVEs / SBOM.\n"
    "- Testing: happy path AND edges, failure-mode tests, coverage, a scoped verify command.\n"
    "- Observability: logging, metrics, tracing, error surfaces — can you tell when it breaks?\n"
    "- DevOps/Deploy: CI/CD, rollback, config/secrets, migration safety, the deploy plan.\n"
    "- Scale: caching, retry/backoff caps, rate limits, resource bounds, load behavior.\n\n"
    'Return JSON only: {{"concerns": ["<dimension>: <concrete gap>", ...], '
    '"actions": ["<specific hardening step>", ...]}}'
)


async def assess_ship_readiness(intent: str, *, reasoner=None) -> "tuple[list[str], list[str]]":
    """Return (concerns, actions) — the production-readiness gaps + hardening steps for `intent`.

    `reasoner`: optional async (prompt:str) -> dict, injected for tests. Default → get_llm().complete_json.
    Non-fatal: any failure → ([], []).
    """
    if not intent or not intent.strip():
        return [], []
    prompt = _ASSESS_PROMPT.format(intent=intent.strip())
    try:
        if reasoner is not None:
            data = await reasoner(prompt)
        else:
            from core.engine.core.llm import get_llm

            data = await get_llm().complete_json(prompt)
        if not isinstance(data, dict):
            return [], []
        concerns = [str(c).strip() for c in (data.get("concerns") or []) if str(c).strip()]
        actions = [str(a).strip() for a in (data.get("actions") or []) if str(a).strip()]
        return concerns, actions
    except Exception as exc:
        # PROPAGATE a dead environment. Returning ([], []) here is what caused the first live run to
        # report "the ship gate surfaced no production-readiness concerns — vacuous" when the truth
        # was that the model had returned garbage three times. An empty concern list from a DEAD
        # model is not the same fact as an empty list from a model that looked and found nothing,
        # and collapsing them blames the work for the environment's failure. Let it raise; dispatch
        # parks the build and tells a human what to fix.
        from core.engine.arms.failure import is_environmental

        if is_environmental(exc):
            logger.warning("assess_ship_readiness: environment failed — PARKING rather than reporting a clean gate")
            raise
        logger.warning("assess_ship_readiness failed (non-fatal)", exc_info=True)
        return [], []
