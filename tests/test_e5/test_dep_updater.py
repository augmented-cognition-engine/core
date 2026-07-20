"""Tests for dep_updater: risk assessment and safe/blocked update splits."""

from unittest.mock import AsyncMock, patch

import pytest

from core.engine.intelligence.dep_updater import _assess_risk, get_dep_updates

# ── _assess_risk ───────────────────────────────────────────────────────────


def test_assess_risk_patch_bump_is_safe():
    assert _assess_risk("1.0.0", "1.0.1", "patch") == "safe"


def test_assess_risk_minor_bump_is_minor():
    assert _assess_risk("1.0.0", "1.1.0", "patch") == "minor"


def test_assess_risk_major_bump_is_breaking():
    assert _assess_risk("1.0.0", "2.0.0", "patch") == "breaking"


def test_assess_risk_same_major_minor_patch_bump():
    assert _assess_risk("2.3.4", "2.3.9", "patch") == "safe"


def test_assess_risk_minor_strategy_allows_minor():
    # _assess_risk only returns the label; strategy gating happens in get_dep_updates
    assert _assess_risk("1.0.0", "1.1.0", "minor") == "minor"


def test_assess_risk_invalid_version_returns_minor():
    # Malformed versions degrade gracefully
    assert _assess_risk("not-a-version", "1.0.0", "patch") == "minor"


def test_assess_risk_equal_versions_safe():
    assert _assess_risk("1.2.3", "1.2.3", "patch") == "safe"


# ── get_dep_updates ────────────────────────────────────────────────────────


VULN_PATCH = {
    "name": "requests",
    "version": "2.28.0",
    "id": "CVE-2023-1234",
    "fix_versions": ["2.28.2"],
}

VULN_MAJOR = {
    "name": "django",
    "version": "3.2.0",
    "id": "CVE-2023-5678",
    "fix_versions": ["4.0.0"],
}

VULN_NO_FIX = {
    "name": "orphan",
    "version": "1.0.0",
    "id": "CVE-2023-9999",
    "fix_versions": [],
}


@pytest.mark.asyncio
async def test_get_dep_updates_returns_list():
    with (
        patch("core.engine.intelligence.dep_updater._get_pip_audit_results", AsyncMock(return_value=[VULN_PATCH])),
        patch("core.engine.intelligence.dep_updater._get_pinned_decisions", AsyncMock(return_value={})),
    ):
        result = await get_dep_updates()
    assert isinstance(result, list)


@pytest.mark.asyncio
async def test_get_dep_updates_patch_is_safe():
    with (
        patch("core.engine.intelligence.dep_updater._get_pip_audit_results", AsyncMock(return_value=[VULN_PATCH])),
        patch("core.engine.intelligence.dep_updater._get_pinned_decisions", AsyncMock(return_value={})),
    ):
        result = await get_dep_updates(strategy="patch")
    assert len(result) == 1
    assert result[0].safe_to_update is True
    assert result[0].risk_level == "safe"


@pytest.mark.asyncio
async def test_get_dep_updates_major_not_safe_with_patch_strategy():
    with (
        patch("core.engine.intelligence.dep_updater._get_pip_audit_results", AsyncMock(return_value=[VULN_MAJOR])),
        patch("core.engine.intelligence.dep_updater._get_pinned_decisions", AsyncMock(return_value={})),
    ):
        result = await get_dep_updates(strategy="patch")
    assert len(result) == 1
    assert result[0].safe_to_update is False
    assert result[0].risk_level == "breaking"


@pytest.mark.asyncio
async def test_get_dep_updates_major_safe_with_semver_strategy():
    with (
        patch("core.engine.intelligence.dep_updater._get_pip_audit_results", AsyncMock(return_value=[VULN_MAJOR])),
        patch("core.engine.intelligence.dep_updater._get_pinned_decisions", AsyncMock(return_value={})),
    ):
        result = await get_dep_updates(strategy="semver")
    assert result[0].safe_to_update is True


@pytest.mark.asyncio
async def test_get_dep_updates_blocked_by_pinned_decision():
    pinned = {"requests": "Pin requests to 2.28.0 for compliance"}
    with (
        patch("core.engine.intelligence.dep_updater._get_pip_audit_results", AsyncMock(return_value=[VULN_PATCH])),
        patch("core.engine.intelligence.dep_updater._get_pinned_decisions", AsyncMock(return_value=pinned)),
    ):
        result = await get_dep_updates(strategy="patch")
    assert result[0].safe_to_update is False
    assert result[0].risk_level == "blocked"
    assert result[0].decision_gate is not None


@pytest.mark.asyncio
async def test_get_dep_updates_skips_no_fix_versions():
    with (
        patch("core.engine.intelligence.dep_updater._get_pip_audit_results", AsyncMock(return_value=[VULN_NO_FIX])),
        patch("core.engine.intelligence.dep_updater._get_pinned_decisions", AsyncMock(return_value={})),
    ):
        result = await get_dep_updates()
    assert result == []


@pytest.mark.asyncio
async def test_get_dep_updates_update_command_format():
    with (
        patch("core.engine.intelligence.dep_updater._get_pip_audit_results", AsyncMock(return_value=[VULN_PATCH])),
        patch("core.engine.intelligence.dep_updater._get_pinned_decisions", AsyncMock(return_value={})),
    ):
        result = await get_dep_updates()
    assert "requests" in result[0].update_command
    assert "2.28.2" in result[0].update_command


@pytest.mark.asyncio
async def test_get_dep_updates_empty_when_no_vulns():
    with (
        patch("core.engine.intelligence.dep_updater._get_pip_audit_results", AsyncMock(return_value=[])),
        patch("core.engine.intelligence.dep_updater._get_pinned_decisions", AsyncMock(return_value={})),
    ):
        result = await get_dep_updates()
    assert result == []
