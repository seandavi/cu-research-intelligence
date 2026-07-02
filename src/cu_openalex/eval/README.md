# Eval harness (`cu_openalex.eval`)

Runnable implementation of the agent evaluation framework (`docs/eval/05`). It
evaluates **both halves** of the platform:

- **Backend & capabilities** (runnable now, deterministic, no LLM): the NL→SQL
  chat (content eval) + API contract checks + **capability coverage** scored
  against the stage-2 requirements.
- **UI/UX** (iterations 2-3): page heuristics and persona task-walkthroughs driven
  by Playwright, LLM-as-judge with a human calibration set.

## Run

```bash
# against the live deployment (includes the chat eval; ~1-3 min)
uv run python -m cu_openalex.eval --base-url https://insights.uccc.cancerdatasci.org --out .

# backend/capabilities only (fast)
uv run python -m cu_openalex.eval --base-url https://insights.uccc.cancerdatasci.org --skip-chat
```

Writes `scorecard.json` + `scorecard.md`. Re-run per release and diff the scorecards
for regression.

## Layout
- `gold.py` — NL→SQL gold set (with negative controls for calibrated-trust).
- `checks.py` — deterministic checks (read-only safety, schema-validity).
- `content_eval.py` — chat content eval (dimensions: read_only / schema_valid /
  transparent / refusal_ok). LLM-judge faithfulness plugs in later.
- `capabilities.py` — API contract checks + capability-coverage probes vs. `02`.
- `scorecard.py` — aggregation + markdown.

## Caveats (see `docs/eval/05`)
Agent/automated scores are **directional + regression signals**, not the sole gate.
The UI/UX layers require a human calibration set and bias controls (randomized
order, ensemble judges, anchored rubrics). Never use for absolute or causal claims.
