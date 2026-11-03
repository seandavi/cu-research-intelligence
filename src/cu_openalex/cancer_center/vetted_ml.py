"""Classifier for the Research Team's vetted publications (#54, #59).

Builds a paper-level feature table over the cohort (FY2016–26 papers with a
PMID), labels each paper by whether it is on the vetted list, and assigns a
fixed random train/val/test split (60/20/20, by a hash of PMID + seed, so the
split doesn't move when the table is rebuilt). The experiment fits on train,
chooses feature groups / model / threshold on validation, and reports test once.

Feature groups:

* ``G0`` mechanical — tenure at publication, Full/Mentored type in effect at
  publication (the roster's current type, from its start date), iCite research /
  clinical / human / animal / molecular scores, excluded PubMed types, cancer
  terms in topic/title, MeSH and abstract, P30, collaboration counts.
* ``G1`` metadata — publication types, member programs, OpenAlex field and
  subfield, journal.
* ``G2`` MeSH descriptors.
* ``G3`` title + abstract TF-IDF.
* ``AX`` decision-model axes (``axes.py``), when a scored cache exists.

Run: ``python -m cu_openalex.cancer_center.vetted_ml build`` then
``... vetted_ml run [--axes clef-flash:v1 ...]`` (needs the ``ml`` extra).
"""

from __future__ import annotations

import hashlib
import re
from pathlib import Path
from typing import TYPE_CHECKING

import polars as pl

from .paths import cc_target
from .scoring import CANCER_TERM_REGEX
from .vetted import latest_vetted_xlsx, vetted_pairs

if TYPE_CHECKING:  # numpy/scikit-learn come with the ml extra
    import numpy as np

SEED = 20261102
FY_MIN, FY_MAX = 2016, 2026
_EXCLUDED_TYPES = (
    r"Review|Comment|Editorial|Letter|Guideline|Consensus|Meta-Analysis|Erratum|News|Retraction"
)


def table_path(name: str = "vetted_ml_table") -> str:
    return cc_target(name)


def split_of(pmid: int) -> str:
    """Fixed 60/20/20 split from a hash of the PMID and ``SEED``."""
    h = int(hashlib.sha256(f"{SEED}:{pmid}".encode()).hexdigest()[:8], 16) / 0xFFFFFFFF
    return "train" if h < 0.6 else ("val" if h < 0.8 else "test")


