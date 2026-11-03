"""Generate the figures and result tables for docs/vetted_classifier/README.md.

Everything is computed from the leakage-clean experiment table
(``cancer_center/vetted_ml_table_trainev.parquet``: member-matching evidence from
train-split vetted papers only) and the cached Clef answers. Models are fit on
train, thresholds chosen on validation, curves drawn on test.

Run from the repo root:  uv run --extra ml python docs/vetted_classifier/make_report_assets.py

Figures are plain SVG written with the standard library (no plotting dependency).
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import polars as pl
import scipy.sparse as sp
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.metrics import (
    average_precision_score,
    precision_recall_curve,
    roc_auc_score,
    roc_curve,
)

from cu_openalex.cancer_center import vetted_ml as V
from cu_openalex.cancer_center.axes import QUESTION_SETS, axis_features

OUT = Path(__file__).parent
TABLE = "vetted_ml_table_trainev"
COLORS = {"baseline": "#7f7f7f", "+Clef-flash": "#1f77b4", "+Clef": "#ff7f0e", "+both": "#2ca02c",
          "mechanical rules": "#d62728"}

# --------------------------------------------------------------------- SVG helpers

W, H, ML, MR, MT, MB = 560, 440, 64, 20, 40, 64


def _x(v, lo=0.0, hi=1.0):
    return ML + (v - lo) / (hi - lo) * (W - ML - MR)


def _y(v, lo=0.0, hi=1.0):
    return H - MB - (v - lo) / (hi - lo) * (H - MT - MB)


def _frame(title, xlabel, ylabel, ticks=(0, 0.2, 0.4, 0.6, 0.8, 1.0), ylo=0.0, yhi=1.0):
    s = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" '
         f'font-family="Helvetica, Arial, sans-serif" font-size="12">',
         f'<rect width="{W}" height="{H}" fill="white"/>',
         f'<text x="{W / 2}" y="22" text-anchor="middle" font-size="14" font-weight="bold">{title}</text>']
    for t in ticks:
        s.append(f'<line x1="{_x(t):.1f}" y1="{_y(ylo):.1f}" x2="{_x(t):.1f}" y2="{_y(yhi):.1f}" stroke="#eee"/>')
        s.append(f'<text x="{_x(t):.1f}" y="{H - MB + 18}" text-anchor="middle">{t:g}</text>')
    yt = np.linspace(ylo, yhi, 6)
    for t in yt:
        s.append(f'<line x1="{_x(0):.1f}" y1="{_y(t, ylo, yhi):.1f}" x2="{_x(1):.1f}" y2="{_y(t, ylo, yhi):.1f}" stroke="#eee"/>')
        s.append(f'<text x="{ML - 8}" y="{_y(t, ylo, yhi) + 4:.1f}" text-anchor="end">{t:.2g}</text>')
    s.append(f'<rect x="{ML}" y="{MT}" width="{W - ML - MR}" height="{H - MT - MB}" fill="none" stroke="#333"/>')
    s.append(f'<text x="{(ML + W - MR) / 2}" y="{H - 22}" text-anchor="middle">{xlabel}</text>')
    s.append(f'<text transform="translate(18,{(MT + H - MB) / 2}) rotate(-90)" text-anchor="middle">{ylabel}</text>')
    return s


def _legend(s, items, x0, y0):
    for i, (label, color, dash) in enumerate(items):
        y = y0 + i * 18
        s.append(f'<line x1="{x0}" y1="{y}" x2="{x0 + 24}" y2="{y}" stroke="{color}" stroke-width="2.5" '
                 f'stroke-dasharray="{dash}"/>')
        s.append(f'<text x="{x0 + 30}" y="{y + 4}">{label}</text>')
    s.append("")


def _poly(xs, ys, color, dash="", ylo=0.0, yhi=1.0, step=1):
    pts = " ".join(f"{_x(a):.1f},{_y(b, ylo, yhi):.1f}" for a, b in list(zip(xs, ys, strict=True))[::step])
    return f'<polyline points="{pts}" fill="none" stroke="{color}" stroke-width="2" stroke-dasharray="{dash}"/>'


def _save(name, s):
    s.append("</svg>")
    (OUT / name).write_text("\n".join(s))


# --------------------------------------------------------------------- models

def main() -> None:
    t = pl.read_parquet(V.table_path(TABLE))
    y = t["vet"].to_numpy().astype(int)
    split = t["split"].to_numpy()
    tr, va, te = (np.where(split == k)[0] for k in ("train", "val", "test"))
    axes = ["clef-flash:v1", "clef:v1"]
    b = V._feature_blocks(t, tr, axes)
    base = ["G0", "G1", "G2"]
    cfg = {
        "baseline": (base, 0.1),
        "+Clef-flash": (base + ["AX[clef-flash:v1]"], 0.05),
        "+Clef": (base + ["AX[clef:v1]"], 0.05),
        "+both": (base + ["AX[clef-flash:v1]", "AX[clef:v1]"], 0.05),
    }
    scores = {}
    for name, (blocks, lr) in cfg.items():
        x = sp.hstack([sp.csr_matrix(b[n]) if isinstance(b[n], np.ndarray) else b[n] for n in blocks])
        x = x.tocsr().toarray().astype(np.float32)
        m = HistGradientBoostingClassifier(learning_rate=lr, max_iter=400, early_stopping=True,
                                           validation_fraction=0.15, random_state=0).fit(x[tr], y[tr])
        pv, pt = m.predict_proba(x[va])[:, 1], m.predict_proba(x[te])[:, 1]
        p, r, th = precision_recall_curve(y[va], pv)
        f1 = 2 * p * r / np.maximum(p + r, 1e-12)
        scores[name] = (pt, th[int(np.nanargmax(f1[:-1]))])
    yt = y[te]
    T = t[te]
    c = pl.col
    rule = T.select(c("in_tenure") & c("core_member") & c("research") & ~c("excl_type")
                    & (c("cancer_meta") | c("cancer_mesh") | c("cancer_abs"))).to_series().to_numpy()
    hard = T.select(c("in_tenure") & c("core_member") & c("research") & ~c("excl_type")
                    & ~(c("cancer_meta") | c("cancer_mesh") | c("cancer_abs"))).to_series().to_numpy()

    def prf(pred, mask=None):
        mask = np.ones_like(pred, bool) if mask is None else mask
        tp = int((pred & (yt == 1) & mask).sum()); fp = int((pred & (yt == 0) & mask).sum())
        fn = int((~pred & (yt == 1) & mask).sum())
        p, r = tp / max(tp + fp, 1), tp / max(tp + fn, 1)
        return round(p, 3), round(r, 3), round(2 * p * r / max(p + r, 1e-12), 3)

    res: dict = {"n": {"table": t.height, "train": len(tr), "val": len(va), "test": len(te),
                       "test_vetted": int(yt.sum()), "hard_test": int(hard.sum()),
                       "hard_test_vetted": int(yt[hard].sum())}, "test": {}, "hard": {}}
    for name, (pt, th) in scores.items():
        p, r, f1 = prf(pt >= th)
        res["test"][name] = {"auc": round(roc_auc_score(yt, pt), 3), "ap": round(average_precision_score(yt, pt), 3),
                             "P": p, "R": r, "F1": f1, "threshold": round(float(th), 3)}
        hp, hr, _ = prf(pt >= th, hard)
        res["hard"][name] = {"P": hp, "R": hr}
    res["test"]["mechanical rules"] = dict(zip(("P", "R", "F1"), prf(rule), strict=True))

    rng = np.random.default_rng(0)
    idx = [rng.integers(0, len(yt), len(yt)) for _ in range(2000)]
    res["bootstrap_ap_gain"] = {}
    for a, b2 in [("+Clef-flash", "baseline"), ("+Clef", "baseline"), ("+both", "baseline"), ("+Clef", "+Clef-flash")]:
        d = np.array([average_precision_score(yt[i], scores[a][0][i]) - average_precision_score(yt[i], scores[b2][0][i])
                      for i in idx])
        res["bootstrap_ap_gain"][f"{a} vs {b2}"] = [round(float(d.mean()), 3), round(float(np.percentile(d, 2.5)), 3),
                                                     round(float(np.percentile(d, 97.5)), 3)]
    progs = ["Cancer Prevention & Control", "Developmental Therapeutics", "Molecular & Cellular Oncology",
             "Tumor-Host Interactions"]
    res["per_program"] = {}
    for prog in progs:
        mask = T["programs"].list.contains(prog).fill_null(False).to_numpy()
        res["per_program"][prog] = {"n": int(mask.sum()), "vetted": int(yt[mask].sum())}
        for name in ("baseline", "+Clef-flash", "+both"):
            pt, th = scores[name]
            p, r, _ = prf(pt >= th, mask)
            res["per_program"][prog][name] = {"P": p, "R": r}
    # Calibration of the chosen model on test.
    pt = scores["+both"][0]
    bins = np.minimum((pt * 10).astype(int), 9)
    res["calibration_test"] = [{"bin": i / 10, "n": int((bins == i).sum()),
                                "mean_predicted": round(float(pt[bins == i].mean()), 3),
                                "observed": round(float(yt[bins == i].mean()), 3)}
                               for i in range(10) if (bins == i).any()]
    # Single-question signal on train (AUC of each Clef-flash answer column).
    qcols = []
    for qid, q in QUESTION_SETS["v1"].items():
        if q["type"] == "noul":
            qcols.append(qid)
        elif q["type"] == "choice":
            qcols += [f"{qid}={k}" for k in q["criteria"]]
        else:
            qcols += [f"{qid}={i}" for i in range(len(q["criteria"]))]
    ax = axis_features(t["pmid"], "clef-flash:v1")[:, :-1]
    aucs = sorted(((roc_auc_score(y[tr], ax[tr, i]), n) for i, n in enumerate(qcols) if ax[tr, i].std() > 0),
                  reverse=True)
    res["question_auc_train"] = [[n, round(a, 3)] for a, n in aucs]
    # Validation ablation (best per feature set) from the saved run.
    val = pl.read_parquet("data/cancer_center/vetted_ml/val_trainev.parquet")
    res["ablation_val_ap"] = (val.group_by("features").agg(pl.col("ap").max().round(3))
                              .sort("ap", descending=True).rows())
    (OUT / "results.json").write_text(json.dumps(res, indent=2))

    # ---- Figures
    s = _frame("ROC curves, held-out test set", "False positive rate", "True positive rate")
    s.append(f'<line x1="{_x(0)}" y1="{_y(0)}" x2="{_x(1)}" y2="{_y(1)}" stroke="#bbb" stroke-dasharray="4,4"/>')
    leg = []
    for name, (pt, _) in scores.items():
        fpr, tpr, _ = roc_curve(yt, pt)
        s.append(_poly(fpr, tpr, COLORS[name], step=max(1, len(fpr) // 600)))
        leg.append((f"{name} (AUC {res['test'][name]['auc']:.3f})", COLORS[name], ""))
    leg.append(("chance", "#bbb", "4,4"))
    _legend(s, leg, _x(0.38), _y(0.36))
    _save("fig_roc.svg", s)

    s = _frame("Precision-recall curves, held-out test set", "Recall", "Precision")
    leg = []
    for name, (pt, th) in scores.items():
        p, r, _ = precision_recall_curve(yt, pt)
        s.append(_poly(r, p, COLORS[name], step=max(1, len(r) // 600)))
        leg.append((f"{name} (AP {res['test'][name]['ap']:.3f})", COLORS[name], ""))
    mr = res["test"]["mechanical rules"]
    s.append(f'<circle cx="{_x(mr["R"]):.1f}" cy="{_y(mr["P"]):.1f}" r="5" fill="{COLORS["mechanical rules"]}"/>')
    leg.append((f"mechanical rules (P {mr['P']:.2f}, R {mr['R']:.2f})", COLORS["mechanical rules"], ""))
    s.append(f'<line x1="{_x(0)}" y1="{_y(yt.mean()):.1f}" x2="{_x(1)}" y2="{_y(yt.mean()):.1f}" stroke="#bbb" stroke-dasharray="4,4"/>')
    leg.append((f"base rate ({yt.mean():.2f})", "#bbb", "4,4"))
    _legend(s, leg, _x(0.05), _y(0.30))
    _save("fig_pr.svg", s)

    s = _frame("Calibration, chosen model (+both) on test", "Mean predicted probability (decile bins)",
               "Observed share vetted")
    s.append(_poly([0, 1], [0, 1], "#bbb", "4,4"))
    cal = res["calibration_test"]
    s.append(_poly([d["mean_predicted"] for d in cal], [d["observed"] for d in cal], COLORS["+both"]))
    for d in cal:
        s.append(f'<circle cx="{_x(d["mean_predicted"]):.1f}" cy="{_y(d["observed"]):.1f}" r="{2 + min(8, d["n"] / 150):.1f}" '
                 f'fill="{COLORS["+both"]}" fill-opacity="0.6"/>')
    _legend(s, [("+both (dot area ~ papers in bin)", COLORS["+both"], ""), ("perfect calibration", "#bbb", "4,4")],
            _x(0.05), _y(0.92))
    _save("fig_calibration.svg", s)

    # Ablation bar chart (validation AP, best model per feature set).
    rows = [r for r in res["ablation_val_ap"] if not r[0].startswith("AX")]
    bw, gap, x0, wa = 24, 10, 330, 680
    hh = 60 + len(rows) * (bw + gap)
    lo, hi = 0.78, 0.88
    s = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{wa}" height="{hh}" font-family="Helvetica, Arial, sans-serif" font-size="12">',
         f'<rect width="{wa}" height="{hh}" fill="white"/>',
         f'<text x="{wa / 2}" y="22" text-anchor="middle" font-size="14" font-weight="bold">Validation AP by feature set (best model each)</text>']
    labels = {"G0": "mechanical", "G1": "metadata", "G2": "MeSH", "G3": "text TF-IDF"}
    for i, (name, ap) in enumerate(rows):
        yy = 40 + i * (bw + gap)
        lab = name
        for k, v in labels.items():
            lab = lab.replace(k, v)
        lab = (lab.replace("AX[clef-flash:v1]", "Clef-flash").replace("AX[clef:v1]", "Clef")
               .replace("all AX", "Clef + Clef-flash").replace("+", " + "))
        wpx = (ap - lo) / (hi - lo) * (wa - x0 - 60)
        col = COLORS["+both"] if "Clef" in lab else COLORS["baseline"]
        s.append(f'<text x="{x0 - 8}" y="{yy + bw / 2 + 4}" text-anchor="end">{lab}</text>')
        s.append(f'<rect x="{x0}" y="{yy}" width="{max(wpx, 1):.1f}" height="{bw}" fill="{col}"/>')
        s.append(f'<text x="{x0 + wpx + 6:.1f}" y="{yy + bw / 2 + 4}">{ap:.3f}</text>')
    s.append(f'<text x="{x0}" y="{hh - 10}" fill="#555">Bars start at AP {lo}. Grey: without Clef answers; green: with.</text>')
    _save("fig_ablation.svg", s)

    # Question table (generated so it never drifts from axes.V1).
    lines = ["| id | type | question | options / levels |", "|---|---|---|---|"]
    for qid, q in QUESTION_SETS["v1"].items():
        opts = ""
        if q["type"] == "choice":
            opts = "; ".join(f"`{k}`: {v}" for k, v in q["criteria"].items())
        elif q["type"] == "score":
            opts = "; ".join(f"{i}: {v}" for i, v in enumerate(q["criteria"]))
        lines.append(f"| `{qid}` | {q['type']} | {q['instructions']} | {opts} |")
    (OUT / "questions_v1.md").write_text("\n".join(lines) + "\n")
    print(json.dumps({k: res[k] for k in ("n", "test", "hard", "bootstrap_ap_gain")}, indent=1))


if __name__ == "__main__":
    main()
