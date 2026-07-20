"""Arm registry — register arms + route a Solution to the arm(s) that can handle it.

This module implements a two-part system:

1. **Arm Registration**: The @register_arm decorator populates a module-level registry of
   Arm subclasses. Each arm class registers itself at import time, allowing centralized
   discovery and routing of specialized handlers.

2. **Lazy Loading**: _ensure_arms_loaded() imports built-in arm modules at routing time
   (not module import time), avoiding circular dependencies that would arise from importing
   arms in this module's top level. The mechanism is idempotent and handles sys.modules
   cache hits: if a module is already imported (e.g. by a prior test), __import__ is a
   no-op, but we fall back to direct registration by inspecting the cached module's
   Arm subclasses.

3. **Fault Tolerance**: Per-arm instantiation and scoring are wrapped in try-except, so
   a single arm's failure does not prevent routing through other arms. Failures are
   logged at debug level for non-fatal operational visibility.

4. **Routing Logic**: route() scores each registered arm via match_score(), sorts by
   score (most-specific first), and instantiates matching arms in descending order.
   The sorting prevents silent misroute: a weakly-matching arm (e.g. substring match)
   cannot shadow a strongly-specific arm if the latter registers later. Ties are broken
   by registration order (FIFO).
"""

from __future__ import annotations

import logging

from core.engine.arms.base import Arm
from core.engine.solution import Solution

logger = logging.getLogger(__name__)

_registry: list[type[Arm]] = []
_loaded = False


def _ensure_arms_loaded() -> None:
    """Import the built-in arm modules so their @register_arm runs. Lazy + idempotent —
    done at route() time (runtime), which avoids the circular import that importing arms
    from this module's top level (or arms/__init__) would cause.

    If a module is already in sys.modules (e.g. imported by an earlier test), __import__
    is a no-op and @register_arm won't re-fire. In that case we pull the arm class from
    the cached module and register it directly if it isn't already present.
    """
    import sys

    global _loaded
    if _loaded:
        return
    _loaded = True
    for mod in ("scaffold_arm", "code_arm", "design_arm", "data_arm", "ship_arm"):  # MAKE arms + SHIP gate
        fqn = f"core.engine.arms.{mod}"
        try:
            __import__(fqn)
            cached = sys.modules.get(fqn)
            if cached is not None:
                # Ensure every Arm subclass in the module is registered — handles the
                # case where the module was already cached (sys.modules hit) so
                # @register_arm didn't re-fire on this __import__ call.
                for attr in vars(cached).values():
                    if isinstance(attr, type) and issubclass(attr, Arm) and attr is not Arm and attr not in _registry:
                        _registry.append(attr)
        except Exception as exc:
            logger.warning("arm bootstrap: failed to import %s (non-fatal): %s", mod, exc)


def register_arm(cls: type[Arm]) -> type[Arm]:
    """Class decorator — register an Arm subclass."""
    _registry.append(cls)
    return cls


def route(solution: Solution) -> list[Arm]:
    """Instantiate the registered arms that can handle the solution, MOST-SPECIFIC FIRST.

    dispatch takes arms[0], so ordering matters: we sort by match_score (higher = more
    specific) and break ties by registration order. This prevents an earlier-registered arm
    that only weakly matches (e.g. a substring) from shadowing a more specific arm — the
    silent-misroute that put design specs through the Code arm. Non-fatal per-arm.
    """
    _ensure_arms_loaded()
    scored: list[tuple[int, int, Arm]] = []
    for idx, cls in enumerate(_registry):
        try:
            arm = cls()
            score = arm.match_score(solution)
            if score > 0:
                # higher score first; on a tie, lower idx (earlier registration) first
                scored.append((score, -idx, arm))
        except Exception as exc:
            logger.debug("arm %s routing failed (non-fatal): %s", getattr(cls, "domain", cls), exc)
    scored.sort(key=lambda t: (t[0], t[1]), reverse=True)
    return [arm for _score, _neg_idx, arm in scored]
