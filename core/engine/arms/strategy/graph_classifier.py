"""graph_grounded_classifier — the production default WorkProfile policy. Measures scope/risk
from the code graph when populated, reasons novelty/task_type (and fallback scope/risk) from the
knowledge graph always, and fire-and-forget scans a cold code graph to self-heal. Every seam
non-fatal; injectable I/O wrappers → deterministic tests. Sibling of code_planner's brain wrappers."""

from __future__ import annotations

import logging

from core.engine.arms.strategy.profile import WorkProfile
from core.engine.core.llm import get_llm

logger = logging.getLogger(__name__)

# Tunable first-cut thresholds (later learnable from action_outcome).
_MODULE_MAX_FILES = 3  # >3 distinct hit files -> repo scope
_ISOLATED_MAX_AFFECTED = 2  # blast radius <= this -> isolated
_CONNECTED_MAX_AFFECTED = 10  # blast radius <= this -> connected; above -> systemic
_TOP_K_BLAST = 3  # measure blast radius over at most this many hit files

_DEFAULT_PRODUCT = "product:platform"

# Allowed enum values per WorkProfile dimension (coerce LLM output to these).
_SCOPE = {"none", "nearby", "module", "repo"}
_NOVELTY = {"greenfield", "extend", "modify", "fix"}
_RISK = {"isolated", "connected", "systemic"}

# Process-level once-guard: at most one scan kicked per product per process.
_scan_kicked: set[str] = set()


def _verify_for_risk(risk: str) -> str:
    return {"isolated": "smoke", "connected": "unit", "systemic": "full"}.get(risk, "unit")


def _coerce(value, allowed: set[str]):
    """Return value if it's a valid enum member, else None (so callers fall back)."""
    if isinstance(value, str) and value in allowed:
        return value
    return None


# --- injectable I/O wrappers (module-level so tests monkeypatch; tools swappable) ---


async def _search_code(intent: str) -> dict:
    from core.engine.mcp.tools import ace_search_code

    return await ace_search_code(query=intent)


async def _blast_radius(path: str, product_id: str) -> dict:
    from core.engine.mcp.tools import ace_blast_radius

    return await ace_blast_radius(target=path, product_id=product_id)


async def _scan(product_id: str) -> dict:
    from core.engine.mcp.tools import ace_scan_repo

    return await ace_scan_repo(repo_path=".", product_id=product_id)


# --- code-graph measurement + scan-on-demand ---


def _distinct_paths(hits: list) -> list[str]:
    paths: list[str] = []
    for h in hits:
        if not isinstance(h, dict):
            continue
        p = h.get("path") or h.get("file")  # hybrid_search rows are keyed `path`
        if p and p not in paths:
            paths.append(p)
    return paths


def _is_semantic_hit(h) -> bool:
    """Measurement-grade only: a real semantic match, not keyword-fallback noise.

    hybrid_search tags keyword-fallback rows with semantic_score == 0.0; trusting those
    as precise scope would let a degraded-embeddings search outrank the LLM's reasoning."""
    try:
        return isinstance(h, dict) and float(h.get("semantic_score", 0) or 0) > 0
    except (TypeError, ValueError):
        return False


async def _maybe_scan(product_id: str) -> None:
    """Fire-and-forget populate a cold code graph, at most once per product per process."""
    if product_id in _scan_kicked:
        return
    _scan_kicked.add(product_id)
    try:
        await _scan(product_id)
    except Exception as exc:
        logger.warning("graph_classifier scan-on-demand failed (non-fatal): %s", exc)


async def _measure_from_code_graph(intent: str, product_id: str) -> dict:
    """Measure scope[/risk] from the code graph. Returns only dims it can actually measure."""
    try:
        res = await _search_code(intent)
        raw_hits = res.get("results", []) if isinstance(res, dict) else []
        if not raw_hits:
            await _maybe_scan(product_id)  # genuinely cold graph -> populate for next time
            return {}
        # Only semantic-grade hits are measurement-grade; keyword-fallback noise (embeddings
        # down) must NOT masquerade as precise scope and outrank reasoning.
        hits = [h for h in raw_hits if _is_semantic_hit(h)]
        if not hits:
            return {}  # graph has files but no semantic signal -> let reasoning fill (don't rescan)
        paths = _distinct_paths(hits)
        if not paths:
            return {}
        scope = "nearby" if len(paths) <= 1 else "module" if len(paths) <= _MODULE_MAX_FILES else "repo"
        affected = 0
        for p in paths[:_TOP_K_BLAST]:
            try:
                br = await _blast_radius(p, product_id)
                if isinstance(br, dict):
                    affected = max(affected, int(br.get("total_affected", 0) or 0))
            except Exception:
                continue
        if affected <= 0:
            return {"scope": scope}  # blast graph silent -> risk left to reasoning/middle
        risk = (
            "isolated"
            if affected <= _ISOLATED_MAX_AFFECTED
            else "connected"
            if affected <= _CONNECTED_MAX_AFFECTED
            else "systemic"
        )
        return {"scope": scope, "risk": risk}
    except Exception as exc:
        logger.warning("graph_classifier code-graph measurement failed (non-fatal): %s", exc)
        return {}


