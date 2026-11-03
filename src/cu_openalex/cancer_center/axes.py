"""Decision-model axes for cancer relevance (#59): Cloudflare Clef / Clef-flash.

A *question set* is a versioned schema of typed questions (``noul`` yes/no,
``choice``, ``score``). Clef answers all of them in one pass per paper and
returns a probability for every option; those probabilities become classifier
features (``vetted_ml``). Answers are cached per (model, version) under
``cancer_center/axes/<model>__<version>/`` as append-only parquet parts, so a
run resumes where it stopped and a new question-set version never mixes with
an old one.

Needs ``CLOUDFLARE_ACCOUNT_ID`` and ``CLOUDFLARE_API_TOKEN`` (Workers AI) in the
environment. Run: ``python -m cu_openalex.cancer_center.axes --model clef-flash
--version v1 [--split train --limit 500]``.
"""

from __future__ import annotations

import asyncio
import json
import os
import time
from pathlib import Path
from typing import TYPE_CHECKING

import polars as pl

from .paths import cc_target

if TYPE_CHECKING:  # numpy is only needed by the ml extra
    import numpy as np

# --- Question sets ------------------------------------------------------------------

_PROGRAM_AIMS = {
    "fit_cpc": (
        "Cancer Prevention and Control: novel approaches to cancer prevention and early "
        "detection; population-based cancer control interventions; reducing cancer "
        "disparities through health services and policy research; behavioral prevention, "
        "chemoprevention, cancer outcomes and survivorship."
    ),
    "fit_dt": (
        "Developmental Therapeutics: discovery, preclinical development and validation, "
        "early clinical development (phase I) and delivery of new anticancer agents."
    ),
    "fit_mco": (
        "Molecular and Cellular Oncology: genomic integrity, telomere structure and "
        "function, gene expression and biomarkers, structural biology of cancer drivers, "
        "pediatric cancers and blood cancers."
    ),
    "fit_thi": (
        "Tumor-Host Interactions: how tumor-intrinsic properties shape immune recognition; "
        "how host physiology affects the tumor microenvironment and progression; therapies "
        "that redirect the immune system or exploit tumor-host interactions."
    ),
}


def _yn(text: str) -> dict:
    return {"type": "noul", "instructions": text}


CORE = {
    "cancer_focus": {
        "type": "score",
        "instructions": "How central is cancer to this paper?",
        "criteria": [
            "Not about cancer",
            "Cancer is mentioned only in passing or as background motivation",
            "Cancer is a model system, context or one of several outcomes",
            "Cancer is the main subject",
        ],
    },
    "nci_counts": _yn(
        "Would an NCI-designated cancer center count this as cancer-relevant research in its "
        "annual report? Count basic biology of processes that drive cancer, cancer prevention, "
        "screening, treatment, survivorship and cancer health services, not only papers that "
        "name a cancer."
    ),
    "bio_cancer_process": _yn(
        "Does the paper study a biological process that drives cancer (for example cell cycle, "
        "genome integrity, gene regulation, oncogenic signaling, tumor immunity, metabolism, "
        "metastasis), even if it doesn't name a cancer?"
    ),
    "cancer_control": _yn(
        "Is this cancer prevention or control research: risk factors (tobacco, HPV, UV, obesity, "
        "alcohol, diet, activity), screening, survivorship, palliative or end-of-life care, or "
        "cancer health services and disparities?"
    ),
}

