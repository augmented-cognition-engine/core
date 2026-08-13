# ACE 0.8.0 Intelligence OS release closeout

Status: **public, passed**

Release: [ACE 0.8.0 — Intelligence OS Realignment](https://github.com/augmented-cognition-engine/core/releases/tag/v0.8.0)

Public package: [`ace-core==0.8.0`](https://pypi.org/project/ace-core/0.8.0/)

## Immutable release coordinates

| Coordinate | Value |
|---|---|
| Core release PR | [#142](https://github.com/augmented-cognition-engine/core/pull/142) |
| Tagged main commit | `48395df2e561928dcd8b7dc6fab044d2d111eca8` |
| Tag | `v0.8.0` |
| Published at | `2026-08-13T02:57:41Z` |
| Trusted workflow | [run 31662422173](https://github.com/augmented-cognition-engine/core/actions/runs/31662422173) |
| Core distribution | `ace-core==0.8.0` |
| Reference adapter distribution | `ace-reference-workspace-action==0.4.0` |
| Adapter Core boundary | `ace-core>=0.8.0,<0.9` |
| Adapter implementation artifact | `ace.workspace_action.reference/v0.1.0` |

The release tag resolves exactly to the green squash-merge commit. The trusted workflow checked out
that tag, verified tag/package identity and the adapter dependency boundary, set a fixed build
epoch, built and validated both distributions, published Core through PyPI trusted publishing, and
attached the independently packaged adapter archives to the GitHub release. All three workflow
jobs passed.

## Public artifact hashes

### PyPI Core artifacts

| Artifact | Bytes | SHA-256 |
|---|---:|---|
| `ace_core-0.8.0-py3-none-any.whl` | 6,364,811 | `c9cb85762192422a1949e2af895fcdc836647a8ef88b7aa341aba8770bf3b8a3` |
| `ace_core-0.8.0.tar.gz` | 5,491,757 | `8bbc43c19469be927be0e67a2d05d2ec73094d3b52d01b2942f8171d9d1b8778` |

### GitHub reference-adapter artifacts

| Artifact | Bytes | SHA-256 |
|---|---:|---|
| `ace_reference_workspace_action-0.4.0-py3-none-any.whl` | 5,406 | `71eada9bc7efb685e920ebb288da61c8cbd15d82adf40c863b9f79975bc62001` |
| `ace_reference_workspace_action-0.4.0.tar.gz` | 5,998 | `8d83c5185f0cd4fddb304801dc0a36dd00a4e80158fbabc9855a1bc4de4cffe5` |

## Checkout-free public reproduction

A new Python 3.12 virtual environment outside every repository installed only
`ace-core==0.8.0` from the public package index with the installer cache disabled. The installed
artifact reproduced:

- `ace.__version__ == "0.8.0"`;
- `ace_mcp_client.__version__ == "0.8.0"`;
- all 22 `IntelligenceResourceKind` members;
- `IntelligenceResourcePlaneService`; and
- exactly eleven HTTP-only MCP functions: `ace_start`, `ace_load`, `ace_capture`, `ace_task`,
  `ace_status`, `ace_capture_idea`, `ace_search`, `ace_briefing`, `ace_impact`, `ace_history`, and
  `ace_related`.

The resolver emitted warnings while normalizing legacy invalid version specifiers in third-party
index metadata. Resolution, installation, and the public contract probe completed successfully.

## Release acceptance

The release PR's independent GitHub gate passed:

- Lint;
- Security Audit;
- Canvas typecheck, 294-test suite, and production build;
- Tests (fast gate);
- Naked kernel with zero extensions; and
- dependent Docker build.

Local cumulative acceptance passed 7,904 tests with 48 documented skips and 249 deselections. A
local naked-kernel run encountered one transient Surreal transaction collision after 7,889 passes;
the exact failed test passed immediately in isolation, and the independent GitHub naked-kernel job
then passed the complete gate. The release-only identity/roadmap gate passed 24 tests, the reference
adapter passed 9 tests against the exact local Core candidate, all four archives passed Twine
validation, and a pre-publication clean-wheel install reproduced the same version and surface.

## Cross-domain product proof

- World Intelligence [PR #22](https://github.com/augmented-cognition-engine/domain-world-intelligence/pull/22),
  merged as `8e3343dbb1e1ae89a3407983ae1a5cfb521dd6d6`, reproduced a LIVE official-source
  evidence-to-reviewed-action-to-outcome-to-feedback journey and passed 136 tests with one
  pre-existing skip.
- Market Intelligence [PR #5](https://github.com/augmented-cognition-engine/domain-market-intelligence/pull/5),
  merged as `6132e2c244502a04bb106a3d58212262b6b83069`, reproduced a materially different
  competitive-price journey with an explicit analyst `no_action` disposition and passed 135 tests
  with one optional pre-existing skip.

Both domains use unchanged public Core + Intelligence contracts. Neither adds domain nouns,
source logic, policy branches, persistence, or authority to Core.

## What passed—and what did not become true

0.8 passes the bounded Intelligence OS release claim: one authorized resource plane, one optional
Atrium experience over it, complete onboarding agents, governed composition and memory, bounded
action/outcome/feedback, and two independent domain proofs.

It does not claim hosted SaaS, multi-tenant collaboration, arbitrary hostile-code sandboxing,
universal source coverage, unrestricted autonomy, autonomous proposal application, general causal
accuracy, or a complete World or Market product. Atrium remains repository-delivered preview
source rather than Python-wheel content or an authoritative state path. The single-node trusted-
adapter topology and schema head v177 remain the release boundary.

## Rollback and next milestone

The previous public artifact is `ace-core==0.7.0`; any downgrade must account for data/schema
compatibility rather than only reinstalling the package. The 0.8 tag and public artifacts are
immutable. Roadmap work now advances to bounded 0.9 Collaborative Intelligence; 0.8 maintenance
must use a patch line and cannot silently widen the 0.8 contract.
