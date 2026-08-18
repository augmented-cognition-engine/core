"""End-to-end spine test: a folder of real files -> cited-ready observations.

This proves the whole local-source spine composes with the real adapters and the governed
acquisition port:

    files on disk
      -> acquire_local_folder (governed inventory: acquired vs unsupported)
      -> source_units_for (adapter parse + normalize)
      -> map_document_units (citable observations)
      -> parse_locator (every citation resolves back to its exact (path, kind, value))
"""

from pathlib import Path

from ace_local_source_normalizers import source_units_for

from ace.application.local_source_acquisition import acquire_local_folder
from ace.intelligence.local_source_locator import parse_locator
from ace.intelligence.local_source_mapping import map_document_units

NOTE_MD = b"intro line\n# Project\nThe roadmap is frozen.\n## Scope\nMarkdown, CSV, JSON, PDF.\n"
DATA_CSV = b"name,role\nAda,engineer\nGrace,admiral\n"
DATA_JSON = b'{"title": "notes", "owner": {"name": "Edwin"}}'
README_TXT = b"unsupported format, inventoried only\n"


def _write_fixture(root: Path) -> None:
    (root / "note.md").write_bytes(NOTE_MD)
    (root / "data.csv").write_bytes(DATA_CSV)
    (root / "data.json").write_bytes(DATA_JSON)
    (root / "README.txt").write_bytes(README_TXT)


def test_folder_of_files_becomes_cited_ready_observations(tmp_path):
    _write_fixture(tmp_path)

    # The governed port routes by extension: supported formats get a payload (status "acquired"),
    # unsupported ones are inventoried with a digest but no payload (status "unsupported").
    def dispatch(extension: str, content: bytes):
        units = source_units_for(extension, content)
        if units is None:
            return None
        return {"unit_count": len(units)}

    acquired = acquire_local_folder(tmp_path, dispatch=dispatch)
    by_path = {f.relative_path: f for f in acquired}

    # Inventory: three supported files acquired, the .txt inventoried as unsupported.
    assert by_path["note.md"].status == "acquired"
    assert by_path["data.csv"].status == "acquired"
    assert by_path["data.json"].status == "acquired"
    assert by_path["README.txt"].status == "unsupported"
    assert by_path["README.txt"].structured_payload_json is None

    # Compose each acquired file into citable observations and prove every locator round-trips.
    expected_kinds = {
        "note.md": {"none", "heading"},
        "data.csv": {"row"},
        "data.json": {"pointer"},
    }
    all_observations = []
    for rel_path, acquired_file in sorted(by_path.items()):
        if acquired_file.status != "acquired":
            continue
        content = (tmp_path / rel_path).read_bytes()
        units = source_units_for(acquired_file.extension, content)
        assert units is not None

        observations = map_document_units(rel_path, acquired_file.byte_digest, units)
        assert observations, f"expected observations for {rel_path}"
        all_observations.extend(observations)

        seen_kinds = set()
        for obs in observations:
            parsed = parse_locator(obs.locator)
            # The citation resolves back to exactly this file and a valid anchor.
            assert parsed.relative_path == rel_path
            assert obs.relative_path == rel_path
            assert obs.source_digest == acquired_file.byte_digest
            assert obs.text.strip()  # empty-text units never yield a citation
            seen_kinds.add(parsed.anchor_kind)

            # The (kind, value) survives the locator grammar intact.
            reunit = next(
                u for u in units if u.anchor_value == parsed.anchor_value and u.anchor_kind == parsed.anchor_kind
            )
            assert reunit.text == obs.text

        assert seen_kinds == expected_kinds[rel_path]

    # Spot-check specific citations resolve to the exact spans we expect.
    locators = {obs.locator for obs in all_observations}
    assert "note.md#heading=Project" in locators
    assert "note.md#heading=Project > Scope" in locators
    assert "data.csv#row=1" in locators
    assert "data.csv#row=2" in locators
    assert "data.json#pointer=/title" in locators
    assert "data.json#pointer=/owner/name" in locators
