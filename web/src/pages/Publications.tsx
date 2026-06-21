import { useEffect, useMemo, useState } from "react";
import type { PublicationFilters, PublicationRow, YearRange } from "../api/types";
import { Card, Caveat, ErrorNote } from "../components/ui";
import { useMeta, usePublications } from "../hooks/useApi";
import { downloadCsv, fmtInt, fmtNum, shorten } from "../lib/format";

const PAGE_SIZE = 50;

export function Publications({ range }: { range: YearRange }) {
  const meta = useMeta();
  // Committed filters (sent to the API).
  const [filters, setFilters] = useState<PublicationFilters>({
    sort: "relevance",
    descending: true,
    page: 1,
    page_size: PAGE_SIZE,
  });
  // Debounced free-text inputs.
  const [text, setText] = useState({ q: "", author: "", journal: "" });
  useEffect(() => {
    const t = setTimeout(
      () =>
        setFilters((f) => ({
          ...f,
          q: text.q || undefined,
          author: text.author || undefined,
          journal: text.journal || undefined,
          page: 1,
        })),
      350,
    );
    return () => clearTimeout(t);
  }, [text]);

  const effective: PublicationFilters = {
    ...filters,
    minYear: range.minYear,
    maxYear: range.maxYear,
  };
  const results = usePublications(effective);

  const patch = (p: Partial<PublicationFilters>) =>
    setFilters((f) => ({ ...f, ...p, page: p.page ?? 1 }));
  const toggleProgram = (program: string) =>
    setFilters((f) => {
      const cur = new Set(f.programs ?? []);
      cur.has(program) ? cur.delete(program) : cur.add(program);
      return { ...f, programs: cur.size ? [...cur] : undefined, page: 1 };
    });

  const total = results.data?.total ?? 0;
  const pages = Math.max(1, Math.ceil(total / PAGE_SIZE));
  const page = filters.page ?? 1;
  const rows = results.data?.rows ?? [];
  const selected = useMemo(() => new Set(filters.programs ?? []), [filters.programs]);

  return (
    <>
      <h1>Publications</h1>
      <p className="lede">
        Full-text search (title &amp; abstract, BM25-ranked) and filter the cancer-center
        publication corpus. Peer-reviewed articles &amp; reviews only; counts respect the year
        range (top-right).
      </p>

      <Card>
        <div className="filters">
          <input
            placeholder="Search title & abstract…"
            value={text.q}
            onChange={(e) => setText({ ...text, q: e.target.value })}
            style={{ minWidth: 240 }}
          />
          <input
            placeholder="Author name…"
            value={text.author}
            onChange={(e) => setText({ ...text, author: e.target.value })}
          />
          <input
            placeholder="Journal…"
            value={text.journal}
            onChange={(e) => setText({ ...text, journal: e.target.value })}
          />
          <select
            value={filters.collaboration_class ?? ""}
            onChange={(e) => patch({ collaboration_class: e.target.value || undefined })}
          >
            <option value="">Any collaboration</option>
            <option value="solo">Solo</option>
            <option value="intra_program">Intra-programmatic</option>
            <option value="inter_program">Inter-programmatic</option>
          </select>
          <select
            value={filters.sort}
            onChange={(e) => patch({ sort: e.target.value })}
          >
            <option value="relevance">Sort: Relevance</option>
            <option value="citations">Sort: Citations</option>
            <option value="rcr">Sort: RCR</option>
            <option value="fwci">Sort: FWCI</option>
            <option value="year">Sort: Year</option>
            <option value="title">Sort: Title</option>
          </select>
          <label className="chk">
            <input
              type="checkbox"
              checked={!!filters.is_oa}
              onChange={(e) => patch({ is_oa: e.target.checked || undefined })}
            />
            Open access
          </label>
          <label className="chk">
            <input
              type="checkbox"
              checked={!!filters.inter_institutional}
              onChange={(e) => patch({ inter_institutional: e.target.checked || undefined })}
            />
            Inter-institutional
          </label>
        </div>

        <div className="chips">
          <span className="chips-label">Programs:</span>
          {(meta.data?.all_programs ?? []).map((p) => (
            <button
              key={p}
              className={`chip ${selected.has(p) ? "on" : ""}`}
              onClick={() => toggleProgram(p)}
            >
              {shorten(p, 28)}
            </button>
          ))}
        </div>
      </Card>

      {results.error && <ErrorNote error={results.error} />}

      <div className="results-head">
        <span className="muted">
          {fmtInt(total)} publications{results.isFetching ? " · updating…" : ""}
        </span>
        <button onClick={() => downloadCsv(rows, "uccc_publications.csv")} disabled={!rows.length}>
          ⬇ CSV (page)
        </button>
      </div>

      <Card>
        <table className="data">
          <thead>
            <tr>
              <th>Title</th>
              <th>Year</th>
              <th>Journal</th>
              <th>Programs</th>
              <th className="num">Cites</th>
              <th className="num">RCR</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => (
              <Row key={r.work_id} r={r} />
            ))}
            {!rows.length && !results.isFetching && (
              <tr>
                <td colSpan={6} className="muted">
                  No publications match these filters.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </Card>

      <div className="pager">
        <button disabled={page <= 1} onClick={() => patch({ page: page - 1 })}>
          ← Prev
        </button>
        <span className="muted">
          Page {page} of {fmtInt(pages)}
        </span>
        <button disabled={page >= pages} onClick={() => patch({ page: page + 1 })}>
          Next →
        </button>
      </div>

      <Caveat />
    </>
  );
}

function Row({ r }: { r: PublicationRow }) {
  const link = r.doi
    ? r.doi.startsWith("http")
      ? r.doi
      : `https://doi.org/${r.doi}`
    : r.pmid
      ? `https://pubmed.ncbi.nlm.nih.gov/${r.pmid}/`
      : null;
  return (
    <tr>
      <td>
        {link ? (
          <a href={link} target="_blank" rel="noreferrer">
            {r.title ?? "(untitled)"}
          </a>
        ) : (
          (r.title ?? "(untitled)")
        )}
        {r.is_oa && <span className="badge high oa">OA</span>}
        {r.has_external_collab && <span className="tag" title="Inter-institutional">↔</span>}
        {r.snippet && <div className="snippet">{r.snippet}…</div>}
      </td>
      <td>{r.publication_year}</td>
      <td>{shorten(r.source_name ?? "—", 28)}</td>
      <td>
        {(r.programs ?? []).filter(Boolean).map((p) => (
          <span key={p} className="pchip" title={p}>
            {abbrev(p)}
          </span>
        ))}
      </td>
      <td className="num">{fmtInt(r.cited_by_count)}</td>
      <td className="num">{fmtNum(r.rcr)}</td>
    </tr>
  );
}

// Compact program initials for the table chips.
function abbrev(p: string): string {
  return p
    .replace(/&/g, "")
    .split(/\s+/)
    .filter(Boolean)
    .map((w) => w[0])
    .join("")
    .toUpperCase()
    .slice(0, 4);
}
