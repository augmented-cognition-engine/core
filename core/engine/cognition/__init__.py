"""Cognitive composition layer.

Provides structured meta-skill recipes for LLM invocations.
CognitiveComposer is the main entry point.
"""

from core.engine.cognition.composer import CognitiveComposer
from core.engine.cognition.models import CognitiveComposition, derive_depth
from core.engine.cognition.phase_output import PhaseOutput

__all__ = ["CognitiveComposition", "CognitiveComposer", "derive_depth", "PhaseOutput"]