V1 = {
    **CORE,
    # Biology links (one yes/no each).
    "bio_cell_cycle": _yn("Does it study the cell cycle, mitosis or chromosome segregation?"),
    "bio_genome_integrity": _yn(
        "Does it study DNA damage, DNA repair, replication stress or telomeres?"
    ),
    "bio_gene_regulation": _yn(
        "Does it study chromatin, epigenetics, transcription or RNA processing?"
    ),
    "bio_signaling": _yn(
        "Does it study growth-factor, kinase or other oncogenic signaling pathways?"
    ),
    "bio_tumor_immunity": _yn("Does it study immune responses to tumors or cancer immunotherapy?"),
    "bio_immunology": _yn(
        "Does it study immune-system biology in general (not specific to tumors)?"
    ),
    "bio_metabolism": _yn("Does it study cellular or systemic metabolism?"),
    "bio_stem_development": _yn(
        "Does it study stem cells, differentiation or developmental biology?"
    ),
    "bio_microenv_metastasis": _yn(
        "Does it study the tumor microenvironment, invasion or metastasis?"
    ),
    "bio_carcinogenesis": _yn(
        "Does it study carcinogens, environmental or occupational exposures, or toxicology?"
    ),
    "bio_radiation": _yn("Does it study radiation biology or radiation therapy?"),
    "bio_drug_development": _yn(
        "Does it involve drug discovery, pharmacology or medicinal chemistry?"
    ),
    "bio_structural": _yn("Is it structural biology or biophysics of proteins or nucleic acids?"),
    # Cancer control continuum and clinical.
    "cc_prevention_risk": _yn(
        "Does it study cancer risk factors or prevention "
        "(tobacco, HPV, UV, obesity, alcohol, diet, activity)?"
    ),
    "cc_screening": _yn("Does it study cancer screening or early detection?"),
    "cc_diagnosis": _yn("Does it study cancer diagnosis, pathology or imaging?"),
    "cc_treatment": _yn(
        "Does it study the treatment of cancer patients "
        "(surgery, radiation, drugs, immunotherapy, transplant)?"
    ),
    "cc_clinical_trial": _yn("Does it report a clinical trial?"),
    "cc_survivorship": _yn(
        "Does it study cancer survivorship, quality of life or long-term effects?"
    ),
    "cc_palliative": _yn("Does it study palliative, hospice or end-of-life care?"),
    "cc_health_services": _yn(
        "Does it study health services, access, cost, disparities or policy?"
    ),
    "cc_colorado_populations": _yn(
        "Does it focus on rural, Hispanic/Latino, American Indian, "
        "or Colorado / Mountain West populations?"
    ),
    # Design and system.
    "study_system": {
        "type": "choice",
        "instructions": "What is the main kind of evidence in this paper?",
        "criteria": {
            "in_vitro": "Cell lines, organoids or biochemical experiments",
            "animal": "Animal models",
            "biospecimens": "Human tissue, blood or other biospecimens",
            "patients": "Human participants: clinical, epidemiological or survey data",
            "qualitative": "Interviews, focus groups or other qualitative research",
            "computational": "Computational methods, software, data resources or modeling",
            "structural": "Structural biology or biophysics",
            "review": "Review, commentary, guideline or opinion",
            "veterinary": (
                "Veterinary patients (for example dogs or cats with naturally occurring disease)"
            ),
        },
    },
    "organism": {
        "type": "choice",
        "instructions": "Which organism is mainly studied?",
        "criteria": {
            "human": "Humans or human cells",
            "rodent": "Mice or rats",
            "companion": "Dogs, cats or other companion animals",
            "model_other": "Other model organisms (fly, worm, yeast, zebrafish)",
            "microbe": "Bacteria, viruses or other microbes",
            "none": "No organism (methods, chemistry, policy)",
        },
    },
    "disease_focus": {
        "type": "choice",
        "instructions": "What is the main disease focus?",
        "criteria": {
            "cancer": "Cancer",
            "cardiovascular": "Cardiovascular disease",
            "metabolic": "Diabetes, obesity or other metabolic disease",
            "infectious": "Infectious disease",
            "neuro_psych": "Neurological or psychiatric disease",
            "pulmonary": "Non-cancer lung disease",
            "immune": "Autoimmune, allergic or inflammatory disease",
            "other": "Another non-cancer disease",
            "none": "No disease focus (basic biology or methods)",
        },
    },
    "cancer_site": {
        "type": "choice",
        "instructions": "Which cancer type is studied, if any?",
        "criteria": {
            "none": "No specific cancer",
            "blood": "Leukemia, lymphoma, myeloma or other blood cancer",
            "breast": "Breast",
            "lung": "Lung",
            "gi": "Colorectal, pancreatic, liver, esophageal or gastric",
            "gu": "Prostate, bladder or kidney",
            "gyn": "Ovarian, uterine or cervical",
            "skin": "Melanoma or other skin cancer",
            "brain": "Brain or central nervous system",
            "head_neck": "Head and neck",
            "sarcoma": "Sarcoma or bone",
            "multiple": "Several cancer types or pan-cancer",
        },
    },
    # Program fit (one per current research program).
    **{
        k: _yn(f"Does this paper fit the aims of this research program? {aims}")
        for k, aims in _PROGRAM_AIMS.items()
    },
}

QUESTION_SETS = {"v1": V1, "v1-core": CORE}

# --- Scoring --------------------------------------------------------------------------

_URL = "https://api.cloudflare.com/client/v4/accounts/{acct}/ai/run/@cf/cloudflare/{model}"


def cache_dir(model: str, version: str) -> Path:
    return Path(cc_target(f"axes/{model}__{version}/x")).parent


def load_cache(model: str, version: str) -> pl.DataFrame:
    d = cache_dir(model, version)
    if not any(d.glob("*.parquet")):
        return pl.DataFrame(schema={"pmid": pl.Int64, "answers": pl.Utf8, "input_tokens": pl.Int64})
    return pl.read_parquet(d / "*.parquet").unique("pmid", keep="last")


