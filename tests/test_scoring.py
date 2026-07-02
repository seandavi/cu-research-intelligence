"""Tests for the deterministic cancer-relevance classifier (ADR-0027, stage 1).

Runs against a small synthetic works parquet (no full corpus needed), so it runs
in CI. Asserts the metadata-first rules and the agent-review routing.
"""

from __future__ import annotations

import datetime as dt

import polars as pl

from cu_openalex.cancer_center import scoring


def _works(tmp_path):
    df = pl.DataFrame(
        {
            "work_id": ["w1", "w2", "w3", "w4", "w5", "w6"],
            "pmid": ["1", "2", "3", "4", "5", "6"],
            "publication_year": [2020, 2021, 2022, 2023, 2024, 2020],
            "title": [
                "Lenvatinib plus pembrolizumab for advanced endometrial cancer",  # onc + title
                "A phase II trial of a novel kinase inhibitor",  # onc topic, no term
                "EWS/FLI1 regulates EYA3 in Ewing sarcoma",  # term, non-onc topic
                "Long-term treatment of gout",  # neither
                "Modeling dark energy in cosmology",  # neither
                "Tumor microenvironment and immune evasion",  # term, non-onc topic
            ],
            # w3/w6 topics deliberately carry NO cancer term, so only the title
            # fires → the needs_review (agent) band.
            "primary_topic": [
                "Cancer immunotherapy", "Kinase inhibitors", "Gene regulation networks",
                "Gout and urate", "Cosmology", "Immune cell signaling",
            ],
            "topic_subfield": ["Oncology", "Oncology", "Molecular Biology",
                               "Rheumatology", "Astronomy and Astrophysics", "Immunology"],
            "topic_field": ["Medicine", "Medicine", "Biochemistry", "Medicine",
                            "Physics", "Immunology"],
        }
    )
    p = tmp_path / "works.parquet"
    df.write_parquet(p)
    return str(p)


def test_classification_rules(tmp_path):
    src = _works(tmp_path)
    df = scoring.classify(src, run_date=dt.date(2026, 7, 2))
    rows = {r["work_id"]: r for r in df.to_dicts()}

    # oncology topic (+ title term) → cancer, high, not flagged
    assert rows["w1"]["is_cancer_relevant"] and rows["w1"]["confidence"] == "high"
    assert not rows["w1"]["needs_review"]

    # oncology topic, no title term → cancer, high (topic is trusted)
    assert rows["w2"]["is_cancer_relevant"] and rows["w2"]["confidence"] == "high"
    assert rows["w2"]["reason"] == "oncology_topic"

    # title term but non-oncology topic → cancer, medium, needs_review (agent queue)
    assert rows["w3"]["is_cancer_relevant"] and rows["w3"]["confidence"] == "medium"
    assert rows["w3"]["needs_review"] and rows["w3"]["reason"] == "title_term_only"

    # clearly not cancer → not relevant, confident, not flagged
    for wid in ("w4", "w5"):
        assert not rows[wid]["is_cancer_relevant"]
        assert rows[wid]["confidence"] == "high" and not rows[wid]["needs_review"]

    # "tumor" in title, immunology topic → needs_review
    assert rows["w6"]["needs_review"]

    # run_date + classifier provenance are stamped
    assert df["run_date"].unique().to_list() == [dt.date(2026, 7, 2)]
    assert df["classifier_name"].unique().to_list() == [scoring.CLASSIFIER_NAME]


def test_build_writes_and_summarizes(tmp_path, monkeypatch):
    src = _works(tmp_path)
    out = tmp_path / "pub_classification.parquet"
    monkeypatch.setattr(scoring, "cc_target", lambda name: str(out))
    summary = scoring.build_cancer_relevance(source=src, run_date=dt.date(2026, 7, 2))
    assert summary["total"] == 6
    assert summary["cancer_relevant"] == 4  # w1, w2, w3, w6
    assert summary["high_conf"] == 2  # w1, w2
    assert summary["needs_review"] == 2  # w3, w6
    assert out.exists()
