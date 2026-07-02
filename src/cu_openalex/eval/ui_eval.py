"""UI/UX eval layer via Obscura (docs/eval/05, iteration 2).

Uses the Obscura headless browser (`fetch --dump markdown` / `--eval`) to render
the React SPA the way a member sees it, then runs content/heuristic checks — the
UI/UX half of the evaluation (the backend half is content_eval + capabilities).

Obscura is located via ``OBSCURA_BIN`` (env) or ``obscura`` on PATH; when neither
is present every check reports ``skipped`` so the harness stays runnable/CI-safe.
Full task-walkthrough automation (clicking through scenarios via Obscura's CDP
`serve` mode) is a further step; this layer scores *what a member sees* per page,
including a responsible-metrics presentation check (median/distribution, not a
bare mean).
"""

from __future__ import annotations

import os
import shutil
import subprocess
from dataclasses import dataclass


@dataclass
class UICheck:
    name: str
    status: str  # "pass" | "fail" | "skipped"
    detail: str = ""


def obscura_bin() -> str | None:
    return os.environ.get("OBSCURA_BIN") or shutil.which("obscura")


def render_markdown(
    url: str, *, bin_path: str | None = None, wait: int = 6, timeout: int = 45
) -> str | None:
    """Render a URL to markdown via Obscura (JS-rendered). None if unavailable/failed."""
    b = bin_path or obscura_bin()
    if not b:
        return None
    private = ["--allow-private-network"] if ("localhost" in url or "127.0.0.1" in url) else []
    try:
        out = subprocess.run(
            [b, "fetch", url, "--dump", "markdown", "--wait", str(wait),
             "--timeout", str(timeout), *private],
            capture_output=True, text=True, timeout=timeout + 20,
        )
        return out.stdout if out.returncode == 0 else None
    except Exception:  # noqa: BLE001
        return None


# Key SPA routes and a substring that must appear once JS has rendered.
_ROUTES = [
    ("/", "Overview"),
    ("/members", "Member"),
    ("/programs", "Program"),
    ("/networks", "Network"),
    ("/funding", "Funding"),
]


def ui_checks(base_url: str, *, bin_path: str | None = None) -> list[UICheck]:
    b = bin_path or obscura_bin()
    if not b:
        return [UICheck("ui (obscura)", "skipped", "OBSCURA_BIN not set and obscura not on PATH")]

    checks: list[UICheck] = []
    rendered: dict[str, str] = {}
    for path, expect in _ROUTES:
        md = render_markdown(base_url.rstrip("/") + path, bin_path=b)
        if md is None:
            checks.append(UICheck(f"renders {path}", "fail", "no render"))
            continue
        rendered[path] = md
        ok = expect.lower() in md.lower() and len(md) > 200
        checks.append(
            UICheck(f"renders {path}", "pass" if ok else "fail",
                    "" if ok else f"missing '{expect}' or too short")
        )

    # Responsible-metrics presentation (stage 4): the overview/KPI surface should
    # show a median/distribution, not only a mean.
    overview = rendered.get("/", "")
    if overview:
        has_median = "median" in overview.lower()
        checks.append(
            UICheck("responsible metrics: median/distribution shown (overview)",
                    "pass" if has_median else "fail",
                    "median present" if has_median else "no 'median' on overview")
        )
    return checks
