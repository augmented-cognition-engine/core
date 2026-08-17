# Personal Intelligence local source adapters v1

- Date: 2026-08-17
- Slices: PI2 (adapters) and PI3 (governed local acquisition) of the
  [ACE 1.2 work packet](personal-intelligence-v1.2-work-packet-v1.md)
- Status: **architecture decision; PI2 implementation starting**

## Decision

Local source support splits into two layers with a hard boundary between them:

1. **Governed local-acquisition port (PI3, application layer, in ace-core).** Owns the
   security-sensitive plumbing: walking an authorized folder, enforcing read-only access and
   include/exclude scope, computing the canonical content digest of exact bytes, and producing the
   recorded-source material admitted through `recorded_source_admission`. This is the trust
   boundary and lives in one governed, audited place.

2. **Thin per-format adapter packages (PI2, adapter ecosystem).** Pure translators with the
   signature `(bytes, format) -> structured document + anchors`. They contain no filesystem
   traversal, no authority logic, and no digesting. Four independently versioned packages:
   `ace-local-markdown-source`, `ace-local-pdf-source`, `ace-local-csv-source`,
   `ace-local-json-source`.

## Why this split

- ACE's constitutional principle is that adapters do **bounded translation** while Core and the
  application layer own **identity, provenance, digest, and authority**. Deciding which of a
  user's files may be read, and digesting exact bytes, is exactly the kind of governed mechanic
  that must not be re-implemented per adapter.
- It minimizes the trusted surface: one governed acquisition port instead of four packages each
  re-implementing read-only enforcement.
- It isolates dependencies: only `ace-local-pdf-source` pulls a PDF parser (**pypdf**). A user who
  connects only Markdown, CSV, and JSON pulls no PDF dependency.
- It keeps adapters trivially small, pure, and independently releasable — satisfying the packet's
  "independently versioned adapters through exact bundle bindings" without duplicating plumbing.

## Adapter output contract (feeds PI4)

A thin adapter returns a structured document whose elements carry a **stable anchor** so PI4's
citation locator grammar can resolve every citation to an exact span:

- Markdown/Obsidian: frontmatter key/values, sections keyed by heading path, and wikilinks; anchor
  is the heading path.
- PDF: text per page; anchor is the page number.
- CSV: rows; anchor is the row range.
- JSON: values; anchor is the JSON Pointer.

Adapters never emit a recorded-source record, a digest, or a freshness claim — those belong to the
governed acquisition port.

## Future formats (docx, pptx, xlsx, …)

Office and other document formats are **out of ACE 1.2 scope** by construction: the 1.2 acceptance
gate (issue #195) is frozen to local Markdown/Obsidian, PDF, CSV, and JSON, and 1.2 does not
promise a universal connector catalog. Adding a format to 1.2 would break that frozen gate.

The whole point of this architecture is that they drop in later without touching Core or the
governed acquisition port. Each new format is another thin sibling adapter package with:

- the same `(bytes, format) -> structured document + anchors` shape;
- its own anchor grammar — docx: heading/paragraph path; pptx: slide number; xlsx: sheet + cell
  reference; and
- its own isolated parser dependency (`python-docx`, `python-pptx`, `openpyxl`), so a user pulls a
  parser only for a format they actually connect.

The governed acquisition port dispatches to an adapter by file extension; adding a format is a new
package plus one registration, never a change to the trust boundary. Which formats to build, and
when, is an adapter-ecosystem decision driven by demonstrated Solution Bundle need — not a 1.2
commitment.

## Scope of this document

This records the PI2/PI3 boundary and the four-package shape for 1.2. It does not implement PI3 (the
acquisition port) or PI4 (the mapping/locator grammar); each lands under its own slice. PI2 begins
with the Markdown/Obsidian adapter, which is stdlib-only and adds no dependency; only the PDF
adapter carries a parser dependency (pypdf).
