# ACE 0.6.0 Measured Intelligence merge-candidate audit evidence (v1)

**Status:** bounded candidate evidence. This is not a merge, issue closeout, package-version
decision, tag, publication, SI4 pass, or ACE 0.6.0 release claim.

**Recorded:** 2026-08-11

## Live source and review state

The audit refreshed GitHub and both remotes after the convergence drafts opened.

| Surface | Exact live result |
|---|---|
| Core source | `be5e76c79715bb34bcbdcae9a0471a5c317fafe7` -> `37e6c8a6da0fc95e378c1be50d8704c00dd96415`; strict ancestry |
| Core PRs | #88 -> #89 -> #90 -> #91; all open, draft, mergeable; zero submitted reviews and zero inline review threads |
| Core issues | #38 and #49 open; neither had an issue comment at audit time |
| Original World stack | #6 -> #7 -> #8 -> #9 -> #10 -> #11 -> #12 -> #13 -> #15; all open drafts with zero submitted reviews and zero inline review threads |
| World divergence | Live `main` advanced to `8de1027c4c995582b42c4a1f936a72e2c42878a0`; bottom PR #6 is not mergeable against that new base even though later internal stack links remain mergeable |
| World direct-main candidate | [PR #17](https://github.com/augmented-cognition-engine/domain-world-intelligence/pull/17), head `2d7a0ace72bed4d175b0884c8a9b81b6ec063d56`, base `main`; open, draft, mergeable; [release-readiness run 31503593324](https://github.com/augmented-cognition-engine/domain-world-intelligence/actions/runs/31503593324) passed |

No existing PR branch was rebased, force-pushed, merged, closed, or retargeted.

## Direct-main World artifact result

The World candidate replayed the thirteen measured-intelligence commits over the exact new live
base and retained the merged AI Command Center lineage proof. The only replay conflict was
documentation; both evidence links and claim boundaries were preserved.

| Artifact | SHA-256 |
|---|---|
| Core wheel | `29752aa751570286794ff2abd1071a43f622883d4778e161687e10363f76f6c3` |
| Reference action-adapter wheel | `9c600d4b3e0d19525f1e04629bd231d8d6913d2ad11bc63fa2858e7da396f8f1` |
| World Federal Register source-adapter wheel | `1b80cc598b467a8ab0f47aabb5f01bd0cb1c7709b48aa02352a0ef802988b4fe` |
| World wheel | `a067b3106772437d2dcfee890dc7d89005d3f7afd9e6dc0cbed027327bea9cae` |
| Canonical World convergence JSON | `b70f972e6b7e86ddce09eb3feaa3cd89eede2b236d3e592ee5417dda4d3e95f7` |

The two repeated World-owned wheel builds were byte-identical. Two fresh installed-artifact journey
runs emitted byte-identical canonical JSON. Repeated sdist gzip containers were not byte-identical,
so no reproducible-sdist claim is made and final release artifacts remain an open gate.

World verification after live-main reconciliation:

```text
combined AI lineage + P2C3-P2C10 + convergence: 37 passed
complete candidate-Core World suite: 120 passed
Federal Register adapter suite: 62 passed
release contract: 7 passed
post-format AI/source controls: 66 passed
Ruff check/format and git diff --check: pass
```

## Core verification inheritance

This audit changes documentation only; Core implementation remains exactly
`433e3d16c5458c975557dcd1552824fb959d4d12`. Its frozen convergence evidence remains:

```text
focused Core impact/disposition/boundary: 45 passed, 2 sandbox-only DB skips
kernel boundary: 4 passed
locked non-E2E/non-extension lane: 7456 passed, 50 skipped, 260 deselected
ordinary-clone historical baseline: 7 passed
loopback checks outside sandbox: 4 passed
clean candidate-wheel catalog check: 1 passed
Ruff check/format, whitespace, and pip-audit: pass; no known vulnerabilities
```

The audit packet reran the focused documentation-adjacent Core gates: `45 passed, 2 skipped` where
both skips were the restricted sandbox denying the local SurrealDB socket; kernel boundary was
`4 passed`. Whitespace passed and a scoped credential-pattern scan found no match. This packet does
not relabel the inherited full result as a new implementation run.

## Issue #49 disposition required

The code audit found:

- F1 still preflights `cognition_head` generation before its transaction and relies on the v169
  unique activation-generation index as the atomic race backstop; exact loser reconciliation from
  durable review/head/proposal receipts is not yet a demonstrated real-database path.
- F3 has ceilings for recipes, routes, resources, task actions, and grounded-state adapters, but
  tools, verify checks, briefing sections, unsupported registrations, and delegated registration
  remain non-atomic; a late extension failure can leave earlier global mutations behind.
- F5 still selects and updates `ONLY <record>$id`, so a caller-controlled record coordinate is not
  pinned to the `self_optimizer_proposal` table before the same-product check.

Recommended owner disposition: implement F1 and F5 before 0.6; re-date F3 to `2026-11-05` with the
trusted-package, kill-switch, compatibility, and disable-on-partial containment recorded in the
work packet. These are recommendations, not accepted decisions. F1, F3, and F5 remain **open 0.6
release gates; not waived, deferred, resolved, or re-dated** until the authenticated owner updates
issue #49.

## What is now proved and what remains

The exact Core candidate and live-main World integration candidate are technically converged for
review. The public World artifact still classifies the frozen correction rule as useful and emits
only a non-effective, non-selectable, unapplied promotion proposal. The independent Market
candidate remains separately expressible through the unchanged neutral contract.

ACE 0.6 remains blocked on review/merge order, issue #49 owner decisions and any selected hardening,
merged-source Core/World/Market compatibility and security, final version/artifact identities,
public-index installation, publication, and final release-owner acceptance. No causal, population,
human-benefit, live-monitoring, proposal-application, SI4-pass, or release claim is made.
