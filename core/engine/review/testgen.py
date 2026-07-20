# engine/review/testgen.py
"""Test generation from capability specs.

Takes ACE capability specs with acceptance criteria and generates
test suites using LLM-powered code generation. Inspired by Qodo's
behavior-based test generation approach.
"""

from __future__ import annotations

import logging

from pydantic import BaseModel, Field

from core.engine.core.config import settings
from core.engine.core.llm import llm

logger = logging.getLogger(__name__)


class TestCase(BaseModel):
    """A single generated test case."""

    name: str
    description: str
    code: str
    category: str = ""  # unit | integration | edge_case | error_handling


class TestSuite(BaseModel):
    """Generated test suite for a capability."""

    capability: str
    file_path: str  # suggested test file path
    framework: str = "pytest"
    test_cases: list[TestCase] = Field(default_factory=list)
    imports: str = ""
    setup_code: str = ""


class TestGenerator:
    """Generates test suites from capability specs."""

    async def from_spec(
        self,
        spec: dict,
        language: str = "python",
        framework: str = "pytest",
    ) -> TestSuite:
        """Generate tests from an agent spec.

        spec should have: name, description, acceptance_criteria (list of strings),
        and optionally: files (list of file paths involved).
        """
        name = spec.get("name", "unknown")
        description = spec.get("description", "")
        criteria = spec.get("acceptance_criteria", [])
        files = spec.get("files", [])

        if not criteria:
            return TestSuite(
                capability=name,
                file_path=f"tests/test_{_slugify(name)}.py",
                framework=framework,
                test_cases=[],
            )

        criteria_text = "\n".join(f"- {c}" for c in criteria)
        files_text = "\n".join(f"- {f}" for f in files) if files else "Not specified"

        prompt = f"""Generate a comprehensive test suite for this capability.

## Capability: {name}
{description}

## Acceptance Criteria
{criteria_text}

## Files Involved
{files_text}

## Requirements
- Framework: {framework}
- Language: {language}
- Generate one test function per acceptance criterion
- Add edge case tests where appropriate
- Add error handling tests
- Use descriptive test names (test_<behavior>_<scenario>)
- Include docstrings explaining what each test verifies
- Mock external dependencies (database, API calls, file system)
- Do NOT use real infrastructure

Respond in this exact JSON format:
```json
{{
  "imports": "import statements needed",
  "setup_code": "any shared fixtures or setup",
  "test_cases": [
    {{
      "name": "test_function_name",
      "description": "What this test verifies",
      "code": "def test_function_name():\\n    ...",
      "category": "unit|integration|edge_case|error_handling"
    }}
  ]
}}
```"""

        try:
            response = await llm.complete(prompt, model=settings.llm_budget_model)
            return self._parse_response(name, response, framework)
        except Exception as exc:
            logger.error("Test generation failed for %s: %s", name, exc)
            return TestSuite(
                capability=name,
                file_path=f"tests/test_{_slugify(name)}.py",
                framework=framework,
            )

    async def from_acceptance_criteria(
        self,
        criteria: list[str],
        capability_name: str = "feature",
        context: str = "",
    ) -> TestSuite:
        """Generate tests from a list of acceptance criteria strings."""
        spec = {
            "name": capability_name,
            "description": context,
            "acceptance_criteria": criteria,
        }
        return await self.from_spec(spec)

    def render(self, suite: TestSuite) -> str:
        """Render a TestSuite to a complete Python test file string."""
        parts = [f'"""Generated tests for {suite.capability}."""\n']

        if suite.imports:
            parts.append(suite.imports)
            parts.append("")

        if suite.setup_code:
            parts.append(suite.setup_code)
            parts.append("")

        for tc in suite.test_cases:
            if tc.description:
                parts.append("")
            parts.append(tc.code)
            parts.append("")

        return "\n".join(parts)

    def _parse_response(self, name: str, response: str, framework: str) -> TestSuite:
        """Parse LLM JSON response into a TestSuite."""
        import json

        # Find JSON in response
        start = response.find("{")
        end = response.rfind("}") + 1
        if start == -1 or end <= start:
            return TestSuite(
                capability=name,
                file_path=f"tests/test_{_slugify(name)}.py",
                framework=framework,
            )

        try:
            data = json.loads(response[start:end])
            test_cases = [
                TestCase(
                    name=tc.get("name", f"test_{i}"),
                    description=tc.get("description", ""),
                    code=tc.get("code", ""),
                    category=tc.get("category", "unit"),
                )
                for i, tc in enumerate(data.get("test_cases", []))
                if tc.get("code")
            ]
            return TestSuite(
                capability=name,
                file_path=f"tests/test_{_slugify(name)}.py",
                framework=framework,
                test_cases=test_cases,
                imports=data.get("imports", ""),
                setup_code=data.get("setup_code", ""),
            )
        except (json.JSONDecodeError, KeyError) as exc:
            logger.warning("Failed to parse test generation response: %s", exc)
            return TestSuite(
                capability=name,
                file_path=f"tests/test_{_slugify(name)}.py",
                framework=framework,
            )


def _slugify(name: str) -> str:
    """Convert a name to a valid Python identifier for test file naming."""
    import re

    slug = re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")
    return slug or "unknown"
