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
import { useGrantsByAgency, useGrantsByProgram, useGrantsSummary } from "../hooks/useApi";
import { downloadCsv, fmtInt, fmtMoney, shorten } from "../lib/format";

export function Funding({ range }: { range: YearRange }) {
  const summary = useGrantsSummary(range);
  const byProgram = useGrantsByProgram(range);
  const byAgency = useGrantsByAgency(range);

  if (summary.isLoading) return <Loading />;
  if (summary.error) return <ErrorNote error={summary.error} />;
  const s = summary.data!;
  const progs = byProgram.data ?? [];
  const agencies = byAgency.data ?? [];

  return (
    <>
      <h1>NIH Funding</h1>
      <p className="lede">
        NIH RePORTER grants for the University of Colorado Denver, matched by PI name to
        cancer-center members. Fiscal years per the range (top-right). A grant is counted once
        (distinct project); award is summed across funded years.
      </p>

      <div className="kpi-row">
        <KpiCard label="Grants" value={fmtInt(s.grants)} hint="Distinct projects with a member PI" />
        <KpiCard label="Total award" value={fmtMoney(s.total_award)} hint="Summed across funded years" />
        <KpiCard label="Funded members" value={fmtInt(s.funded_members)} />
        <KpiCard label="R01s" value={fmtInt(s.r01_grants)} hint="Distinct R01 projects" />
      </div>

      <div className="grid-2">
        <Card title="Funding by program">
          <ResponsiveContainer width="100%" height={280}>
            <BarChart data={progs.map((p) => ({ ...p, short: shorten(p.program, 22) }))} layout="vertical" margin={{ left: 20 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="#eee" />
              <XAxis type="number" tickFormatter={(v) => fmtMoney(v)} />
              <YAxis type="category" dataKey="short" width={150} />
              <Tooltip formatter={(v: number) => fmtMoney(v)} />
              <Bar dataKey="total_award" fill="#4C78A8" name="Total award" />
            </BarChart>
          </ResponsiveContainer>
        </Card>
        <Card title="Grants by NIH institute/center">
          <table className="data compact">
            <thead>
              <tr>
                <th>IC</th>
                <th className="num">Grants</th>
                <th className="num">Total award</th>
              </tr>
            </thead>
            <tbody>
              {agencies.map((a) => (
                <tr key={a.agency}>
                  <td>{a.agency}</td>
                  <td className="num">{fmtInt(a.grants)}</td>
                  <td className="num">{fmtMoney(a.total_award)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </Card>
      </div>

      <Card
        title="Program funding summary"
        action={
          <button onClick={() => downloadCsv(progs, `uccc_funding_by_program_${range.minYear}-${range.maxYear}.csv`)}>
            ⬇ CSV
          </button>
        }
      >
        <table className="data">
          <thead>
            <tr>
              <th>Program</th>
              <th className="num">Grants</th>
              <th className="num">Funded members</th>
              <th className="num">Total award</th>
            </tr>
          </thead>
          <tbody>
            {progs.map((p) => (
              <tr key={p.program}>
                <td>{p.program}</td>
                <td className="num">{fmtInt(p.grants)}</td>
                <td className="num">{fmtInt(p.funded_members)}</td>
                <td className="num">{fmtMoney(p.total_award)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </Card>

      <p className="caveat">
        <strong>About this data.</strong> Grants come from NIH RePORTER for grantee organization
        "University of Colorado Denver" and are matched to roster members by PI name (RePORTER has
        no ORCID), so attribution is a name match — a member is credited if any named PI matches.
        Non-NIH funding is not included.
      </p>
      <Caveat />
    </>
  );
}
