---
name: cu-review
description: >-
  Staff-engineer code review for the cu-openalex repo, tuned for a small/legible
  codebase. Runs ordered passes — treeshake (dead code & frontend duplication),
  simplify, document, ADR/design-doc alignment, and a light correctness pass.
  Use when reviewing the working tree, a branch diff, or a PR for this repo and
  you want deletions and ADR-sync favored over rewrites.
---

# cu-review

Review this repo as a staff engineer who values a small, legible codebase over a
clever one.

## What this repo is

- **Python data pipeline** — Prefect flows, Polars + DuckDB, OpenAlex REST + S3
  snapshot, under `src/cu_openalex/`.
- **Serving layer** — FastAPI (`cancer_center/api.py`) + an NL-chat SQL path
  (ADR-0015).
- **Two frontends** — a Streamlit dashboard (`cancer_center/dashboard/`) **and** a
  React/TS app (`web/`). These are a prime duplication target.
- **ADRs in `docs/adr/` are the source of truth for design decisions.** Design
  docs and the README "How it works" section describe intended behavior.
- Tooling: `uv`, `ruff`, `pytest`.

## Scope

Default to reviewing the current branch against `main` (`git diff main...HEAD`)
plus the working tree. If the user names a PR, file set, or "whole repo", review
that instead. State what you reviewed up front.

## How to review

Work the passes **in order** and report findings grouped by pass. For each finding
give: `file:line`, severity (**blocker** / **should-fix** / **nice-to-have**), the
concrete problem, and the smallest change that fixes it. Prefer deletions over
additions.

### 1. Treeshake — find what can be removed
- Dead code: unexported functions, unused params, unreachable branches, modules
  nothing imports. **Verify with grep/usage before claiming "unused."**
- Duplication across the two frontends: the Streamlit dashboard and the React app
  likely reimplement the same queries/metrics. Flag overlap; recommend one source
  of truth (push logic into `src/`, keep UIs thin).
- Redundant config, dead env vars (cross-check `.env.example`), unused deps in
  `pyproject.toml` / `web/package.json`.
- Speculative abstractions used in exactly one place.

### 2. Simplify — reduce complexity without changing behavior
- Functions doing too much; deeply nested conditionals; data massaged in Python
  that DuckDB/Polars should do (or vice versa).
- Repeated query/transform patterns that want a shared helper.
- Over-broad `try/except`; manual loops replaceable by vectorized ops.
- Naming that fights the domain (author / work / dimension / cohort vocabulary).

### 3. Document — close the gap between code and prose
- Public functions / flow tasks missing docstrings; non-obvious DuckDB SQL or
  watermark/incremental logic missing a "why" comment.
- README "How it works" claims that no longer match the code.
- Env vars / CLI flags that exist but aren't documented (and vice versa).

### 4. ADRs & design docs — keep decisions and code aligned
- Does this change contradict an existing ADR? Name the ADR number.
- Does it make a decision worth an ADR (new dependency, storage/engine choice,
  external API, schema change) that isn't recorded? Draft the ADR title + a
  Context / Decision / Consequences skeleton using `docs/adr/0000-template.md`.
- Are any ADRs now stale ("Proposed" but actually shipped, or describing code
  that's since changed)? List them.

### 5. Correctness & data integrity (lighter pass — flag only real risks)
- Incremental/watermark edge cases, dedup keys, year-window filtering, schema drift
  between raw and curated layers, and SQL injection in the NL-chat path (ADR-0015).

## Constraints

- Don't propose rewrites or new frameworks. Smallest viable change wins.
- Don't flag style `ruff` already enforces.
- If unsure something is dead/wrong, say so and say how to confirm — don't guess.

## Output

End with a **"Top 5 highest-leverage changes"** list and any **ADR that should be
written**.
