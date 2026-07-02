"""Scorecard assembly for the eval harness (docs/eval/05)."""

from __future__ import annotations

from .capabilities import Check
from .content_eval import ItemResult


def _rate(vals: list[bool | None]) -> tuple[int, int]:
    applicable = [v for v in vals if v is not None]
    return sum(bool(v) for v in applicable), len(applicable)


def summarize(content: list[ItemResult], caps: list[Check]) -> dict:
    dims = {
        "read_only": _rate([r.read_only for r in content]),
        "schema_valid": _rate([r.schema_valid for r in content]),
        "transparent": _rate([r.transparent for r in content]),
        "refusal_ok": _rate([r.refusal_ok for r in content]),
    }
    return {
        "content": {
            "dimensions": {k: {"passed": p, "of": n} for k, (p, n) in dims.items()},
            "items": [r.__dict__ for r in content],
        },
        "capabilities": [c.__dict__ for c in caps],
    }


def to_markdown(summary: dict) -> str:
    lines = ["# Eval scorecard", "", "## Content (NL->SQL chat)", ""]
    for dim, s in summary["content"]["dimensions"].items():
        n = s["of"]
        pct = f"{100 * s['passed'] / n:.0f}%" if n else "n/a"
        lines.append(f"- **{dim}**: {s['passed']}/{n} ({pct})")
    lines += ["", "## Backend / capability coverage", ""]
    for c in summary["capabilities"]:
        detail = f" — {c['detail']}" if c.get("detail") else ""
        lines.append(f"- `{c['status']}` **{c['name']}**{detail}")
    lines += [
        "",
        "_Content + capability layers are runnable now; UI/UX heuristic and "
        "persona task-walkthrough layers (Playwright) are iterations 2-3 (docs/eval/05). "
        "Agent scores are directional/regression signals, not the sole gate._",
    ]
    return "\n".join(lines)
