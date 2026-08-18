"""Tests for local-source change detection (PI7, J6).

Diffing two acquisition inventories tells the revision engine what changed since the last scan:
files added, modified (content digest differs), removed, or unchanged.
"""

from ace.application.local_source_acquisition import AcquiredLocalFile
from ace.application.local_source_change import diff_acquisitions


def _f(path, digest, status="acquired"):
    return AcquiredLocalFile(
        relative_path=path,
        extension=path.rsplit(".", 1)[-1] if "." in path else "",
        byte_digest="sha256:" + digest,
        size_bytes=len(digest),
        status=status,
        structured_payload_json="{}" if status == "acquired" else None,
    )


def test_added_file_is_detected():
    prev = (_f("a.md", "aa"),)
    curr = (_f("a.md", "aa"), _f("b.md", "bb"))
    change = diff_acquisitions(prev, curr)
    assert change.added == ("b.md",)
    assert change.modified == ()
    assert change.removed == ()
    assert change.unchanged == ("a.md",)


def test_removed_file_is_detected():
    prev = (_f("a.md", "aa"), _f("b.md", "bb"))
    curr = (_f("a.md", "aa"),)
    change = diff_acquisitions(prev, curr)
    assert change.removed == ("b.md",)
    assert change.unchanged == ("a.md",)


def test_modified_file_is_detected_by_digest_change():
    prev = (_f("a.md", "aa"),)
    curr = (_f("a.md", "ZZ"),)
    change = diff_acquisitions(prev, curr)
    assert change.modified == ("a.md",)
    assert change.unchanged == ()


def test_unchanged_file_has_matching_digest():
    prev = (_f("a.md", "aa"),)
    curr = (_f("a.md", "aa"),)
    change = diff_acquisitions(prev, curr)
    assert change.unchanged == ("a.md",)
    assert change.added == () and change.modified == () and change.removed == ()


def test_empty_previous_makes_everything_added():
    curr = (_f("a.md", "aa"), _f("b.md", "bb"))
    change = diff_acquisitions((), curr)
    assert change.added == ("a.md", "b.md")


def test_mixed_scenario():
    prev = (_f("keep.md", "11"), _f("edit.md", "22"), _f("gone.md", "33"))
    curr = (_f("keep.md", "11"), _f("edit.md", "99"), _f("new.md", "44"))
    change = diff_acquisitions(prev, curr)
    assert change.added == ("new.md",)
    assert change.modified == ("edit.md",)
    assert change.removed == ("gone.md",)
    assert change.unchanged == ("keep.md",)


def test_results_are_sorted_within_each_bucket():
    curr = (_f("c.md", "1"), _f("a.md", "2"), _f("b.md", "3"))
    change = diff_acquisitions((), curr)
    assert change.added == ("a.md", "b.md", "c.md")


def test_has_changes_is_false_only_when_nothing_moved():
    same = (_f("a.md", "aa"),)
    assert diff_acquisitions(same, same).has_changes is False
    assert diff_acquisitions((), same).has_changes is True
