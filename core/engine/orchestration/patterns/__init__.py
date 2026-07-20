# engine/orchestration/patterns/__init__.py
"""Pattern strategy implementations."""

from core.engine.orchestration.patterns.adversarial import AdversarialPattern
from core.engine.orchestration.patterns.base import PatternConfig, PatternResult, PatternStrategy
from core.engine.orchestration.patterns.fanout import FanOutPattern
from core.engine.orchestration.patterns.independent import IndependentPattern
from core.engine.orchestration.patterns.pipeline import PipelinePattern
from core.engine.orchestration.patterns.team import TeamPattern

__all__ = [
    "AdversarialPattern",
    "FanOutPattern",
    "IndependentPattern",
    "PatternConfig",
    "PatternResult",
    "PatternStrategy",
    "PipelinePattern",
    "TeamPattern",
]
