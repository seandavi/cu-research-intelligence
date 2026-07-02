"""Agent evaluation harness (docs/eval/05).

Iteration 1: content evals for the NL->SQL chat — the most objective, defensible
layer. Deterministic checks (read-only safety, schema-validity, transparency,
appropriate refusal on negative controls) run with no LLM and no new deps; an
LLM-judge faithfulness/relevancy dimension is scaffolded for later. Iterations 2-3
(page heuristics, persona task walkthroughs via Playwright) build on this.
"""
