"""Prompt cache optimization — stable prefix + dynamic suffix.

ACE's prompts change every turn because intelligence is injected per discipline.
Instead of tracking cache breaks (which happen by design), split the prompt:
- Stable prefix: base system instructions, tool descriptions (cacheable)
- Dynamic suffix: discipline intelligence, session memory (changes per turn)

Only the stable prefix should get cache_control markers.
"""

from __future__ import annotations

import hashlib
import json


class PromptCacheManager:
    """Manages prompt cache by separating stable and dynamic content."""

    def __init__(self) -> None:
        self.stable_hash: str | None = None
        self.dynamic_hash: str | None = None
        self.tools_hash: str | None = None
        self.break_count: int = 0
        self.latched_headers: set[str] = set()

    def record(self, system_prompt: str, tool_names: list[str]) -> None:
        """Record prompt state. Only counts tool changes as cache breaks."""
        new_tools_hash = self._hash(json.dumps(sorted(tool_names)))

        # Tools changing is a real cache break
        if self.tools_hash is not None and new_tools_hash != self.tools_hash:
            self.break_count += 1

        self.tools_hash = new_tools_hash
        # Store full hash for has_changed() compatibility
        self.stable_hash = self._hash(system_prompt)

    @property
    def prompt_hash(self) -> str | None:
        """Backward compat — returns stable hash."""
        return self.stable_hash

    def has_changed(self, system_prompt: str, tool_names: list[str]) -> bool:
        """Check if tool set changed (dynamic prompt changes are expected)."""
        return self._hash(json.dumps(sorted(tool_names))) != self.tools_hash

    def latch_header(self, header: str) -> None:
        self.latched_headers.add(header)

    def _hash(self, content: str) -> str:
        return hashlib.sha256(content.encode()).hexdigest()[:16]
