# 0002. Package with uv and a src layout

- Status: accepted
- Date: 2026-06-02

## Context

We want reproducible environments, a clean import boundary, and fast installs.
The project will grow beyond a couple of files (client, transforms, state,
flows, tests).

## Decision

Manage the project with **uv** and a **src layout** (`src/cu_openalex/`). The
distribution name is `cu-openalex`; the import package is `cu_openalex`.
Dependencies and the lockfile (`uv.lock`) are committed; dev tools live in the
`dev` dependency group. Run everything via `uv run` (e.g. `uv run pytest`,
`uv run python -m cu_openalex.flows.pipeline`).

## Consequences

- `uv.lock` pins the full graph for reproducible installs.
- src layout prevents accidental imports of the working tree and forces testing
  against the installed package.
- Contributors must use `uv` (or a PEP 621-aware tool) rather than ad-hoc pip.

## Alternatives considered

- **pip + requirements.txt**: weaker locking, no built-in venv/project model.
- **Poetry/PDM**: capable, but uv is faster and already the team default.
- **Flat layout**: simpler, but loses the import-isolation benefit of src.
