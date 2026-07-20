"""AST-based extraction of FastAPI endpoint response shapes.

Parses Python files for ``APIRouter`` endpoints and extracts the field names
from return-dict literals so we can compare them against the frontend contract.
"""

from __future__ import annotations

import ast
from pathlib import Path

from core.engine.seam.types import FieldShape, SeamContract

# HTTP methods recognised on an APIRouter instance
_ROUTE_METHODS = {"get", "post", "put", "patch", "delete"}


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _find_router_prefix(tree: ast.Module) -> str:
    """Return the ``prefix`` kwarg from the first ``APIRouter(...)`` call, or ``""``."""
    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign):
            continue
        value = node.value
        if not isinstance(value, ast.Call):
            continue
        # Match ``APIRouter(...)`` by name
        func = value.func
        if isinstance(func, ast.Name) and func.id == "APIRouter":
            for kw in value.keywords:
                if kw.arg == "prefix" and isinstance(kw.value, ast.Constant):
                    return str(kw.value.value)
        if isinstance(func, ast.Attribute) and func.attr == "APIRouter":
            for kw in value.keywords:
                if kw.arg == "prefix" and isinstance(kw.value, ast.Constant):
                    return str(kw.value.value)
    return ""


def _has_fastapi_router_import(tree: ast.Module) -> bool:
    """Return True if the file imports ``APIRouter`` from ``fastapi``."""
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module == "fastapi":
            for alias in node.names:
                if alias.name == "APIRouter":
                    return True
    return False


def _extract_route_decorator(
    node: ast.FunctionDef | ast.AsyncFunctionDef,
) -> tuple[str, str] | None:
    """Return ``(method, path)`` from the first recognised router decorator, or *None*."""
    for dec in node.decorator_list:
        if not isinstance(dec, ast.Call):
            continue
        func = dec.func
        if not (isinstance(func, ast.Attribute) and func.attr in _ROUTE_METHODS):
            continue
        method = func.attr.upper()
        # First positional arg is the route path
        if dec.args and isinstance(dec.args[0], ast.Constant):
            path = str(dec.args[0].value)
        else:
            path = ""
        return method, path
    return None


def _collect_return_fields(body: list[ast.stmt]) -> list[FieldShape]:
    """Walk a function body and collect string keys from all ``return {…}`` dicts."""
    fields: list[FieldShape] = []
    seen: set[str] = set()
    for node in ast.walk(ast.Module(body=body, type_ignores=[])):
        if not isinstance(node, ast.Return) or node.value is None:
            continue
        val = node.value
        if isinstance(val, ast.Dict):
            for key in val.keys:
                if isinstance(key, ast.Constant) and isinstance(key.value, str):
                    if key.value not in seen:
                        seen.add(key.value)
                        fields.append(FieldShape(name=key.value, source="return_literal"))
    return fields


def _extract_model_fields(tree: ast.Module, model_name: str) -> list[FieldShape]:
    """Extract field names from a class definition in the same file.

    Handles simple annotated assignments like ``name: str = ...`` which is
    the standard pattern for both Pydantic ``BaseModel`` and plain dataclasses.
    """
    for node in ast.walk(tree):
        if not isinstance(node, ast.ClassDef) or node.name != model_name:
            continue
        fields: list[FieldShape] = []
        for item in node.body:
            if isinstance(item, ast.AnnAssign) and isinstance(item.target, ast.Name):
                type_hint = ast.unparse(item.annotation) if item.annotation else None
                fields.append(
                    FieldShape(
                        name=item.target.id,
                        type_hint=type_hint,
                        source="response_model",
                    )
                )
        return fields
    return []


def _get_response_model_name(
    node: ast.FunctionDef | ast.AsyncFunctionDef,
) -> str | None:
    """Return the ``response_model`` class name from the route decorator, if present."""
    for dec in node.decorator_list:
        if not isinstance(dec, ast.Call):
            continue
        for kw in dec.keywords:
            if kw.arg == "response_model" and isinstance(kw.value, ast.Name):
                return kw.value.id
    return None


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def extract_backend_contracts(file_path: str) -> list[SeamContract]:
    """Parse *file_path* and return a :class:`SeamContract` per endpoint found."""
    source = Path(file_path).read_text()
    tree = ast.parse(source, filename=file_path)

    if not _has_fastapi_router_import(tree):
        return []

    prefix = _find_router_prefix(tree)
    contracts: list[SeamContract] = []

    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue

        route_info = _extract_route_decorator(node)
        if route_info is None:
            continue

        method, path = route_info
        full_route = prefix + path

        # Collect fields from return dict literals
        fields = _collect_return_fields(node.body)

        # If no literal fields found, try response_model
        if not fields:
            model_name = _get_response_model_name(node)
            if model_name:
                fields = _extract_model_fields(tree, model_name)

        contracts.append(
            SeamContract(
                route=full_route,
                method=method,
                source_file=file_path,
                source_line=node.lineno,
                response_fields=fields,
            )
        )

    return contracts
