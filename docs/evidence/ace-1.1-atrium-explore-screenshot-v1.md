# ACE 1.1 Code Intelligence — Atrium Explore screenshot v1

Date: 2026-08-17

Status: local release-evidence candidate; not committed, published, deployed, or release approval

## Artifact

- Canonical path: `docs/assets/atrium-intelligence-os-v1.jpg`
- Route: `/atrium/explore`
- Capture viewport: `1440×960`
- Final full-page dimensions: `1440×1748`
- State: supported answer to `What changed in token economics?`, with its evidence and
  why-it-matters explanation visible
- Official product name: **ACE 1.1 Code Intelligence**
- Prior accepted SHA-256: `c269af7fe98f418a888d2f665fa747def498e0522cf6ce43c3d1f42fbf599205`
- Current SHA-256: `c4a42bbb4e7afe049da123b639b1a69416bdbd4e806efedb91290503d6c62486`
- Prior dimensions: `1265×712`

The README remains the canonical public reference. Its image URL is unchanged. The alt text and
caption identify the informative Ask ACE experience rather than the rejected Code Lens view.

## Capture procedure

The source was copied from immutable convergence candidate
`/private/tmp/ace11-convergence-candidate-r2` into an isolated packet. The accepted Canvas lockfile
was installed, then the established deterministic browser seam in
`core/ui/canvas/tests/e2e/atrium-intelligence-os.spec.ts` opened `/atrium/explore`, entered the exact
question, submitted it, and asserted the supported answer, `Why it matters`, `Evidence used`, and
focused result summary before capture.

```bash
cd core/ui/canvas
npm ci
ACE_CAPTURE_ATRIUM=1 npx playwright test \
  tests/e2e/atrium-intelligence-os.spec.ts \
  --grep 'Atrium is a briefing-first Intelligence OS over governed resources' \
  --project=chromium
sips -s format jpeg -s formatOptions 92 \
  test-results/*/atrium-explore-answer.png \
  --out ../../../docs/assets/atrium-intelligence-os-v1.jpg
```

No accepted candidate, user checkout, remote service, published artifact, or product data was
mutated.

## Gates and visual review

- Focused deterministic Playwright journey passed: `1 passed`.
- The captured page visibly includes the question, supported answer, four cited records,
  `Why it matters`, `Evidence used`, the selected result's evidence basis, focused relationships,
  and explicit contract boundary.
- Original-resolution inspection confirmed a balanced full-page composition with no clipping,
  overlap, error state, loading state, credential, source body, or private data.
- SHA-256 and pixel dimensions were independently read after JPEG encoding.

This record proves only the local screenshot bytes and visible deterministic Canvas state. It does
not claim deployment, publication, live-provider output, external-agent execution, or release
approval.
