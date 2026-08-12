# ACE 0.7C Intelligence Builder Map candidate evidence (v1)

**Status:** local stacked candidate above draft PR #102. This record advances only 0.7C Map. It is
not release evidence and does not claim Watch, Brief, Activate, the cumulative onboarding demo,
independent World/Market proof, or 0.7.0.

## Outcome

The public Python application surface consumes the exact approved two-source 0.7B profile handoff
and a user goal/intent, produces an editable cited concept model, persists an immutable edit as
revision 2 with semantic diff and lineage, resolves human/Core approval for that exact revision,
and reopens the same approved proposal and disposition through a fresh service instance.

The separate Ontology Agent has no connector, credential, source-read, authoritative-ontology,
scheduling, delivery, pack activation, grant creation, or self-approval capability. Core receives
generic opaque onboarding records and approval subjects; no concept-model nouns enter Core receipt
contracts.

## Exact provider-free reproduction

Two independent installed-wheel target directories reproduced:

| Material | Exact identity |
|---|---|
| initial concept proposal | `concept_model_proposal:94c9c3194d9d154e6135f2791de05c50` |
| edited concept proposal | `concept_model_proposal:9f0645e38bc535ced839bf011d724b20` |
| edited proposal persistence receipt | `append_only_receipt:e19f50f67a4478db096ff2e4641e70c0` |
| approved disposition | `concept_model_disposition:0e7e83e18785a4e302872d3a5d8bc272` |
| disposition persistence receipt | `append_only_receipt:e983ed518f87d881508f540ffcd3dcda` |
| reopened approved session revision | `intelligence_builder_session_revision:61203e6b00b320b7cde6bb8dc2e7a8df` |

The installed imports resolved from `site-a` and `site-b`, not the source checkout. The built wheel
SHA-256 was `dbecef4a2940f221a2e6bc8d570f2cf6e780a4b9a9711bc50fdf0cac690a0eaa`.

## Proposal contents

The neutral fixture produces one `record` entity type, cited `status` and `value` attributes, one
provisional self-relationship, organization terminology, explicit exclusions, an unknown about
identity/relationship semantics, confidence, and four exact citations spanning both approved
source samples. Each citation binds profile, sample, logical source, source evidence digest, and
field path.

The user edit adds `tracked_record` terminology. It retains revision 1 byte-for-byte, creates
revision 2, binds exact prior proposal ID/digest, and records
`terminology.added:tracked_record` as its semantic diff.
The service recomputes that diff from the exact old and new material and refuses caller-supplied
diff text that hides or misstates a revision change.

## Failure controls

Focused tests prove:

- missing or widened source-profile inputs are refused before proposal persistence;
- invented sources and invalid/unattributed citations fail exact evidence validation;
- duplicate or colliding type IDs fail structural validation;
- imperative/unknown fields are forbidden by strict public contracts and absent from JSON Schema;
- frozen proposals cannot be silently mutated;
- revision changes cannot be hidden behind a false or incomplete semantic diff;
- stale revisions cannot be approved after an edit;
- denied or agent-self approval cannot advance the session;
- low confidence durably blocks as `low_confidence_mapping`;
- contradictory approved inputs durably block as `conflicting_sources`; and
- both blocked paths reopen and resume at `sources_ready` without implying approval.

## Verification

- 0.7B + 0.7C focused suite: **19 passed**.
- 0.7A–0.7C, package identity, narrative, evidence index, naked-kernel, and exact eleven-tool MCP
  gate: **124 passed, 1 expected extension-disabled skip**.
- installed-wheel two-directory reproduction: passed with exact identities and wheel hash above.
- repository-wide Ruff, `git diff --check`, and `uv lock --check`: passed.
- proportionate full non-e2e gate with three documented linked-worktree-incompatible baseline
  cases deselected: **7,514 passed, 50 skipped, 264 deselected**; separate kernel-boundary rerun:
  **4 passed**.

## Limitations and next packet

The deterministic fixture maps declared source shape, not source records or a learned real-world
ontology. Its relationship is explicitly provisional. The strategy port admits optional host
model use, but no model implementation or model-quality claim is included. There is no frontend,
new source read, authoritative ontology activation, Domain Pack generation, monitor, Brief,
scheduling, delivery, or consumer-repository work.

The next bounded packet remains 0.7D Watch + Brief: separate Intelligence Agent and Briefing Agent
services consuming the exact approved concept-model handoff.

## Rollback

Stop composing the additive Ontology Agent and testing exports. Existing opaque Core records remain
immutable history. Rollback performs no connector action, deletes no proposal/disposition, changes
no grant, activates no pack, and leaves 0.7A/0.7B behavior untouched.
