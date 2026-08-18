# ace-personal-intelligence-pack

The declarative **Personal Intelligence Domain Pack** for ACE 1.2 (slice PI5).

Inert data compiled by ACE's pack compiler — it models the personal knowledge domain (notes,
documents, concepts, people, projects, decisions, commitments, relationships, revisions,
provenance, and source policy). It holds no credentials, executes no code, and grants no authority.

This distribution ships the pack tree at the path ACE's installed-pack discovery scans:

```
domain_packs/personal_intelligence/
  manifest.json
  modules/{ontology.json, source_mapping.json}
  conformance/activation_golden_fixture.json
```

Installing it into an ACE environment makes Personal Intelligence discoverable in the catalog so a
user can choose it (J2). See `docs/design/personal-intelligence-v1.2-work-packet-v1.md`.