def build_table(name: str = "vetted_ml_table") -> pl.DataFrame:
    """Assemble and persist the paper-level feature table."""
    from ..lake import pubmed_features

    vet = set(vetted_pairs(latest_vetted_xlsx())["pmid"].cast(pl.Int64))
    w = pl.read_parquet(cc_target("works")).with_columns(
        pmid=pl.col("pmid").str.extract(r"(\d+)$").cast(pl.Int64),
        pd=pl.col("publication_date").str.to_date(strict=False),
    )
    w = w.with_columns(fy=pl.col("pd").dt.year() + (pl.col("pd").dt.month() >= 7).cast(pl.Int32))
    w = w.filter(pl.col("pmid").is_not_null(), pl.col("fy").is_between(FY_MIN, FY_MAX)).unique(
        "pmid"
    )

    # Tenure and member type at publication, per paper (any attributed member).
    mw = pl.read_parquet(cc_target("member_works"), columns=["member_id", "work_id"])
    ev = pl.read_parquet(cc_target("member_lifecycle_event"))
    ten = ev.group_by("member_id").agg(
        joined=pl.col("event_date")
        .filter(pl.col("event_type").is_in(["applied", "type_effective"]))
        .min(),
        departed=pl.col("event_date").filter(pl.col("event_type") == "departed").max(),
    )
    # The roster holds only each member's *current* type, effective from
    # member_type_start_date; earlier papers have an unknown type (not Full/Mentored).
    mt = pl.read_parquet(
        cc_target("membership"), columns=["member_id", "member_type", "member_type_start_date"]
    )
    x = (
        mw.join(w.select("work_id", "pd"), on="work_id")
        .join(ten, on="member_id", how="left")
        .join(mt, on="member_id", how="left")
        .with_columns(
            in_ten=(pl.col("pd") >= pl.col("joined"))
            & (pl.col("departed").is_null() | (pl.col("pd") <= pl.col("departed")))
        )
        .with_columns(
            core=pl.col("in_ten")
            & pl.col("member_type").is_in(["Full", "Mentored"])
            & (
                pl.col("member_type_start_date").is_null()
                | (pl.col("pd") >= pl.col("member_type_start_date"))
            )
        )
        .group_by("work_id")
        .agg(in_tenure=pl.col("in_ten").any(), core_member=pl.col("core").any())
    )
    pm = pubmed_features(w["pmid"].to_list())
    pc = pl.read_parquet(cc_target("pub_classification"), columns=["work_id", "is_cancer_relevant"])
    rx = CANCER_TERM_REGEX
    t = (
        w.select(
            "work_id",
            "pmid",
            "fy",
            "title",
            "n_total_authors",
            "n_cc_members",
            "n_programs",
            "programs",
            "is_intra_program",
            "is_inter_program",
            "has_external_collab",
            "is_oa",
            "topic_field",
            "topic_subfield",
            "source_name",
            oa_abstract="abstract",
        )
        .join(x, on="work_id", how="left")
        .join(pm, on="pmid", how="left")
        .join(pc, on="work_id", how="left")
        .with_columns(
            abstract=pl.coalesce("abstract", "oa_abstract"),
            vet=pl.col("pmid").is_in(vet),
            research=pl.col("is_research_article").fill_null(False),
            excl_type=pl.col("publication_types").fill_null("").str.contains(_EXCLUDED_TYPES),
            cancer_meta=pl.col("is_cancer_relevant").fill_null(False),
            cancer_mesh=pl.col("mesh_terms").fill_null("").str.to_lowercase().str.contains(rx),
            in_tenure=pl.col("in_tenure").fill_null(False),
            core_member=pl.col("core_member").fill_null(False),
            p30=pl.col("p30").fill_null(False),
        )
        .with_columns(
            cancer_abs=pl.col("abstract").fill_null("").str.to_lowercase().str.contains(rx),
            split=pl.col("pmid").map_elements(split_of, return_dtype=pl.Utf8),
        )
        .drop("oa_abstract")
    )
    t.write_parquet(table_path(name))
    return t


def state_text(row: dict) -> str:
    """What the decision model reads about a paper (title, journal, abstract, MeSH)."""
    mesh = "; ".join(
        re.sub(r"^D\d+:", "", m.split(" / ")[0])
        for m in (row.get("mesh_terms") or "").split("; ")
        if m
    )
    parts = [f"Title: {row.get('title') or ''}", f"Journal: {row.get('source_name') or ''}"]
    if row.get("abstract"):
        parts.append(f"Abstract: {row['abstract']}")
    if mesh:
        parts.append(f"MeSH headings: {mesh}")
    return "\n".join(parts)


# --------------------------------------------------------------------------- run


def _feature_blocks(t: pl.DataFrame, tr: np.ndarray, axes: list[str]):
    import numpy as np
    import scipy.sparse as sp
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.preprocessing import MultiLabelBinarizer

    bools = [
        "in_tenure",
        "core_member",
        "research",
        "excl_type",
        "cancer_meta",
        "cancer_mesh",
        "cancer_abs",
        "p30",
        "is_clinical",
        "is_intra_program",
        "is_inter_program",
        "has_external_collab",
        "is_oa",
    ]
    g0 = t.select(
        [pl.col(c).cast(pl.Float64).fill_null(0) for c in bools]
        + [
            pl.col(c).cast(pl.Float64).fill_null(0)
            for c in ("human", "animal", "apt", "n_cc_members", "n_programs")
        ]
        + [
            pl.col("is_research_article").is_null().cast(pl.Float64).alias("no_icite"),
            (pl.col("n_total_authors").fill_null(1).cast(pl.Float64) + 1)
            .log()
            .alias("log_authors"),
            (pl.col("abstract").fill_null("") == "").cast(pl.Float64).alias("no_abstract"),
        ]
    ).to_numpy()

    def multihot(lists, min_count):
        lists = [lst or [] for lst in lists]
        counts: dict[str, int] = {}
        for i in tr:
            for v in set(lists[i]):
                counts[v] = counts.get(v, 0) + 1
        vocab = sorted(v for v, c in counts.items() if c >= min_count)
        import warnings

        with warnings.catch_warnings():
            warnings.simplefilter("ignore")  # unseen labels outside train are dropped
            return (
                MultiLabelBinarizer(classes=vocab, sparse_output=True)
                .fit_transform(lists)
                .tocsr()
                .astype(np.float64)
            )

    pt = [
        [p.split(":", 1)[-1] for p in (s or "").split("; ") if p]
        for s in t["publication_types"].to_list()
    ]
    g1 = sp.hstack(
        [
            multihot(pt, 20),
            multihot(t["programs"].to_list(), 1),
            multihot([[v] if v else [] for v in t["topic_field"].to_list()], 5),
            multihot([[v] if v else [] for v in t["topic_subfield"].to_list()], 10),
            multihot([[v] if v else [] for v in t["source_name"].to_list()], 5),
        ]
    ).tocsr()
    mesh = [
        [re.sub(r"^D\d+:", "", m.split(" / ")[0]) for m in (s or "").split("; ") if m]
        for s in t["mesh_terms"].to_list()
    ]
    g2 = multihot(mesh, 15)
    text = (t["title"].fill_null("") + " . " + t["abstract"].fill_null("")).to_list()
    tf = TfidfVectorizer(
        min_df=5, max_features=60000, ngram_range=(1, 2), sublinear_tf=True, stop_words="english"
    )
    tf.fit([text[i] for i in tr])
    g3 = tf.transform(text).tocsr()
    blocks = {"G0": g0, "G1": g1, "G2": g2, "G3": g3}
    for spec in axes:
        from .axes import axis_features

        blocks[f"AX[{spec}]"] = axis_features(t["pmid"], spec)
    return blocks


