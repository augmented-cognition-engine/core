# ACE 0.8.2 Intelligence Catalog release closeout

Status: **passed — published and reproduced from public artifacts**

## Promise

ACE 0.8.2 makes first use outcome-led. Atrium asks what intelligence a person wants, discovers
every admitted onboarding profile through the governed Intelligence resource plane, and carries the
selection into the existing Connect → Map → Watch → Brief → Activate Builder flow. The catalog is
presentation over durable resources, not a new registry, state store, or authority path.

## Release coordinates

- source base: Core main merge `7dd98c09b2285cc5577226a8f7384ba4a5b9021a`;
- release commit: `36bb938a2070cf4cc26b0e05bfe55773ed9c4d5c`;
- release: [`v0.8.2`](https://github.com/augmented-cognition-engine/core/releases/tag/v0.8.2);
- public distribution: [`ace-core==0.8.2`](https://pypi.org/project/ace-core/0.8.2/);
- paired public domains: World Intelligence 0.12.0 and Market Intelligence 0.7.0;
- schema head: v177;
- public MCP surface: exactly eleven tools;
- reference action adapter: unchanged distribution 0.4.0 with `ace-core>=0.8.0,<0.9`.

## Included changes

1. The generic resource plane can project multiple admitted onboarding profiles in product scope.
2. Atrium deduplicates profiles by durable identity and always adds the Core-owned Custom
   Intelligence path.
3. Profiles can declare display labels, starter questions, and grouped source choices without
   adding domain nouns to Core or imperative code to a pack.
4. World and Market provide their own declarative profiles from independent repositories.
5. Selecting a profile grants no installation, connection, monitoring, or activation authority;
   all effects remain on the existing reviewed Builder boundaries.

## Acceptance

- Core lint, fast tests, naked-kernel, Canvas, security, and Docker gates pass at the exact
  candidate head.
- Package identity, roadmap positioning, evidence-index, and build-backend gates pass.
- The wheel and sdist build reproducibly, pass strict Twine validation, install outside the
  checkout, report 0.8.2, preserve the 24-kind resource plane, and expose exactly eleven MCP tools.
- Atrium desktop and mobile acceptance proves World, Market, and Custom catalog choices without
  overflow, uncaught console errors, hidden authority, or domain naming in Core contracts.
- Independently built World 0.12.0 and Market 0.7.0 candidates install against the exact Core 0.8.2
  artifact and admit their profiles through the unchanged public resource plane.

## Boundaries

This patch does not claim collaborative multi-tenancy, hostile-code isolation, distributed
operation, autonomous source authorization, arbitrary web access, autonomous publication,
general real-world causal accuracy, or general beneficial impact. It does not advance the 0.9
Collaborative Intelligence or 1.0 stable-contract gates.

## Immutable public artifacts

- `ace_core-0.8.2-py3-none-any.whl` — SHA-256
  `de936efc9aafa0f2e365abeb0bfe9fcf592ba7506bca4d2411ce7c340ca7a4a9`;
- `ace_core-0.8.2.tar.gz` — SHA-256
  `b4714c97dd290a93b7b26c9f36236d9e089dcf4cc3b3b30b3e9f07178752617a`.

Trusted publication completed in
[workflow 31740809332](https://github.com/augmented-cognition-engine/core/actions/runs/31740809332).
A fresh Python 3.12 environment installed Core 0.8.2, World 0.12.0, and Market 0.7.0 from PyPI only;
both domain profiles resolved and neither separately packaged connector was installed.
