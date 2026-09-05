import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import type { PublicationFilters, YearRange } from "../api/types";
import { Heatmap } from "../components/Heatmap";
import { NetworkGraph } from "../components/NetworkGraph";
import { UpsetPlot } from "../components/UpsetPlot";
import { Card, Caveat, ErrorNote, KpiCard, Loading } from "../components/ui";
import {
  useCollaborationMatrix,
  useFoci,
  useFociCombinations,
  useMembers,
  useMeta,
  useNetwork,
  useProgramSummary,
  usePublications,
} from "../hooks/useApi";
import { fmtInt, fmtNum, fmtPct, programColors, shorten } from "../lib/format";
import { PublicationRowView } from "./Publications";

const PAGE_SIZE = 25;

// Strategic foci (issue #38): the Program Collaboration page, scoped to one
// keyword-matched focus from the FY26–31 Strategic Plan (or a retreat theme).
export function Foci({ range }: { range: YearRange }) {
  const meta = useMeta();
  const foci = useFoci(range);
  const combos = useFociCombinations(range);
  const [focus, setFocus] = useState<string>("");

  const rows = foci.data ?? [];
  const plan = rows.filter((f) => f.group.startsWith("Strategic Plan"));
  const trial = rows.filter((f) => !f.group.startsWith("Strategic Plan"));
  const selected = rows.find((f) => f.name === focus) ?? plan[0];
  const name = selected?.name;

  const matrix = useCollaborationMatrix(range, true, name);
  const summary = useProgramSummary(range, true, name);
  const net = useNetwork(range, 2, undefined, name);
  const authors = useMembers(range, name);

  const [text, setText] = useState("");
  const [filters, setFilters] = useState<PublicationFilters>({ sort: "citations", page: 1 });
  useEffect(() => {
    const t = setTimeout(() => setFilters((f) => ({ ...f, q: text || undefined, page: 1 })), 350);
    return () => clearTimeout(t);
  }, [text]);
  useEffect(() => setFilters((f) => ({ ...f, page: 1 })), [name]);
  const pubs = usePublications({
    ...filters,
    focus: name,
    minYear: range.minYear,
    maxYear: range.maxYear,
    descending: true,
    page_size: PAGE_SIZE,
  });

  const colors = useMemo(() => {
    const all = new Set<string>(meta.data?.current_programs ?? []);
    net.data?.nodes.forEach((n) => all.add(n.program));
    return programColors([...all]);
  }, [net.data, meta.data]);

  if (foci.isLoading) return <Loading />;
  if (foci.error) return <ErrorNote error={foci.error} />;

  const programs = meta.data?.current_programs ?? [];
  const page = filters.page ?? 1;
  const total = pubs.data?.total ?? 0;
  const pages = Math.max(1, Math.ceil(total / PAGE_SIZE));

  return (
    <>
      <h1>Strategic Foci</h1>
      <p className="lede">
        The Center's FY26–31 Strategic Plan foci mapped onto members' cancer-relevant
        publications — output, program mix, and who is doing the work in each focus.
      </p>
      <p className="hint">
        Foci are keyword-matched on title and abstract; counts are recall-limited and overlaps
        partly reflect shared vocabulary.
      </p>

      <Card title="Papers in more than one focus (UpSet)">
        <p className="hint">
          Publications by the exact set of Strategic Plan foci they match. Multi-focus bars are
          where the foci meet on the same paper.
        </p>
        {combos.data && <UpsetPlot combos={combos.data} />}
      </Card>

      <div className="chips">
        <span className="chips-label">Strategic Plan foci:</span>
        {plan.map((f) => (
          <button key={f.name} className={`chip ${f.name === name ? "on" : ""}`} onClick={() => setFocus(f.name)}>
            {f.name}
          </button>
        ))}
      </div>
      <div className="chips">
        <span className="chips-label">Clinical-trial themes:</span>
        {trial.map((f) => (
          <button key={f.name} className={`chip ${f.name === name ? "on" : ""}`} onClick={() => setFocus(f.name)}>
            {f.name}
          </button>
        ))}
      </div>

      {selected && (
        <>
          <h3 className="section">{selected.name}</h3>
          <div className="kpi-row">
            <KpiCard label="Publications" value={fmtInt(selected.publications)} hint="Cancer-relevant, peer-reviewed, in window" />
            <KpiCard label="Inter-programmatic" value={fmtPct(selected.inter_program_pct)} hint="Members from ≥2 programs" />
            <KpiCard label="Median RCR" value={fmtNum(selected.median_rcr)} hint="NIH iCite Relative Citation Ratio (1.0 = median NIH paper)" />
            <KpiCard label="Top 10% cited" value={fmtPct(selected.pct_top_10)} hint="Share in the top 10% of OpenAlex citation percentile for year and field" />
          </div>

          <Card title="Program × program co-authorship in this focus">
            <p className="hint">
              Cell = publications co-authored by both programs. Diagonal = intra-programmatic (≥2
              members of that program).
            </p>
            {matrix.data && <Heatmap cells={matrix.data} programs={programs} />}
            {summary.data && (
              <table className="data compact">
                <thead>
                  <tr>
                    <th>Program</th>
                    <th className="num">Publications</th>
                    <th className="num">Median RCR</th>
                    <th className="num">Inter %</th>
                  </tr>
                </thead>
                <tbody>
                  {summary.data.map((r) => (
                    <tr key={r.program}>
                      <td>{r.program}</td>
                      <td className="num">{fmtInt(r.publications)}</td>
                      <td className="num">{fmtNum(r.median_rcr)}</td>
                      <td className="num">{fmtNum(r.pct_inter_program, 1)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </Card>

          <div className="grid-2">
            <Card title="Top authors">
              <table className="data compact">
                <thead>
                  <tr>
                    <th>Member</th>
                    <th>Program</th>
                    <th className="num">Publications</th>
                  </tr>
                </thead>
                <tbody>
                  {(authors.data ?? []).slice(0, 15).map((m) => (
                    <tr key={m.member_id}>
                      <td>
                        <Link to={`/members/${m.member_id}`}>{m.name}</Link>
                      </td>
                      <td>{shorten(m.program, 26)}</td>
                      <td className="num">{fmtInt(m.publications)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </Card>
            <Card title="Co-author network (≥2 shared papers in this focus)">
              {net.isLoading && <Loading />}
              {net.data && (
                <>
                  <div className="legend">
                    {[...new Set(net.data.nodes.map((n) => n.program))].sort().map((p) => (
                      <span key={p} className="legend-item">
                        <span className="swatch" style={{ background: colors[p] }} />
                        {shorten(p, 22)}
                      </span>
                    ))}
                  </div>
                  <NetworkGraph data={net.data} colors={colors} height={420} />
                </>
              )}
            </Card>
          </div>

          <Card
            title="Publications"
            action={
              <span className="muted">
                {fmtInt(total)} publications{pubs.isFetching ? " · updating…" : ""}
              </span>
            }
          >
            <div className="filters">
              <input placeholder="Search title & abstract…" value={text} onChange={(e) => setText(e.target.value)} style={{ minWidth: 240 }} />
              <select value={filters.sort} onChange={(e) => setFilters((f) => ({ ...f, sort: e.target.value, page: 1 }))}>
                <option value="citations">Sort: Citations</option>
                <option value="rcr">Sort: RCR</option>
                <option value="fwci">Sort: FWCI</option>
                <option value="year">Sort: Year</option>
                <option value="title">Sort: Title</option>
                {text && <option value="relevance">Sort: Relevance</option>}
              </select>
            </div>
            {pubs.error && <ErrorNote error={pubs.error} />}
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
                {(pubs.data?.rows ?? []).map((r) => (
                  <PublicationRowView key={r.work_id} r={r} />
                ))}
              </tbody>
            </table>
            <div className="pager">
              <button disabled={page <= 1} onClick={() => setFilters((f) => ({ ...f, page: page - 1 }))}>
                ← Prev
              </button>
              <span className="muted">
                Page {page} of {fmtInt(pages)}
              </span>
              <button disabled={page >= pages} onClick={() => setFilters((f) => ({ ...f, page: page + 1 }))}>
                Next →
              </button>
            </div>
          </Card>
        </>
      )}

      <Caveat />
    </>
  );
}