def run(
    axes: list[str] | None = None, out: str | None = None, table: str = "vetted_ml_table"
) -> pl.DataFrame:
    """Fit/select on train/val, report test once; return the validation table."""
    import numpy as np
    import scipy.sparse as sp
    from sklearn.ensemble import HistGradientBoostingClassifier
    from sklearn.linear_model import LogisticRegression
    from sklearn.metrics import average_precision_score, precision_recall_curve, roc_auc_score

    axes = axes or []
    t = pl.read_parquet(table_path(table))
    y = t["vet"].to_numpy().astype(int)
    sp_ = t["split"].to_numpy()
    idx = {s: np.where(sp_ == s)[0] for s in ("train", "val", "test")}
    tr, va, te = idx["train"], idx["val"], idx["test"]
    b = _feature_blocks(t, tr, axes)

    def dense_scaled(name):
        m = b[name]
        mu, sd = m[tr].mean(0), m[tr].std(0)
        sd[sd < 1e-6] = 1
        return sp.csr_matrix((m - mu) / sd)

    ax_names = [k for k in b if k.startswith("AX")]
    sets: dict[str, list[str]] = {
        "G0": ["G0"],
        "G0+G1": ["G0", "G1"],
        "G0+G1+G2": ["G0", "G1", "G2"],
        "G0+G1+G2+G3": ["G0", "G1", "G2", "G3"],
    }
    for a in ax_names:
        sets[f"{a}"] = [a]
        sets[f"G0+{a}"] = ["G0", a]
        sets[f"G0+G1+G2+{a}"] = ["G0", "G1", "G2", a]
    if len(ax_names) > 1:
        sets["G0+G1+G2+all AX"] = ["G0", "G1", "G2", *ax_names]

    def mat(names, for_lr):
        parts = []
        for n in names:
            dense = isinstance(b[n], np.ndarray)
            parts.append(
                dense_scaled(n) if (for_lr and dense) else (sp.csr_matrix(b[n]) if dense else b[n])
            )
        return sp.hstack(parts).tocsr()

    def best_th(yv, pv):
        p, r, th = precision_recall_curve(yv, pv)
        f1 = 2 * p * r / np.maximum(p + r, 1e-12)
        i = int(np.nanargmax(f1[:-1]))
        return th[i], p[i], r[i], f1[i]

    def models(names):
        if "G3" not in names:
            for lr in (0.05, 0.1):
                yield (
                    f"gbm lr={lr}",
                    lambda lr=lr: HistGradientBoostingClassifier(
                        learning_rate=lr,
                        max_iter=400,
                        early_stopping=True,
                        validation_fraction=0.15,
                        random_state=0,
                    ),
                    False,
                )
        for c in (0.1, 0.3):
            yield (
                f"logreg C={c}",
                lambda c=c: LogisticRegression(C=c, max_iter=3000, solver="liblinear"),
                True,
            )

    rows, fitted = [], {}
    for sname, names in sets.items():
        for mname, make, is_lr in models(names):
            x = mat(names, is_lr)
            x = x if is_lr else x.toarray().astype(np.float32)
            m = make().fit(x[tr], y[tr])
            pv = m.predict_proba(x[va])[:, 1]
            th, p, r, f1 = best_th(y[va], pv)
            rows.append(
                dict(
                    features=sname,
                    model=mname,
                    auc=roc_auc_score(y[va], pv),
                    ap=average_precision_score(y[va], pv),
                    P=p,
                    R=r,
                    F1=f1,
                    th=th,
                )
            )
            fitted[(sname, mname)] = (m, x)
    val = pl.DataFrame(rows).sort("ap", descending=True)
    with pl.Config(tbl_rows=-1, tbl_width_chars=200, float_precision=3):
        print("VALIDATION (threshold = max F1 on validation)")
        print(val.select("features", "model", "auc", "ap", "P", "R", "F1"))

    best = val.row(0, named=True)
    m, x = fitted[(best["features"], best["model"])]
    pt = m.predict_proba(x[te])[:, 1]
    pred = pt >= best["th"]
    yt = y[te]
    tp, fp, fn = (
        int((pred & (yt == 1)).sum()),
        int((pred & (yt == 0)).sum()),
        int((~pred & (yt == 1)).sum()),
    )
    print(f"\nchosen on validation: {best['features']} / {best['model']}")
    print(
        f"TEST  AUC={roc_auc_score(yt, pt):.3f} AP={average_precision_score(yt, pt):.3f} "
        f"P={tp / max(tp + fp, 1):.3f} R={tp / max(tp + fn, 1):.3f}"
    )
    if out:
        Path(out).parent.mkdir(parents=True, exist_ok=True)
        val.write_parquet(out)
    return val


