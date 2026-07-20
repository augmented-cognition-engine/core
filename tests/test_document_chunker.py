# tests/test_document_chunker.py


def test_splits_by_headings():
    """Document chunker splits markdown by ## headings."""
    from core.engine.capture.document_chunker import chunk_document

    content = """# Token Conventions

## Naming
Tokens use acme- prefix with kebab-case.

## Colors
Color tokens follow acme-color-{name}-{weight} pattern.

## Spacing
Spacing uses 8px grid multiples."""

    sections = chunk_document(content)
    assert len(sections) >= 3
    assert any("kebab-case" in s["content"] for s in sections)
    assert all(s["section_title"] for s in sections)


def test_splits_by_paragraphs_without_headings():
    """Falls back to paragraph splitting when no headings."""
    from core.engine.capture.document_chunker import chunk_document

    content = """First important point about tokens.

Second important point about naming.

Third point about distribution."""

    sections = chunk_document(content)
    assert len(sections) == 3


def test_preserves_metadata():
    """Each section includes title and index."""
    from core.engine.capture.document_chunker import chunk_document

    content = """## Setup
Install dependencies.

## Usage
Run the command."""

    sections = chunk_document(content)
    assert sections[0]["section_title"] == "Setup"
    assert sections[0]["index"] == 0
    assert sections[1]["section_title"] == "Usage"


def test_empty_document():
    """Empty doc returns empty list."""
    from core.engine.capture.document_chunker import chunk_document

    assert chunk_document("") == []
    assert chunk_document("   ") == []