async def _score(
    states: list[tuple[int, str]], model: str, questions: dict, concurrency: int, out: Path
):
    import httpx

    acct, token = os.environ["CLOUDFLARE_ACCOUNT_ID"], os.environ["CLOUDFLARE_API_TOKEN"]
    url = _URL.format(acct=acct, model=model)
    sem = asyncio.Semaphore(concurrency)
    done: list[dict] = []
    failures = 0

    async def one(client, pmid, state):
        nonlocal failures
        body = {"model": model, "state": state, "questions": questions}
        async with sem:
            for attempt in range(6):
                try:
                    r = await client.post(url, json=body)
                    if r.status_code == 200 and r.json().get("success"):
                        res = r.json()["result"]
                        done.append(
                            {
                                "pmid": pmid,
                                "answers": json.dumps(res["answers"]),
                                "input_tokens": res["usage"]["input_tokens"],
                            }
                        )
                        return
                    if r.status_code not in (429, 500, 502, 503, 504):
                        print(f"  pmid {pmid}: HTTP {r.status_code} {r.text[:200]}")
                        break
                except httpx.HTTPError:
                    pass
                await asyncio.sleep(min(30, 2**attempt))
            failures += 1

    async with httpx.AsyncClient(
        headers={"Authorization": f"Bearer {token}"}, timeout=120
    ) as client:
        chunk = 500  # flush a parquet part per chunk so long runs can resume
        for i in range(0, len(states), chunk):
            done.clear()
            await asyncio.gather(*(one(client, p, s) for p, s in states[i : i + chunk]))
            if done:
                pl.DataFrame(done).write_parquet(
                    out / f"part-{time.strftime('%Y%m%dT%H%M%S')}-{i:06d}.parquet"
                )
            print(
                f"  {min(i + chunk, len(states))}/{len(states)} scored ({failures} failed)",
                flush=True,
            )


def score(
    model: str,
    version: str,
    split: str | None = None,
    limit: int | None = None,
    concurrency: int = 16,
    table: str = "vetted_ml_table",
) -> None:
    """Score unscored papers from the vetted_ml table; resumable."""
    from .vetted_ml import state_text, table_path

    t = pl.read_parquet(table_path(table))
    if split:
        t = t.filter(pl.col("split") == split)
    t = t.sort("pmid")
    if limit:
        # A fixed random sample (by PMID hash order), not the first N PMIDs.
        t = t.with_columns(h=pl.col("pmid").hash(seed=59)).sort("h").head(limit).drop("h")
    have = set(load_cache(model, version)["pmid"])
    todo = [(r["pmid"], state_text(r)) for r in t.iter_rows(named=True) if r["pmid"] not in have]
    print(f"  {model} {version}: {len(todo)} to score ({len(have)} cached)")
    out = cache_dir(model, version)
    out.mkdir(parents=True, exist_ok=True)
    asyncio.run(_score(todo, model, QUESTION_SETS[version], concurrency, out))


def axis_features(pmids: pl.Series, spec: str) -> np.ndarray:
    """Dense feature matrix for ``spec`` (``model:version``), aligned to ``pmids``.

    One column per yes/no probability and per option probability of every
    choice/score question, plus a ``missing`` indicator column (0-filled rows).
    """
    import numpy as np

    model, version = spec.split(":")
    cache = load_cache(model, version)
    qs = QUESTION_SETS[version]
    cols: list[str] = []
    for qid, q in qs.items():
        if q["type"] == "noul":
            cols.append(qid)
        elif q["type"] == "choice":
            cols += [f"{qid}={k}" for k in q["criteria"]]
        else:
            cols += [f"{qid}={i}" for i in range(len(q["criteria"]))]
    lookup = dict(zip(cache["pmid"].to_list(), cache["answers"].to_list(), strict=True))
    x = np.zeros((len(pmids), len(cols) + 1), dtype=np.float64)
    pos = {c: i for i, c in enumerate(cols)}
    for r, pmid in enumerate(pmids.to_list()):
        a = lookup.get(pmid)
        if a is None:
            x[r, -1] = 1.0
            continue
        for qid, ans in json.loads(a).items():
            if ans["type"] == "noul":
                x[r, pos[qid]] = ans["noul"]
            else:
                for k, p in ans["probabilities"].items():
                    c = f"{qid}={k}"
                    if c in pos:
                        x[r, pos[c]] = p
    return x


def main() -> None:
    import argparse

    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--model", default="clef-flash", choices=["clef", "clef-flash"])
    ap.add_argument("--version", default="v1", choices=sorted(QUESTION_SETS))
    ap.add_argument("--split", default=None, choices=["train", "val", "test"])
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--concurrency", type=int, default=16)
    ap.add_argument("--table", default="vetted_ml_table")
    a = ap.parse_args()
    score(a.model, a.version, a.split, a.limit, a.concurrency, a.table)


if __name__ == "__main__":
    main()


def axis_summary(spec: str) -> pl.DataFrame:
    """One readable column per question for ``spec`` (``model:version``), by PMID.

    Yes/no questions give the probability of yes; ``score`` questions the
    probability-weighted level; ``choice`` questions the top option and its
    probability (two columns).
    """
    model, version = spec.split(":")
    rows = []
    for pmid, a in load_cache(model, version).select("pmid", "answers").iter_rows():
        r: dict = {"pmid": pmid}
        for qid, ans in json.loads(a).items():
            if ans["type"] == "noul":
                r[qid] = round(ans["noul"], 3)
            elif ans["type"] == "score":
                r[qid] = round(ans["score"], 2)
            else:
                r[qid] = ans["choice"]
                r[f"{qid}_p"] = round(ans["probabilities"][ans["choice"]], 3)
        rows.append(r)
    return pl.DataFrame(rows, infer_schema_length=None)
