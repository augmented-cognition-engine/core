from core.engine.core.db import parse_record_ids


def test_parse_record_ids_converts_colon_strings():
    from surrealdb import RecordID

    out = parse_record_ids(["insight:a", "insight:b"])
    assert all(isinstance(x, RecordID) for x in out)
    assert str(out[0]) == "insight:a"


def test_parse_record_ids_passes_through_non_strings():
    from surrealdb import RecordID

    rid = RecordID("insight", "c")
    out = parse_record_ids([rid, "insight:d"])
    assert out[0] is rid  # already a RecordID — untouched
    assert isinstance(out[1], RecordID)


def test_parse_record_ids_empty():
    assert parse_record_ids([]) == []
