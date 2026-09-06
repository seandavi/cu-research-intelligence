import { Fragment, useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import type { PublicationFilters, RetreatTheme, RetreatWork, YearRange } from "../api/types";
import { Heatmap } from "../components/Heatmap";
import { NetworkGraph } from "../components/NetworkGraph";
import { UpsetPlot } from "../components/UpsetPlot";
import { Card, ErrorNote, KpiCard, Loading } from "../components/ui";
import {
  useCollaborationMatrix,
  useFociCombinations,
  useMe,
  useMeta,
  useNetwork,
  useProgramSummary,
  usePublications,
  useRetreatPeople,
  useRetreatThemeWorks,
  useRetreatThemes,
} from "../hooks/useApi";
import { downloadCsv, fmtInt, fmtNum, fmtPct, initials, programColors, shortFocus, shorten } from "../lib/format";
import { PublicationRowView } from "./Publications";

const PAGE_SIZE = 25;
const EC = <span className="badge ec" title="Assistant professor / instructor, or joined 2020 or later">early-career</span>;

// Strategic foci (issues #38, #41): the FY26–31 Strategic Plan foci and the retreat's
// clinical-trial themes over members' cancer-relevant publications — one place for foci.
export function Foci({ range }: { range: YearRange }) {
  const meta = useMeta();
  const me = useMe();
  const report = useRetreatThemes(range);
  const combos = useFociCombinations(range);
  const myMemberId = me.data?.member_id ?? null;
  const [sel, setSel] = useState(0);
  const [showHow, setShowHow] = useState(false);
  const [member, setMember] = useState<number | undefined>();
  const [showMine, setShowMine] = useState(false);

  const themes = report.data?.themes ?? [];
  const cur = themes[sel];
  const name = cur?.name;
  const matrix = useCollaborationMatrix(range, true, name);
  const summary = useProgramSummary(range, true, name);
  const net = useNetwork(range, 2, undefined, name);
  const works = useRetreatThemeWorks(sel, member, range);
  const mine = useRetreatThemeWorks(sel, myMemberId ?? undefined, range);
  const people = useRetreatPeople(sel, myMemberId, range);

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

  if (report.isLoading) return <Loading />;
  if (report.error) return <ErrorNote error={report.error} />;

  const { denominator: d, window } = report.data!;
  const programs = [...(meta.data?.current_programs ?? [])].sort();
  const page = filters.page ?? 1;
  const total = pubs.data?.total ?? 0;
  const pages = Math.max(1, Math.ceil(total / PAGE_SIZE));
  const shown = cur?.top_members.find((m) => m.member_id === member);
  const noList = !cur || cur.top_members.length === 0 || cur.top_members[0].publications < 2;

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
        {combos.data && (
          <UpsetPlot combos={combos.data.map((c) => ({ ...c, programs: c.programs.map(shortFocus) }))} />
        )}
      </Card>

      <Card
        title={`Foci across member publications (${window.min_year}–${window.max_year})`}
        action={
          <span>
            <button onClick={() => setShowHow((v) => !v)}>{showHow ? "Hide" : "Show"} how counted</button>{" "}
            <button onClick={() => downloadCsv(themeCsv(themes, programs), "uccc_foci.csv")}>⬇ CSV</button>
          </span>
        }
      >
        <table className="data compact">
          <thead>
            <tr>
              <th>Focus</th>
              <th className="num">Publications</th>
              <th className="num" title="Share of the focus's publications with members from ≥2 programs">
                Inter-program
              </th>
              <th className="num" title="Active members with ≥1 publication in the focus">Members</th>
              {programs.map((p) => (
                <th key={p} className="num" title={p}>
                  {initials(p)}
                </th>
              ))}
              <th title="Publications per year across the window">Trend</th>
              <th className="num" title="NIH iCite Relative Citation Ratio (1.0 = median NIH paper)">Median RCR</th>
              <th className="num" title="Share of iCite-scored papers at NIH percentile ≥ 90">Top 10%</th>
            </tr>
          </thead>
          <tbody>
            {themes.map((th, i) => (
              <Fragment key={th.name}>
                {(i === 0 || themes[i - 1].group !== th.group) && (
                  <tr>
                    <td colSpan={8 + programs.length} className="muted group">{th.group}</td>
                  </tr>
                )}
                <tr className={`clickable ${i === sel ? "sel" : ""} ${th.footnote ? "muted" : ""}`} onClick={() => setSel(i)}>
                  <td>
                    {th.name}
                    {th.footnote && <span className="termlist"> (topic signal only)</span>}
                    {showHow && (
                      <div className="termlist">
                        {th.terms.length ? th.terms.join(" · ") + (th.how.startsWith("any term") ? "" : ` — ${th.how}`) : th.how}
                      </div>
                    )}
                  </td>
                  <td className="num">
                    {fmtInt(th.publications)}
                    <div className="termlist" title="Keyword hits before the cancer-relevance filter · counted works with a current member author">
                      of {fmtInt(th.keyword_hits)} hits · {fmtInt(th.active_publications)} current
                    </div>
                  </td>
                  <td className="num">{fmtPct(th.inter_program_pct)}</td>
                  <td className="num">{fmtInt(th.members)}</td>
                  {programs.map((p) => (
                    <td key={p} className="num">
                      {fmtInt(th.by_program.find((b) => b.program === p)?.publications ?? 0)}
                    </td>
                  ))}
                  <td>
                    <Spark data={th.by_year} />
                  </td>
                  <td className="num">{fmtNum(th.median_rcr)}</td>
                  <td className="num">{fmtPct(th.pct_top_10)}</td>
                </tr>
              </Fragment>
            ))}
          </tbody>
        </table>
        <p className="caveat">
          <strong>How to read this.</strong> A publication counts toward a focus when its title or
          abstract contains one of its terms (word-start match); a <em>clinical trial report</em>{" "}
          must name a trial phase or design in its title or cite an NCT id, and reviews are
          excluded. These are provisional keyword sets, not a classification of the science.{" "}
          {d.cancer_filter
            ? "Only publications the deterministic cancer-relevance labeler (ADR-0027) marks cancer-relevant are counted — a high-precision, lower-bound set. "
            : "The cancer-relevance labeler is not baked into this deployment; all member publications are counted. "}
          A member's paper counts only if they were a Center member when it was published, so a
          recruit's earlier work elsewhere is not Center output (stricter than the Overview's
          attribution; ADR-0028 proposes aligning them). <em>Hits</em> is the keyword match
          before the cancer filter; retention differs by focus (lowest for basic-science
          vocabulary), so compare rows with that in mind. <em>Current</em> counts works with at
          least one currently active member author. Meeting abstracts are excluded.
          Program columns count a publication under every current program with a member author,
          so they can add to more than the total; legacy programs are omitted. <em>Members</em> are
          active members only; {fmtInt(d.active_members - d.active_members_resolved)} of{" "}
          {fmtInt(d.active_members)} active members are not yet matched to OpenAlex and cannot
          appear. Recent years are provisional (indexing lag). Click a focus for members, topics,
          and the papers behind each count.
        </p>
      </Card>

      {cur && (
        <>
          <div className="tabs" role="tablist" aria-label="Strategic Plan focus">
            {themes.map((t, i) =>
              t.group.startsWith("Strategic Plan") ? (
                <button key={t.name} role="tab" aria-selected={i === sel} className={`tab ${i === sel ? "on" : ""}`} onClick={() => setSel(i)}>
                  {shortFocus(t.name)}
                </button>
              ) : null,
            )}
          </div>
          <div className="tabs sub" role="tablist" aria-label="Clinical-trial theme">
            <span className="chips-label">Clinical-trial themes:</span>
            {themes.map((t, i) =>
              t.group.startsWith("Strategic Plan") ? null : (
                <button key={t.name} role="tab" aria-selected={i === sel} className={`tab ${i === sel ? "on" : ""}`} onClick={() => setSel(i)}>
                  {shortFocus(t.name)}
                </button>
              ),
            )}
          </div>
          <h3 className="section">{cur.name}</h3>
          <div className="kpi-row">
            <KpiCard label="Publications" value={fmtInt(cur.publications)} hint="Cancer-relevant, peer-reviewed, in window" />
            <KpiCard label="Inter-programmatic" value={fmtPct(cur.inter_program_pct)} hint="Members from ≥2 programs" />
            <KpiCard label="Median RCR" value={fmtNum(cur.median_rcr)} hint="NIH iCite Relative Citation Ratio (1.0 = median NIH paper)" />
            <KpiCard label="Top 10% cited" value={fmtPct(cur.pct_top_10)} hint="Share of iCite-scored papers at NIH percentile ≥ 90" />
          </div>

          {myMemberId != null && (
            <Card title={`You in this focus — ${cur.name}`}>
              {mine.isLoading ? <Loading /> : (
                <p className="muted">
                  {(mine.data ?? []).length === 0
                    ? "None of your counted papers matches this focus's terms in the selected years."
                    : <>{(mine.data ?? []).length} of your papers match. <a href="#" onClick={(e) => { e.preventDefault(); setShowMine((v) => !v); }}>{showMine ? "Hide" : "Show"}</a></>}
                </p>
              )}
              {showMine && <WorkList works={mine.data ?? []} />}
            </Card>
          )}

          <div className="grid3">
            <Card title="Current members with the most matching papers">
              {noList && <p className="muted">Too few matching papers per member to rank anyone; use the focus's paper list instead.</p>}
              <table className="data compact" hidden={noList}>
                <tbody>
                  {cur.top_members.map((m) => (
                    <tr key={m.member_id} className={`clickable ${m.member_id === member ? "sel" : ""}`} onClick={() => setMember(m.member_id === member ? undefined : m.member_id)}>
                      <td>
                        <Link to={`/members/${m.member_id}`} onClick={(e) => e.stopPropagation()}>{m.name}</Link>
                        {m.match_confidence !== "high" && (
                          <span className="badge medium" title="Name-based OpenAlex match (no ORCID); papers may include a namesake's">?</span>
                        )}
                        {m.early_career && EC}
                        <div className="termlist">
                          {m.rank ?? ""}{m.joined_year ? ` · member since ${m.joined_year}` : ""}
                          {m.joined_year && m.joined_year > window.min_year ? " (joined inside the window)" : ""}
                        </div>
                      </td>
                      <td className="muted">{initials(m.program)}</td>
                      <td className="num">{fmtInt(m.publications)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
              <p className="muted">Click a name to see the papers behind the count. ? = name-based match without ORCID.</p>
            </Card>
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
            <Card title="OpenAlex topics in this focus">
              <table className="data compact">
                <tbody>
                  {cur.top_topics.map((x) => (
                    <tr key={x.topic}>
                      <td>
                        {x.topic_id ? (
                          <a href={`https://openalex.org/${x.topic_id}`} target="_blank" rel="noreferrer" title="Open this topic on OpenAlex">
                            {x.topic}
                          </a>
                        ) : (
                          x.topic
                        )}
                      </td>
                      <td className="num">{fmtInt(x.publications)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </Card>
          </div>

          {shown && (
            <Card title={`${shown.name}: ${cur.name} publications (${range.minYear}–${range.maxYear})`}>
              {works.isLoading ? <Loading /> : <WorkList works={works.data ?? []} />}
            </Card>
          )}

          {myMemberId != null && (
            <Card title={`People to meet in this focus — ${cur.name}`}>
              {people.isLoading ? <Loading /> : (people.data ?? []).length === 0 ? (
                <p className="muted">No one outside your program and your existing collaborators publishes in this focus.</p>
              ) : (
                <table className="data compact">
                  <tbody>
                    {(people.data ?? []).map((p) => (
                      <tr key={p.member_id}>
                        <td>
                          <Link to={`/members/${p.member_id}`}>{p.name}</Link>
                          {p.early_career && EC}
                        </td>
                        <td className="muted">{initials(p.program)}</td>
                        <td className="muted">{p.top_topic ?? ""}</td>
                        <td className="num">{fmtInt(p.publications)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
              <p className="muted">Active members in other programs you have not co-authored or co-held a grant with, with at least two matching papers and their most frequent topic in the focus.</p>
            </Card>
          )}

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
    </>
  );
}

function Spark({ data }: { data: { year: number; publications: number }[] }) {
  const max = Math.max(1, ...data.map((d) => d.publications));
  return (
    <span className="spark" title={data.map((d) => `${d.year}: ${d.publications}`).join(", ")}>
      {data.map((d) => (
        <i key={d.year} style={{ height: `${Math.max(2, (18 * d.publications) / max)}px` }} />
      ))}
    </span>
  );
}

function WorkList({ works }: { works: RetreatWork[] }) {
  return (
    <ol className="worklist">
      {works.map((w) => (
        <li key={w.work_id}>
          {w.doi ? <a href={`https://doi.org/${w.doi}`} target="_blank" rel="noreferrer">{w.title}</a> : w.title}{" "}
          <span className="muted">
            {w.source_name ?? ""} {w.publication_year}
            {w.rcr != null ? ` · RCR ${fmtNum(w.rcr, 1)}` : ""}
            {w.programs.length > 1 ? ` · ${w.programs.map(initials).join(" + ")}` : ""}
          </span>
        </li>
      ))}
    </ol>
  );
}

function themeCsv(t: RetreatTheme[], programs: string[]) {
  return t.map((th) => ({
    focus: th.name,
    publications: th.publications,
    inter_program_pct: th.inter_program_pct,
    median_rcr: th.median_rcr,
    pct_top_10: th.pct_top_10,
    members: th.members,
    ...Object.fromEntries(programs.map((p) => [p, th.by_program.find((b) => b.program === p)?.publications ?? 0])),
    ...Object.fromEntries(th.pairs.map((p) => [`${initials(p.a)}x${initials(p.b)}`, p.publications])),
    keyword_hits: th.keyword_hits,
    by_current_members: th.active_publications,
  }));
}
