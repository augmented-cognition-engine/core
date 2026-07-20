"""Tests for engine.seam.backend_extractor — AST-based FastAPI shape extraction."""

from __future__ import annotations

from pathlib import Path
from textwrap import dedent

from core.engine.seam.backend_extractor import extract_backend_contracts


def _write(tmp_path: Path, code: str) -> str:
    """Write *code* to a temp .py file and return its path as a string."""
    p = tmp_path / "endpoint.py"
    p.write_text(dedent(code))
    return str(p)


# ------------------------------------------------------------------
# 1. Simple return dict
# ------------------------------------------------------------------


def test_simple_return_dict(tmp_path):
    path = _write(
        tmp_path,
        """\
        from fastapi import APIRouter

        router = APIRouter()

        @router.get("/items")
        async def list_items():
            return {"items": [], "count": 0}
        """,
    )

    contracts = extract_backend_contracts(path)
    assert len(contracts) == 1

    c = contracts[0]
    assert c.route == "/items"
    assert c.method == "GET"
    assert c.source_file == path

    names = [f.name for f in c.response_fields]
    assert "items" in names
    assert "count" in names
    assert all(f.source == "return_literal" for f in c.response_fields)


# ------------------------------------------------------------------
# 2. Router with prefix
# ------------------------------------------------------------------


def test_router_with_prefix(tmp_path):
    path = _write(
        tmp_path,
        """\
        from fastapi import APIRouter

        router = APIRouter(prefix="/api/v1")

        @router.get("/users")
        async def list_users():
            return {"users": [], "total": 0}
        """,
    )

    contracts = extract_backend_contracts(path)
    assert len(contracts) == 1
    assert contracts[0].route == "/api/v1/users"


# ------------------------------------------------------------------
# 3. Multiple endpoints
# ------------------------------------------------------------------


def test_multiple_endpoints(tmp_path):
    path = _write(
        tmp_path,
        """\
        from fastapi import APIRouter

        router = APIRouter(prefix="/things")

        @router.get("/all")
        async def get_all():
            return {"items": []}

        @router.get("/count")
        async def get_count():
            return {"count": 42}
        """,
    )

    contracts = extract_backend_contracts(path)
    assert len(contracts) == 2

    routes = {c.route for c in contracts}
    assert routes == {"/things/all", "/things/count"}


# ------------------------------------------------------------------
# 4. Non-FastAPI file returns empty list
# ------------------------------------------------------------------


def test_no_fastapi_file(tmp_path):
    path = _write(
        tmp_path,
        """\
        import os

        def helper():
            return {"key": "value"}
        """,
    )

    assert extract_backend_contracts(path) == []


# ------------------------------------------------------------------
# 5. Variable return (not a dict literal)
# ------------------------------------------------------------------


def test_variable_return(tmp_path):
    path = _write(
        tmp_path,
        """\
        from fastapi import APIRouter

        router = APIRouter()

        @router.get("/data")
        async def get_data():
            result = do_something()
            return result
        """,
    )

    contracts = extract_backend_contracts(path)
    assert len(contracts) == 1
    assert contracts[0].response_fields == []


# ------------------------------------------------------------------
# 6. POST method
# ------------------------------------------------------------------


def test_post_method(tmp_path):
    path = _write(
        tmp_path,
        """\
        from fastapi import APIRouter

        router = APIRouter()

        @router.post("/submit")
        async def submit():
            return {"status": "ok", "id": "abc"}
        """,
    )

    contracts = extract_backend_contracts(path)
    assert len(contracts) == 1

    c = contracts[0]
    assert c.method == "POST"
    assert c.route == "/submit"
    names = [f.name for f in c.response_fields]
    assert "status" in names
    assert "id" in names


# ------------------------------------------------------------------
# 7. response_model — extract model fields from class in same file
# ------------------------------------------------------------------


def test_response_model_decorator(tmp_path):
    path = _write(
        tmp_path,
        """\
        from fastapi import APIRouter
        from pydantic import BaseModel

        router = APIRouter()

        class UserOut(BaseModel):
            name: str
            email: str
            age: int = 0

        @router.get("/user", response_model=UserOut)
        async def get_user():
            return get_user_from_db()
        """,
    )

    contracts = extract_backend_contracts(path)
    assert len(contracts) == 1

    c = contracts[0]
    names = [f.name for f in c.response_fields]
    assert "name" in names
    assert "email" in names
    assert "age" in names
    assert all(f.source == "response_model" for f in c.response_fields)
    # Verify type hints were extracted
    by_name = {f.name: f for f in c.response_fields}
    assert by_name["name"].type_hint == "str"
    assert by_name["age"].type_hint == "int"
