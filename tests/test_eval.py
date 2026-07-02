"""Offline tests for the eval harness deterministic layer (docs/eval/05)."""

from __future__ import annotations

from cu_openalex.eval import checks
from cu_openalex.eval.content_eval import evaluate_item, run_content_eval
from cu_openalex.eval.gold import GOLD, GoldItem
from cu_openalex.eval.scorecard import summarize, to_markdown


def test_is_read_only():
    assert checks.is_read_only("SELECT 1")
    assert checks.is_read_only("  with x as (select 1) select * from x ")
    assert not checks.is_read_only("INSERT INTO t VALUES (1)")
    assert not checks.is_read_only("DROP TABLE t")
    assert not checks.is_read_only("SELECT 1; DELETE FROM t")  # multi-statement
    assert not checks.is_read_only("")


def test_references_any():
    assert checks.references_any("SELECT * FROM works w", ("works",))
    assert not checks.references_any("SELECT * FROM members", ("works",))
    assert checks.references_any("SELECT 1", ())  # no expectation => trivially ok


def test_evaluate_answerable_item():
    item = GoldItem("x", "q", True, ("works",))
    resp = {"queries": ["SELECT publication_year, count(*) FROM works GROUP BY 1"],
            "table": [{"publication_year": 2020, "n": 5}], "error": None}
    r = evaluate_item(item, resp)
    assert r.read_only and r.schema_valid and r.transparent
    assert r.refusal_ok is None


def test_evaluate_answerable_wrong_table():
    item = GoldItem("x", "q", True, ("works",))
    resp = {"queries": ["SELECT * FROM members"], "table": [{"a": 1}], "error": None}
    r = evaluate_item(item, resp)
    assert r.read_only and not r.schema_valid


def test_evaluate_negative_control_refused():
    item = GoldItem("neg", "impossible", False)
    # a good refusal: error set or empty table
    assert evaluate_item(item, {"queries": [], "table": None, "error": "cannot answer"}).refusal_ok
    assert evaluate_item(item, {"queries": [], "table": [], "error": None}).refusal_ok
    # a bad refusal: fabricated a non-empty answer
    assert not evaluate_item(
        item, {"queries": ["SELECT 1"], "table": [{"a": 1}], "error": None}
    ).refusal_ok


def test_ui_checks_logic(monkeypatch):
    from cu_openalex.eval import ui_eval

    pages = {
        "/": "# Overview\nMedian FWCI 1.2 ... " + "x" * 300,
        "/members": "# Members directory " + "x" * 300,
        "/programs": "# Program Collaboration " + "x" * 300,
        "/networks": "# Networks force graph " + "x" * 300,
        "/funding": "# NIH Funding " + "x" * 300,
    }
    monkeypatch.setattr(
        ui_eval, "render_markdown", lambda url, **k: pages.get(url.replace("http://x", ""))
    )
    checks = ui_eval.ui_checks("http://x", bin_path="dummy")
    by = {c.name: c.status for c in checks}
    assert by["renders /"] == "pass"
    assert by["renders /members"] == "pass"
    # the overview mentions "Median" -> responsible-metrics check passes
    assert by["responsible metrics: median/distribution shown (overview)"] == "pass"


def test_ui_checks_skipped_without_obscura(monkeypatch):
    from cu_openalex.eval import ui_eval

    monkeypatch.setattr(ui_eval, "obscura_bin", lambda: None)
    monkeypatch.delenv("OBSCURA_BIN", raising=False)
    checks = ui_eval.ui_checks("http://x")
    assert len(checks) == 1 and checks[0].status == "skipped"


def test_run_content_eval_with_injected_fetch():
    def fake(base, question, timeout):
        return {"queries": ["SELECT * FROM works"], "table": [{"n": 1}], "error": None}

    results = run_content_eval("http://x", GOLD, fetch=fake)
    assert len(results) == len(GOLD)
    # answerable items touching `works` pass schema_valid; others may not — just
    # assert the harness ran and produced a scorecard.
    summary = summarize(results, [])
    md = to_markdown(summary)
    assert "Content (NL->SQL chat)" in md
    assert "read_only" in summary["content"]["dimensions"]
