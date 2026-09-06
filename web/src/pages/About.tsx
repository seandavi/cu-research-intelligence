import { Card } from "../components/ui";
import { useMeta } from "../hooks/useApi";

// What the numbers on this site are made of: sources, processing, rules, and the
// system that serves them. Prose mirrors the ADRs in docs/adr/ — keep them in sync.
const FRESHNESS: [string, string][] = [
  ["openalex_works_watermark", "OpenAlex works snapshot"],
  ["openalex_authors_snapshot", "OpenAlex author roster pull"],
  ["icite_version", "NIH iCite release"],
  ["reporter_version", "NIH RePORTER load"],
  ["roster_snapshot", "Member roster"],
  ["built_at", "Serving database built"],
];

export function About() {
  const meta = useMeta();
  const fresh = meta.data?.data_freshness ?? {};
  return (
    <>
      <h1>About this site</h1>
      <p className="lede">
        Research intelligence for the University of Colorado Cancer Center: who publishes what,
        with whom, across programs and strategic foci — built from public bibliographic data
        joined to the Center's membership roster. Every number here is reproducible from the
        sources and rules described below.
      </p>

      <Card title="Data as of">
        <table className="data compact">
          <tbody>
            {FRESHNESS.filter(([k]) => fresh[k]).map(([k, label]) => (
              <tr key={k}>
                <td>{label}</td>
                <td className="num">{fresh[k].replace("T", " ").slice(0, 16)}</td>
              </tr>
            ))}
          </tbody>
        </table>
        <p className="muted">
          Data refreshes automatically on the 5th of each month, a few days after OpenAlex
          publishes its snapshot. The refresh streams the new snapshot partitions, rebuilds the
          curated tables, and redeploys the site; a failed refresh leaves the previous data in
          place and alerts the maintainers.
        </p>
      </Card>

      <Card title="Data sources">
        <ul className="prose">
          <li>
            <strong>OpenAlex</strong> (CC0) — authors affiliated with CU Anschutz from the REST API,
            filtered to a rolling window of affiliation years; their works from the public S3
            snapshot (title, abstract, authorship, venue, DOI/PMID, open-access status, topics,
            citation counts, field-weighted citation impact). Reference dimensions (institutions,
            sources, funders, topics) come from the same snapshot.
          </li>
          <li>
            <strong>NIH iCite</strong> — Relative Citation Ratio (RCR) and NIH percentile per PMID,
            plus the DOI→PMID crosswalk used to backfill missing PMIDs. Read from the shared
            <em> cdsci-lake</em> store, which loads the monthly iCite release once for all projects.
          </li>
          <li>
            <strong>NIH RePORTER</strong> — funded projects matched to members by PI name, also
            read from cdsci-lake. Drives the NIH Funding page.
          </li>
          <li>
            <strong>Membership roster</strong> — the Center's member list with programs, ranks,
            appointments, and membership dates (the membership spine), resolved to OpenAlex
            authors by ORCID where available, otherwise by name with a recorded confidence tier.
          </li>
          <li>
            <strong>Strategic Plan foci</strong> — the five FY26–31 foci and the retreat's
            clinical-trial themes, as keyword vocabularies matched against titles and abstracts.
          </li>
        </ul>
      </Card>

      <Card title="Processing">
        <pre className="diagram">{`OpenAlex API ──▶ author roster (year window) ─┐
OpenAlex S3 snapshot ──▶ raw works (verbatim JSON, per partition) ──▶ curated works (deduped, typed)
                                                                             │
membership roster ──▶ member ↔ author resolution ──▶ cohort marts: members, works, member×work
cdsci-lake (iCite, RePORTER) ──▶ RCR / PMID backfill, grants ────────────────┤
                                                                             ▼
cancer-relevance labels ─▶ strategic-focus tags ─▶ serving.duckdb (one read-only file, baked into the API image)`}</pre>
        <ol className="prose">
          <li>
            <strong>Capture, then curate.</strong> Snapshot records are stored verbatim first
            (the raw layer), and curated tables are derived from them, so a parsing fix is an
            offline re-run rather than a re-download. A watermark on the snapshot's partition
            dates makes monthly refreshes incremental; the latest capture of each work wins.
          </li>
          <li>
            <strong>Cohort attribution.</strong> A work belongs to the Center when at least one
            resolved member is an author. It is attributed to every program those members
            belong to, and classified as intra-programmatic (two or more members of one
            program) or inter-programmatic (members of two or more programs), the metrics an
            NCI Cancer Center Support Grant review examines.
          </li>
          <li>
            <strong>Cancer relevance.</strong> A deterministic labeler marks each publication
            cancer-relevant or not, over the full CU corpus; the Strategic Foci page counts only
            cancer-relevant work.
          </li>
          <li>
            <strong>Strategic foci.</strong> Each work is tagged with every focus whose terms
            appear in its title or abstract; the tags are stored once so every page reports the
            same answer. Clinical-trial reports must name a phase or design or cite an NCT id,
            and reviews are excluded.
          </li>
          <li>
            <strong>Serving.</strong> The curated marts, the focus tags, and a full-text index are
            baked into a single DuckDB file that the API reads in-process. No database server
            runs at request time, and each deployed image is a pinned, reproducible snapshot.
          </li>
        </ol>
      </Card>

      <Card title="Reading the numbers">
        <ul className="prose">
          <li>
            <strong>Peer-reviewed only.</strong> Counts are articles and reviews; preprints,
            datasets, supplementary files, and meeting abstracts are excluded.
          </li>
          <li>
            <strong>Lower bounds.</strong> Not every member resolves to an OpenAlex author, and
            keyword-matched foci miss work that uses other vocabulary. Ratios (collaboration %,
            RCR, top-decile share) are more robust than absolute counts.
          </li>
          <li>
            <strong>Two attribution rules.</strong> The Overview counts a member's papers in the
            window regardless of when they joined; the Strategic Foci page counts a paper only if
            the author was a member when it was published. A decision record proposes aligning
            them.
          </li>
          <li>
            <strong>Indexing lag.</strong> The most recent year or two are provisional: OpenAlex
            and iCite keep adding records and citations after publication.
          </li>
          <li>
            <strong>Name-based matches</strong> (no ORCID) are flagged with a "?" where they
            appear; their paper lists may include a namesake's work.
          </li>
        </ul>
      </Card>

      <Card title="Architecture">
        <pre className="diagram">{`browser ──HTTPS──▶ Traefik ──▶ nginx (React SPA) ──/api──▶ FastAPI + DuckDB (serving.duckdb, read-only)
                                                            ├──▶ Postgres overlay (sign-in, editable profiles)   [optional app tier]
                                                            └──▶ Gemini (Ask: natural language → guarded read-only SQL)

monthly timer ──▶ refresh job: OpenAlex pipeline → cdsci-lake reads → marts → bake → rebuild + redeploy the API image
                  (failure → alert to the shared ops channel; the live site keeps the previous data)`}</pre>
        <ul className="prose">
          <li>
            <strong>Pipeline</strong> — Python; Polars for author transforms, DuckDB for streaming
            the snapshot, incremental state, and the marts; Prefect flows for retries.
          </li>
          <li>
            <strong>API</strong> — FastAPI over one read-only DuckDB file with a materialized
            full-text index. The container is fully offline: no data mounts, no lake access.
          </li>
          <li>
            <strong>Frontend</strong> — Vite + React + TypeScript, served by nginx, which also
            proxies the API so the site is one origin behind the Center's Traefik.
          </li>
          <li>
            <strong>Shared data substrate</strong> — cdsci-lake, a DuckLake catalog on Postgres with
            data on object storage, holds institution-neutral sources (iCite, RePORTER, OpenAlex)
            once for every project; this site reads its cohort slice at build time.
          </li>
          <li>
            <strong>Operations</strong> — a systemd timer runs the refresh on the host; failures
            post to the shared ops notification topic; the freshness stamps above are written at
            bake time and served by the API.
          </li>
        </ul>
        <p className="muted">
          Design decisions are recorded as architecture decision records (ADRs) in the source
          repository, from orchestration and storage through cohort attribution, the cancer-relevance
          spine, the membership spine, and the application tier.
        </p>
      </Card>
    </>
  );
}
