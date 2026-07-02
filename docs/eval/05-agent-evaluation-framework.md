# Evaluation — Stage 5: agent evaluation framework

A repeatable, multi-agent harness that scores the live platform against the
requirements (`02`), personas (`03`), and impact measures (`04`), grounded in the
state-of-the-art (and its caveats) from the landscape review (`01`, Part C/D).
Design principle: **triangulate and never let agents be the sole gate** — the
harness is a *regression + prioritization* tool paired with a human calibration set.

## Two halves, evaluated together

The platform is judged on **both** halves, and the harness covers both:

- **Backend & capabilities** — is the data/API correct, and are the *required
  capabilities actually present*? (content/chat correctness, API contracts, data
  quality/provenance, metric correctness, and **capability coverage vs. the
  stage-2 requirements**). Runnable now, deterministically, no LLM.
- **UI/UX** — can each persona do their job, and is it usable/trustworthy? (page
  heuristics, persona task-walkthroughs, trust/satisfaction). Playwright-driven,
  iterations 2-3.

## What we're evaluating, and with what

| Layer | Half | Method | Agent role | Ground truth |
| --- | --- | --- | --- | --- |
| **Content — NL→SQL chat** | backend | Gold-set eval (relevancy, faithfulness/groundedness, schema-validity, transparency-of-query, safe-refusal) | LLM judge vs. gold Q/SQL | curated gold answers |
| **API contract + capability coverage** | backend | Probe endpoints; assert invariants; score each stage-2 requirement present/partial/absent | deterministic | requirements (`02`) |
| **Heuristics — each page** | UI/UX | Rubric scoring (Nielsen-10 + Few + viz-honesty + responsible-metrics rules from `04`) with 0–4 severity + evidence | LLM/MLLM judge over DOM+screenshot | human calibration set |
| **Tasks — persona × job** | UI/UX | Goal-driven walkthroughs (success, steps, deviations) | persona "simulated user" driving the live SPA (Playwright) | human calibration set |
| **Trust/satisfaction** | UI/UX | SUS, 4-item viz-trust inventory, calibrated-trust probes | (human survey; agents seed probes) | humans |
| **Compliance** | both | Automated checks of `04`'s presentation rules (distribution? normalized? provenance label? caveat? no JIF/h-index?) | deterministic + judge | rules |

## Architecture (modeled on UXAgent/UXCascade + LLM-as-judge)

```
scenarios (persona × job, from 02/03)  ─┐
rubrics (heuristic + content + 04 rules) ┼─▶  runner ──▶ [simulated-user agent] ─drive─▶ live SPA (Playwright MCP)
gold set (chat Q/SQL)                    ─┘                    │ transcript, steps, screenshots, DOM
                                                               ▼
                                              [judge agent(s)] ─score vs rubric─▶ findings (+severity, +evidence)
                                                               │
                        human calibration set ──agreement──────┤
                                                               ▼
                                                  aggregation ──▶ scorecard (JSON + markdown), per release
```

Two **separate** agent roles (never the same model for both):
- **Simulated user** — executes a persona's job as a goal, driving the real SPA;
  emits success/steps/deviations + a short "interview" (SEQ, confusion points).
- **Judge** — scores content and heuristics against **anchored rubrics**, each
  finding requiring a 1-sentence evidence citation (DOM element / screenshot region).

## Bias & validity controls (non-negotiable — from `01` Part C)

- **Randomize option ordering**; use **≥2 judge model families** (ensemble/cross-model)
  to counter position/verbosity/self-preference bias.
- **Anchored rubrics** (present/violated + 0–4 severity + required evidence) to tame
  judge variance; score against anchors, not free-text preference.
- **Human calibration set** — a few dozen scenarios scored by real people; report
  **agent–human agreement each cycle**; trust agent scores only where agreement is high.
- Synthetic users **compress variance and can't support causal/absolute claims** —
  use for **relative comparison, regression, triage**, never final decisions or
  representativeness claims.
- **Log model id/version, prompt, seed** for every run (reproducibility; models go stale).

## Progressive build plan (per direction: 1 → 1+2 → 1+2+3, eval & refine each)

- **Iteration 1 — content evals (chat).** The most objective, defensible layer.
  Gold Q/SQL set → live `/api/chat` → judge faithfulness / schema-validity /
  transparency / safe-refusal. Seed known-unanswerable questions to test calibrated
  trust. **Eval the harness itself** against a hand-scored subset; refine rubric.
- **Iteration 1+2 — add heuristic evals.** Rubric-score each page (Nielsen/Few +
  `04` presentation rules) over DOM + screenshot; add the responsible-metrics
  compliance checks (distribution/normalization/provenance/caveat/no-JIF). Refine
  against a human heuristic pass (seed the calibration set with a 3-evaluator round).
- **Iteration 1+2+3 — add persona task walkthroughs.** Persona simulated-users drive
  the live SPA via Playwright through the `02/03` scenarios; record success/steps/
  deviations + SEQ. Add **replay-on-change** regression (UXCascade pattern) so each
  release re-runs the suite and diffs the scorecard. Refine against a human usability
  round; report agent–human agreement.

Each iteration ends with: run → compare to the prior scorecard → a short "what
regressed / what's newly flagged" diff → refine rubric/scenarios.

## Scenario spec (per persona × job)

```
{ persona, job_id, start_url, goal (natural language),
  ideal_path[], success_criterion (machine-checkable where possible),
  heuristic_watchlist[], mode (exploratory|reportable) }
```

Example (Maria / J1.1): *"From the program-collaboration page, in reportable mode,
find the % inter-programmatic publications for program CPC in FY24 and confirm it's
labelled reportable + shows provenance."* Success = correct value surfaced + a
provenance/reportable label present.

## Content-eval gold set (iteration 1, starter)

A small, curated set of NL questions with an expected-answer sketch + a
schema-validity check (does the generated SQL touch the right tables/filters?),
including **negative controls** (questions the data cannot answer → the system
should refuse/flag, not hallucinate). Grows over time; the human-verified subset
is the calibration set.

## Outputs

- **`scorecard.json`** — per-layer scores, findings (with severity + evidence),
  agent–human agreement, model/version/prompt metadata, timestamp/release.
- **`scorecard.md`** — human-readable summary + a **regression diff** vs. the prior run.
- Findings feed the product backlog (ranked by severity × persona-priority).

## Explicit limits (state these in every report)
- Agent scores are **directional and comparative**, not absolute or causal.
- No representativeness claim for simulated personas (real users differ; variance is compressed).
- The harness **prioritizes and regresses**; humans decide. Escalate flagged issues
  to a small human study before acting on anything high-stakes.

## Implementation
Code lives under `eval/` (see `eval/README.md`). Iteration 1 (content-eval) ships
first as runnable Python against the live API; iterations 2–3 add the
Playwright-driven page/heuristic and persona-task layers.
