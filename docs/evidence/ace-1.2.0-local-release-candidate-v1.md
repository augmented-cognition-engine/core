# ACE 1.2.0 local release candidate v1

Status: **passed for a local release candidate; not published**

This record freezes the public-source-safe disposition of the ACE 1.2.0 Personal Intelligence
release candidate. It is not a Git tag, GitHub Release, PyPI publication, clean public-index
installation, or public acceptance claim; it does not close issue #195, and it does not stand in
for the J1–J10 public acceptance record, which only a clean user who is not an ACE maintainer can
produce from published artifacts. Artifact hashes and machine verification output belong to the
detached local release receipt so this source record does not authenticate itself.

## Candidate scope

ACE 1.2 Personal Intelligence delivers, over the unchanged 1.1 substrate: labeled local read-only
source acquisition for Markdown/Obsidian folders, PDF, CSV, and JSON with span-resolving citation
locators; typed document mapping; the declarative Personal Intelligence domain pack and its
conformance evidence; install and inventory experience with honest readiness states; content-digest
change detection with append-only Brief revisions and semantic diffs; server-side grounded Ask with
claim-bound corrections; ownership depth across export and truthful deletion of bundle-derived
artifacts; and the Solution Bundle machinery — exact manifests, deterministic resolution receipts,
read-only previews, and atomic single-commit activation — with the Personal and Code Intelligence
bundles proven to co-install and co-activate on one workspace without conflict, leakage, or either
requiring the other. Nothing personal enters Core ontology, the public MCP surface remains exactly
eleven tools, and no surface grants approve, merge, release, deploy, or promotion authority.

The release carries eight independently packaged artifacts beside the `ace-core` distribution: the
re-released reference workspace-action adapter (0.5.0, envelope widened to `ace-core>=0.8.0,<2`
with unchanged implementation identity 0.1.0), the five read-only local-source adapter
distributions, the Personal Intelligence pack distribution, and the pure-data
`ace-personal-intelligence-bundle` distribution whose manifest is generated deterministically from
the repository's real artifacts and discovered checkout-free from installed distributions.

The `ACE Builds ACE` reference program (decision 13) completed inside this milestone with three
preregistered subjects and its evidence record closed on main; its comparative result — push-based
ambient delivery adopts where election-based delivery does not, with value not yet demonstrated —
is reported in that record and does not gate this release.

## Local reconciliation gate (what was actually verified here)

- Focused release guard tests pass: the 1.2.0 release-candidate surfaces, package identity,
  release-workflow content, adapter envelopes (PEP 503-normalized, bound to the release being
  cut), the bundle artifact's exactness and byte-identical regeneration, and the installed-bundle
  discovery suite including the staged real-wheel layout.
- Whole-repo lint and format checks pass. The full non-e2e suite passes except a documented,
  pre-existing environmental set (host git/GitPython drift, stale local venv metadata, shared
  development database data) verified unchanged against a pristine main baseline.
- `ace-core` 1.2.0 sdist and wheel build reproducibly under `SOURCE_DATE_EPOCH` and pass twine
  metadata checks; an isolated installation of the wheel reports the exact 1.2.0 package, import,
  and engine version identities.
- The bundle distribution's wheel was built and its manifest discovered end-to-end through
  `importlib.metadata` at the exact declared path with its exact derived identity.

## What publication requires next

1. Merge this release-candidate change to `main`, create the exact `v1.2.0` tag on the merged
   commit, and publish the GitHub Release; the trusted workflow then publishes `ace-core` to PyPI
   and attaches the eight independent artifacts, gating every attached artifact's `ace-core`
   envelope against the released core.
2. A clean user who is not an ACE maintainer executes the frozen J1–J10 journey from public
   artifacts only, producing the public acceptance record with digests, environment, deviations,
   and limitations.
3. The four-record reconciliation (`ROADMAP.md`, issue #195, the ACE Public Roadmap Project, and
   the release evidence) closes ACE 1.2; only then does 1.3 become **Now**.

## Compatibility, migration, and rollback

- Runtime support remains Python 3.12 and the documented single-node topology with SurrealDB 3.2;
  the packaged schema head is unchanged from the 1.1 series. Operators take and verify a backup
  before upgrade; rollback is restoration of the verified pre-upgrade backup.
- Deactivating the Personal Intelligence bundle and uninstalling its adapters returns the
  installation to the supported 1.1 contract with no orphaned registrations or stranded authority.
- Known limitations carry into the release notes truthfully: no runnable restore from export;
  deletion non-reappearance proven in the primary immutable-record store; deletion never presented
  as universal erasure across backups, exports, or third-party copies; single-node topology; the
  bundle's adapter digests pin installable source bytes (wheel-hash pinning may join later).
