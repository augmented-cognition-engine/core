# Atrium opportunity contract v1

## Definition

An **Opportunity** is a decision-relevant opening inferred from current evidence. It
exists when a Signal or combination of Signals produces a material Shift and that
Shift implies a favorable or avoidable window worth investigating.

It is deliberately not:

- a sales lead;
- downstream Work or a task;
- an Agent's unreviewed suggestion;
- a generic alert with no decision consequence.

The lifecycle is:

`Entity graph -> Signal -> Shift -> Opportunity candidate -> Case -> Decision -> Action -> Outcome -> Feedback`

ACE may detect and rank the candidate. A person still decides whether to investigate,
accept, dismiss, defer, or convert it into Strategy and downstream Work.

## Required presentation

Every decision-ready Opportunity should answer:

1. **What opened?** The favorable or avoidable window.
2. **Why now?** The material Shift relative to the baseline.
3. **Why it matters?** Expected upside, avoided harm, or learning value.
4. **What supports it?** Cited evidence, provenance, and conflicts.
5. **How certain are we?** Confidence and known uncertainty.
6. **How long is the window?** Time horizon, urgency, or expiry condition.
7. **What decision is needed?** A bounded question and recommended next step.
8. **Who owns the decision?** Persona or accountable principal when configured.

If those fields are incomplete, Atrium presents the record as an early Signal or
emerging Shift—not as a scored, decision-ready Opportunity.

## Domain examples

| Domain | Opportunity |
|---|---|
| World / AI | A model-price move opens a near-term migration or workload-expansion window. |
| World / AI | A new security requirement creates an avoidable readiness gap before enforcement. |
| Market Intelligence | A competitor claim change opens defensible positioning whitespace. |
| Market Intelligence | Repeated customer evidence reveals an underserved need worth testing in the next launch. |
| Market Intelligence | A competitor weakness and a launch window align around a specific buying group. |

The Core contract does not encode these nouns. Domain Packs declare the entities,
Shift types, personas, thresholds, and synthesis language that give the shared
Opportunity lifecycle its local meaning.
