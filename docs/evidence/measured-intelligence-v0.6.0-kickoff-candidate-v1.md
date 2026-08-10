# ACE 0.6.0 Measured Intelligence kickoff candidate evidence (v1)

**Status:** candidate, local. This record does not complete issue
[#38](https://github.com/augmented-cognition-engine/core/issues/38), pass SI4, publish a World
Intelligence journey, or promote the 0.6.0 milestone.

**Recorded:** 2026-08-10

**Base:** live `main` at `be5e76c79715bb34bcbdcae9a0471a5c317fafe7`

**Candidate branch:** `codex/measured-intelligence-kickoff`

## Contract demonstrated

The candidate implements the domain-neutral contract frozen in the
[Measured Intelligence kickoff work packet](../design/measured-intelligence-v0.6.0-kickoff-work-packet-v1.md):

- exact immutable identities link an intelligence artifact or cognition revision, product-owned
  criterion, matched conditions, material-use attribution, Decision, reviewed Action, terminal
  result, observed Outcome, evaluation, and proposal;
- the pure Intelligence evaluator classifies complete matched-pair evidence as useful, harmful,
  or unproven without accepting a caller-supplied quality label;
- the receipt records the effect interval, evidence/exclusions, outcome coverage, latency, cost,
  failures, degraded states, uncertainty, limitations, and cutoff;
- Core-backed application composition authorizes against the exact criterion head and atomically
  appends the evaluation plus optional proposal;
- every proposal is non-effective, non-selectable, and requires separate human review; and
- exact replay returns history without recomputation, while changed-material replay conflicts.

## Negative controls demonstrated

Deterministic tests establish that:

- missing exact material-use attribution is excluded and remains unproven;
- treatment/control condition mismatch cannot be compared;
- an unavailable Outcome remains unproven rather than being reconstructed from Decision or Action
  success;
- an Outcome unavailable at the cutoff cannot leak into the evaluation or have its payload loaded;
- duplicate identities and relabelled reuse of exact evidence coordinates fail validation and
  cannot inflate counts;
- exact replay is stable, including through a fresh service whose authorizer would deny new work;
- divergent replay under the same evaluation key conflicts;
- denied or post-authentication-expiry authorization appends no evaluation or proposal;
- an interrupted evaluation-plus-proposal transaction leaves no partial history; and
- constructing a proposal with a live effect fails contract validation.

## Persistence and restart evidence

The real-store test creates actual governed criterion and operation heads, appends complete matched
Decision/Action/Outcome chains, evaluates them through the public application service, closes the
store, and reopens the exact result through a fresh SurrealDB-backed service. A separate Python
process then parses the original request and reloads the identical transaction, evaluation, and
proposal with an authorizer that raises if invoked. The record counts remain one evaluation and one
proposal, proving restart replay rather than reclassification or duplicate append.

## Verification

Focused verification at candidate creation:

```text
uv run ruff check ace tests/intelligence/test_measured_impact.py \
  tests/intelligence/measured_impact_restart_process.py \
  tests/intelligence/test_contract_boundaries.py
PASS

uv run pytest tests/intelligence/test_measured_impact.py \
  tests/intelligence/test_contract_boundaries.py -q --tb=short
30 passed in 2.53s

uv run pytest tests/intelligence/test_measured_impact.py \
  tests/intelligence/test_contract_boundaries.py \
  tests/intelligence/test_runtime_use_and_preconditions.py \
  tests/intelligence/test_prepared_intelligence_ledger.py \
  tests/test_governed_cognition_effectiveness.py \
  tests/test_governed_action_execution.py \
  tests/test_governed_action_restart.py -q --tb=short
99 passed in 4.27s
```

Repository verification:

```text
uv run ruff check .
PASS

uv run ruff format --check .
2040 files already formatted

ACE_DISABLE_EXTENSIONS=1 uv run pytest \
  -m "not e2e and not requires_extensions" \
  --ignore=tests/test_grounded_state_runtime_baseline.py -q --tb=short
7439 passed, 50 skipped, 260 deselected in 196.82s

# Same candidate tree copied to a temporary ordinary-checkout layout.
pytest tests/test_grounded_state_runtime_baseline.py -q --tb=short
7 passed in 0.51s

uv run pytest tests/test_kernel_boundary.py -q --tb=short
4 passed in 1.10s

uv build --out-dir <temporary-directory>/dist
Successfully built wheel and source distribution; both contain
ace/application/measured_impact.py, ace/intelligence/impact.py, and
ace/intelligence/contracts/impact.py

wheel-only import of MeasuredImpactService, ImpactEvaluationV1Alpha1,
and evaluate_measured_impact
PASS

git diff --check
PASS
```

The historical TP0 baseline hashes its own source and reads `.git/HEAD` directly. Git represents
`.git` as a pointer file in the isolated worktree required for this packet, so three runtime replay
tests cannot reach their assertions there. The unchanged candidate tree was copied to a temporary
ordinary-checkout layout with a directory-form `.git/HEAD`; all seven baseline tests then passed.
The frozen baseline source retained its recorded
`b42ec0dd7a25810ec2c923e3adf6811dbb84db22b9313f3abc86d6c2c6c9b88d` hash. Together the split
executes all 7,446 non-E2E/non-extension test cases without altering historical evidence. This
candidate record remains an implementation receipt rather than a release receipt.

### World integration addendum

The first source-checkout run from World Intelligence exposed one composition mismatch: the real
Core reasoning authorizer correctly strengthens an authorization with exact capability and grant
heads, while the measured-impact service originally required its projection to contain only the
criterion and operation heads. The service now requires both requested heads to remain present and
byte/model exact while permitting additional exact heads. A changed requested head still fails
closed before append; an expanded authorization appends with the complete strengthened closure.

```text
uv run pytest tests/intelligence/test_measured_impact.py -q --tb=short
18 passed in 1.95s

uv run ruff check ace/application/measured_impact.py \
  tests/intelligence/test_measured_impact.py
PASS

World source-checkout candidate against this Core tree
2 passed in 0.55s
```

The repository-wide non-E2E run in this isolated worktree reached `7459 passed, 48 skipped` and
only the same three documented `.git/HEAD` pointer-layout failures. The original candidate's
ordinary-checkout replay result and green GitHub checks remain the applicable evidence for those
environment-sensitive historical tests; the authority change touches neither baseline path nor
source hash.

## Boundary and remaining work

The candidate changes no package version, storage schema, CLI/MCP surface, existing public record
shape, or governed state. It imports no `core.engine` implementation into `ace`. World and Market
nouns, sources, conditions, trust, thresholds, and outcome policy remain outside Core and
Intelligence.

The first public proof remains the World Intelligence real-data path:

```text
Observation -> Shift -> Signal -> Brief -> Decision -> reviewed Action
            -> observed Outcome -> governed feedback
```

That packet must freeze the real product criterion and controls, run this contract from public
data, reproduce after restart, and explicitly review the proposal through separate Core authority.
Market Intelligence must remain able to reproduce or falsify the unchanged neutral contract.

Issue [#49](https://github.com/augmented-cognition-engine/core/issues/49) findings F1, F3, and F5
still require an explicit 0.6.0 release-owner disposition because their accepted deadline is "next
minor." This packet does not implement or re-date them.
