# ACE 1.1.0 Code Intelligence public release v1

Status: **public, passed**

This record closes the bounded ACE 1.1 Code Intelligence release gate. It composes the immutable
candidate and acceptance records with the public merge, tag, trusted publication, public artifact,
and checkout-free installation facts observed on 2026-08-17.

## Public identities

- reviewed PR: [#204](https://github.com/augmented-cognition-engine/core/pull/204), all six required
  GitHub Actions checks passed;
- squash merge: `4915ca24eccaf64490f8965ab8d8ab4576fd5960`;
- tag and GitHub Release: [`v1.1.0`](https://github.com/augmented-cognition-engine/core/releases/tag/v1.1.0);
- trusted publication run:
  [`32053847446`](https://github.com/augmented-cognition-engine/core/actions/runs/32053847446),
  passed build, PyPI publication, and reference-adapter attachment;
- public package: [`ace-core==1.1.0`](https://pypi.org/project/ace-core/1.1.0/);
- public wheel SHA-256:
  `06460b0378a89588e50f724adcb73b9a0672a53f5e01b1d4f2d6ca1a0675ee67`;
- public source archive SHA-256:
  `a1e6b3918259e8696864bdd8eb0e4169a2dc2b97223a25461d525951cea88b1d`.

## Checkout-free verification

A fresh Python 3.12 environment installed exactly `ace-core==1.1.0` from the public PyPI index,
without a repository checkout or local artifact path. Dependency validation reported no broken
requirements. Both `ace` and `ace_mcp_client` resolved inside that environment's `site-packages`,
and `ace.__version__` returned `1.1.0`.

The installed thin MCP surface contained exactly:

`ace_start`, `ace_load`, `ace_capture`, `ace_task`, `ace_status`, `ace_capture_idea`, `ace_search`,
`ace_briefing`, `ace_impact`, `ace_history`, and `ace_related`.

## Four-record reconciliation

| Record | Public disposition |
|---|---|
| ROADMAP | 1.1 is **Passed**; Personal Intelligence 1.2 is **Now** |
| Issue #194 | Closed with the tag, publication run, artifact digests, and this evidence record |
| Release Spine Project | Code Intelligence complete; Personal Intelligence moved to **Now** |
| Release evidence | This public record supersedes the local candidate as the current release disposition |

## Supported boundary and limitations

The supported boundary remains Python 3.12, SurrealDB 3.2, schema head v179, and the documented
single-node topology. Code Intelligence provides bounded read-only repository reasoning,
untrusted-repository admission, strict downstream returns, and product-scoped delegated cognition
review under pre-existing grants. It grants no general self-approval, merge, deployment, network,
delivery, external-effect, or authority-expansion power.

This release does not claim universal language coverage, safe-deletion proof, hostile-code or
compromised-host isolation, exhaustive secret detection, managed hosting, collaboration,
distributed availability, universal connectors, or general causal benefit. Upgrade operators must
follow the documented dry-run, backup, mapping, quarantine, restart, and restore procedure.
