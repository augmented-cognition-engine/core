"""Tests for test generation from capability specs."""

from unittest.mock import AsyncMock, patch

import pytest

from core.engine.review.testgen import TestCase, TestGenerator, TestSuite, _slugify


def test_slugify():
    assert _slugify("Auth Middleware") == "auth_middleware"
    assert _slugify("API v2") == "api_v2"
    assert _slugify("") == "unknown"


@pytest.mark.asyncio
async def test_from_spec_generates_tests():
    gen = TestGenerator()
    mock_response = '{"imports": "import pytest", "setup_code": "", "test_cases": [{"name": "test_auth_required", "description": "Verify auth is required", "code": "def test_auth_required():\\n    assert True", "category": "unit"}]}'

    with patch("core.engine.review.testgen.llm") as mock_llm:
        mock_llm.complete = AsyncMock(return_value=mock_response)
        suite = await gen.from_spec(
            {
                "name": "Authentication",
                "description": "JWT auth",
                "acceptance_criteria": ["Users must authenticate"],
            }
        )

    assert suite.capability == "Authentication"
    assert len(suite.test_cases) == 1
    assert suite.test_cases[0].name == "test_auth_required"
    assert suite.test_cases[0].category == "unit"


@pytest.mark.asyncio
async def test_empty_criteria():
    gen = TestGenerator()
    suite = await gen.from_spec({"name": "empty", "acceptance_criteria": []})
    assert suite.test_cases == []
    assert suite.capability == "empty"
    assert suite.file_path == "tests/test_empty.py"


@pytest.mark.asyncio
async def test_from_acceptance_criteria():
    gen = TestGenerator()
    mock_response = '{"imports": "", "setup_code": "", "test_cases": [{"name": "test_it", "code": "def test_it():\\n    pass", "category": "unit"}]}'
    with patch("core.engine.review.testgen.llm") as mock_llm:
        mock_llm.complete = AsyncMock(return_value=mock_response)
        suite = await gen.from_acceptance_criteria(["it works"], capability_name="feature")
    assert len(suite.test_cases) == 1
    assert suite.capability == "feature"


def test_render():
    gen = TestGenerator()
    suite = TestSuite(
        capability="Auth",
        file_path="tests/test_auth.py",
        imports="import pytest",
        test_cases=[
            TestCase(
                name="test_login",
                description="",
                code="def test_login():\n    assert True",
                category="unit",
            ),
        ],
    )
    rendered = gen.render(suite)
    assert "def test_login" in rendered
    assert "import pytest" in rendered
    assert "Generated tests for Auth" in rendered


def test_render_with_setup_code():
    gen = TestGenerator()
    suite = TestSuite(
        capability="Feature",
        file_path="tests/test_feature.py",
        imports="import pytest\nfrom unittest.mock import MagicMock",
        setup_code="@pytest.fixture\ndef client():\n    return MagicMock()",
        test_cases=[
            TestCase(
                name="test_works",
                description="Verify it works",
                code="def test_works(client):\n    assert client is not None",
                category="integration",
            ),
        ],
    )
    rendered = gen.render(suite)
    assert "@pytest.fixture" in rendered
    assert "def test_works" in rendered
    assert "import pytest" in rendered


def test_parse_bad_json():
    gen = TestGenerator()
    suite = gen._parse_response("test", "not json at all", "pytest")
    assert suite.test_cases == []
    assert suite.capability == "test"
    assert suite.file_path == "tests/test_test.py"


def test_parse_json_missing_code_skipped():
    """Test cases without 'code' field are skipped."""
    gen = TestGenerator()
    response = '{"imports": "", "setup_code": "", "test_cases": [{"name": "test_a", "description": "desc"}, {"name": "test_b", "code": "def test_b(): pass", "category": "unit"}]}'
    suite = gen._parse_response("feat", response, "pytest")
    # Only test_b has code — test_a should be skipped
    assert len(suite.test_cases) == 1
    assert suite.test_cases[0].name == "test_b"


@pytest.mark.asyncio
async def test_from_spec_llm_error_returns_empty_suite():
    gen = TestGenerator()
    with patch("core.engine.review.testgen.llm") as mock_llm:
        mock_llm.complete = AsyncMock(side_effect=RuntimeError("LLM unavailable"))
        suite = await gen.from_spec(
            {
                "name": "broken",
                "acceptance_criteria": ["something works"],
            }
        )
    assert suite.capability == "broken"
    assert suite.test_cases == []


def test_file_path_derived_from_name():
    gen = TestGenerator()
    suite = gen._parse_response("My Feature", "{}", "pytest")
    assert suite.file_path == "tests/test_my_feature.py"


def test_slugify_special_characters():
    assert _slugify("hello-world") == "hello_world"
    assert _slugify("  spaces  ") == "spaces"
    assert _slugify("123 numbers") == "123_numbers"