# --- knowledge grounding + reasoning ---


async def _knowledge_search(intent: str, product_id: str) -> dict:
    from core.engine.mcp.tools import ace_search

    return await ace_search(query=intent, product_id=product_id)


async def _knowledge_context(intent: str, product_id: str) -> str:
    """Digest what ACE already knows about the work (to ground the reasoning). '' on failure."""
    try:
        res = await _knowledge_search(intent, product_id)
        results = res.get("results", []) if isinstance(res, dict) else []
        lines: list[str] = []
        for r in results[:8]:
            if isinstance(r, dict):
                text = r.get("content") or r.get("text") or r.get("summary") or ""  # ace_search rows: `content`
                if text:
                    lines.append(f"- {str(text)[:200]}")
        return "\n".join(lines)
    except Exception as exc:
        logger.warning("graph_classifier knowledge_context failed (non-fatal): %s", exc)
        return ""


async def _reason_profile(intent: str, conversation, knowledge: str) -> dict:
    """Reason novelty/task_type (always) + scope/risk (fallback) from objective + conversation + knowledge."""
    try:
        convo = str(conversation)[:2000] if conversation else "(none)"  # bound unbounded transcripts
        prompt = (
            "Classify a unit of engineering work along independent dimensions. "
            "Reply with STRICT JSON and nothing else:\n"
            '{"novelty":"greenfield|extend|modify|fix","task_type":"<short label>",'
            '"scope":"none|nearby|module|repo","risk":"isolated|connected|systemic"}\n'
            "Definitions: novelty=how new (greenfield=brand-new thing, extend=add to existing, "
            "modify=change existing, fix=repair a defect); scope=how much code to touch/understand; "
            "risk=blast radius if it goes wrong.\n\n"
            f"OBJECTIVE: {intent}\n\n"
            f"CONVERSATION: {convo}\n\n"
            f"WHAT ACE ALREADY KNOWS:\n{knowledge or '(nothing relevant)'}"
        )
        data = await get_llm().complete_json(prompt)
        if not isinstance(data, dict):
            return {}
        out: dict = {}
        nov = _coerce(data.get("novelty"), _NOVELTY)
        if nov:
            out["novelty"] = nov
        tt = data.get("task_type")
        if isinstance(tt, str) and tt.strip():
            out["task_type"] = tt.strip()[:48]
        sc = _coerce(data.get("scope"), _SCOPE)
        if sc:
            out["scope"] = sc
        rk = _coerce(data.get("risk"), _RISK)
        if rk:
            out["risk"] = rk
        return out
    except Exception as exc:
        logger.warning("graph_classifier reason_profile failed (non-fatal): %s", exc)
        return {}


# --- the classifier ---


async def graph_grounded_classifier(solution, conversation=None, overrides=None) -> WorkProfile:
    """Production default classifier. `overrides` is accepted to match classify_work's call
    contract but is applied by classify_work, not here."""
    intent = (getattr(solution, "intent", "") or "") if solution is not None else ""
    product_id = getattr(solution, "product_id", None) or _DEFAULT_PRODUCT

    profile = WorkProfile()
    measured = await _measure_from_code_graph(intent, product_id)
    knowledge = await _knowledge_context(intent, product_id)
    reasoned = await _reason_profile(intent, conversation, knowledge)

    profile.scope = measured.get("scope") or reasoned.get("scope") or profile.scope
    profile.risk = measured.get("risk") or reasoned.get("risk") or profile.risk
    profile.novelty = reasoned.get("novelty") or profile.novelty
    profile.task_type = reasoned.get("task_type") or profile.task_type
    profile.verify_depth = _verify_for_risk(profile.risk)
    return profile
