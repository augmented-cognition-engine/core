"""Tests for the thin Markdown/Obsidian structural parser."""

from ace_local_markdown_source import MarkdownSection, parse_markdown


def test_frontmatter_key_values_are_parsed():
    doc = parse_markdown(b"---\ntitle: My Note\ntags: a\n---\n# Heading\nbody\n")
    assert doc.frontmatter == {"title": "My Note", "tags": "a"}


def test_absent_frontmatter_is_empty():
    doc = parse_markdown(b"# Heading\nbody\n")
    assert doc.frontmatter == {}


def test_headings_become_sections_with_heading_path():
    doc = parse_markdown(b"# One\nalpha\n## Two\nbeta\n")
    assert doc.sections == (
        MarkdownSection(heading_path=("One",), level=1, text="alpha", anchor="One"),
        MarkdownSection(heading_path=("One", "Two"), level=2, text="beta", anchor="One > Two"),
    )


def test_text_before_first_heading_is_a_preamble_section():
    doc = parse_markdown(b"intro line\n# One\nbody\n")
    assert doc.sections[0] == MarkdownSection(heading_path=(), level=0, text="intro line", anchor="")


def test_sibling_heading_resets_path_to_its_level():
    doc = parse_markdown(b"# One\n## Two\n# Three\ngamma\n")
    assert doc.sections[-1] == MarkdownSection(heading_path=("Three",), level=1, text="gamma", anchor="Three")


def test_wikilinks_are_extracted_with_alias_stripped():
    doc = parse_markdown(b"See [[Note A]] and [[Note B|the alias]].\n")
    assert doc.wikilinks == ("Note A", "Note B")


def test_wikilinks_are_deduplicated_in_first_seen_order():
    doc = parse_markdown(b"[[X]] then [[Y]] then [[X]] again\n")
    assert doc.wikilinks == ("X", "Y")


def test_content_is_decoded_as_utf8():
    doc = parse_markdown("# Café\nrésumé\n".encode("utf-8"))
    assert doc.sections[0].heading_path == ("Café",)
    assert doc.sections[0].text == "résumé"
