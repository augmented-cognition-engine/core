# Changelog

Notable user- and contributor-visible changes are recorded here.

## Unreleased

- Add the versioned, authenticated, strictly read-only `ace landscape` journey for inspecting the
  Living Product Graph with stable identity, evidence, provenance, uncertainty, assertion history,
  deterministic ordering, bounded degraded behavior, and no change to the eleven-tool MCP surface.
- Correct top-level CLI identity copy and hide the legacy experimental `ace skills` command and
  `ace run --skill` selector from default help. Both remain callable for compatibility; this is a
  visibility cleanup, not removal, migration, or a new cognition abstraction.
- Durable public task receipts expose contributor and phase coverage in an `execution` block,
  including explicit partial-result attention without discarding usable output.
- The experimental conflict workflow now persists product-scoped pending conflicts and quarantines
  both claims atomically, writes a durable attention signal, and returns provenance-bearing claims
  and resolution actions through the authenticated conflict API.
- Complete I1 decision and correction inspection with structured evidence, assumptions,
  alternatives and reconsideration conditions; all four human dispositions; preserved
  supersession, invalidation, contestation and expiry; explicit incomplete provenance; fail-closed
  authorization, isolation and redaction; and schema-zero-to-v145 replay without widening the
  eleven-tool MCP surface.
- API startup and the standalone schema installer share one audited historical-migration
  compatibility policy while migrations v142 and later remain fail-closed.

## 0.1.1

### Supported

- Lead the public entry journey with one product-builder quickstart: bring a real decision,
  choose an existing model route, start the self-hosted runtime, and receive a recommendation.
- Keep advanced architecture, MCP, provider, extension, and manual-operation material available
  through progressive disclosure after the quickstart.

### Fixed

- Use concise outcome-led package metadata and absolute public links that continue to work when
  the README is rendered on PyPI.
- Make installed `ace setup --help`, missing-runtime guidance, provider selection, `ace doctor`,
  and service recovery point to concrete commands or public documentation without assuming
  repository knowledge.
- Include the R1 setup fixes for optional Discord configuration, Docker/Colima recovery, API log
  discovery, failed activation exit status, managed-process shutdown, and doctor recovery actions.

### Release maintenance

- Keep distribution, import package, engine, thin MCP client, reference extension, and public
  capability versions aligned at `0.1.1`.
- Default manual trusted publishing to `v0.1.1` and fail closed when a release tag does not match
  package metadata.

### Known limitations

- The complete self-hosted first-recommendation flow still uses a source checkout for its pinned
  Compose stack and local service scripts; the wheel provides imports and commands but does not
  silently download or provision runtime assets.
- Python 3.12 is the supported interpreter. R1 usability evidence is based on isolated AI-operated
  proxy trials rather than independent human testing, and model quality, capacity, and latency
  remain provider-dependent.

## 0.1.0

- Initial developer preview of the `ace-core` Python distribution, preserving the `ace` import
  package, `ace` CLI command, and version `0.1.0`.
- The supported public interaction boundary is the thin 11-tool MCP package and CLI.
- Atrium remains a separate experimental visual-product/research track and releases as public
  repository beta source while staying outside the Python wheel/sdist, golden path,
  supported-runtime claims, and supported release contract.
- The frozen `ace-preview-surface-v1` M2 scenario proved one durable preference survived restart
  and materially affected a later decision. Its matched-model evidence is n=1 and does not support
  a general superiority claim.
- Python packaging includes the kernel, CLI, thin MCP client, schema migrations, reference
  extension, evaluation material, public documentation, license, and notice while excluding
  Atrium beta source and local state.
- `ace doctor` validates a protected authenticated request and reports the effective provider-neutral
  model policy; `ace model-policy` exposes fast/capable/frontier mapping and degraded state.
- Supported Python is 3.12; the SurrealDB Python client is constrained to the compatible 1.x line.
- The heavyweight CodeSage/PyTorch embedding backend is now an explicit `codesage` extra; the
  default ONNX-backed install no longer pulls GPU/CUDA packages into the release container.

Release entries separate supported, experimental, fixed, security, migration, and known-
limitation notes.
