# tests/test_review_integration.py
"""Integration test: full PR review pipeline end-to-end."""

from unittest.mock import AsyncMock, patch

import pytest

from core.engine.github.models import PRInfo
from core.engine.review.engine import ReviewEngine
from core.engine.review.judge import Judge

SAMPLE_DIFF = """\
diff --git a/engine/core/auth.py b/engine/core/auth.py
index abc1234..def5678 100644
--- a/engine/core/auth.py
+++ b/engine/core/auth.py
@@ -10,6 +10,12 @@ from engine.core.config import settings

 def verify_token(token: str) -> dict:
     \"\"\"Verify a JWT token.\"\"\"
+    if not token:
+        return None  # BUG: should raise, not return None
+    secret = "hardcoded-secret-key"  # BUG: hardcoded secret
     try:
-        payload = jwt.decode(token, settings.jwt_secret)
+        payload = jwt.decode(token, secret)
         return payload
+    except Exception:
+        pass  # BUG: silently swallowing exceptions
"""


@pytest.mark.asyncio
async def test_full_review_pipeline():
    """End-to-end: parse diff → select disciplines → run passes → judge → gate."""
    from core.engine.github.diff_parser import parse_diff

    # 1. Parse diff
    files = parse_diff(SAMPLE_DIFF)
    assert len(files) == 1
    assert files[0].path == "engine/core/auth.py"

    # 2. Select disciplines
    engine = ReviewEngine(product_id="product:default")
    disciplines = engine.select_disciplines(files)
    assert "security" in disciplines
    assert "architecture" in disciplines

    # 3. Run passes with mocked LLM
    pr = PRInfo(
        number=99,
        title="Fix auth",
        body="Security improvements",
        author="bob",
        base_branch="main",
        head_branch="fix/auth",
        repo_owner="acme",
        repo_name="app",
    )

    security_response = '{"findings": [{"file": "engine/core/auth.py", "line": 15, "message": "Hardcoded secret key — use environment variable", "severity": "critical", "category": "security", "confidence": 0.95}, {"file": "engine/core/auth.py", "line": 13, "message": "Returning None instead of raising on empty token allows bypass", "severity": "high", "category": "security", "confidence": 0.9}], "summary": "2 critical security issues"}'
    arch_response = '{"findings": [{"file": "engine/core/auth.py", "line": 18, "message": "Bare except swallows all errors — use specific exception type", "severity": "medium", "category": "architecture", "confidence": 0.85}], "summary": "1 error handling concern"}'
    testing_response = '{"findings": [{"file": "engine/core/auth.py", "line": 13, "message": "No test for empty token edge case", "severity": "medium", "category": "testing", "confidence": 0.8}], "summary": "Missing edge case test"}'

    responses = iter([security_response, arch_response, testing_response])

    # load_intelligence is a lazy import inside _run_single_pass:
    #   from engine.orchestrator.loader import load_intelligence
    # Patch at the source module so the lazy import resolves to the mock.
    with (
        patch("core.engine.review.engine.llm") as mock_llm,
        patch(
            "core.engine.orchestrator.loader.load_intelligence", new_callable=AsyncMock, return_value={"insights": []}
        ),
    ):
        mock_llm.complete = AsyncMock(side_effect=lambda *a, **kw: next(responses))
        passes = await engine.run_passes(pr, files, disciplines=["security", "architecture", "testing"])

    assert len(passes) == 3
    total_findings = sum(len(p.findings) for p in passes)
    assert total_findings == 4

    # 4. Judge synthesis
    judge = Judge()

    with patch.object(
        judge,
        "_llm_judge",
        new_callable=AsyncMock,
        return_value=[
            {"finding_index": 0, "action": "keep"},
            {"finding_index": 1, "action": "keep"},
            {"finding_index": 2, "action": "keep"},
            {"finding_index": 3, "action": "merge", "merged_with": 1},
        ],
    ):
        synthesis = await judge.synthesize(passes)

    # 5. Verify synthesis
    assert synthesis.passes_run == 3
    assert synthesis.findings_before_judge == 4
    assert synthesis.findings_after_judge == 3
    assert not synthesis.pass_quality_gate  # critical finding → gate fails
    assert any("critical" in f.lower() for f in synthesis.gate_failures)
    assert synthesis.findings[0].severity == "critical"  # sorted by severity
