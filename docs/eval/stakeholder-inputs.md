# Evaluation — stakeholder inputs (ground truth)

Insights distilled from real correspondence with the UCCC CCSG/reporting team,
the Office of Community Outreach & Engagement (COE), and a Shared Resource
director. **Names, emails, and phone numbers are deliberately omitted** — people
are referred to by role. Raw correspondence is not committed (PII/confidential).
This is the ground truth that anchors the personas (stage 3), requirements
(stage 2), and impact measures (stage 4) so they don't drift into
plausible-but-wrong.

## Who (roles)

- **Research Administrator / Asst. Director, Research Administration** — owns CCSG
  data curation: the authoritative, hand-curated publication/grant portfolio used
  for the renewal. The **primary "administrative/reporter" persona.** Currently
  runs a highly manual process (and was heading toward Power BI).
- **Asst. Director, Community Engaged Research (COE office)** — owns the
  catchment-relevance review process and coordinates the **program research
  liaisons**. The COE persona.
- **Program research liaisons** (per program) — do first-line publication pulls and
  catchment review for their program. A source of process confusion when inputs
  aren't standardized.
- **Data/dev collaborators** (e.g. "Christian", "Sochi") — can extend/iterate the
  platform; one was independently building something similar on OpenAlex.
- **Shared Resource directors** (e.g. Drug Discovery SR / "D3SR") — want to evidence
  the long-term impact of SR services.
- **Center leadership / CCSG leaders / retreat planning committee** — strategic
  planning, collaboration catalysis, the scientific retreat.

## Load-bearing strategic signals

1. **"We must all work from the same curated data sets."** *Verbatim intent:* for
   any metric used in the grant or shown to leaders in a CCSG context, the platform
   must reconcile to the **curated CCSG data set**, not raw OpenAlex. This is the
   single most important requirement to emerge. → The platform needs an explicit
   **dataset-provenance switch**: an *exploratory* mode (OpenAlex, comprehensive)
   vs. an authoritative **CCSG-reportable** mode (the curated set), clearly labelled,
   never silently mixed.
2. **This platform is a candidate to replace a highly manual process — and Power
   BI.** *Intent:* "you just put my team out of business… how do we replace current
   highly manual processes to get to CCSG-reportable metrics?" and "we were headed
   down the PBI route but this seems more nimble/clean — should we shift gears?"
   The administrative/reporter persona's core job: **raw data → CCSG-reportable
   metrics with minimal manual effort.**
3. **The AI cancer-relevance process is theirs, and it's already validated.** A PoC
   (two models vs. human catchment reviews) showed strong agreement, and where they
   disagreed the models were usually right. The classifier (ADR-0024/0027) is an
   **assist to a process the team owns**, validated against their curated review —
   not a replacement. Integrating it "at scale" is explicitly wanted.
4. **Trust and definitions outrank everything** — the entire thread is about making
   sure everyone works from the same curated, correctly-scoped data. This is direct
   confirmation of stage 1's "trust/definitions > aesthetics" finding.

## Concrete requirements this surfaces (high priority)

1. **"Reportable" ≠ our current `is_publication`.** CCSG-reportable is **research
   articles only** — it **excludes reviews, commentaries, opinions, letters,
   guidelines, meeting reports, and preprints.** Our current
   `programs.PUBLICATION_TYPES = {article, review}` **includes reviews** →
   discrepancy. Need a stricter **`is_reportable`** definition distinct from
   `is_publication`, and CCSG views must use it. *(Near-term, concrete code change.)*
2. **Fiscal-year windows, not calendar.** The curation and the renewal run on
   **fiscal years (FY22–FY26; the CU FY ends June 30)**. The provided curated set is
   **FY22–25**; **FY26 curation completes ~8–10 weeks out (~mid-October)**. The
   platform defaults to calendar years — it needs **FY-aware time windows** and must
   not imply FY26 is complete.
