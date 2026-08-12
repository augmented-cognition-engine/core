# ACE 0.8.0 runtime-boundary realignment work packet

Status: **active 0.8B packet; B1–B3 runtime isolation and ownership guards implemented**
Public milestone: [issue #40](https://github.com/augmented-cognition-engine/core/issues/40)
Accepted base: `main@bb7f4ba` (0.8A plus explicitly reviewed AM4 lifecycle semantics)

## Outcome

The default ACE runtime must compose the domain-neutral Intelligence OS, not the historical
ACE-product intelligence implementation. Compatibility remains deliberate and reversible:

- `ace.core` owns governed mechanics and has no inward Intelligence dependency;
- `ace.intelligence` owns pure evidence-to-orientation meaning and imports no host;
- `ace.application` composes public Core and Intelligence ports without owning authority or storage;
- Domain Packs remain inert declarative meaning;
- executable source acquisition and external effects remain adapters; and
- the legacy `core.engine` host may bridge into public ACE only through declared compatibility seams.

This packet does not delete historical code or rewrite immutable evidence. It stops the default
runtime from silently activating a domain-specific branch and makes any temporary opt-in visible.

## B1 — isolate embedded product intelligence

The pre-Domain-Pack sentinel host contains four ACE-product engines:

- community scanning against tracked competitors;
- competitor web/changelog observation;
- competitor GitHub release watching; and
- whitespace scoring over competitor coverage and community pain signals.

Those implementations remain import-compatible while deployments migrate, but they are no longer
registered by default. `ENABLE_LEGACY_PRODUCT_INTELLIGENCE=true` is the one explicit compatibility
switch. Enabling it emits an operator warning and grants no source, model, or action authority.

The domain-neutral graph community summarizer remains enabled. World and Market Intelligence must
obtain source-specific behavior from their Domain Packs and authorized connectors rather than this
legacy switch.

## Accepted AM4 input

Agent Memory lifecycle and erasure entered 0.8 through a separate compatibility review before this
packet began. Its additive merge onto the 0.8A base passed 157 combined roadmap, package-boundary,
kernel-boundary, exact-eleven, AM1–AM4, and restart-oriented tests. Retention, scoped export/import,
soft forget, and dependency-complete supported-store erasure are therefore available to the later
0.8C resource plane and 0.8D Atrium experience; they are not reimplemented here.

## B2 — enforce ownership and classify the compatibility host

The canonical dependency direction is now machine checked across every Python module in the three
public layers:

- `ace.core` cannot import Intelligence, application, the legacy host, transports, or extensions;
- `ace.intelligence` cannot import application, the legacy host, transports, or extensions;
- `ace.application` may compose public Core and Intelligence ports but cannot import the legacy
  host or a transport framework; and
- none of the three layers may acquire sources or execute external effects through a concrete
  network, process, or socket client. Those operations enter through declared ports and adapters.

The broader `core.engine` tree remains a compatibility host during 0.8. Every top-level package is
therefore assigned exactly one machine-checked disposition in
`core-engine-compatibility-disposition-v0.8.0.json`. Adding a directory without declaring its
owner and treatment fails the boundary suite. Product-era arms, product surfaces, and Canvas are
explicitly frozen compatibility applications; their presence does not make their vocabulary or
dependency direction canonical.

## B3 — freeze deprecated callers and reproduce restart behavior

The same disposition manifest freezes the current direct callers of the MAKE/SHIP-era arms, the
Living Product Graph compatibility projection, and the broad engine MCP host. A new caller fails
the ownership suite until an explicit compatibility review changes that allowlist; code cannot
quietly deepen the dependency while 0.8 introduces canonical resources.

The cumulative 0.7 builder, exact activation plan, Watch behavior, AM3 authorized recall, and AM4
lifecycle/erasure gates reproduce on this boundary. The real AM3 later-use and AM4 non-reappearance
checks also pass through fresh processes and disposable durable storage. This closes runtime
ownership without claiming that historical host directories have been deleted.

## Acceptance

B1 passes only when:

1. the compatibility flag is false by default and accepts an explicit environment opt-in;
2. the disabled path imports and registers none of the four frozen legacy engines;
3. the opt-in path registers exactly the declared compatibility set;
4. the API composition root contains no unconditional import of those modules;
5. each legacy module remains callable for bounded migration compatibility;
6. Core, Intelligence, application, thin-MCP, naked-kernel, and roadmap boundaries remain green;
7. no Domain Pack, connector, or UI is copied into Core; and
8. the exact eleven-tool public MCP surface is unchanged.

## Remaining 0.8B work

B1–B3 close the bounded 0.8B runtime realignment when their independent reviews and CI pass. They:

- keep generic planning, authority, execution admission, assurance, outcomes, and erasure behind
  public Core ports;
- keep Observation-to-Feedback interpretation behind Intelligence and application services;
- require artifact creation and external effects to enter through explicit strategy/adapter ports;
- prevent new direct callers of deprecated MAKE/SHIP, Living Product Graph category, broad MCP,
  and legacy product-intelligence paths; and
- reproduce Connect → Map → Watch → Brief → Activate plus AM3/AM4 behavior after restart.

0.8C may not depend on an undeclared legacy host route.

## Rollback

Reverting B1 restores the old implicit engine registration. No stored record is rewritten by this
change. A deployment that temporarily requires the historical behavior can set the compatibility
flag while its data sources, schedules, and consumers migrate to the Domain Pack lifecycle. The
flag is not a promise that the old engines survive 1.0.
