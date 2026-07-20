"""Dependency update automation — decision-aware dependency management.

Strategy:
1. Run pip-audit to get vulnerability list (reuses E2 pip_audit_runner)
2. Check each vulnerable package against the decision graph:
   - Is there a locked decision pinning this version?
   - Does update exceed the requested strategy level?
3. Return safe update commands, blocked packages, and decision rationale

NOT a full Renovate integration (E5c v2). E5c v1 generates safe update commands
that a developer or CI job can run after review.
"""

from __future__ import annotations

import json
import logging
import shutil
import subprocess
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class DepUpdate:
    package: str
    current_version: str
    target_version: str
    vulnerability_id: str | None
    decision_gate: str | None
    safe_to_update: bool
    update_command: str
    risk_level: str  # safe | minor | breaking | blocked


async def get_dep_updates(
    strategy: str = "patch",
    product_id: str = "product:platform",
) -> list[DepUpdate]:
    """Get dependency updates filtered through the decision graph.

    Args:
        strategy: patch | minor | semver (how aggressive to be)
        product_id: Product for decision graph lookup.

    Returns list of DepUpdate — safe and blocked combined.
    """
    vulnerabilities = await _get_pip_audit_results()
    pinned = await _get_pinned_decisions(product_id)

    updates: list[DepUpdate] = []
    for vuln in vulnerabilities:
        pkg = vuln["name"]
        fix_versions = vuln.get("fix_versions", [])
        target = fix_versions[0] if fix_versions else None
        if not target:
            continue

        gate_decision = pinned.get(pkg.lower())
        risk = _assess_risk(vuln.get("version", "0"), target, strategy)

        safe = (gate_decision is None) and (
            risk == "safe"
            or (risk == "minor" and strategy in ("minor", "semver"))
            or (risk == "breaking" and strategy == "semver")
        )
        if gate_decision:
            risk_label = "blocked"
        else:
            risk_label = risk

        updates.append(
            DepUpdate(
                package=pkg,
                current_version=vuln.get("version", "unknown"),
                target_version=target,
                vulnerability_id=vuln.get("id"),
                decision_gate=gate_decision,
                safe_to_update=safe,
                update_command=f"pip install '{pkg}>={target}'",
                risk_level=risk_label,
            )
        )

    return updates


async def _get_pip_audit_results() -> list[dict]:
    """Run pip-audit and return raw vulnerability records."""
    if not shutil.which("pip-audit"):
        return []
    try:
        output = subprocess.check_output(
            ["pip-audit", "--format", "json", "--output", "-"],
            stderr=subprocess.DEVNULL,
            timeout=60,
        )
        data = json.loads(output)
        results: list[dict] = []
        for pkg in data:
            for vuln in pkg.get("vulns", []):
                results.append(
                    {
                        "name": pkg["name"],
                        "version": pkg["version"],
                        "id": vuln.get("id", ""),
                        "fix_versions": vuln.get("fix_versions", []),
                    }
                )
        return results
    except Exception as exc:
        logger.debug("pip-audit failed (non-fatal): %s", exc)
        return []


async def _get_pinned_decisions(product_id: str) -> dict[str, str]:
    """Query decision graph for version-pinning decisions.

    Returns: {package_name_lower: decision_title}
    """
    from core.engine.core.db import parse_rows, pool

    try:
        async with pool.connection() as db:
            rows = parse_rows(
                await db.query(
                    """SELECT title FROM decision
                WHERE product = <record>$product
                AND outcome = 'accepted'
                AND (decision_type = 'convention' OR title CONTAINS 'pin' OR title CONTAINS 'version')
                LIMIT 20""",
                    {"product": product_id},
                )
            )
        return {r["title"].lower().split()[0]: r["title"] for r in rows if r.get("title")}
    except Exception:
        return {}


def _assess_risk(current: str, target: str, strategy: str) -> str:
    """Assess version update risk level using packaging.version."""
    try:
        from packaging.version import Version

        cur = Version(current)
        tgt = Version(target)
        if tgt.major > cur.major:
            return "breaking"
        if tgt.minor > cur.minor:
            return "minor"
        return "safe"
    except Exception:
        return "minor"
