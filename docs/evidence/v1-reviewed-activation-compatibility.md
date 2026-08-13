# V1 reviewed activation compatibility

Status: **bounded seam implemented; product gate remains open**

Verified base: Core `main` at
`8424b12de5999eede6babfec42cc54c27cec7c8e`.

## What this packet establishes

- A reviewed Intelligence-build request carries a separate activation-approval
  receipt reference and exact approval subject.
- Core resolves that reference for the authenticated product and actor before
  an executor receives the build. The resolved approval is historical material,
  not reusable runtime authority.
- Invocation-scoped host services expose the same Core authority resolver so an
  executor can re-resolve current approval at the activation point of use.
- The explicit `ace.application.domain-activation-v1alpha2-to-v1alpha1/v1alpha1`
  adapter accepts only an initial active v1alpha2 plan. It produces canonical
  v1alpha1 activation material only when a **second** approval resolves to the
  exact embedded `DomainActivationSpecV1.spec_id`.
- The adapter refuses plan-approval reuse, product/actor/subject mismatch,
  approvals outside the reviewed plan-to-transition interval, revoked approval
  resolution, and non-initial lifecycle transitions.

The Intelligence-build `AuthorityUseReceipt` is never interpreted as approval.
No authority class, token claim, MCP tool, Domain Pack vocabulary, or executable
discovery surface changes in this packet.

## Remaining v1 product gate

Core does not yet have a supported product flow that lets a person review the
exact activation specification and persist a resolvable approval for it. The
default production build runtime therefore fails closed with
`no reviewed activation approval resolver is registered`.

That product flow must be implemented and exercised before the canonical first
Brief can be claimed from Atrium. A fixture, hard-coded receipt, build-authority
receipt, v1alpha2 plan approval, or executor-generated approval does not close
this gate.

## Focused verification

- Build/host/compatibility: 16 passed.
- Both activation generations plus kernel and exact-eleven boundary: 28 passed,
  1 skipped.
- Unit suite: 946 passed, 11 skipped.
- Supported suite: 7,743 passed, 245 skipped; its six loopback-only sandbox
  failures all passed when rerun with loopback access.
- Wheel and source distribution built successfully without isolation, and the
  compatibility API imported directly from the built wheel. Isolated build
  dependency resolution was unavailable in the network-restricted verification
  environment.