def main() -> None:
    import argparse

    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    sub = ap.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser(
        "build", help="Build the feature table (needs the lake and the vetted sheet)."
    )
    b.add_argument("--table", default="vetted_ml_table", help="Table name under cancer_center/.")
    r = sub.add_parser("run", help="Fit/select/test (needs the 'ml' extra).")
    r.add_argument("--axes", nargs="*", default=[], help="Axis caches to add, as model:version.")
    r.add_argument("--out", default=None, help="Write the validation table here.")
    r.add_argument("--table", default="vetted_ml_table", help="Table name under cancer_center/.")
    e = sub.add_parser("export", help="Write the review workbook (needs the 'ml' extra).")
    e.add_argument("--out", required=True, help="Path of the .xlsx to write.")
    e.add_argument("--table", default="vetted_ml_table", help="Table name under cancer_center/.")
    args = ap.parse_args()
    if args.cmd == "build":
        t = build_table(args.table)
        print(
            t.height,
            t.group_by("split").agg(pl.len(), pl.col("vet").mean().round(3)).sort("split").rows(),
        )
    elif args.cmd == "export":
        th = export(args.out, args.table)
        print(f"  wrote {args.out}; thresholds {th}")
    else:
        run(args.axes, args.out, args.table)


# ------------------------------------------------------------------------ export

EXPORT_AXES = ["clef-flash:v1", "clef:v1"]  # the configuration chosen in #59


def oof_scores(t: pl.DataFrame, axes: list[str], folds: int = 5) -> np.ndarray:
    """Out-of-fold P(vetted) for every paper: each fold's papers are scored by a
    model fit on the other folds, so no paper is scored by a model that saw it."""
    import numpy as np
    import scipy.sparse as sp
    from sklearn.ensemble import HistGradientBoostingClassifier
    from sklearn.model_selection import StratifiedKFold

    y = t["vet"].to_numpy().astype(int)
    b = _feature_blocks(t, np.arange(t.height), axes)  # unsupervised vocabularies only
    names = ["G0", "G1", "G2", *(f"AX[{a}]" for a in axes)]
    x = sp.hstack([sp.csr_matrix(b[n]) if isinstance(b[n], np.ndarray) else b[n] for n in names])
    x = x.tocsr().toarray().astype(np.float32)
    out = np.zeros(t.height)
    for fit_idx, score_idx in StratifiedKFold(folds, shuffle=True, random_state=SEED).split(x, y):
        m = HistGradientBoostingClassifier(
            learning_rate=0.05,
            max_iter=400,
            early_stopping=True,
            validation_fraction=0.15,
            random_state=0,
        ).fit(x[fit_idx], y[fit_idx])
        out[score_idx] = m.predict_proba(x[score_idx])[:, 1]
    return out


