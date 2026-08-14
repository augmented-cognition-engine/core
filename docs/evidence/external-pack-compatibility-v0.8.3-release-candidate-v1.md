# ACE 0.8.3 external-pack compatibility release candidate

Status: **candidate — artifact, publication, and public-index gates pending**

## Promise

ACE 0.8.3 lets independently packaged Intelligence products verify the exact installed Domain
Pack through a public conformance seam and retain source publication time separately from
observation and ingestion time. The patch exists to remove version skew between Core and external
pack conformance without exposing the private host runtime or changing the 0.8 product promise.

## Candidate coordinates

- source base: Core main merge `1fe2d3c0759d42aebd057018ebf00aa6d2178f3b`;
- release branch: `codex/v083-compat-release`;
- candidate distribution: `ace-core==0.8.3`;
- required compatibility merges: `94b55c2` (#166) and `08f8419` (#170);
- schema head: v177;
- public MCP surface: exactly eleven tools;
- reference action adapter: unchanged distribution 0.4.0 with `ace-core>=0.8.0,<0.9`.

## Included changes

1. `ace.intelligence.conformance` resolves and verifies exact installed pack material for external
   consumer tests without a private `core.engine` import.
2. Declarative source mapping preserves nullable publication time independently from observed and
   ingested time.
3. The durable Intelligence build-host composer is loaded and exported by the public Application
   package, including in an isolated installed-surface conformance run.
4. Subsequent merged Builder hardening through active-session first-Brief binding remains on the
   same schema, MCP, authority, and separately installed adapter boundaries.

## Required acceptance before publication

- Core lint, fast tests, naked-kernel, Canvas, security, and Docker gates pass at the exact
  candidate head.
- Package identity, roadmap positioning, evidence-index, conformance, source-mapping, and
  build-backend gates pass.
- The wheel and sdist build reproducibly, pass strict Twine validation, install outside the
  checkout, report 0.8.3, import the public conformance seam, preserve semantic source time, and
  expose exactly eleven MCP tools.
- The Market consumer can then pin the public 0.8.3 artifact, regenerate only its current
  candidate artifacts, and preserve every frozen historical release packet.

## Boundaries

This patch does not claim a universal connector catalog, collaborative multi-tenancy, hostile-code
isolation, distributed operation, autonomous source authorization, arbitrary web access,
autonomous publication, general real-world causal accuracy, or general beneficial impact. It does
not advance roadmap maturity or complete the 0.9 or 1.0 release gates.
