"""Domain-neutral Intelligence detection strategies."""

from ace.intelligence.detection.categorical_transition import (
    CategoricalTransitionDetectionError,
    detect_categorical_shift,
    detect_live_categorical_shift,
    route_categorical_shift_as_signal,
    route_live_categorical_shift_as_signal,
)
from ace.intelligence.detection.numeric_delta import (
    NumericDeltaDetectionError,
    detect_live_numeric_shift,
    detect_numeric_shift,
    route_live_shift_as_signal,
    route_shift_as_signal,
)

__all__ = [
    "CategoricalTransitionDetectionError",
    "NumericDeltaDetectionError",
    "detect_categorical_shift",
    "detect_live_categorical_shift",
    "detect_live_numeric_shift",
    "detect_numeric_shift",
    "route_categorical_shift_as_signal",
    "route_live_categorical_shift_as_signal",
    "route_live_shift_as_signal",
    "route_shift_as_signal",
]
