from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from core.engine.proactive.models import ProactiveLine
    from core.engine.voice.salience import SaliencePolicy
    from core.engine.voice.thread import VoiceThread


@dataclass
class RenderContext:
    thread: "VoiceThread | None" = None
    recent_emissions: "list[ProactiveLine]" = field(default_factory=list)
    salience_policy: "SaliencePolicy | None" = None
    fresh_payload_hash: str | None = None
    channel: str = "default"
    calibration_mode: str = "live"
