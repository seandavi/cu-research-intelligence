"""Content eval for the NL->SQL chat (docs/eval/05, iteration 1).

Runs the gold set against a target ``/api/chat`` and scores each item on
deterministic dimensions (no LLM required):

- **read_only** — every generated query is a single read-only statement (safety).
- **schema_valid** — a query touches an expected table (answerable items only).
- **transparent** — the executed query is returned (answerable items only).
- **refusal_ok** — negative controls are refused/empty, not fabricated.

An LLM-judge dimension (relevancy / faithfulness) is a future addition; it plugs
in via the optional ``judge`` callable.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from .checks import all_read_only, references_any
from .gold import GOLD, GoldItem


@dataclass
class ItemResult:
    id: str
    answerable: bool
    read_only: bool
    schema_valid: bool | None  # None => N/A (negative control)
    transparent: bool | None
    refusal_ok: bool | None
    error: str | None = None


def _post_chat(base_url: str, question: str, timeout: float) -> dict:
    import httpx

    r = httpx.post(
        base_url.rstrip("/") + "/api/chat", json={"question": question}, timeout=timeout
    )
    r.raise_for_status()
    return r.json()


def evaluate_item(
    item: GoldItem, response: dict
) -> ItemResult:
    """Score one gold item against a chat response dict (pure — testable offline)."""
    queries = response.get("queries") or []
    table = response.get("table")
    error = response.get("error")
    answered = bool(table) and not error

    read_only = all_read_only(queries) if queries else (item.answerable is False)
    if item.answerable:
        schema_valid = any(references_any(q, item.expect_tables) for q in queries)
        transparent = len(queries) > 0
        refusal_ok = None
    else:
        # negative control: should refuse or return nothing, not fabricate an answer
        schema_valid = None
        transparent = None
        refusal_ok = (not answered) or bool(error)
    return ItemResult(
        id=item.id,
        answerable=item.answerable,
        read_only=read_only,
        schema_valid=schema_valid,
        transparent=transparent,
        refusal_ok=refusal_ok,
        error=error,
    )


def run_content_eval(
    base_url: str,
    gold: tuple[GoldItem, ...] = GOLD,
    *,
    timeout: float = 60.0,
    fetch: Callable[[str, str, float], dict] | None = None,
) -> list[ItemResult]:
    """Evaluate the chat over the gold set. ``fetch`` is injectable for tests."""
    fetch = fetch or _post_chat
    results: list[ItemResult] = []
    for item in gold:
        try:
            resp = fetch(base_url, item.question, timeout)
        except Exception as e:  # noqa: BLE001 — record transport errors as a failed item
            results.append(
                ItemResult(item.id, item.answerable, False, None, None, None, error=str(e))
            )
            continue
        results.append(evaluate_item(item, resp))
    return results
