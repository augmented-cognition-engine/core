# PI13 WS4 local candidate evidence v1

- Date: 2026-08-21
- Baseline: `origin/main` / `e9a53ae63d209a266dc8a5156b1afcd5c939dd08`
- Disposition: **locally verified candidate; not landed**
- Scope: WS4 (full source-kind mapping) only. This record does not claim a public release acceptance
  run or an ACE 1.2 acceptance pass.

## What WS4 delivers

The shipped Personal Pack mapped Markdown alone; the onboarding profile advertised four local kinds.
That gap was the acceptance runs' FINDING-6. The pack now declares four mappings, one per advertised
kind, and the two sets are identical by test.

| Advertised `source_id` | Mapping | Source type | Unit anchor the citation resolves to |
|---|---|---|---|
| `local_markdown_folder` | `local_markdown_note` | `markdown.note` | heading path |
| `local_pdf_document` | `local_pdf_page` | `pdf.page` | one-based page number |
| `local_csv_table` | `local_csv_row` | `csv.row` | one-based row index |
| `local_json_document` | `local_json_pointer` | `json.pointer` | RFC 6901 JSON Pointer |

PDF, CSV, and JSON map into the ontology's existing `document` entity, mirroring the shipped Markdown
declaration exactly: `document_ref` and `title` from the unit's `/0/anchor_value`, `body` from `/0/text`.
Those anchors are what the locator grammar round-trips for each format, so a citation names a real span
inside the file rather than the file as a whole. No ontology change was required and no new entity type
was invented.

The Markdown mapping's `source_definition_ref` moved from `local_markdown_notes` to
`local_markdown_folder`. The packet's acceptance is that "the profile's advertised kinds and the pack's
mapped kinds must be identical by test"; without a shared identifier there is nothing to compare. Pack
manifest resource digests and the solution-bundle manifest were regenerated from the new bytes.

## Verification

Three invariants are now held by tests in
`tests/intelligence/test_personal_intelligence_pack_source_mapping.py`:

1. every kind the profile advertises is mapped, and every mapped kind is advertised;
2. each new kind resolves its declared attributes against the exact first normalized unit its shipped
   adapter really produces — those unit shapes were captured from live `ace-local-source-normalizers`
   output against the real fixtures, not assumed;
3. every mapped entity type and attribute is declared by the pack ontology.

The WS0 lane connects one scope per kind and now requires breadth on both sides: J4 fails
`WS0:inventory_source_kinds_incomplete` and J5 fails `WS0:brief_citation_kinds_incomplete` when any
advertised kind silently drops out, so this cannot regress unnoticed.

## Installed-artifact result

Freshly built wheels, a bare venv outside the checkout, and an ephemeral memory-only SurrealDB at
schema v179:

| Step | Result | Evidence |
|---|---|---|
| J1 Install | PASS | Distributions, schema 179, four fixture kinds, exactly eleven MCP tools |
| J2 Choose | PASS | Installed Personal profile and planner resolve to the pack |
| J3 Connect | PASS | Installed snapshot binding, both exact Connect routes, consent-before-read with zero provider calls; `executor_present:True` |
| **J4 Inventory** | **PASS** | `source_health=5 entity=5 observation=5`, page complete with no degraded reasons; observations resolve to `notes/vault.md`, `notes/second.md`, `sample.pdf`, `sample.csv`, `sample.json` across `csv,json,md,pdf` |
| **J5 First Brief** | **PASS** | `briefs=1 cited_claims=6 uncited_claims=0 unresolved_citations=0`; citations resolve to admitted spans across `csv,json,md,pdf` |
| J6 Change | BLOCKED | No watched source or prior Brief revision (WS5) |
| J7 Ask | PARTIAL | Route present; connected cited answers exercisable once WS5 lands |
| J8 Correct | PARTIAL | Route present; real claim re-derivation is WS5 |
| J9 Restart / J10 Own | BLOCKED | Scoped claims not re-established at this frontier |

WS4's stated acceptance — the WS0 fixture corpus includes all four kinds and every citation resolves to
its span — is met.

Repository verification: full fast suite `9601 passed, 50 skipped, 4 failed`; repo-wide Ruff check/format
and `git diff --check` clean. The four failures are the unchanged pre-existing baseline set (three in
`tests/test_graph_context.py`, whose test file and target are untouched in this worktree, plus the known
pristine-baseline `test_extension_disabled_kernel_starts_without_live_composition`).

This is candidate evidence for WS4 only. It is not a public release acceptance: the amended gate still
requires a clean-context run reporting J1–J10 end to end, maintainer cross-check concurrence, and the
four-record reconciliation. WS5 has not started, and nothing was committed, merged, pushed, tagged,
published, or released.
