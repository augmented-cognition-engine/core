"""Changelog generator.

Strategy:
1. Run git-cliff subprocess for commit parsing and grouping (if installed)
2. For each commit SHA found: look up manifested_by edges → decision records
3. Annotate changelog entry with decision rationale where found

git-cliff handles: parsing, grouping, deduplication, version tagging.
ACE handles: the "why" behind each commit group.
Falls back to git log when git-cliff is not installed.
"""

from __future__ import annotations

import asyncio
import re
import shutil
import subprocess

from core.engine.core.db import parse_rows, pool

_gitcliff_available = bool(shutil.which("git-cliff"))


async def generate_changelog(
    since_tag: str | None = None,
    output_format: str = "markdown",
    product_id: str = "product:platform",
) -> dict:
    """Generate enriched changelog with decision rationale layer.

    Args:
        since_tag:     Generate from this git tag. None = full changelog.
        output_format: markdown | json
        product_id:    Product for decision lookup.

    Returns: {content, generated_by, since_tag, decisions_linked}
    """
    if not _gitcliff_available:
        return await _fallback_changelog(since_tag, product_id)

    cmd = ["git-cliff", "--output", "/dev/stdout"]
    if since_tag:
        cmd += ["--tag", since_tag]

    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL,
        )
        stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=30)
        raw_changelog = stdout.decode()
    except Exception:
        return await _fallback_changelog(since_tag, product_id)

    enriched, decisions_linked = await _enrich_with_decisions(raw_changelog, product_id)

    return {
        "content": enriched,
        "generated_by": "git-cliff + ACE decision layer",
        "since_tag": since_tag,
        "decisions_linked": decisions_linked,
    }


async def _enrich_with_decisions(changelog_text: str, product_id: str) -> tuple[str, int]:
    """Annotate changelog entries with decision rationale from manifested_by edges.

    Returns: (enriched_text, decisions_linked_count)
    """
    sha_pattern = re.compile(r"\b([0-9a-f]{7,40})\b")
    shas = list(set(sha_pattern.findall(changelog_text)))
    if not shas:
        return changelog_text, 0

    try:
        async with pool.connection() as db:
            rows = parse_rows(
                await db.query(
                    """SELECT
                    gd.source_commit AS sha,
                    d.title AS decision_title,
                    d.rationale AS rationale
                FROM graph_decision AS gd
                JOIN manifested_by AS mb ON mb.out = gd.id
                JOIN decision AS d ON d.id = mb.in
                WHERE gd.source_commit IN $shas
                AND d.outcome = 'accepted'
                """,
                    {"shas": shas},
                )
            )
    except Exception:
        return changelog_text, 0

    if not rows:
        return changelog_text, 0

    sha_decisions: dict[str, list[dict]] = {}
    for row in rows:
        sha = (row.get("sha") or "")[:7]
        if sha:
            sha_decisions.setdefault(sha, []).append(row)

    decisions_linked = 0
    lines = changelog_text.split("\n")
    output: list[str] = []
    for line in lines:
        output.append(line)
        for sha, decisions in sha_decisions.items():
            if sha in line:
                for dec in decisions[:1]:
                    title = dec.get("decision_title", "")
                    rationale = (dec.get("rationale") or "")[:100]
                    if title:
                        output.append(f'  > Decision: "{title}"')
                        decisions_linked += 1
                    if rationale:
                        output.append(f"  > Why: {rationale}")

    return "\n".join(output), decisions_linked


async def _fallback_changelog(since_tag: str | None, product_id: str) -> dict:
    """Fallback: generate changelog from git log when git-cliff is not installed."""
    cmd = ["git", "log", "--oneline", "--no-merges"]
    if since_tag:
        cmd += [f"{since_tag}..HEAD"]
    try:
        output = subprocess.check_output(cmd, stderr=subprocess.DEVNULL, timeout=10).decode()
        enriched, decisions_linked = await _enrich_with_decisions(output, product_id)
        return {
            "content": enriched,
            "generated_by": "git log (git-cliff not installed)",
            "since_tag": since_tag,
            "decisions_linked": decisions_linked,
        }
    except Exception as exc:
        return {"error": str(exc), "content": "", "decisions_linked": 0}
