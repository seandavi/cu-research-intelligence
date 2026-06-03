# 0009. Task management in local markdown

- Status: accepted
- Date: 2026-06-02

## Context

We want lightweight, reviewable task tracking that lives with the code, needs no
external service, and shows up in diffs/PRs alongside the work it describes.

## Decision

Track tasks in **`docs/TASKS.md`** — a single markdown board grouped by milestone
with checkbox status (`[ ]` / `[~]` / `[x]`). It is versioned with the repo, so
task changes land in the same commits/branches as the code.

## Consequences

- Zero infrastructure; full history via git; trivially editable.
- No automation, assignees, or cross-linking that a tracker (GitHub Issues,
  Linear) would give — fine at this project's size.
- If the project grows or gains collaborators, revisit moving to GitHub Issues.

## Alternatives considered

- **GitHub Issues / Projects**: better for collaboration and automation, but
  requires a remote and pulls planning out of the repo.
- **TODO comments in code**: get lost; no single overview.
