"""Tests for engine.seam.frontend_extractor."""

from core.engine.seam.frontend_extractor import (
    extract_frontend_expectations,
    extract_interface_fields,
)

# --- extract_interface_fields ---


def test_simple_interface():
    source = """
export interface Foo {
    a: string;
    b: number;
}
"""
    fields = extract_interface_fields("Foo", source)
    assert len(fields) == 2
    assert fields[0].name == "a"
    assert fields[0].type_hint == "string"
    assert fields[0].source == "interface"
    assert fields[1].name == "b"
    assert fields[1].type_hint == "number"


def test_interface_not_found():
    source = """
export interface Bar {
    x: boolean;
}
"""
    fields = extract_interface_fields("Missing", source)
    assert fields == []


# --- extract_frontend_expectations ---


def test_named_type_api_call(tmp_path):
    # Create a types file with the interface definition
    types_file = tmp_path / "types.ts"
    types_file.write_text("""
export interface OverviewResponse {
    name: string;
    score: number;
    items: Item[];
}
""")

    # Create the consumer file
    consumer = tmp_path / "Page.tsx"
    consumer.write_text("""
import { api } from "@/lib/api";

const data = await api.get<OverviewResponse>("/overview");
""")

    results = extract_frontend_expectations(str(consumer), [str(types_file)])
    assert len(results) == 1
    exp = results[0]
    assert exp.route == "/overview"
    assert exp.method == "GET"
    assert exp.type_name == "OverviewResponse"
    assert len(exp.expected_fields) == 3
    names = [f.name for f in exp.expected_fields]
    assert names == ["name", "score", "items"]


def test_inline_type_api_call(tmp_path):
    consumer = tmp_path / "Items.tsx"
    consumer.write_text("""
import { api } from "@/lib/api";

const resp = await api.get<{ items: Item[]; count: number }>("/items");
""")

    results = extract_frontend_expectations(str(consumer))
    assert len(results) == 1
    exp = results[0]
    assert exp.route == "/items"
    assert exp.method == "GET"
    assert exp.type_name == ""
    assert len(exp.expected_fields) == 2
    assert exp.expected_fields[0].name == "items"
    assert exp.expected_fields[0].type_hint == "Item[]"
    assert exp.expected_fields[0].source == "inline"
    assert exp.expected_fields[1].name == "count"
    assert exp.expected_fields[1].type_hint == "number"


def test_template_literal_route(tmp_path):
    consumer = tmp_path / "User.tsx"
    consumer.write_text("""
import { api } from "@/lib/api";

const user = await api.get<{ name: string }>(`/users/${encodeURIComponent(id)}`);
""")

    results = extract_frontend_expectations(str(consumer))
    assert len(results) == 1
    assert results[0].route == "/users/{}"


def test_no_api_import(tmp_path):
    consumer = tmp_path / "NoApi.tsx"
    consumer.write_text("""
import axios from "axios";

const data = await api.get<{ x: number }>("/stuff");
""")

    results = extract_frontend_expectations(str(consumer))
    assert results == []


def test_post_method(tmp_path):
    consumer = tmp_path / "Create.tsx"
    consumer.write_text("""
import { api } from "@/lib/api";

const session = await api.post<{ token: string }>("/auth/token", { api_key: key });
""")

    results = extract_frontend_expectations(str(consumer))
    assert len(results) == 1
    exp = results[0]
    assert exp.route == "/auth/token"
    assert exp.method == "POST"
    assert len(exp.expected_fields) == 1
    assert exp.expected_fields[0].name == "token"


def test_del_method(tmp_path):
    consumer = tmp_path / "Delete.tsx"
    consumer.write_text("""
import { api } from "@/lib/api";

await api.del<{ ok: boolean }>("/items/123");
""")

    results = extract_frontend_expectations(str(consumer))
    assert len(results) == 1
    exp = results[0]
    assert exp.route == "/items/123"
    assert exp.method == "DELETE"
    assert len(exp.expected_fields) == 1
    assert exp.expected_fields[0].name == "ok"


def test_extracts_top_level_fields_from_nested_interface(tmp_path):
    """Fields whose types are nested objects should still be extracted.

    Only top-level fields should be returned; nested fields (city, zip) must
    not appear as independent entries.
    """
    code = """
export interface UserResponse {
  id: number;
  name: string;
  address: {
    city: string;
    zip: string;
  };
}
"""
    fields = extract_interface_fields("UserResponse", code)
    field_names = [f.name for f in fields]
    assert "id" in field_names
    assert "name" in field_names
    assert "address" in field_names
    assert "city" not in field_names, "nested field 'city' should not be a top-level field"
    assert "zip" not in field_names, "nested field 'zip' should not be a top-level field"
    assert len(fields) == 3
