# Changelog

Notable user- and contributor-visible changes are recorded here.

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
