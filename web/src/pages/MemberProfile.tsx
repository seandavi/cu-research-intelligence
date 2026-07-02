import { useEffect } from "react";
import { Link, useParams } from "react-router-dom";
import {
  Bar,
  BarChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import type { YearRange } from "../api/types";
import { Card, Caveat, ErrorNote, KpiCard, Loading } from "../components/ui";
import { useMemberLinks, useMemberProfile } from "../hooks/useApi";
import { track } from "../lib/analytics";
import { fmtInt, fmtMoney, fmtNum, fmtPct } from "../lib/format";

const ID_LABELS: Record<string, string> = {
  orcid: "ORCID",
  openalex_author_id: "OpenAlex",
  employee_id: "Employee ID",
  email: "Email",
  ilab: "iLab",
  ilab_standardized: "iLab (std)",
};

export function MemberProfile({ range }: { range: YearRange }) {
  const { id } = useParams();
  const memberId = id ? Number(id) : undefined;
  const profile = useMemberProfile(memberId, range);
  const cogrant = useMemberLinks(memberId, "cogrant");

  useEffect(() => {
    if (memberId !== undefined) track("view_member_profile", { member_id: memberId });
  }, [memberId]);

  if (profile.isLoading) return <Loading />;
  if (profile.error) return <ErrorNote error={profile.error} />;
  if (!profile.data) return <ErrorNote error="Member not found" />;

  const { member, summary, by_year, top_topics, top_journals, top_coauthors, grants, spine } =
    profile.data;
  const grantTotal = grants.reduce((s, g) => s + (g.total_award ?? 0), 0);

  // Group spine identifiers by type for a compact display.
  const idsByType: Record<string, string[]> = {};
  for (const i of spine?.identifiers ?? []) (idsByType[i.id_type] ??= []).push(i.id_value);
  const membership = spine?.membership?.[0];
  const cograntLinks = cogrant.data ?? [];

  return (
    <>
      <Link to="/members" className="back">
        ← Member directory
      </Link>
      <h1>{member.name}</h1>
      <p className="lede">
        {member.rank} · {member.program} · {member.dept}
        {member.orcid && (
          <>
            {" · "}
            <a href={`https://orcid.org/${member.orcid}`} target="_blank" rel="noreferrer">
              ORCID
            </a>
          </>
        )}
        {member.match_confidence && (
          <>
            {" · "}
            <span className={`badge ${member.match_confidence}`}>{member.match_confidence} match</span>
          </>
        )}
      </p>

      <h3 className="section">
        {range.minYear}–{range.maxYear}
      </h3>
      <div className="kpi-row">
        <KpiCard label="Publications" value={fmtInt(summary.publications)} />
        <KpiCard label="Citations" value={fmtInt(summary.citations)} />
        <KpiCard label="Mean FWCI" value={fmtNum(summary.mean_fwci)} hint="1.0 = world average" />
        <KpiCard
          label="Median RCR"
          value={fmtNum(summary.median_rcr)}
          hint="NIH iCite (1.0 = median NIH paper)"
        />
      </div>

      <div className="grid-2">
        <Card title="Publications per year">
          <ResponsiveContainer width="100%" height={240}>
            <BarChart data={by_year} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="#eee" />
              <XAxis dataKey="publication_year" />
              <YAxis allowDecimals={false} />
              <Tooltip />
              <Bar dataKey="publications" fill="#4C78A8" />
            </BarChart>
          </ResponsiveContainer>
        </Card>

        <Card title="Frequent co-authors (cancer-center members)">
          {top_coauthors.length === 0 && <p className="muted">No member co-authors in this window.</p>}
          <ul className="ranklist">
            {top_coauthors.map((c) => (
              <li key={c.member_id}>
                <Link to={`/members/${c.member_id}`}>{c.name}</Link>
                <span className="muted"> · {c.program}</span>
                <span className="count">{c.shared}</span>
              </li>
            ))}
          </ul>
        </Card>
      </div>

      <div className="grid-2">
        <Card title="Top fields">
          <ul className="ranklist">
            {top_topics.map((t) => (
              <li key={t.topic}>
                {t.topic}
                <span className="count">{t.publications}</span>
              </li>
            ))}
          </ul>
        </Card>
        <Card title="Top journals">
          <ul className="ranklist">
            {top_journals.map((j) => (
              <li key={j.journal}>
                {j.journal}
                <span className="count">{j.publications}</span>
              </li>
            ))}
          </ul>
        </Card>
      </div>

      {grants.length > 0 && (
        <Card title={`NIH grants — ${grants.length} (${fmtMoney(grantTotal)} total)`}>
          <p className="hint">
            NIH RePORTER grants where this member is a named PI (any institution), matched by
            name. Award = sum across funded years.
          </p>
          <table className="data">
            <thead>
              <tr>
                <th>Project</th>
                <th>Type</th>
                <th>NIH IC</th>
                <th>Title</th>
                <th className="num">Latest FY</th>
                <th className="num">Total award</th>
              </tr>
            </thead>
            <tbody>
              {grants.map((g) => (
                <tr key={g.core_project_num}>
                  <td>
                    <a
                      href={`https://reporter.nih.gov/search/?projects=${g.core_project_num}`}
                      target="_blank"
                      rel="noreferrer"
                    >
                      {g.core_project_num}
                    </a>
                    {g.is_active && <span className="badge high oa">active</span>}
                  </td>
                  <td>{g.activity_code}</td>
                  <td>{g.agency}</td>
                  <td>{g.title}</td>
                  <td className="num">{g.latest_fy}</td>
                  <td className="num">{fmtMoney(g.total_award)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </Card>
      )}

      {spine && (
        <>
          <h3 className="section">Membership &amp; identity</h3>
          {spine.link_counts.length > 0 && (
            <p className="muted">
              Spine links:{" "}
              {spine.link_counts
                .map((lc) => `${fmtInt(lc.n)} ${lc.link_type.replace("_", "-")}`)
                .join(" · ")}
            </p>
          )}
          <div className="grid-2">
            <Card title="Membership &amp; appointment">
              <table className="data">
                <tbody>
                  {membership && (
                    <>
                      <tr>
                        <th>Status</th>
                        <td>
                          {membership.member_status}
                          {membership.is_active && <span className="badge high oa">active</span>}
                        </td>
                      </tr>
                      <tr>
                        <th>Member type</th>
                        <td>{membership.member_type ?? "—"}</td>
                      </tr>
                      <tr>
                        <th>Applied</th>
                        <td>{membership.applied_date?.slice(0, 10) ?? "—"}</td>
                      </tr>
                    </>
                  )}
                  <tr>
                    <th>Faculty rank</th>
                    <td>{spine.appointment.faculty_rank ?? "—"}</td>
                  </tr>
                  <tr>
                    <th>Org unit</th>
                    <td>{spine.appointment.org_path ?? "—"}</td>
                  </tr>
                </tbody>
              </table>
            </Card>
            <Card title="Identifiers">
              {Object.keys(idsByType).length === 0 && <p className="muted">No identifiers on file.</p>}
              <ul className="ranklist">
                {Object.entries(idsByType).map(([type, values]) => (
                  <li key={type}>
                    {ID_LABELS[type] ?? type}
                    <span className="muted">
                      {" · "}
                      {type === "orcid" ? (
                        <a href={`https://orcid.org/${values[0]}`} target="_blank" rel="noreferrer">
                          {values[0]}
                        </a>
                      ) : values.length > 2 ? (
                        `${values.length} ids`
                      ) : (
                        values.join(", ")
                      )}
                    </span>
                  </li>
                ))}
              </ul>
            </Card>
          </div>
          {cograntLinks.length > 0 && (
            <Card title={`Co-grant collaborators (${cograntLinks.length})`}>
              <p className="hint">
                Cancer-center members sharing an NIH award (RePORTER core project number)
                {cograntLinks.length > 25 && " — top 25 by shared awards"}.
              </p>
              <ul className="ranklist">
                {cograntLinks.slice(0, 25).map((l) => (
                  <li key={l.other_member_id}>
                    <Link to={`/members/${l.other_member_id}`}>{l.other_name}</Link>
                    {l.other_program && <span className="muted"> · {l.other_program}</span>}
                    <span className="count">{l.weight}</span>
                  </li>
                ))}
              </ul>
            </Card>
          )}
        </>
      )}

      <p className="muted">Open access: {fmtPct(summary.pct_open_access)} of publications.</p>
      <Caveat />
    </>
  );
}
