"""Error explanation pipeline.

Given a Python traceback (or any error string), returns:
1. Plain-English explanation of what went wrong
2. The specific ACE capability/decision governing the failing code
3. Fix commands
4. Whether this error has been seen before (runbook lookup)

Pipeline: parse_traceback → locate capabilities → load decisions
          → LLM explain → check/capture runbook

All steps fail gracefully: partial failure = partial result, never raises.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class ErrorContext:
    """Parsed traceback with enriched context."""

    error_type: str
    error_message: str
    traceback_files: list[str]
    innermost_file: str | None
    innermost_line: int | None
    related_capabilities: list[dict] = field(default_factory=list)
    related_decisions: list[dict] = field(default_factory=list)
    existing_runbook: dict | None = None
    explanation: str = ""
    fix_commands: list[str] = field(default_factory=list)


def parse_traceback(error_text: str) -> dict:
    """Extract structured data from a Python traceback.

    Returns: {files: [{path, line}], error_type, error_message, innermost}
    """
    file_pattern = re.compile(r'File "([^"]+)", line (\d+)')
    files = [{"path": m.group(1), "line": int(m.group(2))} for m in file_pattern.finditer(error_text)]
    last_line = error_text.strip().split("\n")[-1]
    if ":" in last_line:
        error_type = last_line.split(":")[0].strip()
        error_message = last_line.split(":", 1)[1].strip()
    else:
        error_type = last_line.strip() or "UnknownError"
        error_message = ""

    return {
        "files": files,
        "error_type": error_type,
        "error_message": error_message,
        "innermost": files[-1] if files else None,
    }


def _extract_fix_commands(explanation_text: str) -> list[str]:
    """Extract lines starting with 'FIX:' from LLM output."""
    return [line[4:].strip() for line in explanation_text.split("\n") if line.strip().startswith("FIX:")]


def _build_explanation_prompt(
    error_text: str,
    context: str,
    capabilities: list[dict],
    decisions: list[dict],
    existing_runbook: dict | None,
) -> str:
    parts = [
        "You are ACE, a debugging assistant with full knowledge of this codebase.",
        "",
        "ERROR:",
        error_text[:2000],
    ]
    if context:
        parts += ["", "CONTEXT:", context[:500]]
    if capabilities:
        parts += ["", "AFFECTED CAPABILITIES:"]
        for cap in capabilities[:3]:
            parts.append(f"- {cap.get('slug', '?')}: {(cap.get('description') or '')[:100]}")
    if decisions:
        parts += ["", "RELEVANT DECISIONS:"]
        for dec in decisions[:2]:
            parts.append(f"- {dec.get('title', '?')}: {(dec.get('rationale') or '')[:100]}")
    if existing_runbook:
        parts += ["", "SIMILAR PAST ERROR (check if relevant):"]
        parts.append((existing_runbook.get("content") or "")[:300])
    parts += [
        "",
        "Provide:",
        "1. Plain-English explanation (2-3 sentences, no jargon)",
        "2. Root cause (1 sentence)",
        "3. Fix steps — prefix each with 'FIX:' followed by a command or code change",
    ]
    return "\n".join(parts)


async def explain_error(
    error_text: str,
    context: str = "",
    product_id: str = "product:platform",
) -> ErrorContext:
    """Full explanation pipeline.

    Never raises — all steps degrade gracefully.
    """
    from core.engine.core.db import parse_record_ids, parse_rows, pool

    parsed = parse_traceback(error_text)
    innermost = parsed.get("innermost")
    traceback_files = [f["path"] for f in parsed["files"]]

    capabilities: list[dict] = []
    decisions: list[dict] = []

    if innermost:
        try:
            rel_path = innermost["path"]
            async with pool.connection() as db:
                cap_rows = parse_rows(
                    await db.query(
                        """SELECT cap.id, cap.slug, cap.name, cap.description
                    FROM graph_file AS gf
                    JOIN realizes AS r ON r.in = gf.id
                    JOIN capability AS cap ON cap.id = r.out
                    WHERE gf.path CONTAINS $path
                    AND cap.product = <record>$product
                    LIMIT 3""",
                        {"path": rel_path, "product": product_id},
                    )
                )
                capabilities = cap_rows

                if cap_rows:
                    cap_ids = [str(c["id"]) for c in cap_rows]
                    dec_rows = parse_rows(
                        await db.query(
                            """SELECT d.title, d.rationale, d.decision_type
                        FROM affected AS a
                        JOIN decision AS d ON d.id = a.in
                        WHERE a.out IN $cap_ids
                        AND d.outcome = 'accepted'
                        LIMIT 3""",
                            {"cap_ids": parse_record_ids(cap_ids)},
                        )
                    )
                    decisions = dec_rows
        except Exception as exc:
            logger.debug("Error context lookup failed: %s", exc)

    existing_runbook = await _check_runbook(parsed["error_type"], error_text, product_id)

    explanation = ""
    fix_commands: list[str] = []
    try:
        from core.engine.core.llm import get_llm

        prompt = _build_explanation_prompt(
            error_text=error_text,
            context=context,
            capabilities=capabilities,
            decisions=decisions,
            existing_runbook=existing_runbook,
        )
        llm = get_llm()
        response = await llm.complete(prompt, max_tokens=400)
        explanation = (response or "").strip()
        fix_commands = _extract_fix_commands(explanation)
    except Exception as exc:
        logger.debug("LLM explanation failed: %s", exc)
        explanation = f"{parsed['error_type']}: {parsed['error_message']}"

    if not existing_runbook and explanation:
        await _capture_as_runbook(
            error_type=parsed["error_type"],
            error_message=parsed["error_message"],
            explanation=explanation,
            fix_commands=fix_commands,
            product_id=product_id,
        )

    return ErrorContext(
        error_type=parsed["error_type"],
        error_message=parsed["error_message"],
        traceback_files=traceback_files,
        innermost_file=innermost["path"] if innermost else None,
        innermost_line=innermost["line"] if innermost else None,
        related_capabilities=capabilities,
        related_decisions=decisions,
        existing_runbook=existing_runbook,
        explanation=explanation,
        fix_commands=fix_commands,
    )


async def _check_runbook(error_type: str, error_text: str, product_id: str) -> dict | None:
    from core.engine.core.db import parse_one, pool

    try:
        async with pool.connection() as db:
            result = parse_one(
                await db.query(
                    """SELECT * FROM insight
                WHERE product = <record>$product
                AND content CONTAINS $error_type
                AND tags CONTAINS 'runbook'
                ORDER BY confidence DESC LIMIT 1""",
                    {"product": product_id, "error_type": error_type},
                )
            )
        return result
    except Exception:
        return None


async def _capture_as_runbook(
    error_type: str,
    error_message: str,
    explanation: str,
    fix_commands: list[str],
    product_id: str,
) -> None:
    """Auto-capture new error pattern as runbook insight (best-effort)."""
    try:
        from core.engine.capture.pipeline import CaptureService

        svc = CaptureService()
        await svc.emit(
            {
                "type": "learning",
                "content": (f"Error pattern: {error_type}: {error_message[:100]}. {explanation[:200]}"),
                "tags": ["runbook", "error", error_type.lower()],
                "discipline_hint": "error_handling",
                "product_id": product_id,
            }
        )
    except Exception:
        pass
