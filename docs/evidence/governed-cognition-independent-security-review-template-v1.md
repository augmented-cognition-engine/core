# Governed cognition independent security review v1

Status: **pending independent review**

This record is the required external sign-off for the E1 governed-cognition
extension boundary. The implementation author or authoring agent must not mark
it accepted. The reviewer validates the exact bundle produced by:

```bash
uv run python scripts/build_e1_security_review_bundle.py \
  --output /absolute/review/path/e1-security-review-bundle-v1.json
```

## Review identity

- Reviewer name and organization:
- Reviewer independence from implementation workstream:
- Review date:
- Bundle SHA-256:
- Base commit:
- Reviewed deployment/package versions:

## Required findings

For every item, record `accepted`, `rejected`, or `remediation required` and
link concrete evidence.

| Boundary | Reviewer disposition | Evidence / finding |
|---|---|---|
| Trusted in-process code is explicitly the only supported execution boundary | pending | |
| Untrusted in-process extension code fails before registration or execution | pending | |
| Current/N-1/future contract negotiation cannot partially register an incompatible extension | pending | |
| Stable identity, owner namespace, product scope, and revision collisions fail closed | pending | |
| Resource manifests reject traversal, absolute paths, invalid digests, and undeclared resources | pending | |
| Registration and discovery have bounded recipes, routes, candidates, bytes, tokens, calls, and artifacts | pending | |
| Models cannot approve, activate, roll back, expire, disable, supersede, or retire cognition | pending | |
| Approval/activation and lifecycle changes use immutable revisions, human authority, and optimistic concurrency | pending | |
| Public receipts exclude raw exceptions, secrets, prompts, credentials, and unbounded attacker-controlled labels | pending | |
| Product, extension, workspace, and user scope cannot silently widen to global | pending | |
| Legacy facades cannot synthesize approval provenance or bypass canonical review | pending | |
| Recovery, restart, rollback, expiry, and historical preservation match the threat model | pending | |
| Package contents and mixed-package behavior match the hashed review bundle | pending | |
| Residual risks and unsupported distributed/external side effects are accurately documented | pending | |

## Findings log

| ID | Severity | Surface | Finding | Required remediation | Resolution evidence |
|---|---|---|---|---|---|
| — | — | — | No findings recorded yet | — | — |

## Reviewer verdict

Choose exactly one after every required finding is resolved or explicitly
accepted by the authorized release owner.

- [ ] **Accepted for E1 release**
- [ ] **Rejected**
- [ ] **Remediation required; review remains open**

Reviewer signature or verifiable approval reference:

Release-owner acceptance reference:

Any accepted residual risk must name its owner, expiry/review date, and rollback
or containment procedure. An empty, self-authored, or bundle-hash-mismatched
record does not close the E1 security gate.