3. **Grant portfolio, CCSG-style.** Reliable automated capture of all NIH awards
   where a member is PI is wanted — but with CCSG counting nuances the naive pull
   misses: **sub-awards** (we're a sub) and **prime-with-sub "countable" amounts.**
   Also: apply the **cancer-relevance classifier to grant abstracts** (as for pubs).
4. **Clinical-trial portfolio (DT4).** Not yet in the platform. Wanted: classify
   protocols open to accrual in FY26, then compute **% accruals** (incl. CA-representative
   accrual) once data is locked. A whole new data domain, aligned to CCSG DT4.
5. **Strategic foci linkage.** There's a **Strategic Plan FY26–31** with scientific
   priorities/foci; research (pubs, programs, collaborations) should map to these —
   analogous to catchment priorities. Feeds the retreat's "cross-program initiatives."
6. **Shared-Resource-enabled publication detection.** (Also flagged as a required
   CCSG component we don't touch.) Determine whether an SR contributed to a
   manuscript by comparing SR descriptions (website / RRID) against PubMed/PMC full
   text — an AI matching task. High CCSG value.

## Notable feature request — the SR-impact knowledge graph

A Shared Resource director's "perfect universe": a way to link the **long-term,
cross-dataset impact** of SR services over time — e.g. *an SR screens a compound for
an investigator (2023) → hits → pending patent (2025) → spinoff company.* Known
anecdotally, but no way to build/discover these connections. The ask:

- An **interactive graph** (molecule-like node/edge model): nodes = member / SR /
  compound / publication / patent / grant / company; edges = the connections. Click a
  node → a plain-language summary of the connection.
- **Discoverable via key-term filters** (an investigator name, an SR, a compound).
- **Sustainable without manual logging** — an AI "spider" that crawls the center's
  data *and its stories* (written + spoken) to infer connections, and **proactively,
  low-burden-ly asks members for "the back story"** when they publish or get a grant.

This is a research-impact **provenance knowledge graph** — ambitious, but it unifies
several threads (SR-enabled pubs, patents/translational impact, the membership spine,
and narrative capture). A strong long-horizon vision item; sustainability (auto-inference
+ friendly member solicitation) is the crux, exactly as they noted.

## Other use cases surfaced

- **Scientific retreat / collaboration catalysis** — leadership wants sessions that
  "catalyze new collaborations" aligned to strategic foci, cross-program initiatives,
  and SR strengths. The platform's collaboration network + expertise discovery +
  strategic-foci mapping could **recommend collaboration opportunities and surface
  cross-program gaps** (link-prediction, already in EXTENSIONS.md).
- **COE / community-engaged research** — catchment relevance is COE-driven; the COE
  persona needs catchment-relevant output tied to CA burden and community engagement.

## Tensions / decisions to resolve (raise with the team)

- **Dataset authority:** confirm the curated CCSG set is the system-of-record for
  CCSG views, and design the OpenAlex layer as *discovery/augmentation* that must be
  reconciled before anything is "reportable."
- **`is_reportable` definition:** confirm the exact excluded types (reviews excluded?)
  and whether it differs by context (COE/catchment vs. program productivity).
- **We do not yet have the newer curated FY22–25 set** referenced here (distinct from
  the FY22–24 catchment-review `cc-data` drop). Obtaining it is a prerequisite for
  re-running the cancer-relevance eval on the reportable data and for reconciling
  platform metrics to the grant.

## Near-term actionable asks (from the thread, outside this eval)

- **Re-run the cancer-relevance evaluation on the curated FY22–25 set** (all programs,
  research-articles-only), then review agreement with the team — a scoped, concrete task.
- **Reconcile platform publication/collaboration metrics to the curated set** for any
  CCSG-facing view; label exploratory vs. reportable.
- These are tracked here as inputs; they'll become requirements in stage 2 and
  candidate implementation work after the evaluation.
