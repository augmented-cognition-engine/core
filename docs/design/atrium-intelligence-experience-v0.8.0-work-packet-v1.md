# ACE 0.8.0 Atrium Intelligence experience work packet

Status: **active 0.8D packet; briefing-first shell, first-class navigation, governed resource client,
provenance inspection, degraded states, and grounded Ask ACE implemented for review**

Accepted base: `main@6ce115b` (0.8A architecture, 0.8B runtime boundaries, and the 0.8C public
resource-plane implementation, including governed Action projection)

## Outcome

Atrium becomes the optional human experience for ACE as an Intelligence Operating System. A user
arrives at current intelligence, sees what needs attention, can inspect evidence and revision
receipts, and can move into investigation or downstream action without learning package boundaries.
The interface is a disposable consumer of the same authorized resource plane available to machine
clients. It owns no intelligence, durable state, or authority.

## Reference lock

Research was intentionally locked before implementation:

- [Palantir Ontology](https://www.palantir.com/platforms/ontology/) provides the object/action model:
  data, logic, decisions, and operational Actions become connected first-class objects. ACE adopts
  the legibility of this model, not Palantir's visual language or proprietary architecture.
- [Palantir ontology-aware applications](https://www.palantir.com/docs/foundry/ontology/applications/index.html)
  demonstrate that an object view can be the stable center of related information and workflows.
  ACE applies this to governed Intelligence resources and their exact provenance.
- [Feedly AI Feeds](https://docs.feedly.com/article/699-guide-to-ai-feeds-market-intel) provide the
  monitoring/refinement pattern: define what matters, constrain sources, watch continuously, and
  refine based on relevance. ACE maps this to Connect, Map, Watch, Brief, and governed Feedback.
- [Ground News methodology](https://ground.news/rating-system) and its
  [Bias Bar](https://ground.news/bias-bar) show how disagreement, source context, and coverage gaps
  can be visible without claiming an arbiter of truth. ACE preserves available evidence and names
  degraded or unsupported state instead of inventing certainty.
- The existing ACE Canvas design system remains the visual source of truth: Spline Sans, paper and
  cloud surfaces, restrained ACE cognitive blue, Midnight text, semantic status colors, canonical shadcn
  primitives, and the existing accessibility enforcement suite.

## Product decisions

1. **Briefing first.** `/atrium` opens on the latest Brief, attention queue, and Ask ACE—not a blank
   reasoning room or infrastructure console.
2. **Five first-class surfaces.** Intelligence, Opportunities, Agents, Connections, and Strategy
   are navigation concepts. They are projections over canonical resource kinds, never new kernel
   nouns. Work is downstream and appears separately.
3. **Ask ACE is pure intelligence.** The first bounded experience ranks only authorized loaded
   resources and cites the exact matching revisions. When evidence is absent it says so. It does
   not open a generic brainstorm or manufacture an answer.
4. **Trace before payload.** Human-readable summaries lead. A detail sheet exposes revision,
   availability, evidence lineage, and missing context without dumping internal storage material.
5. **Honest partial truth.** Source Health, standalone Uncertainty, standalone Conflict, and
   Semantic Revision remain visible contract gaps. Atrium presents the available 18 governed
   families and an explicit partial-state notice.
6. **Onboarding is the empty state.** With no admitted resources, Atrium explains the agent-assisted
   Connect → Map → Watch path. It never substitutes prepared intelligence for an empty live system.
7. **Investigation remains downstream.** The existing deliberation and board experiences remain
   reachable as investigation tools; neither becomes another intelligence source of truth.
8. **Jobs before agents.** First use asks what decision or landscape the user needs to stay ahead
   of. A Domain Pack proposes sources, concepts, watches, and cadence; agent work appears as one
   inspectable assembly story. The full reference is the
   [Atrium JTBD onboarding and AI command-center lock](atrium-jtbd-onboarding-reference-lock-v1.md).

## Implemented slice

- a typed, paginated client for `POST /v1/intelligence/resources/query` with token refresh and the
  declared `observe_read` grant;
- one request path covering all 22 canonical kinds and retaining exact returned receipts;
- briefing, attention, opportunities, agents/memory/monitors, connections/sources, and
  decision/action/outcome/feedback views over the same returned records;
- resource detail sheets with revision and provenance lineage;
- explicit loading, empty, error, denied, and partial/degraded presentation;
- responsive sidebar access and keyboard-operable controls;
- model tests, the full Canvas enforcement suite, production build, and a browser acceptance journey
  over the public HTTP contract.

## Remaining 0.8D acceptance

The current slice still needs an exact live backend journey after the combined Core candidate is
installed, automated accessibility inspection, and a verified denied/expired-entitlement browser
journey. Domain presentation hints may enrich labels later but cannot change the navigation or
resource contract. 0.8E supplies materially different World and Market data through this same UI.

## Rollback

Atrium changes are additive application code. Reverting the resource client, route, shell, tests,
and this packet restores the previous experimental deliberation home without rewriting governed
state, resource identities, or domain artifacts.
