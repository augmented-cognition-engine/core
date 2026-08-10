# ACE 0.5.0 Reasoning into Action release work packet (v1)

Status: **complete; public release and external-consumer reproduction passed**

Date: 2026-08-10

## Outcome

Release the bounded Reasoning into Action promise already implemented through T1A–T1C and
B1A–B1D, then prove it from public artifacts through an external World Intelligence consumer.

The accepted journey is:

```text
admitted public evidence
→ governed reasoning
→ exact cited Brief
→ authorized Decision
→ effect-free adapter plan
→ durable exact-material human review
→ admitted bounded effect
→ honest terminal receipt
→ separate human verification
→ separate promotion
→ exact replay with no second reasoning call or effect
```

## Release artifacts

- `ace-core==0.5.0` is the Core + Intelligence runtime and is published to PyPI through trusted
  publishing.
- `ace-reference-workspace-action==0.1.0` is a separately built trusted reference adapter. It is
  excluded from the Core wheel and attached as a wheel and source distribution to the `v0.5.0`
  GitHub Release.
- The adapter imports only the public `ace.core` contract, is never dynamically discovered, and
  requires explicit construction and exact artifact registration by the host.

Publishing the adapter as a separate release asset preserves the executable-code boundary without
requiring it to become a Core dependency or a Domain Pack capability. Only `ace-core` is uploaded
to the Core PyPI project.

## Supported topology and portability claim

The supported 0.5.0 topology is one ACE host, one durable store, and explicitly trusted
constructor-supplied adapters executing in process. Portability means the action contract is public,
provider-neutral, host-internal imports are forbidden, and an independently packaged adapter can be
built, installed, registered, and exercised outside the source checkout.

It does not mean remote execution, distributed locks, multi-writer ordering, cross-process
exactly-once effects, compensation, or hostile-code isolation. Those are later platform and
collaborative-runtime concerns rather than hidden 0.5.0 promises.

## External acceptance consumer

World Intelligence P2C2 is the release consumer. Its green candidate on
[domain-world-intelligence PR #3](https://github.com/augmented-cognition-engine/domain-world-intelligence/pull/3)
uses two exact official Federal Register records under recorded transport and the unchanged public
Core contracts to produce the full journey above. The Domain Pack remains JSON-only and contains no
action code or authority. Its only effect is a human-reviewed create-only local workspace export.

The consumer proof does not claim test-time network freshness, autonomous monitoring, automatic
publishing, political persuasion, or legal/policy impact.

The consumer is now public as World Intelligence
[`v0.9.0`](https://github.com/augmented-cognition-engine/domain-world-intelligence/releases/tag/v0.9.0)
and `ace-domain-world-intelligence==0.9.0`.

## Acceptance sequence

1. Version all Core identities, container labels, lock metadata, and the trusted-publishing default
   at `0.5.0` without rewriting historical release evidence.
2. Build and inspect the Core wheel/source distribution and the adapter wheel/source distribution
   independently. Prove the Core archives exclude adapter code.
3. Pass the focused task/action/restart/package suites, full required repository gates, naked
   kernel, dependency audit, Canvas, and Docker checks.
4. Merge the exact green release candidate, tag that merge as `v0.5.0`, and publish the GitHub
   Release. Trusted publishing uploads only Core to PyPI and attaches the adapter artifacts to the
   same GitHub Release.
5. Verify public artifact hashes, provenance, tag/version equality, clean installation, and the
   eleven-tool MCP boundary.
6. Install the public Core package plus the released adapter outside both repositories and
   reproduce the World P2C2 journey without a source-checkout dependency.
7. Record final evidence and reconcile T1, B1, issue #37, the roadmap checkpoint, and the World
   0.9.0 release gate.

## Fail-closed release conditions

The release does not pass if any of the following is true:

- the tag, package version, import version, engine version, extension version, container label, or
  lock identity diverges;
- the Core wheel contains the adapter, either wheel contains tests, or any release artifact contains
  credentials, local build state, or unintended executable packages;
- an unauthorized, rejected, expired, changed, cross-product, or unreviewed plan reaches an effect;
- an uncertain effect can be retried or repaired;
- success implies verification or promotion without separate receipts;
- restart replay prepares or executes a second effect; or
- the external consumer requires a private Core or host-internal import.

## Closeout

All seven acceptance steps passed. The exact merge was tagged and published as
[`v0.5.0`](https://github.com/augmented-cognition-engine/core/releases/tag/v0.5.0),
`ace-core==0.5.0` is public on PyPI, both independently built adapter archives are attached with
matching digests, and a checkout-free environment reproduced the World P2C2 journey from public
Core and adapter artifacts. The authoritative hashes, install receipts, external test totals, and
limitations are recorded in the
[0.5.0 release evidence](../evidence/reasoning-into-action-v0.5.0-release-readiness.md).

T1, B1, and the 0.5.0 milestone are **passed** for the supported one-host, one-durable-store,
explicitly trusted in-process-adapter topology. Later distributed and hostile-code guarantees are
not implied.
