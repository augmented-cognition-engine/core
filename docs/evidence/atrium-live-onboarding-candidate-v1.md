# Atrium live onboarding candidate v1

## Outcome

Atrium consumes the Intelligence Builder's durable onboarding state through the existing governed
resource plane. Core remains domain-neutral; a Domain Pack may provide one declarative starting
profile, while a product host runs the public Connection, Ontology, Intelligence, and Briefing
services under explicit approvals.

## Candidate boundary

- `builder_profile` projects one inert profile whose guardrails explicitly grant neither source nor
  monitor authority.
- `builder_session` projects every append-only revision with exact `supersedes` ancestry.
- malformed, forked, or incomplete session ancestry degrades rather than fabricating progress.
- blocked and retrying revisions expose a safe diagnostic and explicit degraded reason.
- Atrium reads the canonical JSON payload, chooses the latest exact revision, and never marks a
  lane complete from client time or animation.
- the first-Brief completion action is available only at `first_briefing_ready` or later.

The paired World candidate runs eight exact session revisions over two admitted recorded official
AI-policy lineages: goal selected, sources connecting, sources ready, concept model proposed,
concept model approved, intelligence model proposed, intelligence model approved, and first
briefing ready. It makes no network-freshness, autonomous publication, or independent-outcome
corroboration claim.

## Verification

- focused Core projection tests cover profile replay, exact session ancestry, restart
  reconstruction, and blocked degradation;
- Atrium model tests cover canonical profile/session parsing and latest-revision selection;
- the Atrium production build completes;
- focused World tests reproduce the four-agent journey and exact 23-resource Atrium page.

The paired implementation landed through Core PR #145 and World PR #24 after the supported Core,
World, Canvas, naked-kernel, Docker, installed-wheel, and browser gates passed. Post-landing demo
hardening adds a Vite-only immutable-page replay seam and removes internal persistence vocabulary
from the leadership-facing journey. Live network freshness, general accessibility review, and
broader AI-area coverage remain separate follow-on gates.
