# ACE Agent Memory AM6 evaluation-preparation candidate evidence v1

## Candidate coordinates

- Date: 2026-08-12
- Exact base: `f761a682164d10e2ff81ba38cd2d0c987b4f8efd`
- Base branch: `codex/v0.7-cumulative-integration-acceptance`
- Candidate branch: `codex/v0.7-agent-memory-am6-evaluation-prep`
- Exact implementation artifact: `948f452cc691e68c599dbe8ee4b57b61f0c95710`
- Cumulative review-only authority: PR #122; unchanged by this lane
- Unpublished wheel: `ace_core-0.6.0-py3-none-any.whl`
- Wheel SHA-256: `191c2930163f80ffdd4deb98c0042a9907e3fad9618e2809969ffa737094b415`
- Status: isolated stacked draft candidate; not accepted, merged, released, or supported

## Candidate claim and limit

This candidate freezes a provider-neutral AM6 corpus, measurement protocol, matched condition
assignment, observation, comparison, report shape, deterministic fixture, verifier, and conformance
suite that can run over the existing AM0–AM3 boundary.

It does not prove Agent Memory benefit, general correctness, causal effect, production maturity, or
an eligible policy change. Its beneficial, harmful, neutral, and underpowered results are synthetic
oracle labels that prove the evaluator recognizes the preregistered cases. Causality remains
`not_established` for every result.

No rank, retention, consolidation, promotion, roster, authority, delivery, or effect policy changes
are emitted or applied. No provider, credential, network, schema, migration, database, package
identity, public TaskCreate field, or new MCP tool is required.

## Frozen corpus and protocol

The frozen provider-free coordinates are:

- corpus:
  `memory_evaluation_corpus:57b629504eac4f10af39f7943be4143f`
  (`sha256:57b629504eac4f10af39f7943be4143fac31d483e9029769aabfcea3024f02be`);
- protocol:
  `memory_evaluation_protocol:434a03e50ca5c3c43c3eaa9430600ac9`
  (`sha256:434a03e50ca5c3c43c3eaa9430600ac95bf00e26101400795df030db4b045729`);
- 18 cases;
- three matched conditions per case: memory, no-memory, and full authorized context;
- 54 condition observations;
- 31 frozen measures; and
- 15 AM0–AM3-runnable cases plus three future-AM4 gated placeholders.

The assignments hold exact task, provider, model, prompt contract, decision schema, toolset, and
configuration constant. The acceptance fixture explicitly uses `model:none`; provider credentials
and network access are not required.

Coverage includes AM1 ingestion/replay/restart, every AM2 family, extraction and source spans,
identity/unresolved state, conflict/correction/contradiction/uncertainty, instruction isolation,
the three time axes, scope/privacy, AM3 authorization denial, stale/superseded influence, Context
Manifest selection and omission, degraded signals, later restart/material use, resource telemetry,
and the separation of material influence from benefit.

The deterministic outcome distribution is:

| Disposition | Count | Meaning |
|---|---:|---|
| beneficial | 8 | Synthetic bounded rule cleared; not an Agent Memory benefit claim |
| harmful | 1 | Deliberately injected stale/superseded negative probe was detected |
| neutral | 4 | No bounded score gain, including one materially different result |
| underpowered | 5 | Missing signal/telemetry or future AM4 coordinate was explicit |

## AM4 boundary

The current runnable suite imports no AM4 implementation and invents no AM4 runtime contract. The
retention/expiry, export/import, and hard-erasure cases require only the literal
`future_accepted_am4_coordinate`; all their required measurements are unavailable and their result
is underpowered.

The minimal later convergence is to bind exact accepted AM4 artifact coordinates, replace only the
three placeholder observation inputs with existing AM4 evidence, and rerun the same matched
protocol. No current AM3 case, held constant, or v1 evidence record needs rewriting.

## Verification ledger

