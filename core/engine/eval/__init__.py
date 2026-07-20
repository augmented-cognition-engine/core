"""ACE evaluation harness — baseline-relative regression gate.

The grader (grader.py) is pure logic: golden-set results + a committed baseline -> a verdict that
absorbs single-case LLM variance (tolerance) while failing on genuine regressions and on any case
that flipped pass->fail vs the baseline. Runners (e.g. scripts/eval_classifier.py) produce the
results; the grader decides the gate. Generic over CaseResult so one grader covers many golden sets.
"""
