# engine/capture/document_chunker.py
"""Split documents into sections for intelligence extraction.

Unlike the stream chunker (which buffers real-time events), this operates
on complete document content — split by markdown headings or paragraphs.
"""

from __future__ import annotations

import re


def chunk_document(content: str) -> list[dict]:
    """Split markdown content into sections. Returns list of section dicts."""
    content = content.strip()
    if not content:
        return []

    # Try splitting by markdown headings (##, ###, etc.)
    sections = _split_by_headings(content)
    if len(sections) >= 2:
        return sections

    # Fallback: split by double newline (paragraphs)
    return _split_by_paragraphs(content)


def _split_by_headings(content: str) -> list[dict]:
    """Split content at ## or ### boundaries."""
    pattern = r"^(#{1,4})\s+(.+)$"
    lines = content.split("\n")
    sections = []
    current_title = ""
    current_lines = []

    for line in lines:
        match = re.match(pattern, line)
        if match:
            # Save previous section
            if current_lines:
                text = "\n".join(current_lines).strip()
                if text:
                    sections.append(
                        {
                            "section_title": current_title or "Introduction",
                            "content": text,
                            "index": len(sections),
                        }
                    )
            current_title = match.group(2).strip()
            current_lines = []
        else:
            current_lines.append(line)

    # Save last section
    if current_lines:
        text = "\n".join(current_lines).strip()
        if text:
            sections.append(
                {
                    "section_title": current_title or "Introduction",
                    "content": text,
                    "index": len(sections),
                }
            )

    return sections


def _split_by_paragraphs(content: str) -> list[dict]:
    """Split content by double newlines."""
    paragraphs = [p.strip() for p in re.split(r"\n\n+", content) if p.strip()]
    return [
        {
            "section_title": p[:50].rstrip(".") if len(p) > 50 else p.split(".")[0],
            "content": p,
            "index": i,
        }
        for i, p in enumerate(paragraphs)
    ]
