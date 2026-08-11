# ACE 0.6.0 Measured Intelligence release-candidate work packet (v1)

Status: **bounded release candidate; unpublished; does not close issue #38**

Date: 2026-08-11

## Outcome

Freeze the final package and build identities for the already merged Measured Intelligence runtime
without merging, tagging, publishing, or claiming the milestone complete. The release candidate
must preserve the public product promise:

> ACE can determine, under explicit and inspectable product-defined criteria, whether an
> intelligence artifact or governed cognition revision helped, harmed, or remains unproven, and
> can propose—but never silently apply—promotion, rejection, rollback, or retirement.

The smallest accepted journey remains:

```text
artifact or cognition revision
→ exact material-use attribution
→ Decision
→ reviewed Action
→ observed result and Outcome
→ matched product-owned evaluation
→ useful | harmful | unproven
→ non-effective governance proposal
→ optional authorized no-action disposition
```

## Source and dependencies

This packet starts from exact Core default-branch commit
`f0d2191ba7cf2d33ccfc3c821422786929be8349`. Runtime Measured Intelligence, issue #49 F1/F5
hardening, and owner-governed monitoring are already merged inputs. The public issue #49 checklist
marks F1 and F5 complete; unresolved, unwaived F3 is re-dated to `2026-11-05` under documented
containment.

Release closeout still depends on review and merge of Core PR #95, review and merge of World PR
#17, final artifact verification from the eventual release merge, clean public-index installation,
compatibility/security acceptance, and explicit release-owner approval. This packet does not infer
any of those outcomes.

## Candidate identities

| Artifact | Candidate identity | Publication boundary |
|---|---|---|
| Core + Intelligence | `ace-core==0.6.0` | PyPI only after a separately authorized exact `v0.6.0` release |
| Reference action adapter | `ace-reference-workspace-action==0.2.0` | separate wheel and sdist attached to the Core GitHub Release; never bundled into Core or uploaded by the Core PyPI job |

The adapter distribution changes because its dependency window becomes `ace-core>=0.6.0,<0.7`.
Its executable implementation is unchanged, so the public capability artifact identity remains
0.1.0. Dependency metadata alone must not manufacture a new implementation identity or invalidate
accepted action receipts.

## Acceptance

1. Every Core package, import, engine, reference-extension, lock, container, and workflow identity
   agrees on 0.6.0.
2. The adapter distribution is 0.2.0, depends exactly on `ace-core>=0.6.0,<0.7`, retains executable
   artifact identity 0.1.0, and imports only public `ace.core` contracts.
3. Core and adapter wheel/source archives build twice under one fixed source epoch with byte-equal
   pairs, pass strict metadata validation, keep tests out of both wheels, exclude unintended
   packages, and keep adapter code out of Core.
4. A clean Python 3.12 environment installs the exact candidate archives, resolves both versions
   from `site-packages`, exposes exactly eleven thin MCP tools, and runs the focused package,
   measured-impact, authority, replay, and adapter suites.
5. Required repository lint, fast, naked-kernel, security, Canvas, and Docker gates pass on the
   final draft-PR head.
6. The draft records exact hashes and limitations. No tag, GitHub Release, PyPI upload, milestone
   closure, or supported/public claim occurs in this packet.

## Fail-closed release conditions

The candidate fails if any identity diverges; a version is already occupied on PyPI; the Core
archive contains adapter code; an archive contains tests, credentials, or local build state; a
proposal becomes effective or selectable; historical replay reauthorizes or recomputes; the World
journey requires domain nouns in Core/Intelligence; or an unavailable outcome is reported as
benefit.

## Non-claims

This packet does not prove causality, general benefit, SI4 completion, live freshness, hostile-code
isolation, distributed execution, cross-process exactly-once effects, automatic promotion, or a
general model of reality. Market's independent `unproven` reproduction remains valid evidence that
the neutral contract can abstain; it is not a release blocker or a harmful result.

## Owned files, rollback, and deletion criteria

This packet owns only version identities, release workflow guards, candidate-facing README and
changelog text, focused version tests, this work packet, and its candidate evidence. It changes no
schema, runtime contract, durable record, authority path, Domain Pack, connector policy, MCP tool,
tag, or publication state.

Rollback reverts only those release-candidate changes. Preserve the evidence as a point-in-time
record if final merge identities or artifact epochs change, and supersede it with public release
evidence only after the actual tag, trusted publication, clean public-index installation, World
artifact reproduction, and release-owner acceptance all pass.
