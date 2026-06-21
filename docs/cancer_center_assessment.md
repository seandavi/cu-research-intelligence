# Cancer Center subsection — independent assessment & response

Four independent agents evaluated the first build of the cancer-center dashboard
+ chat, each from a distinct stakeholder lens. Scores and the highest-priority
findings are below, followed by what was changed in response (commit `74aac42`).

## Scores (first build)

| Reviewer | Score | One-line verdict |
| --- | --- | --- |
| Cancer-center researcher | 5/10 | Useful backbone; author-attribution trust + missing grants/profiles |
| Center leadership | 6/10 | Right metrics; no export, fragmented program list, diluted denominator |
| NIH EAB evaluator | 4/10 | Honest framing, but a document-type artifact made the headline charts false |
| UX designer | 6.5/10 | Credible bones; misleading hero chart, weak hierarchy, buried caveat |

## The decisive finding

The EAB evaluator traced the 2023 publication "surge" (and a doubled
collaboration rate) to a **March–April 2023 OpenAlex bulk-index event** that
injected ~5,300 misclassified records — AACR supplementary files and figure
supplements tagged `preprint` / `supplementary-materials` (titles like "Figure S3
from…", "Data from…"). These are not publications. The flagship longitudinal
chart was therefore an artifact, not a result, and the headline publication count
was inflated ~21%.

## What changed (addressed)

| Finding (reviewer) | Response |
| --- | --- |
| Document-type artifact → false 2023 spike, +21% count (EAB, UX, Leadership) | `is_publication` filter (`article`/`review`); all headline metrics filter on it. Spike gone; collaboration flat ~10–12%. |
| "Name-exact" matches called *high* confidence despite common-name merges (Researcher, EAB) | Only ORCID = high; name matches cap at medium. Caveat states it. |
| Duplicate roster rows; dirty publication years (Researcher) | Dedupe on `Member_ID`; bound years to 1950–2026. |
| Mean FWCI (3.83) overclaims; impact is right-skewed (EAB) | Report **median (0.95)** beside mean; help text flags skew. |
| No export for CCSG/EAB reporting (Leadership) | CSV download on program summary, collaboration matrix, member directory. |
| Fragmented / legacy program taxonomy (Leadership) | Fold near-duplicate labels; exclude non-programs; small-program threshold slider. |
| "10% historical floor" line steers to a retired target (Leadership) | Removed; stable 0–25% y-axis instead. |
| Home fails the 5-second test; no direction (UX) | "Headline" section with YoY deltas + median FWCI; clearer hierarchy. |
| Emoji in H1 undercuts NIH tone (UX) | Emoji is the tab icon only; plain titles. |
| Caveat buried at page bottom (UX) | Inline provisional-year flags directly above time-series. |
| Network is a poor first impression (UX) | Lead with the bridge-investigator table; add a program color legend. |
| Unreadable FWCI color scale (UX) | Topic bars labeled with FWCI values. |

## Delivered since the assessment

- **iCite RCR** — the most NCI-native impact metric; now the headline figure
  (median ~1.2) and per-program.
- **Inter-institutional collaboration %** — work×institution bridge from
  `authorships_json`; ~85% inter-institutional, ~36% international, top-collaborator
  ranking (other NCI cancer centers). New dashboard/SPA page.
- **Meeting-abstract exclusion** — removed the residual that depressed PMID
  coverage and inflated counts.
- **Member profile pages** and a **co-authorship network** (React + force graph).

## Open / deferred (tracked for next iteration)

- **Entity-resolution precision audit** (EAB): hand-verify a sample of name
  matches and report a measured precision (target ≥95%), rather than asserting it.
- **Collaboration sensitivity band** (EAB): quantify how much incomplete matching
  biases collaboration % (upper bound assuming unmatched co-authors are members).
- **Researcher value gaps**: grants/funding linkage (OpenAlex grants are empty
  upstream — would need NIH RePORTER), biosketch/RPPR export, clinical-trial and
  trainee/mentorship ties.
- **Co-citation / bibliographic-coupling networks** (from the original ask —
  needs `referenced_works` curated from raw).
- **Program taxonomy**: confirm the `Molecular Oncology → Molecular & Cellular
  Oncology` fold and the current program list against the center's official roster.
- **Fractional / position-aware authorship** to temper honorary-authorship
  inflation of collaboration ties.
