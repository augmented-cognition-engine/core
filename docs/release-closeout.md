# Release closeout and roadmap reconciliation

Every published ACE Core minor or patch release must close as one product event, not four drifting records.

Before the next milestone moves to **Now**, reconcile:

1. **ROADMAP.md** — current released artifact, outcome state, limitations, and the next release spine.
2. **Release milestone issue** — acceptance gate, evidence, dependencies, follow-ups, and final disposition.
3. **ACE Public Roadmap Project** — Now, Next, and Later placement, with the active view focused on open work.
4. **Release evidence or GitHub Release** — immutable version, artifacts, verification, migration or compatibility notes, and known limitations.

For each record, either update it or record **reviewed — no change required**. Do not leave a surface silently stale.

## Minor release gate

- The public promise and acceptance journey passed with reproducible evidence.
- Declared boundaries and degraded states remain accurate.
- The milestone issue, Project lane, and this roadmap agree.
- The supported version, installation path, upgrade path, and rollback or recovery guidance are explicit.
- The next milestone does not move to Now until all four records agree.

## Patch release gate

A patch may harden a published promise but must not silently widen authority or introduce a backward-incompatible public contract.

- Confirm version discovery and update guidance.
- Record compatibility, migration, backup, recovery, and rollback impact.
- Re-run the proportionate release and public-artifact verification.
- Update all affected records, or mark each unaffected record reviewed.

## Ownership

The release owner performs the reconciliation. Reviewers verify that public claims are no broader than the evidence. The active control tower treats a mismatch among these records as unfinished release work.
