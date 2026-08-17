"""Tests for the thin JSON structural parser."""

from ace_local_json_source import JsonLeaf, parse_json


def test_flat_object_leaves_carry_json_pointers():
    doc = parse_json(b'{"name": "Ada", "age": 36}')
    assert doc.leaves == (
        JsonLeaf(pointer="/name", value="Ada", anchor="/name"),
        JsonLeaf(pointer="/age", value=36, anchor="/age"),
    )


def test_nested_object_pointer_is_joined():
    doc = parse_json(b'{"a": {"b": 1}}')
    assert doc.leaves == (JsonLeaf(pointer="/a/b", value=1, anchor="/a/b"),)


def test_array_elements_use_index_pointers():
    doc = parse_json(b'{"xs": [10, 20]}')
    assert doc.leaves == (
        JsonLeaf(pointer="/xs/0", value=10, anchor="/xs/0"),
        JsonLeaf(pointer="/xs/1", value=20, anchor="/xs/1"),
    )


def test_root_scalar_has_empty_pointer():
    doc = parse_json(b"42")
    assert doc.leaves == (JsonLeaf(pointer="", value=42, anchor=""),)


def test_pointer_tokens_are_escaped_per_rfc6901():
    doc = parse_json(b'{"a/b": 1, "m~n": 2}')
    assert doc.leaves == (
        JsonLeaf(pointer="/a~1b", value=1, anchor="/a~1b"),
        JsonLeaf(pointer="/m~0n", value=2, anchor="/m~0n"),
    )


def test_bool_and_null_are_preserved_as_leaves():
    doc = parse_json(b'{"ok": true, "x": null}')
    assert doc.leaves == (
        JsonLeaf(pointer="/ok", value=True, anchor="/ok"),
        JsonLeaf(pointer="/x", value=None, anchor="/x"),
    )


def test_empty_object_has_no_leaves():
    doc = parse_json(b"{}")
    assert doc.leaves == ()
