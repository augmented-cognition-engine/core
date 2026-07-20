# engine/core/exceptions.py
"""ACE exception hierarchy.

All internal errors should be ACEError subclasses so callers can:
- Catch specific subtypes for targeted recovery (LLMError vs DatabaseError)
- Always get correlation_id for log correlation without manual plumbing
- Never accidentally swallow unrelated exceptions with bare `except Exception`

Usage:
    raise LLMError("Timeout after 30s")
    # → "[abc123def456] Timeout after 30s" in logs (cid auto-captured)

    try:
        ...
    except LLMError as e:
        logger.error("LLM call failed [%s]: %s", e.correlation_id, e)
        # recover or re-raise
"""

from __future__ import annotations


class ACEError(Exception):
    """Base for all ACE internal errors.

    Automatically captures the current correlation ID so errors are always
    traceable back to the originating request or job without manual threading.
    """

    def __init__(self, message: str, *, correlation_id: str = "") -> None:
        super().__init__(message)
        if not correlation_id:
            try:
                from core.engine.core.log_context import get_correlation_id

                correlation_id = get_correlation_id()
            except Exception:
                pass
        self.correlation_id = correlation_id

    def __str__(self) -> str:
        base = super().__str__()
        return f"[{self.correlation_id}] {base}" if self.correlation_id else base


class LLMError(ACEError):
    """LLM call failed (timeout, auth error, parse error, etc.)."""


class DatabaseError(ACEError):
    """Database operation failed (connection, query, write rejection, etc.)."""


class OrchestrationError(ACEError):
    """Task orchestration failed (dispatch, sequencing, handoff, etc.)."""


class ClassificationError(OrchestrationError):
    """Task classification failed or produced unusable output."""


class ValidationError(ACEError):
    """Input validation failed — missing required fields or invalid values."""


class ConfigurationError(ACEError):
    """Missing or invalid configuration — typically fatal at startup."""


class CapabilityMapperError(ACEError):
    """Capability mapping failed (graph query, LLM proposal, glob match, etc.)."""


class PrioritizationError(ACEError):
    """Prioritization scoring or ranking failed."""


class DecompositionError(OrchestrationError):
    """Spec decomposition into work units failed."""


class EcosystemError(DatabaseError):
    """Ecosystem or project operation failed."""


class EmbeddingError(ACEError):
    """Embedding generation or vector store operation failed."""


class ScannerError(ACEError):
    """Code scanner or AST parser failed."""


class EmergenceError(ACEError):
    """Specialty emergence detection or creation failed."""


class AffinityError(ACEError):
    """Specialty affinity computation or persistence failed."""
