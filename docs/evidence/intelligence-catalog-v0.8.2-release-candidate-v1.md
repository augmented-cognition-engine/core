# ACE 0.8.2 Intelligence Catalog release candidate

Status: **candidate — artifact, public-domain, and publication gates pending**

## Promise

ACE 0.8.2 makes first use outcome-led. Atrium asks what intelligence a person wants, discovers
every admitted onboarding profile through the governed Intelligence resource plane, and carries the
selection into the existing Connect → Map → Watch → Brief → Activate Builder flow. The catalog is
presentation over durable resources, not a new registry, state store, or authority path.

## Candidate coordinates

- source base: Core main merge `7dd98c09b2285cc5577226a8f7384ba4a5b9021a`;
- release branch: `codex/v0.8.2-intelligence-catalog-release`;
- candidate distribution: `ace-core==0.8.2`;
- paired domain candidates: World Intelligence 0.12.0 and Market Intelligence 0.7.0;
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

## Required acceptance before publication

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

Publication, tags, hashes, public-index reproduction, and final limitations require a separate
immutable closeout after all three independently versioned artifacts exist.
