import {
  Area,
  AreaChart,
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { Link } from "react-router-dom";
import type { YearRange } from "../api/types";
import { Card, Caveat, ErrorNote, KpiCard, Loading } from "../components/ui";
import {
  useCollaborationTrend,
  useKpi,
  useMeta,
  usePublicationsByYear,
} from "../hooks/useApi";
import { fmtInt, fmtNum, fmtPct } from "../lib/format";

// One row per nav tab (issue #48). "Scope" is the population each tab counts; today all
// three are member-scoped (ADR-0027's campus-wide cancer view is not built yet).
const MEMBER_PUBS = "Peer-reviewed papers by roster members in the year window";
const GUIDE = [
  { to: "/", tab: "Overview", answers: "Headline output, impact, and collaboration mix by year",
    scope: `${MEMBER_PUBS}, whenever they joined`, caveat: "The latest year or two are provisional (indexing lag)" },
  { to: "/publications", tab: "Publications", answers: "Find and filter individual papers",
    scope: MEMBER_PUBS, caveat: "Relevance ranks title and abstract text only" },
  { to: "/programs", tab: "Program Collaboration", answers: "Intra- vs inter-programmatic co-authorship, by program",
    scope: `${MEMBER_PUBS}; a paper counts for every program its member authors belong to`,
    caveat: "Deprecated programs are hidden unless toggled on" },
  { to: "/foci", tab: "Strategic Foci", answers: "Output, program mix, and people per Strategic Plan focus",
    scope: "Cancer-relevant member papers, counted only while the author was a member",
    caveat: "Keyword-matched: a lower bound, and overlaps partly reflect shared vocabulary" },
  { to: "/institutions", tab: "Inter-institutional", answers: "External and international co-authorship and top partner institutions",
    scope: "Member papers with a co-author outside the CU Anschutz complex", caveat: "Relies on OpenAlex affiliation parsing" },
  { to: "/funding", tab: "NIH Funding", answers: "NIH grants, award totals, and institutes by program", needsGrants: true,
    scope: "NIH RePORTER projects where a member is a named PI at any institution",
    caveat: "Matched by exact PI name (no ORCID); non-NIH funding is not included" },
  { to: "/networks", tab: "Networks", answers: "Who co-authors with whom; bridge investigators",
    scope: "Member-to-member ties with at least N shared papers", caveat: "External co-authors are not in the graph" },
  { to: "/members", tab: "Members", answers: "Per-member output, impact, and foci",
    scope: "Members resolved to an OpenAlex author", caveat: "Name-only matches (no ORCID) may include a namesake's papers" },
  { to: "/ask", tab: "Ask", answers: "Plain-English questions over the same tables",
    scope: "Whatever the generated SQL selects", caveat: "Open the SQL under each answer before quoting a number" },
];

const CLASS_COLOR = { solo: "#BAB0AC", intra_program: "#4C78A8", inter_program: "#F58518" };

export function Overview({ range }: { range: YearRange }) {
  const kpi = useKpi(range);
  const meta = useMeta();
  const trend = useCollaborationTrend(range);
  const pubs = usePublicationsByYear(range, "collaboration_class");

  if (kpi.isLoading) return <Loading />;
  if (kpi.error) return <ErrorNote error={kpi.error} />;
  const k = kpi.data!;

  // Pivot publications-by-year into stacked-area rows keyed by year.
  const byYear = new Map<number, Record<string, number>>();
  for (const r of pubs.data ?? []) {
    const row = byYear.get(r.publication_year) ?? { year: r.publication_year };
    row[r.collaboration_class ?? "solo"] = r.publications;
    byYear.set(r.publication_year, row);
  }
  const areaData = [...byYear.values()].sort((a, b) => a.year - b.year);

  return (
    <>
      <h1>Cancer Center Research Intelligence</h1>
      <p className="lede">
        Publications, program collaboration, and research impact for the University of Colorado
        Cancer Center, from OpenAlex and the membership roster.
      </p>

      <details className="guide">
        <summary>New here? What each tab shows</summary>
        <p className="hint">
          Every tab counts the work of <strong>Cancer Center members</strong> on the roster —
          not all cancer research at CU Anschutz. A campus-wide cancer view (any CU author, with
          the member share) is planned but not yet on the site.
        </p>
        <table className="data compact">
          <thead>
            <tr>
              <th>Tab</th>
              <th>Answers</th>
              <th>Who is counted</th>
              <th>Watch out for</th>
            </tr>
          </thead>
          <tbody>
            {GUIDE.filter((g) => !g.needsGrants || meta.data?.grants_available).map((g) => (
              <tr key={g.to}>
                <td><Link to={g.to}>{g.tab}</Link></td>
                <td>{g.answers}</td>
                <td>{g.scope}</td>
                <td className="muted">{g.caveat}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </details>

      <h3 className="section">Headline — {range.maxYear}</h3>
      <div className="kpi-row">
        <KpiCard label="Publications (window)" value={fmtInt(k.publications)} hint="Peer-reviewed articles & reviews" />
        <KpiCard label="Inter-programmatic" value={fmtPct(k.pct_inter_program)} hint="Members from ≥2 programs" />
        <KpiCard label="Intra-programmatic" value={fmtPct(k.pct_intra_program)} hint="≥2 members of one program" />
        <KpiCard
          label="Median RCR"
          value={fmtNum(k.median_rcr)}
          hint={`NIH iCite Relative Citation Ratio (1.0 = median NIH paper). ${fmtInt(k.n_with_rcr)} scored.`}
        />
      </div>
      <div className="kpi-row">
        <KpiCard label="Median FWCI" value={fmtNum(k.median_fwci)} hint="Field-weighted impact (1.0 = world avg)" />
        <KpiCard label="Open access" value={fmtPct(k.pct_open_access)} />
        <KpiCard label="Collaborative" value={fmtPct(k.pct_collaborative)} hint={`${fmtInt(k.n_collaborative)} pubs with ≥2 members`} />
        <KpiCard label="Active members" value={fmtInt(k.members_active)} hint={`${fmtInt(k.active_resolved)} matched to OpenAlex`} />
      </div>

      <div className="grid-2">
        <Card title="Publications over time">
          <ResponsiveContainer width="100%" height={300}>
            <AreaChart data={areaData} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="#eee" />
              <XAxis dataKey="year" />
              <YAxis />
              <Tooltip />
              <Legend />
              <Area type="monotone" dataKey="solo" stackId="1" name="Solo" stroke={CLASS_COLOR.solo} fill={CLASS_COLOR.solo} />
              <Area type="monotone" dataKey="intra_program" stackId="1" name="Intra" stroke={CLASS_COLOR.intra_program} fill={CLASS_COLOR.intra_program} />
              <Area type="monotone" dataKey="inter_program" stackId="1" name="Inter" stroke={CLASS_COLOR.inter_program} fill={CLASS_COLOR.inter_program} />
            </AreaChart>
          </ResponsiveContainer>
        </Card>

        <Card title="Collaboration mix">
          <ResponsiveContainer width="100%" height={300}>
            <LineChart data={trend.data ?? []} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="#eee" />
              <XAxis dataKey="publication_year" />
              <YAxis domain={[0, 25]} unit="%" />
              <Tooltip />
              <Legend />
              <Line type="monotone" dataKey="pct_intra" name="Intra %" stroke={CLASS_COLOR.intra_program} strokeWidth={2} />
              <Line type="monotone" dataKey="pct_inter" name="Inter %" stroke={CLASS_COLOR.inter_program} strokeWidth={2} />
            </LineChart>
          </ResponsiveContainer>
        </Card>
      </div>

      <Caveat provisional={range.maxYear >= (meta.data?.indexing_lag_from ?? 9999)} />
    </>
  );
}