| Gate | Result |
|---|---|
| Exact base, detached-head cleanliness, and requested sibling branch | Passed before changes; base was exact `f761a682164d10e2ff81ba38cd2d0c987b4f8efd` |
| Focused AM6 conformance | 14 passed |
| Focused AM0–AM3 plus AC6 and AM6 matrix | 177 passed |
| Privacy, package, naked-kernel, evidence-index, public Core/Intelligence and exact-MCP boundaries | 60 passed |
| Full supported extension-disabled non-E2E lane | 7,820 passed, 50 skipped, 261 marker-deselected |
| Provider-free AM6 verifier | 18 cases, 54 observations, three AM4 placeholders, deterministic restart reconstruction |
| Existing provider-free AC6 verifier | 14 matched cases, one inert AC6 proposal, deterministic restart replay |
| Whole-repository Ruff and changed-file format | Passed |
| Lock and diff integrity | `uv lock --check` and `git diff --check` passed; no dependency or lock change |
| Secret scan | Passed across every AM6-owned path |
| Provider/host/storage/import boundary | Passed; pure Intelligence contracts/evaluator import no host, provider, extension, MCP, or SurrealDB runtime |
| Authority/privacy/AM4-invention scan | Passed in focused negative conformance; no policy-applying type or AM4 service/contract exists in the diff |
| Checkout-free installed-wheel reproduction | Passed in two clean targets; both loaded the evaluator from the installed wheel and reproduced exact corpus/protocol IDs, 18 outcomes, restart determinism, and 11 thin MCP tools |

The full supported lane emitted existing dependency deprecation, weak synthetic JWT test-key, and
test-collection/runtime warnings. It had no failure. No local database, live provider, or external
network was used by AM6 acceptance.

## Installed-wheel reproduction

The wheel was built without isolation from the exact locked repository environment and was not
published. It was installed without dependencies into:

- `/tmp/ace-am6-wheel-target-one.3m7zNM`; and
- `/tmp/ace-am6-wheel-target-two.UBQwf6`.

Both targets loaded `ace.intelligence.agent_memory_evaluation` from the installed target rather
than the checkout and reproduced:

- corpus `memory_evaluation_corpus:57b629504eac4f10af39f7943be4143f`;
- protocol `memory_evaluation_protocol:434a03e50ca5c3c43c3eaa9430600ac9`;
- 18 cases with outcome counts 8 beneficial, 1 harmful, 4 neutral, and 5 underpowered;
- fresh reconstruction identity equality; and
- exactly eleven unique public thin-MCP tools.

## Artifacts and effective diff

The implementation commit changes 12 paths against the exact base:

- additive Intelligence contract and pure comparator modules;
- additive exports in the existing Intelligence initializers;
- frozen fixture and result;
- provider-free source runner and verifier;
- focused AM6 conformance plus one public-surface boundary expectation; and
- AM6 work packet and documentation index.

It changes no AM0–AM3 runtime implementation, AM4 branch or contract, AC6 composition policy,
schema, migration, dependency, package version, MCP server, TaskCreate contract, release metadata,
or external repository.

## Publication and convergence limit

The effective diff is independently reviewable against
`codex/v0.7-cumulative-integration-acceptance` and contains no AM4 invention. It is therefore
eligible only for the requested stacked **draft** PR while that exact remote base ref exists.
Merge, release, tag, package publication, policy activation, and downstream dispatch remain
prohibited.

After this evidence commit, the exact candidate branch was pushed successfully. The preferred
GitHub integration rejected draft creation with `403 Resource not accessible by integration`. The
authenticated CLI fallback then reported that both base and head SHA were blank and that the base
was not a branch. Read-only inspection established the cause: PR #122 merged at
`2026-08-12T20:04:34Z` with exact head
`f761a682164d10e2ff81ba38cd2d0c987b4f8efd`, and GitHub deleted remote branch
`codex/v0.7-cumulative-integration-acceptance`. The AM6 remote branch remains present at the exact
candidate head. This lane did not recreate, mutate, or retarget an upstream branch and did not open
a PR against `main`.

The minimal publication convergence is for the control tower to restore the requested base ref at
exact `f761a682164d10e2ff81ba38cd2d0c987b4f8efd`, or explicitly authorize a new target after reviewing
the merged topology. The unchanged AM6 branch can then be used to open the stacked draft. Retargeting
is not inferred from PR #122's merge.

After AM4 acceptance, the minimal convergence step is a new additive commit that supplies the exact
accepted AM4 coordinate and observation evidence for the three gated cases, then reruns this frozen
protocol and publishes a new point-in-time result without rewriting this record.
