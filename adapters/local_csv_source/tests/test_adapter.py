"""Tests for the thin CSV structural parser."""

from ace_local_csv_source import CsvRow, parse_csv


def test_header_row_becomes_field_names():
    doc = parse_csv(b"name,age\nAda,36\n")
    assert doc.headers == ("name", "age")


def test_data_rows_are_anchored_by_one_based_row_number():
    doc = parse_csv(b"name,age\nAda,36\nGrace,45\n")
    assert doc.rows == (
        CsvRow(index=1, cells=(("name", "Ada"), ("age", "36")), anchor="row 1"),
        CsvRow(index=2, cells=(("name", "Grace"), ("age", "45")), anchor="row 2"),
    )


def test_quoted_field_with_comma_is_one_cell():
    doc = parse_csv(b'name,note\nAda,"Lovelace, Ada"\n')
    assert doc.rows[0].cells == (("name", "Ada"), ("note", "Lovelace, Ada"))


def test_ragged_row_pads_missing_cells_with_empty():
    doc = parse_csv(b"a,b,c\n1,2\n")
    assert doc.rows[0].cells == (("a", "1"), ("b", "2"), ("c", ""))


def test_extra_cells_beyond_header_get_positional_keys():
    doc = parse_csv(b"a\n1,2\n")
    assert doc.rows[0].cells == (("a", "1"), ("column_2", "2"))


def test_empty_input_has_no_headers_and_no_rows():
    doc = parse_csv(b"")
    assert doc.headers == ()
    assert doc.rows == ()
