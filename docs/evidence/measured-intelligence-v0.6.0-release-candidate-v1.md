# ACE 0.6.0 Measured Intelligence release-candidate evidence (v1)

Status: **candidate, unpublished; verification incomplete; does not close issue #38**

Date: 2026-08-11

## Point-in-time source

- Default-branch base: `f0d2191ba7cf2d33ccfc3c821422786929be8349`
- Candidate implementation commit: `6e1a3a733e17a5c8e0d7edc9bcb8017ff5f0e8f0`
- Candidate branch: `codex/v0.6.0-release`
- Fixed build epoch: `1786477483`, the candidate implementation commit timestamp

This record verifies only that exact implementation commit. The evidence commit, PR review,
dependency merges, and any later release commit necessarily change the Core archives and require a
fresh exact-source rebuild. No artifact named below has been tagged, uploaded, or published.

## Candidate artifacts

Two independent builds under the fixed epoch produced byte-equal pairs:

| Artifact | Candidate identity | SHA-256 |
|---|---|---|
| Core wheel | `ace_core-0.6.0-py3-none-any.whl` | `baf11e4a6283a28e1593adb992a8d59a3bfcec29dba003aeb06c94ae3043647f` |
| Core source distribution | `ace_core-0.6.0.tar.gz` | `a42984b3dcb5dfb0872230767de74ed745e79566937d85f47109c3c49510d67a` |
| Reference adapter wheel | `ace_reference_workspace_action-0.2.0-py3-none-any.whl` | `32ec89012aea11fbc08018ccb80dc72ccae435b92c187e65a8b0ad23d3fcc58a` |
| Reference adapter source distribution | `ace_reference_workspace_action-0.2.0.tar.gz` | `0cd3e7fbe746c7780baa6206d9cc2d568d884cb9f949578cabaf0569991db523` |

Strict package-metadata validation passed for all four archives. An independent archive probe
confirmed:

- both wheels exclude tests;
- the Core wheel contains no reference-adapter package;
- the adapter wheel contains no Core or engine package;
- the adapter metadata requires exactly `ace-core>=0.6.0,<0.7`;
- both source distributions have normalized epoch, owner, and group metadata.

The release workflow now normalizes the separately built adapter source distribution with the same
repository build backend used for Core. Before that guard was added, repeated raw adapter source
builds differed in host/build metadata; the release candidate therefore records the discovered
failure and the reproducible result rather than treating a one-off build as sufficient.

## Installed-artifact probe

A new CPython 3.12.13 environment outside the repository installed only the exact Core and adapter
wheels above plus their resolved public dependencies. The probe reported:

- `ace-core==0.6.0` and `ace.__version__ == "0.6.0"`, imported from `site-packages`;
- `ace-reference-workspace-action==0.2.0`, imported from `site-packages`;
- unchanged adapter capability implementation identity `0.1.0`;
- exactly eleven thin runtime tools with Intelligence disabled.

`pip-audit 2.10.0` reported **no known vulnerabilities** in the installed dependency set. It skipped
only `ace-core==0.6.0` and `ace-reference-workspace-action==0.2.0`, because neither candidate
version exists on PyPI. Exact-version registry probes independently returned not-found for both
candidate versions at the time of this record.

## Repository verification

Focused candidate verification:

```text
PYTHONPATH=adapters/reference_workspace_action/src .venv/bin/pytest \
  tests/test_package_identity.py \
  tests/test_build_backend.py \
  tests/intelligence/test_measured_impact.py \
  tests/intelligence/test_measured_impact_disposition.py \
  adapters/reference_workspace_action/tests/test_adapter.py \
  -q --tb=short
```

Result: **51 passed, 2 skipped** in 4.49 seconds.

Repository lint and format checks:

- `.venv/bin/ruff check .` — passed;
- `.venv/bin/ruff format --check .` — passed, 2,047 files already formatted.

Local fast-suite attempt:

```text
.venv/bin/pytest -m "not e2e" -q --tb=short
```

Result: **7,299 passed, 241 skipped, 249 deselected, 7 failed** in 231.88 seconds. The seven
failures were environmental rather than measured-impact or package-identity failures:

- four loopback socket tests could not bind/connect inside the default local sandbox and passed
  unchanged when rerun with loopback access;
- three checksum-frozen historical runtime-baseline tests require a normal Git checkout, while
  this packet is intentionally built in a linked Git worktree whose `.git` entry is a file.

The historical baseline reader was not changed to conceal that worktree limitation: doing so would
change checksum-frozen acceptance source. A normal-checkout GitHub run is therefore a mandatory
remaining gate. The draft PR must also pass the repository's naked-kernel, security, Canvas,
Docker, and other required checks before this candidate can advance.

## Product evidence composed, not re-certified

This packaging packet does not recompute or promote the Measured Intelligence outcome. It composes
already merged Core runtime and issue #49 F1/F5 hardening with two still-reviewable proving targets:

- Core convergence PR #95 at `475cdf537e1ebae941785adb539bb2b48489c739`;
- World Intelligence public-data PR #17 at `a85da4289ff80fff6e6507b546dca191ff92d841`.

The World journey demonstrates the useful path from an exact Brief through Decision, reviewed
Action, observed result, Outcome, matched evaluation, and a non-effective proposal. Market's
independent reproduction remains `unproven`, which demonstrates abstention rather than benefit or
harm. Both contracts remain domain-neutral; source policy and domain nouns stay outside Core.

## Remaining release gates and non-claims

The candidate is not release-ready until human review and merge of Core PR #95 and World PR #17,
normal-checkout CI, final-merge artifact rebuild, compatibility/security acceptance, clean
public-index installation, independently rerun World artifact evidence, and explicit release-owner
approval all pass. Issue #49 F3 remains open, unwaived, contained, and explicitly due
`2026-11-05`; this packet does not silently resolve it.

This evidence does not prove causality, general benefit, SI4 completion, live freshness,
hostile-code isolation, distributed execution, cross-process exactly-once effects, automatic
promotion, or ACE 0.6 completion. It authorizes no merge, tag, GitHub Release, PyPI upload, issue
closure, or milestone claim.