def _thresholds(y, p) -> dict[str, float]:
    """Band cut-offs on the out-of-fold scores: ``propose`` where precision >= 90%,
    ``held_back`` below the score that keeps 98% of vetted papers above it, and
    ``max_f1`` (the single best yes/no cut)."""
    import numpy as np
    from sklearn.metrics import precision_recall_curve

    prec, rec, th = precision_recall_curve(y, p)
    f1 = 2 * prec * rec / np.maximum(prec + rec, 1e-12)
    ok = np.where(prec[:-1] >= 0.90)[0]
    return {
        "propose": float(th[ok[0]]) if len(ok) else 1.0,
        "held_back": float(np.quantile(p[y == 1], 0.02)),
        "max_f1": float(th[int(np.nanargmax(f1[:-1]))]),
    }


def export(path: str, table: str = "vetted_ml_table") -> dict[str, float]:
    """Write the review workbook: our columns full-outer-joined to the team's sheet."""

    from .axes import axis_summary

    t = pl.read_parquet(table_path(table))
    p = oof_scores(t, EXPORT_AXES)
    y = t["vet"].to_numpy().astype(int)
    th = _thresholds(y, p)
    # Full precision: bands are compared against unrounded scores (the workbook
    # displays 4 decimals via float_precision).
    t = t.with_columns(model_prob=pl.Series(p))

    # Our attributed members per paper, "Last F (Program)".
    mem = pl.read_parquet(cc_target("members"), columns=["Member_ID", "Last_Name", "First_Name"])
    mw = pl.read_parquet(cc_target("member_works"), columns=["member_id", "work_id", "program"])
    our_members = (
        mw.join(mem, left_on="member_id", right_on="Member_ID")
        .with_columns(
            m=pl.format(
                "{} {} ({})",
                "Last_Name",
                pl.col("First_Name").str.slice(0, 1),
                pl.col("program").fill_null("?"),
            )
        )
        .group_by("work_id")
        .agg(our_members=pl.col("m").unique().sort().str.join("; "))
    )
    w = pl.read_parquet(
        cc_target("works"), columns=["work_id", "publication_date", "doi", "collaboration_class"]
    )
    clef = axis_summary("clef-flash:v1").rename(lambda c: c if c == "pmid" else f"clef: {c}")
    ours = (
        t.join(w, on="work_id", how="left")
        .join(our_members, on="work_id", how="left")
        .join(clef, on="pmid", how="left")
        .with_columns(
            model_says_yes=pl.col("model_prob") >= th["max_f1"],
            model_band=pl.when(pl.col("model_prob") >= th["propose"])
            .then(pl.lit("1 propose"))
            .when(pl.col("model_prob") < th["held_back"])
            .then(pl.lit("3 held back"))
            .otherwise(pl.lit("2 needs judgment")),
            programs=pl.col("programs").list.join("; "),
            pubmed=pl.format("https://pubmed.ncbi.nlm.nih.gov/{}/", "pmid"),
        )
        .drop("work_id", "abstract", "vet", "is_cancer_relevant")
    )

    team = pl.read_excel(
        latest_vetted_xlsx(), read_options={"header_row": 2}, infer_schema_length=0
    )
    team = team.select([c for c in team.columns if not c.startswith("__UNNAMED")])
    team = team.with_columns(pmid=pl.col("PMID").cast(pl.Int64, strict=False)).rename(
        lambda c: c if c == "pmid" else f"team: {c}"
    )

    x = ours.join(team, on="pmid", how="full", coalesce=True).with_columns(
        in_team_list=pl.col("team: PMID").is_not_null(),
        in_our_cohort=pl.col("model_prob").is_not_null(),
    )
    x = x.with_columns(
        agreement=pl.when(pl.col("in_team_list") & pl.col("model_says_yes").fill_null(False))
        .then(pl.lit("both yes"))
        .when(pl.col("in_team_list") & ~pl.col("in_our_cohort"))
        .then(pl.lit("team only: not in our cohort"))
        .when(pl.col("in_team_list"))
        .then(pl.lit("team only: model said no"))
        .when(pl.col("model_says_yes"))
        .then(pl.lit("model only: possible team miss"))
        .otherwise(pl.lit("neither")),
    )
    front = [
        "pmid",
        "pubmed",
        "in_team_list",
        "in_our_cohort",
        "agreement",
        "model_prob",
        "model_band",
        "model_says_yes",
        "split",
        "fy",
        "publication_date",
        "title",
        "source_name",
        "our_members",
        "programs",
        "collaboration_class",
    ]
    x = x.select(front + [c for c in x.columns if c not in front]).sort(
        "model_prob", descending=True, nulls_last=True
    )

    # Calibration: observed share vetted by predicted-probability decile.
    cal = (
        t.select("model_prob", "vet")
        .with_columns(bin=(pl.col("model_prob") * 10).floor().clip(0, 9) / 10)
        .group_by("bin")
        .agg(
            n=pl.len(),
            mean_predicted=pl.col("model_prob").mean(),
            observed_vetted=pl.col("vet").mean(),
        )
        .sort("bin")
    )
    summary = x.group_by("agreement").len().sort("len", descending=True)
    readme = pl.DataFrame({"item": list(_README), "description": list(_README.values())})
    readme = pl.concat(
        [
            readme,
            pl.DataFrame(
                {
                    "item": [f"threshold: {k}" for k in th],
                    "description": [f"{v:.4f}" for v in th.values()],
                }
            ),
        ]
    )
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    import xlsxwriter

    with xlsxwriter.Workbook(path) as wb:
        x.write_excel(
            wb,
            worksheet="papers",
            autofilter=True,
            freeze_panes=(1, 2),
            column_widths={"title": 60, "our_members": 40, "team: Citation": 60},
            autofit=False,
            float_precision=4,
        )
        summary.write_excel(wb, worksheet="summary", autofit=True)
        cal.write_excel(wb, worksheet="calibration", autofit=True, float_precision=3)
        readme.write_excel(wb, worksheet="README", column_widths={"item": 32, "description": 110})
    return th


