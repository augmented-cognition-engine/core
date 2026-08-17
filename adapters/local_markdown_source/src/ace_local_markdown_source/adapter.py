"""Pure Markdown/Obsidian structural parser.

`parse_markdown` turns Markdown bytes into a `MarkdownDocument`: parsed frontmatter,
sections keyed by their heading path (so a citation can anchor to an exact heading), and
deduplicated Obsidian wikilinks. It reads no files and makes no acquisition or freshness
claim; the governed local-acquisition port owns those.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

_HEADING = re.compile(r"^(#{1,6})\s+(.*\S)\s*$")
_WIKILINK = re.compile(r"\[\[([^\]]+)\]\]")


@dataclass(frozen=True, slots=True)
class MarkdownSection:
    """One section of a Markdown document, anchored by its heading path."""

    heading_path: tuple[str, ...]
    level: int
    text: str
    anchor: str


@dataclass(frozen=True, slots=True)
class MarkdownDocument:
    """The structured translation of one Markdown source."""

    frontmatter: dict[str, str]
    sections: tuple[MarkdownSection, ...]
    wikilinks: tuple[str, ...]


def _split_frontmatter(text: str) -> tuple[dict[str, str], str]:
    """Return (frontmatter, body). Frontmatter is a leading `---`-delimited block."""
    if not text.startswith("---\n"):
        return {}, text
    end = text.find("\n---", 3)
    if end == -1:
        return {}, text
    block = text[4:end]
    rest = text[end + 4 :]
    if rest.startswith("\n"):
        rest = rest[1:]
    frontmatter: dict[str, str] = {}
    for line in block.splitlines():
        if ":" not in line:
            continue
        key, _, value = line.partition(":")
        key = key.strip()
        if key:
            frontmatter[key] = value.strip()
    return frontmatter, rest


def _anchor(path: tuple[str, ...]) -> str:
    return " > ".join(path)


def parse_markdown(content: bytes) -> MarkdownDocument:
    """Parse Markdown/Obsidian bytes into a structured document."""
    text = content.decode("utf-8")
    frontmatter, body = _split_frontmatter(text)

    sections: list[MarkdownSection] = []
    stack: list[tuple[int, str]] = []
    cur_path: tuple[str, ...] = ()
    cur_level = 0
    cur_lines: list[str] = []

    def flush() -> None:
        joined = "\n".join(cur_lines).strip()
        # A heading always yields a section; a preamble only when it has text.
        if cur_level > 0 or joined:
            sections.append(
                MarkdownSection(heading_path=cur_path, level=cur_level, text=joined, anchor=_anchor(cur_path))
            )

    for line in body.splitlines():
        match = _HEADING.match(line)
        if match:
            flush()
            level = len(match.group(1))
            title = match.group(2).strip()
            while stack and stack[-1][0] >= level:
                stack.pop()
            stack.append((level, title))
            cur_path = tuple(entry[1] for entry in stack)
            cur_level = level
            cur_lines = []
        else:
            cur_lines.append(line)
    flush()

    seen: dict[str, None] = {}
    for raw in _WIKILINK.findall(body):
        target = raw.split("|", 1)[0].strip()
        if target and target not in seen:
            seen[target] = None

    return MarkdownDocument(
        frontmatter=frontmatter,
        sections=tuple(sections),
        wikilinks=tuple(seen),
    )
