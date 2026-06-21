import {
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import type { YearRange } from "../api/types";
import { Card, Caveat, ErrorNote, KpiCard, Loading } from "../components/ui";
import { useInterInstTrend, useKpi, useTopCollaborators } from "../hooks/useApi";
import { downloadCsv, fmtInt, fmtPct } from "../lib/format";

export function Institutions({ range }: { range: YearRange }) {
  const kpi = useKpi(range);
  const trend = useInterInstTrend(range);
  const collab = useTopCollaborators(range, 25);

  if (kpi.isLoading || collab.isLoading) return <Loading />;
  if (kpi.error) return <ErrorNote error={kpi.error} />;
  const k = kpi.data!;
  const rows = collab.data ?? [];

  return (
    <>
      <h1>Inter-institutional Collaboration</h1>
      <p className="lede">
        Collaboration beyond the home campus — a publication is inter-institutional when a co-author
        is affiliated with an institution outside the University of Colorado Anschutz complex. A
        standard CCSG indicator of external reach.
      </p>

      <div className="kpi-row">
        <KpiCard
          label="Inter-institutional"
          value={fmtPct(k.pct_inter_institutional)}
          hint="Publications with ≥1 external institution"
        />
        <KpiCard
          label="International"
          value={fmtPct(k.pct_international)}
          hint="Publications with ≥1 non-US institution"
        />
        <KpiCard label="Publications" value={fmtInt(k.publications)} hint="Window total" />
        <KpiCard
          label="Top collaborator"
          value={rows[0] ? rows[0].institution.split(",")[0] : "—"}
          hint={rows[0] ? `${fmtInt(rows[0].publications)} shared publications` : ""}
        />
      </div>

      <Card title="Inter-institutional & international trend">
        <ResponsiveContainer width="100%" height={280}>
          <LineChart data={trend.data ?? []} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="#eee" />
            <XAxis dataKey="publication_year" />
            <YAxis domain={[0, 100]} unit="%" />
            <Tooltip />
            <Line
              type="monotone"
              dataKey="pct_inter_institutional"
              name="Inter-institutional %"
              stroke="#4C78A8"
              strokeWidth={2}
            />
            <Line
              type="monotone"
              dataKey="pct_international"
              name="International %"
              stroke="#F58518"
              strokeWidth={2}
            />
          </LineChart>
        </ResponsiveContainer>
      </Card>

      <Card
        title="Top external collaborating institutions"
        action={
          <button
            onClick={() => downloadCsv(rows, `uccc_collaborators_${range.minYear}-${range.maxYear}.csv`)}
          >
            ⬇ CSV
          </button>
        }
      >
        <p className="hint">
          Most frequent external partners — overwhelmingly other NCI-designated cancer centers and
          top research institutions.
        </p>
        <table className="data">
          <thead>
            <tr>
              <th>Institution</th>
              <th>Country</th>
              <th className="num">Shared publications</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((c) => (
              <tr key={c.institution}>
                <td>{c.institution}</td>
                <td>{c.country ?? "—"}</td>
                <td className="num">{fmtInt(c.publications)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </Card>

      <Caveat />
    </>
  );
}