_README = {
    "rows": (
        "One row per PMID: every FY2016–26 cohort paper with a PMID (our columns), full-"
        "outer-joined to every row of the Research Team's vetted sheet (columns prefixed "
        "'team: ')."
    ),
    "in_team_list": (
        "TRUE if the PMID is on the Research Team's vetted sheet. Filter TRUE to see "
        "their chosen papers."
    ),
    "in_our_cohort": (
        "TRUE if the paper is in our cohort (attributed to a member through our OpenAlex matching)."
    ),
    "agreement": (
        "both yes / team only: model said no / team only: not in our cohort / model only:"
        " possible team miss / neither."
    ),
    "model_prob": (
        "Probability the team would list this paper: gradient-boosted trees on mechanical"
        " checks, metadata, MeSH and Clef + Clef-flash v1 answers (#59). Out-of-fold: "
        "each paper is scored by a model trained on the other 4 of 5 folds. Member "
        "attribution itself used the team's list as evidence (#57), so this is still "
        "optimistic."
    ),
    "model_band": (
        "1 propose (precision >= 90% on these out-of-fold scores) / 2 needs judgment / 3 "
        "held back (below the score that keeps 98% of vetted papers above it)."
    ),
    "model_says_yes": ("model_prob at or above the max-F1 cut-off."),
    "split": ("The fixed train/val/test split used in the experiments (#59); informational."),
    "in_tenure / core_member": (
        "A member was a member when it was published / a Full or Mentored member (type in"
        " effect at publication)."
    ),
    "research / excl_type": (
        "iCite research article / PubMed type is review, comment, editorial, letter, "
        "guideline, consensus, meta-analysis, erratum, news or retraction."
    ),
    "cancer_meta / cancer_mesh / cancer_abs": (
        "Cancer terms in OpenAlex topic or title / MeSH / abstract."
    ),
    "p30": ("NIH RePORTER links the paper to the center's P30 (CA046934)."),
    "clef: *": (
        "Clef-flash v1 answers: probability for yes/no questions, expected level for "
        "cancer_focus (0 not about cancer … 3 main subject), top option + its probability"
        " for choice questions."
    ),
    "caution": ("Contains member names; internal use only."),
}


if __name__ == "__main__":
    main()
