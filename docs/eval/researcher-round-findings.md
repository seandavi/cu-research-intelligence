# Researcher round — findings

First evaluation round focused on the **cancer-center researcher/member** persona
(per direction: focus on members this round; admin/reporting engages later with
Michaela as primary). Driven by the **real questions members ask**, run live
against https://insights.uccc.cancerdatasci.org. Coverage is probed by
`cu_openalex.eval.researcher_questions`; the quality read below is human-judged.

## Strategic framing (from the stakeholder)
Target state: **the app becomes the source of truth, with levers for research
staff to influence reporting**, and likely **per-user views/panes** by role and
priority. This round deliberately guesses *less* about admin/reporting needs
(engage those stakeholders directly) and *more* about the researcher, whose
questions are concrete and in hand.

## The member questions × how the app answers today

| Member question | Capability | Verdict | Notes |
| --- | --- | --- | --- |
| Who works on *pancreatic cancer*? | expertise discovery | **Works (partial)** | 20 members; but relies on abstract text (missing for ~36% of works) → recall-limited |
| How many *cancer* papers does member YYY have? | cancer-relevant count | **Misleading** | Returned "951 cancer papers" for one member — a **conflated author** and it counted *all* pubs, **no cancer-relevance filter** surfaced |
| Does anyone have a *grant about* immunotherapy? | grant topic search | **Works** | Grant-title search returns relevant PIs |
| How to *stimulate more inter-programmatic* research? | collaboration opportunity (advisory) | **Gap (refused)** | NL→SQL chat declines — advisory/recommendation is out of its scope |
| How can I *find collaborators*? | collaborator discovery | **Misleading** | Answered with **institutional** collaborators (CU Health, NJH), not personal/expertise-based |
| Which researchers work on the *KRAS* gene/pathway? | expertise by gene/pathway | **Works** | 100 researchers via title/abstract mentions |
| *Build a team* around a P01 by needed expertise? | team assembly | **Gap (refused)** | Not supported |
| What research areas are we *strongest in*? | research-strength analysis | **Weak** | "Medicine, 32,939 pubs" — broad `topic_field`, raw count, not cancer-specific or **normalized** |

## The pattern
- **Factual lookups work** (who/what/grant/gene) — the NL→SQL chat + topic/abstract
  text is genuinely useful for discovery.
- **The highest-value member questions are gaps or misleading:** personalized
  collaborator discovery, team assembly, inter-programmatic stimulation, and
  meaningful research strengths — exactly the "stimulate collaboration / build teams
  / where are we good" jobs that matter most to members and to the CCSG
  transdisciplinary story.
- **Two data-quality issues surfaced by real use:** (1) **author conflation** leaks
  into answers (951 pubs for one member); (2) **no cancer-relevance filter** on
  "cancer papers" (the classifier exists but isn't wired into counts/chat).

## Researcher-facing capability priorities (this round)

Ranked by member value × feasibility, grounded in the questions above and stage-1/4:

1. **Expertise & collaborator discovery, done right** — a first-class "find an
   expert / find collaborators" surface: search by topic **and gene/pathway**,
   return people (not institutions), ranked by relevant output, with expertise
   concept-clouds (stage-1 profile playbook). Fixes *who_works_on / gene_pathway /
   find_collab*. *(High value, medium cost — data largely present.)*
2. **Cancer-relevance filter wired into counts + chat** — surface
   `is_cancer_relevant` (the deterministic classifier already built) so "cancer
   papers" means cancer papers; and **guard author conflation** more tightly in
   member-facing answers. *(High value, low–medium — classifier exists.)*
3. **Research-strengths analysis (responsible)** — cancer-specific, topic-level,
   **normalized** (FWCI **percentiles / % in top 10%** — data confirmed available
   in the raw layer) with distributions, not raw broad-field counts. This is where
   metrics work (#2) directly serves a member question. *(Medium.)*
4. **Collaboration/team recommender** — link-prediction for new/cross-program ties
   and **expertise-gap → candidate-member** assembly for P01/U teams. Answers the
   two currently-refused questions; the highest-value, most-novel capability, and
   central to the retreat/collaboration-catalysis use case. *(Higher cost — the
   flagship researcher feature.)*
5. **Chat honesty on advisory questions** — when a question is advisory/out-of-scope,
   the chat should **offer the relevant view/tool** ("here's the collaboration
   network / expertise finder") instead of a flat refusal.

## How this feeds the two chosen threads
- **#2 (metrics):** implement **FWCI percentiles / % in top 1%/10%** (raw layer has
  `citation_normalized_percentile`) — serves *research strengths* responsibly; then
  the free **iCite APT / Cited-by-Clinical** (needs a lake-query extension).
- **#4 (harness UI/UX iteration 2):** these member questions become the
  **researcher persona's task scenarios**; the coverage probe is committed
  (repeatable per release), and the next step drives the SPA via Playwright to score
  whether a member can *actually accomplish* each on the interface (not just the chat).

## Open questions for members (the "sort out with user interaction" part)
- For "find collaborators" — collaborators for *me* (personalized) vs. topic-based?
- Which genes/pathways/topics matter most (to prioritize the expertise index)?
- What would make a *strengths* view credible — normalized impact, funding, both?
- Per-user views: what does a member want on landing vs. a program leader?
