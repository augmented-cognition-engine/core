# ACE 1.0 Personal Intelligence OS release candidate

Status: **candidate — trusted publication and clean public-artifact reproduction pending**

## Release promise

ACE 1.0 is the stable single-user Intelligence OS for one local owner and the documented
single-node deployment. Atrium guides a person from Intelligence selection through exact reviewed
source binding, permission/readiness checks, activation, visible ingestion health, and a cited
first Brief. A later recorded source revision produces a new cited Brief and semantic change diff
without rewriting the prior Brief.

ACE owns source-grounded state, knowledge formation, Intelligence swimlanes, provenance,
authority, engine-ready direction packages, outcome return, and governed learning proposals. It
does not recreate or silently operate downstream design, coding, campaign, ERP, logistics,
trading, or other execution engines.

## Candidate coordinates

- Core distribution: `ace-core==1.0.0`;
- schema head: v177;
- public MCP surface: exactly eleven tools;
- reference action adapter: distribution `0.4.1`, capability implementation `0.1.0`, and
  `ace-core>=0.8.0,<1.1`;
- Market Intelligence: public `ace-domain-market-intelligence==0.8.0` plus separately attached
  trusted Builder `0.1.0`;
- World Intelligence: candidate `ace-domain-world-intelligence==0.13.0` plus separately attached
  trusted Builder `0.2.0`;
- topology: one local owner, one ACE API/worker deployment, one SurrealDB instance, explicitly
  trusted separately installed adapters.

## Bounded acceptance already implemented

1. Local owner bootstrap grants build/read authority only; source reads, destination delivery, and
   external effects remain separately reviewed and authorized.
2. Onboarding discovers installed Intelligence profiles, preserves Custom as proposal-only, binds
   exact reviewed source material, and exposes credential, permission, activation, admission,
   last-success/error/retry, semantic-time, availability-time, and unverified-freshness state.
3. World and Market use the same public Core build-host and Intelligence formation ports to produce
   exact Observation, Entity, Shift/Signal, and cited Brief lineage.
4. A later source revision creates an append-only Brief revision plus decision-readable
   what-changed, why, and evidence details. Restart/reopen preserves the first and later revisions.
5. Market prepares a content-addressed direction package from an exact Brief/Decision, requires
   exact package and destination approval, records an acknowledged reference delivery, accepts a
   later Outcome, and projects a non-effective Feedback proposal through existing Core contracts.
6. Retrieval uses indexed SurrealDB lexical and HNSW vector plans with deterministic reciprocal-rank
   fusion, product/type/tag isolation, correction-aware authoritative projection, a no-answer gate,
   strict 768-dimension compatibility, and explicit degraded receipts. Frozen provider-free RAG
   evaluation: 5/5 cases, Recall@5 100%, MRR 1.0, and zero association, isolation, correction, or
   no-answer violations.
7. Provider setup supports direct OpenAI/Anthropic API keys, signed-in Codex/Claude CLI subscription
   routes, OpenAI-compatible endpoints, and local Ollama. A consumer subscription is not treated as
   a reusable API key.

## Final release gate

The exact merged candidate must pass required Core CI, reproducible wheel/sdist build and strict
validation, naked-kernel and eleven-tool checks, security and container gates, and trusted
publication. A fresh environment using public indexes and release assets only must then reproduce:

```text
install → launch service and Atrium → owner login → select Intelligence → review exact sources
→ approve/bind → visible healthy or degraded state → cited first Brief → restart/reopen
→ later recorded update → cited Brief diff → grounded Ask/correction
→ exact approved package handoff → acknowledgement → Outcome → proposal-only Feedback
→ backup/restore → export/two-step delete
```

The acceptance packet records exact versions, hashes, timings, citations, authority and lineage
receipts, degraded-state cases, and limitations. A gate is not passed by a source checkout, cached
local wheel, prepared UI-only record, hidden provider call, or implicit authority.

## Explicit non-claims and post-1.0 work

ACE 1.0 does not claim a universal connector or destination catalog, managed hosting, collaboration
or tenant isolation, hostile-extension sandboxing, autonomous source authorization, autonomous
delivery or policy application, arbitrary web access, customer-corpus relevance, multilingual
quality, high-concurrency operation, distributed availability, calibrated real-world causal
accuracy, or general beneficial impact. Personal knowledge sources such as Obsidian and Notion are
a post-1.0 Personal Intelligence Solution Bundle over the same substrate, not a new Core ontology.
