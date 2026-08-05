# Governed Cognition Extension Threat Model v1

Status: implemented boundary; independent security review pending

Date: 2026-08-04

## Support decision

E1 supports cognition supplied by explicitly trusted, installed Python packages running in the ACE
process. Untrusted executable extension code is out of scope. Registration that declares
`trusted_in_process=false` fails before any recipe, route, instrument, or resource becomes visible.
This is a support-boundary decision, not a claim that Python in-process execution is isolated.

Declarative cognition and executable callbacks are distinct. A recipe body, dependency descriptor,
source identity, or resource manifest grants no execution, filesystem, network, review, promotion,
or product authority. Python instruments remain executable trusted package code and are identified
by an exact extension/version/module digest. Product cognition approval cannot make an untrusted
callback trusted.

## Assets and trust boundaries

Protected assets are product-scoped task/source content, approved cognition material and history,
human review authority, package/resource integrity, model context, provider credentials, tool and
execution authority, selection/use evidence, and service availability.

The boundaries are:

1. Package installation and `ace.extensions` entry-point discovery.
2. Registration into the bounded Core registry.
3. Callable-free Level 0/1 catalog metadata.
4. Digest-verified Level 2 resource loading.
5. Product-scoped discovery and task-context composition.
6. Human proposal/review/lifecycle authority.
7. Trusted Python instrument execution.
8. Public task, API, CLI, MCP, metrics, and log projections.

## Threats and required controls

| Threat | Control and fail-closed behavior | Current evidence |
|---|---|---|
| Slug/route collision or same identity with different material | Bounded names; exact owner namespace; duplicate recipe, route, revision, and provenance conflicts reject registration/activation | Catalog, registry, and conformance tests |
| Future or incompatible cognition contract | Current extensions negotiate as their first operation; only current contract and the documented N-1 legacy signature are accepted; future contracts and current-extension/N-1-Core skew refuse before capability mutation; stored future records project unavailable without reinterpretation | Extension conformance, local package matrix, and discovery tests |
| Package/resource substitution | Module/package and resource SHA-256 digests are in callable-free manifests; invalid, absolute, traversing, or malformed resource entries reject registration | Extension conformance tests |
| Prompt or instruction authority injection | Embedded text is data. Instructions cannot grant tools, execution, review, lifecycle, product, workspace, user, filesystem, or network authority | Governance contracts and trusted-code decision |
| Cross-product disclosure or activation | Product ID is required in heads, proposals, reviews, selections, uses, task projections, and receipt reads; foreign records return unavailable/not found | Governance, discovery, API, and restart tests |
| Model self-approval or automatic retirement | Only authenticated human actors with `cognition-review` can approve or move a head; evaluation emits a non-selectable proposal only | Governance, lifecycle, effectiveness tests |
| Missing extension after restart | Stored identity/revision/head history remains; required missing extension dependencies are `unavailable`; no same-slug fallback is selected | Discovery missing-dependency tests |
| Registry/resource denial of service | Recipe, route, dependency, source, candidate, serialized-byte, selected-revision, token, artifact, and receipt bounds fail closed | Contract, budget, and conformance tests |
| Secret/private detail in public evidence | Public manifests contain stable metadata and digests, not callables or resource bodies. Discovery exposes bounded reason codes, never raw database/provider exceptions | Manifest and public normalization tests |
| Partial registration | Current reference packages negotiate before adapters, actions, instruments, recipes, tools, or sentinels mutate a registry; unsupported committee/persona/framework/schema cognition surfaces emit explicit `unsupported_registration`; registration conflicts fail before selection | Extension conformance and local package-matrix tests |
| Package skew | Current Core adapts the v0.2.0 reference signature; v0.2.0 Core refuses the current reference before mutation; both current wheel/sdist mixes load an independent consumer; unknown future and incompatible accepted-version sets refuse | `verify_e1_package_matrix.py` receipt plus extension conformance tests |

## Operational recovery

Disabling extension loading leaves the Core package catalog and eleven thin MCP tools intact.
Approved product recipes whose required extension dependency disappears become unavailable on the
next selection. Operators restore the exact compatible package/digest or move the head, under human
authority, to an available prior revision. They do not edit or delete immutable history.

Backup and restore must include `cognition`, `cognition_revision`, `cognition_head`,
`cognition_activation_event`, proposal/review/import aliases, and selection/use/effectiveness
receipts. Restore verification compares stable IDs, material hashes, generations, product scopes,
and active dependency availability before traffic resumes.

## Review record

The implementation author has completed the threat model and executable control checks. The E1
readiness gate still requires review by a security reviewer independent of the implementation. That
review must record reviewer identity, date, examined commit/artifact hash, findings and severity,
product-isolation and package-skew test results, the accepted trusted-only decision, and closure or
explicit acceptance of every finding. Until that record exists, this document must not be cited as
an independent security approval.

The implementation workstream prepares the fixed, hashed surface with
`scripts/build_e1_security_review_bundle.py`. The independent reviewer completes
`docs/evidence/governed-cognition-independent-security-review-template-v1.md` and binds the verdict
to the emitted bundle hash. The bundle itself always remains `pending_independent_review` and has no
approval authority.
