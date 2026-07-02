"""CLI for the eval harness (docs/eval/05).

    uv run python -m cu_openalex.eval --base-url https://insights.uccc.cancerdatasci.org

Runs the content (chat) + backend capability layers against a target and writes
a scorecard (JSON + markdown). The UI/UX heuristic + persona layers (Playwright)
are iterations 2-3.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from .capabilities import api_contract_checks, capability_coverage
from .content_eval import run_content_eval
from .scorecard import summarize, to_markdown
from .ui_eval import ui_checks


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://localhost:8000")
    parser.add_argument("--out", default=".", help="Directory for scorecard.json/.md")
    parser.add_argument("--skip-chat", action="store_true", help="Skip the (slow) chat eval")
    parser.add_argument("--skip-ui", action="store_true", help="Skip the Obscura UI eval")
    args = parser.parse_args()

    content = [] if args.skip_chat else run_content_eval(args.base_url)
    caps = api_contract_checks(args.base_url) + capability_coverage(args.base_url)
    ui = [] if args.skip_ui else ui_checks(args.base_url)
    summary = summarize(content, caps, ui)

    out = Path(args.out)
    (out / "scorecard.json").write_text(json.dumps(summary, indent=2))
    md = to_markdown(summary)
    (out / "scorecard.md").write_text(md)
    print(md)


if __name__ == "__main__":
    main()
