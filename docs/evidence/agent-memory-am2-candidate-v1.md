# ACE 0.7F Agent Memory AM2 candidate evidence v1

## Candidate coordinates

- Exact AM1 base: `8b5cd08e5c49962024323bb981bc221deacef649`
- Base branch: `codex/v0.7-agent-memory-am1`
- Candidate branch: `codex/v0.7-agent-memory-am2`
- Exact AM2 implementation artifact: `5f678941e0cfca82463a932b5fd3eb8c785bece9`
- Checkout-free wheel: `ace_core-0.6.0-py3-none-any.whl`
- Wheel SHA-256: `44f101e8e5d6e3bb659e194e1568e8db0ba9d5a9b586e70d0c5f2333a9c1df80`
- Status: isolated stacked draft candidate; not accepted, merged, released or supported

## Claim and limit

This candidate implements typed, source-grounded memory-assertion proposals and deterministic
reconciliation over authorized AM1 turn/event and other exact source envelopes.  Extraction does not
become truth.  Reconciliation does not grant instruction authority, correction authority, current
truth, recall eligibility, context injection, lifecycle autonomy or durable learning.

The exact contracts, ownership, canonical journey, fail-closed matrix and AM3 entry gate are frozen
in `docs/design/agent-memory-am2-work-packet-v1.md`.

## Verification ledger

| Gate | Result |
| --- | --- |
| Frozen AM0/AM1/PR topology and exact base | Passed before branch creation |
| Provider-free AM2 conformance | 19 passed |
| Focused AM0-AM2 | 124 passed with local Surreal access |
| Real Surreal restart/reopen, fresh process, projection rebuild and atomic failure | Passed; exact replay did not reread source body, fresh client/process reproduced transaction and graph, injected append left zero AM2 records |
| Relevant Core/Intelligence/governed-cognition/time/graph/privacy/boundary suites | 209 passed with local Surreal access |
| Full supported non-E2E/non-extension lane | 7,589 passed, 245 skipped, 261 marker-deselected; four sandbox-only localhost failures passed in the exact unsandboxed rerun |
| Package, naked kernel and exactly eleven MCP tools | 76 passed in the final focused boundary rerun; public MCP inventory remains exactly eleven |
| Ruff, format, lock, diff, schema, authority, privacy, domain, composition and secret scans | Whole-repository Ruff, AM2-path format, lock, diff, focused schema (34 passed), AC6, AC7, secret and domain-vocabulary scans passed |
| Checkout-free installed wheel in two clean targets | Passed from the exact implementation artifact in two fresh `/tmp` targets outside the checkout; both loaded AM2 application and contract modules from the installed wheel, exposed all seven families and the `v1alpha1` candidate contract, and retained exactly eleven thin MCP tools |

## Environmental disclosure

The first repository-environment command attempted to reconstruct dependencies and could not fetch
`hf-xet==1.4.2` because sandbox DNS was unavailable.  No dependency, lock, package-version or source
contract was changed.  Verification then used the repository's already-installed environment.

The first sandboxed AM2 Surreal run skipped because localhost access was denied with `Operation not
permitted`.  The identical test passed in the approved unsandboxed rerun.  This is reported as an
environmental first-pass limitation, not represented as an initially green database run.

Whole-repository format check remains red on 16 unrelated pre-existing files; all AM2-owned paths
and the two additive public initializers are formatted.  A deliberately broad legacy schema sweep
reported nine pre-existing failures: missing `org`, missing `schema/v043_composition_memory.surql`,
four legacy string-record DELETE assumptions, and three legacy field-coercion assumptions across
v020/v024.  The focused current schema integrity lane passed 34 tests, and AM2 adds no schema or
migration.

## Privacy and causal boundaries

Receipts and graph projections expose no transcript, document or assertion body.  A successful
extraction receipt proves only exact structured proposal construction.  Agreement proves only
inspectable agreement among classified sources.  A governed-state commit proves exact approval and
authority admission for exact material; it does not prove downstream use, benefit, quality or
correctness.  AM2 makes no AM3 recall, ranking or context-use claim.
