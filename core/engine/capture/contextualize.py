"""Contextual chunk enrichment (index-time) — Anthropic "Contextual Retrieval", lightweight no-LLM form.

Before embedding an insight, prepend a compact STRUCTURAL context (discipline · type · tags) to the
text. The stored `content` stays raw; only the embedding vector captures the context — so retrieval can
distinguish e.g. a `security` pattern from a `ux` pattern that share wording. No LLM call (cost-
disciplined, no-API): the situating signal comes from fields the insight already carries. Asymmetric by
design — chunks are enriched, the query is embedded raw, so a domain-relevant query aligns with the
domain-prefixed chunk vector.
"""

from __future__ import annotations

_MAX_PREFIX_PARTS = 4


def _clean(token) -> str:
    """First comma-segment, trimmed — domains can be comma-joined ('a,b,c') or dotted; keep it readable."""
    if not token or not isinstance(token, str):
        return ""
    return token.split(",")[0].strip()


def contextualize_for_embedding(
    content: str,
    *,
    domain_path: str | None = None,
    insight_type: str | None = None,
    tags: list[str] | None = None,
) -> str:
    """Return `content` prefixed with a compact `[discipline · type · tag …]` context for embedding.

    Returns `content` unchanged when no context is available. Deduplicates parts and caps the prefix
    length so it situates without dominating the chunk.
    """
    parts: list[str] = []
    disc = _clean(domain_path)
    if disc:
        parts.append(disc)
    if insight_type:
        it = str(insight_type).strip()
        if it and it not in parts:
            parts.append(it)
    for t in tags or []:
        ct = str(t).strip()
        if ct and ct not in parts:
            parts.append(ct)
        if len(parts) >= _MAX_PREFIX_PARTS:
            break
    if not parts:
        return content
    return f"[{' · '.join(parts[:_MAX_PREFIX_PARTS])}] {content}"
